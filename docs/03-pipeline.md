# 03 — Pipeline (new_layout)

5-step pipeline สำหรับสร้าง layout ใหม่จากศูนย์

Entry point: [`PipelineOrchestrator.run()`](../src/modules/layout/application/pipeline/orchestrator.py#L50)

## ภาพรวม

```
room_spec (ดิบ)
     │
     ▼
┌──────────────────────┐
│ Step 1: Data Builder │ ← parse + validate
└──────────┬───────────┘
           │
           ▼
    [RAG retrieval]        ← ดึงความรู้ฮวงจุ้ย
           │
           ▼
┌──────────────────────┐
│ Step 2: Generator    │ ← LLM วาง layout
└──────────┬───────────┘
           │
           ├──────────────┐
           ▼              │
┌──────────────────────┐  │ (max 3 loops)
│ Step 3: Rule Checker │  │
└──────────┬───────────┘  │
           │              │
    มี conflict?          │
      │     │             │
     ไม่    ใช่            │
      │     │             │
      │     ▼             │
      │ ┌──────────────┐  │
      │ │ Step 4: Repair│─┘
      │ └──────────────┘
      │
      ▼
┌──────────────────────┐
│ Step 5: Explainer    │ ← LLM เขียนคำอธิบาย
└──────────┬───────────┘
           ▼
   PipelineResult
```

## PipelineState (shared state)

File: [models.py](../src/modules/layout/application/pipeline/models.py)

```python
@dataclass
class PipelineState:
    pipeline_id: str              # UUID prefix
    current_step: PipelineStep
    repair_iteration: int         # 0, 1, 2, 3
    step_results: list[StepResult]
    started_at: datetime

    room_spec: dict               # Input (mutates)
    layout_items: list[dict]      # Output furniture placements
    conflicts: list[Conflict]
    repair_actions: list[RepairAction]
    explanation: str

    feng_shui_score: dict = {     # 4-component scoring
        "command_position": int,
        "five_elements_balance": int,
        "chi_flow": int,
        "sha_chi_avoidance": int,
    }

    rag_context: dict             # ใส่ใน Step 1.5
    personality_mode: str         # buddy | mentor | fun
```

## PipelineConfig (default)

```python
max_repair_loops: int = 3          # Step 3↔4 loops
llm_model: str = "anthropic/claude-3.5-sonnet"
llm_temperature: float = 0.3
step_timeout_seconds: float = 60.0
total_timeout_seconds: float = 300.0
```

---

## Step 1: Structured Data Builder

File: [step1_data_builder.py](../src/modules/layout/application/pipeline/steps/step1_data_builder.py)

### Input
- `state.room_spec` (dict ดิบจาก frontend)

### Output
- `Room` entity (stored in `state._room`)
- Validated `room_spec` dict

### Process

1. **Parse room type** (line 79–80)
   ```python
   ROOM_TYPE_MAP = {
       "bedroom": RoomType.BEDROOM,
       "studio_apartment": RoomType.STUDIO_APARTMENT,
       "office": RoomType.OFFICE,
       # ...
   }
   ```

2. **Build Room entity** (line 96)
   - Parse `doors[]` → list of `DoorPosition` (wall, offset, width, swing_inward)
   - Parse `windows[]` → list of `WindowPosition`
   - Wall string → `WallSide` enum

3. **SpatialAnalyzer** (line 108)
   - คำนวณ `room_area = width * depth`
   - `usable_area ≈ room_area * 0.7` (หลังหักทางเดิน)
   - `command_positions` — ตำแหน่งผู้บัญชาการ (ผนังตรงข้ามประตู, เยื้องจากแนวประตู)

### Emits
- `STEP_STARTED` → `STEP_PROGRESS` → `STEP_COMPLETED`

---

## RAG Retrieval (between Step 1 & 2)

File: [orchestrator.py:82-110](../src/modules/layout/application/pipeline/orchestrator.py#L82)

```python
_injector = ContextInjector()
_rag = await _injector.retrieve(state.room_spec)
state.rag_context = {
    "layout_prompt_context": _rag.layout_prompt_context,
    "rule_descriptions": _rag.rule_descriptions,
    "source_citations": _rag.source_citations,
    "rules_retrieved": len(_rag.rules),
}
```

- **Graceful**: ถ้า RAG fail → rag_context เป็น empty (pipeline ยังรันต่อ)
- ใช้ใน Step 2 (inject เข้า LLM prompt) และ Step 3 (enrich conflict suggestion)

---

## Step 2: Layout Generator ⭐

File: [step2_layout_generator.py](../src/modules/layout/application/pipeline/steps/step2_layout_generator.py)

**นี่คือ step หลักที่เรียก LLM วาง layout**

### Input
- `state.room_spec` (พร้อม Room entity + RAG context)

### Output
- `state.layout_items` — list of physical placement dicts
- `state.feng_shui_score["deterministic"]` — คะแนนเบื้องต้น (0–70)

### Process

#### 2.1 Furniture Selection (line 83–89)

```python
selector = FurnitureSelector()
results = selector.select_furniture(
    room_type=..., budget_level=..., owned_categories=...,
)
```

- `owned_categories` ได้จาก `_parse_owned_furniture()` (regex บนข้อความผู้ใช้)
- OWNERSHIP_CUES: `"มีแค่|มีเพียง|ของฉัน|only have|own"`
- ถ้า user บอกว่า "มีแค่เตียงกับโต๊ะ" → ระบบเลือกเฉพาะชิ้นเหล่านั้น ไม่เพิ่มอื่น

#### 2.2 Build furniture_list สำหรับ LLM (line 100–109)

```python
furniture_list = [
    {
        "id": f.id,
        "name": f.name,
        "width": f.width,
        "depth": f.depth,
        "height": f.height,
        "is_essential": f.is_essential,
    }
    for f in selected_furniture
]
```

#### 2.3 Furniture Relationships hints

File: [services/furniture_relationships.py](../src/modules/layout/application/services/furniture_relationships.py)

```python
hints = build_relationship_hints(furniture_list)
# → ["TV stand should face sofa", "nightstand beside bed", ...]
user_prefs["furniture_relationships"] = "\n".join(hints)
```

Auto-detect จาก type: TV ↔ sofa, nightstand ↔ bed, coffee_table ↔ sofa, chair ↔ desk

#### 2.4 LLM plan_layout() — **LLM call ตัวที่ 2 ของระบบ**

```python
llm_response = await self._llm_agent.plan_layout(
    room_type=room_type,
    width=width, depth=depth,
    usable_area=usable_area,
    doors=doors, windows=windows,
    furniture_list=furniture_list,
    command_positions=command_positions,
    user_preferences=user_prefs,           # มี placement_constraints + user_message
    extra_context=state.rag_context,       # RAG hints
)
```

**LLM คืนอะไร:**
```json
{
  "placements": [
    {
      "furniture_id": "bed_queen_001",
      "furniture_type": "bed",
      "size": {"w": 1.6, "l": 2.0, "h": 0.6},
      "target_wall": "north",
      "alignment": "center",
      "offset_from_wall": 0.05,
      "facing": "south",
      "priority": 1
    },
    ...
  ]
}
```

**สิ่งที่ LLM คิด:** ผนัง, alignment, facing (semantic)
**สิ่งที่ LLM ไม่คิด:** พิกัด x/z, rotation organizer, collision

#### 2.5 Heuristic fallback (line 147–160)

ถ้า LLM fail → stack ทุกชิ้นเรียงตามผนังใต้:
```python
x = 0.1
for f in furniture_list:
    place(f, x=x, z=room.depth - f.depth - 0.1)
    x += f.width + 0.1
```

ไม่สวยแต่ไม่ crash

#### 2.6 Resolve semantic → physical (line 181)

```python
resolution = self._resolver.resolve(placements, room_spec)
# resolution.physical_placements — พิกัด x/z/rotation จริง
# resolution.collisions — ชิ้นที่ทับกัน
# resolution.deterministic_score — 0–70
```

ดู [05-spatial-resolver.md](./05-spatial-resolver.md) สำหรับรายละเอียด

#### 2.7 Enrich with catalog metadata (line 191–193)

```python
for item in physical_placements:
    catalog_item = FURNITURE_CATALOG[item.furniture_id]
    item.name = catalog_item.name
    item.category = catalog_item.category
    item.model_url = catalog_item.model_url  # สำหรับ Three.js
    item.model_rotation_offset = catalog_item.model_rotation_offset
```

---

## Step 3: Rule Checker

File: [step3_rule_checker.py](../src/modules/layout/application/pipeline/steps/step3_rule_checker.py)

### Input
- `state.layout_items` + Room entity + spatial analysis

### Output
- `state.conflicts` — list of unresolved conflicts
- `state.feng_shui_score` — full breakdown (100 points total)

### Clearance Constants

```python
MIN_CLEARANCE = 0.6      # ช่องว่างขั้นต่ำระหว่างเฟอร์นิเจอร์
DOOR_CLEARANCE = 0.9     # Clearance หน้าประตู
MIN_WALKWAY = 0.7        # ทางเดินขั้นต่ำ
```

### 3A. Universal Standards (line 167–246)

เช็คทางฟิสิกส์ ไม่เกี่ยวฮวงจุ้ย

| Check | Method | Conflict Type | Severity |
|---|---|---|---|
| ทับกัน | `box_a.intersects(box_b)` | `OVERLAP` | CRITICAL |
| ชิดเกินไป | `box_a.distance_to(box_b) < 0.6` | `CLEARANCE_VIOLATION` | WARNING |
| หลุดห้อง | centre-based bounds check | `OUT_OF_BOUNDS` | CRITICAL |
| ทับประตู | ≤0.9m รอบประตู | `DOOR_BLOCKED` | CRITICAL |

### 3B. Feng Shui Principles (line 248–501)

**Bed-specific rules:**

| Rule ID | Trigger | Type | Severity |
|---|---|---|---|
| bed_001 | เตียงในแนวเดียวกับประตู | `SHA_CHI_ALIGNMENT` | WARNING |
| bed_002 | เตียงในแนวเดียวกับหน้าต่าง | `SHA_CHI_ALIGNMENT` | WARNING |
| bed_003 | TV/กระจกหันเข้าเตียง | `SHA_CHI_ALIGNMENT` | WARNING |
| bed_004 | AC เหนือเตียง | `SHA_CHI_ALIGNMENT` | INFO |
| bed_005 | เตียงลอยกลางห้อง (ไม่ชิดผนัง) | `BAD_COMMAND_POSITION` | WARNING |
| bed_006 | ประตู-หน้าต่างตรงกัน | `BLOCKED_CHI_FLOW` | WARNING |
| bed_007 | เฟอร์นิเจอร์ใหญ่ผนังเดียวกับหัวเตียง | `SHA_CHI_ALIGNMENT` | INFO |
| bed_008 | ไม่มีทางเดินรอบเตียง | `CLEARANCE_VIOLATION` | INFO |
| bed_009 | โต๊ะหันเข้าหน้าต่าง | `SHA_CHI_ALIGNMENT` | INFO |
| bed_011 | จอภาพตรงปลายหัวเตียง | `SHA_CHI_ALIGNMENT` | WARNING |

**Desk/Sofa rules:**

| Rule | Method | Type |
|---|---|---|
| back_to_door | `_has_back_to_door()` — angle diff < 60° | `BACK_TO_DOOR` |

### 3C. Scoring (line 91–100)

```python
scorer = FengShuiScorer()
score = scorer.score_layout(room, placed_furniture, spatial_analysis)

state.feng_shui_score = {
    "command_position": score.command_position,       # 0–30
    "five_elements_balance": score.five_elements,     # 0–20
    "chi_flow": score.chi_flow,                       # 0–25
    "sha_chi_avoidance": score.sha_chi_avoidance,     # 0–25
}
# Total: 0–100
```

ดู [08-feng-shui.md](./08-feng-shui.md) สำหรับ scoring formula

### 3D. RAG Enrichment (line 102–104)

Map `ConflictType` → rule_id → ดึงคำอธิบายจาก RAG:
```python
_CONFLICT_TO_RULE = {
    ConflictType.BAD_COMMAND_POSITION: "cmd_001",
    ConflictType.SHA_CHI_ALIGNMENT: "sha_001",
    # ...
}
conflict.suggestion += "\n" + rag_context["rule_descriptions"][rule_id]
```

### Emits
- `CONFLICT_FOUND` สำหรับแต่ละ conflict
- `STEP_COMPLETED` พร้อม conflicts summary

---

## Step 4: Repair

File: [step4_repair.py](../src/modules/layout/application/pipeline/steps/step4_repair.py)

### Input
- `state.layout_items` + unresolved conflicts

### Output
- Modified `layout_items`
- `state.repair_actions` — log ของ action ที่ทำ
- Some `conflict.resolved = True`

### Constants

```python
SHIFT_INCREMENTS = [0.3, 0.5, 0.8, 1.0, 1.3, 1.6, 2.0]   # เมตร
MIN_SHIFT_CLEARANCE = 0.15
_DOOR_CLEAR = 1.50   # walking clearance หน้าประตู
_DOOR_PAD = 0.50     # padding ด้านข้างประตู

SHIFT_DIRECTIONS = [  # 8 ทิศทาง
    (1, 0), (-1, 0), (0, 1), (0, -1),       # cardinal
    (1, 1), (-1, 1), (1, -1), (-1, -1),     # diagonal (normalized ต่อไป)
]
```

### Repair Strategy (line 84–94)

ลำดับที่พยายาม: **Shift → Rotate → Swap → Remove**

ปัจจุบัน implementation หลักคือ **Shift** และ **Rotate** (Swap/Remove ไม่ค่อยถูกเรียก)

### 4.1 Shift Algorithm (`_try_shift`, line 182–294)

```python
for dist in SHIFT_INCREMENTS:
    for dx, dz in SHIFT_DIRECTIONS:
        new_x = original_x + dx * dist
        new_z = original_z + dz * dist

        if not in_bounds(new_x, new_z, width, depth):
            continue
        if collides_with_any_other(new_x, new_z):
            continue
        if in_door_zone(new_x, new_z):
            continue

        apply_shift(new_x, new_z)
        yield RepairAction(action_type=SHIFT, before, after, success=True)
        return
```

**Door zone check** (line 207–235):
- ขยายประตูออกจากผนัง 1.5m (walking zone)
- เว้น 0.5m ข้างละ (side padding)
- ห้ามวางเฟอร์นิเจอร์ในโซนนี้

### 4.2 Rotate Algorithm (`_try_rotate`, line 296–365)

```python
for new_rot in [90, 180, 270, 0]:
    if new_rot == current_rot:
        continue

    # ถ้า 90° หรือ 270° → swap width/depth
    fw, fd = swap_if_rotated(width, depth, new_rot)

    if in_bounds_with_new_footprint(fw, fd):
        if not collides():
            apply_rotation(new_rot)
            return
```

### 4.3 Pair Re-anchoring (line 392–549)

เมื่อ shift anchor (เช่น โต๊ะ) → dependent (เก้าอี้) ต้องตามไปด้วย

```python
DEPENDENT_RULES = {
    ("chair", "office_chair"): "desk",
    ("dining_chair",): "dining_table",
    ("coffee_table",): "sofa",
}

for anchor in shifted_anchors:
    dependents = find_by_type(DEPENDENT_RULES[anchor.type])
    for dep in dependents:
        snap_to_anchor_front_face(dep, anchor)
```

**Front face priority** (line 515–518):
```python
front_priority = {
    0: 1,     # north-facing anchor → front = north side
    180: 0,   # south-facing → front = south side
    90: 2,
    270: 3,
}
# snap dependent to anchor's front first, then sides
```

### Emits
- `REPAIR_APPLIED` สำหรับแต่ละ action
- `LAYOUT_UPDATED` หลังปรับทุก conflict

### Loop Back to Step 3

หลัง Step 4 เสร็จ → orchestrator รัน Step 3 ใหม่ (line 144 ของ orchestrator.py) จนกว่า:
- ไม่มี unresolved conflicts → break
- วน `max_repair_loops + 1 = 4` รอบ → give up, log warning

**ทำไมต้อง re-check?** เพราะการเลื่อนชิ้น A อาจไปชนชิ้น C ที่ไม่เคยเกี่ยวข้องใน conflict เดิม

---

## Step 5: Explainer

File: [step5_explainer.py](../src/modules/layout/application/pipeline/steps/step5_explainer.py)

### Input
- `state` ทุกอย่าง: layout_items, conflicts, repair_actions, feng_shui_score

### Output
- `state.explanation` (string ภาษาไทย)

### Grade Thresholds

```python
GRADE_EXCELLENT = 80
GRADE_GOOD = 60
GRADE_FAIR = 40
# < 40 = NEEDS_WORK
```

### Process

1. **Build summary** (line 56)
   - Items summary: list of placed furniture
   - Conflicts summary: unresolved + resolved counts
   - Repair summary: actions taken
   - Score: total + grade
   - Kua line (ถ้ามี birth_year)

2. **Kua calculation** (line 168–181)
   ```python
   if birth_year and gender:
       kua = calculate_kua(birth_year, gender)
       info = kua_best_direction_info(kua)  # {"wall_th", "benefit"}
       kua_line = f"หัวเตียงหันทิศ{info['wall_th']}ตามเลขกัว {kua} เสริม{info['benefit']}"
   ```

3. **LLM explain_layout()** — **LLM call ตัวที่ 3 ของระบบ**
   ```python
   explanation = await self._llm_agent.explain_layout(
       room_type=..., dimensions=...,
       items_summary=..., conflicts_summary=...,
       repairs_summary=..., total_score=..., grade=...,
       kua_line=..., personality_mode=mode,
   )
   ```

4. **Template fallback** (line 82–259)
   ถ้า LLM fail → สร้างข้อความจาก template

5. **Overlap safety net** (line 118–139)
   ```python
   actual_overlaps = _count_actual_overlaps(layout_items)
   if actual_overlaps > 0:
       # Override: warn user that actual collisions exist
       explanation = override_with_warning(actual_overlaps)
   ```
   ป้องกันกรณีที่ conflicts.resolved=True แต่ geometry ยังทับอยู่จริง

### Emits
- `STEP_COMPLETED` พร้อม explanation

---

## Pipeline Completion

Orchestrator ส่ง `PIPELINE_COMPLETED` event (line 156) พร้อม `PipelineResult`:

```python
PipelineResult(
    success=True,
    pipeline_id=...,
    layout_items=[...],              # ← frontend ใช้ render
    feng_shui_score={...},           # ← frontend แสดงคะแนน
    conflicts=[...],                  # ← อาจมี unresolved ที่ critical
    repair_actions=[...],             # ← log การแก้
    explanation="...",                # ← แสดงใน chat
    step_results=[...],               # ← timing per step
    total_duration_ms=1234,
)
```

## ลำดับ Events ที่ Frontend เห็น

```
1.  router_classified           {intent: "new_layout"}
2.  pipeline_started            {pipeline_id, steps, config}
3.  step_started                {step: "structured_data_builder"}
4.  step_progress               {progress: 0.5}
5.  step_completed              {step: "structured_data_builder"}
6.  step_progress               {step: "rag_retrieval", progress: 1.0}
7.  step_started                {step: "layout_generator"}
8.  step_progress × N
9.  step_completed              {step: "layout_generator"}
10. step_started                {step: "rule_checker"}
11. conflict_found × N
12. step_completed              {step: "rule_checker"}
13. [repair loop...]
14. step_started                {step: "repair"}
15. repair_applied × N
16. layout_updated              {layout_items: [...]}
17. step_completed              {step: "repair"}
18. [loop back to step_started rule_checker]
19. step_started                {step: "explainer"}
20. step_completed              {step: "explainer", explanation: "..."}
21. pipeline_completed          {layout_items, feng_shui_score, explanation}
```

## จุดที่ควรรู้

- **Repair loop ไม่ guaranteed converge** — หลัง 3 รอบถ้ายังมี conflict ก็ปล่อยไป (log warning)
- **Deterministic score (0-70) จาก Step 2** แยกจาก **Full score (0-100) จาก Step 3** — ค่าในช่วง pipeline อาจไม่ตรง
- **LLM ใน Step 2 อาจคืนชิ้นไม่ครบ** — step ไม่มี guard ต่างจาก RearrangeAgent (ดูข้อถัดไป)
- **Step 5 โดน wrap ด้วย overlap safety net** — เพื่อไม่ให้ LLM โกหกว่าไม่มี collision ในเมื่อมีจริง
