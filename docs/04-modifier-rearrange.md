# 04 — Modifier & Rearrange Agents

เอเจนต์ที่ไม่รัน 5-step pipeline เต็ม ใช้สำหรับแก้ layout ที่มีอยู่แล้ว

| Agent | ใช้ตอนไหน | Scope |
|---|---|---|
| `ModifierAgent` | User บอก "ย้ายโซฟา", "หมุนเตียง", "ขวางประตู" | ชิ้นเดียว |
| `RearrangeAgent` | User บอก "จัดใหม่", "จัดให้ถูกฮวงจุ้ย" | ทุกชิ้นในห้อง |

ต่างจาก pipeline: ไม่ call catalog selection, ไม่มี Step 1, ไม่มี Rule Checker (ใช้แค่ collision check), ไม่มี Explainer

---

## ModifierAgent

File: [modifier_agent.py](../src/modules/layout/application/modifier/modifier_agent.py)

### Constants

```python
_MAX_REPAIR_ATTEMPTS = 6
_NUDGE_DISTANCE = 0.3
```

### Entry: `async def apply()`

```python
async def apply(
    current_layout: list[dict],
    room_spec: dict,
    modification_request: str,       # ข้อความ user
    extracted_params: dict,          # จาก RouterAgent:
                                     #   {action, target_furniture, details}
) -> AsyncGenerator[SSEEvent, None]:
```

### Flow

#### 1. Identify target item

ใช้ `is_target()` function (token-based matching) — หาชิ้นที่ user พูดถึง

```python
def is_target(fid: str, target_type: str) -> bool:
    tokens = re.split(r"[-_\s]+", fid)
    primary = tokens[0]
    return primary == target_type

# "sofa-bed" primary="sofa" ≠ "bed" → ถ้า target="bed" ชิ้นนี้ไม่โดนเลือก
```

ทำไมต้องเทียบ primary token? เพราะ `sofa_bed` ไม่ควร match เมื่อ user ขอ "ย้ายเตียง"

#### 2. Convert physical → semantic (`_layout_to_semantics`)

แต่ละชิ้นใน `current_layout` ถูกแปลงกลับเป็น semantic placement:
```python
{
    "furniture_id": fid,
    "target_wall": infer_from_position(pos_x, pos_z, room),
    "alignment": infer_alignment(pos, wall),
    "offset_from_wall": compute_gap(pos, wall),
    ...
}
```

Target item ได้ `priority=0` (เพื่อให้ resolve ก่อน)

#### 3. Detect modification type (keyword parsing)

```python
_WALL_KEYWORDS = {
    "ทิศเหนือ": "north", "เหนือ": "north",
    "ทิศใต้": "south", ...
}
_BLOCK_DOOR_KEYWORDS = {"ขวางประตู", "across from door", "opposite door"}
_DOOR_KEYWORDS = {"ชิดประตู", "near door", "by the door"}

# ถ้าเจอ _BLOCK_DOOR_KEYWORDS → ผนังตรงข้ามประตู
# ถ้าเจอ _DOOR_KEYWORDS → ผนังเดียวกับประตู  [ต่างกัน!]
```

**ลำดับการเช็ค:** `_BLOCK_DOOR_KEYWORDS` ก่อน `_DOOR_KEYWORDS` — เพราะ "ขวางประตู" มี "ประตู" อยู่ด้วย ถ้าเช็ค door ก่อนจะ match ผิด

#### 4. Update target's semantic constraints

```python
if wall_direction:
    target_semantic["target_wall"] = wall_direction
if block_door:
    target_semantic["target_wall"] = _OPPOSITE_WALL[door_wall]
# etc.
```

#### 5. Resolve (target only)

```python
resolution = self._resolver.resolve([target_semantic], room_spec)
# non-target items ไม่ผ่าน resolver — ใช้ตำแหน่งเดิม
```

#### 6. Merge & enrich

```python
new_layout = [target_resolved] + [item for item in current if not is_target]
enrich_from_catalog(new_layout)
```

#### 7. Collision repair (max 6 attempts)

เช็คว่า target (ตำแหน่งใหม่) ชนกับ bystander ไหม:
```python
for attempt in range(_MAX_REPAIR_ATTEMPTS):
    collisions = check_collisions(new_layout)
    if not collisions:
        break

    for c in collisions:
        if target.id in c.furniture_ids:
            # shift เฉพาะ target ไม่แตะ bystander
            RepairStep._try_shift(c, new_layout, room)
```

เงื่อนไขสำคัญ: **bystander ไม่ถูกขยับ** — ผู้ใช้สั่งย้ายชิ้นเดียว ชิ้นอื่นควรนิ่ง

#### 8. MODIFIER_EXPLANATION_PROMPT

หลัง resolve เรียก LLM เขียนคำอธิบายสั้นๆ
- **Rule**: ห้ามเตือนเรื่อง sha chi / bad energy / เสนอทางเลือก
- ต้อง echo คำของ user: ถ้าพูด "ขวางประตู" ให้ตอบ "ขวางประตู" ไม่ใช่ "ตรงข้ามประตู"

### Emits

```
modifier_started      {modification: "..."}
step_progress × N
layout_updated        {layout_items: [...]}
modifier_completed    {changed_furniture: "<id>", collisions_after: 0}
```

---

## RearrangeAgent

File: [rearrange_agent.py](../src/modules/layout/application/modifier/rearrange_agent.py)

### Entry: `async def apply()`

```python
async def apply(
    current_layout: list[dict],
    room_spec: dict,
    modification_request: str,
) -> AsyncGenerator[SSEEvent, None]:
```

### Flow

#### 1. Build furniture_list from current_layout (line 128–144)

```python
furniture_list = [
    {
        "id": item.furniture_id,
        "name": item.name,
        "width": item.dimensions.width,
        "depth": item.dimensions.depth,
        ...
    }
    for item in current_layout
]

allowed_ids = {item.id for item in current_layout}  # ใช้กัน LLM หลอน
```

#### 2. Build room features (line 146–165)

```python
doors = [{"wall": d.wall, "offset": d.offset, "width": d.width} for d in room_spec.doors]
windows = [{"wall": w.wall, "offset": w.offset, "width": w.width} for w in room_spec.windows]
command_positions = self._build_command_positions(doors)
```

#### 3. Parse wall direction (line 176)

```python
wall_dir = _parse_wall_direction(modification_request)
# "จัดห้องให้หน่อย" → None (ไม่มี keyword ทิศ)
# "ย้ายทุกอย่างไปฝั่งเหนือ" → "north"
```

#### 4. Build hard constraints (line 179–189)

```python
hard_constraints = (
    f"You MUST place ALL {len(furniture_list)} of these furniture IDs — "
    f"every single one: [{owned_ids_str}]. "
    f"Do NOT skip, drop, or omit any item from the list. "
    f"Your response MUST contain exactly {len(furniture_list)} placements."
)
user_prefs["placement_constraints"] = hard_constraints
```

เหตุผล: LLM ชอบทิ้งชิ้นที่มันคิดว่า "ไม่จำเป็น" — ต้องสั่งให้วางครบ

#### 5. LLM plan_layout (line 191–201)

```python
llm_response = await self._llm_agent.plan_layout(
    room_type=room_type,
    width=room_w, depth=room_d,
    usable_area=room_w * room_d * 0.7,
    doors=doors, windows=windows,
    furniture_list=furniture_list,
    command_positions=command_positions,
    user_preferences=user_prefs,
)
```

#### 6. Override LLM sizes (line 228–246)

```python
dims_by_id = {item.furniture_id: item.dimensions for item in current_layout}

for p in llm_response.placements:
    real_dims = dims_by_id[p.furniture_id]
    p.size = {
        "w": real_dims.width,
        "l": real_dims.depth,
        "h": real_dims.height,
    }  # override — กัน LLM หลอนขนาด
```

#### 7. WallAssigner (line 256–257)

```python
wall_assigner = WallAssigner()
corrected_placements = wall_assigner.assign(corrected_placements, room_spec)
```

Deterministic wall assignment — แทน LLM reasoning ที่พลาดบ่อย ดู [06-wall-assigner.md](./06-wall-assigner.md)

#### 8. Explicit wall override (line 259–266)

ถ้า user พูดระบุทิศชัด:
```python
if wall_dir:
    _pack_alignments = ["left", "center", "right", "left", "center", "right"]
    for idx, p in enumerate(corrected_placements):
        p["target_wall"] = wall_dir
        p["offset_from_wall"] = 0.0
        p["alignment"] = _pack_alignments[idx % len(_pack_alignments)]
```

กรณีนี้: force ทุกชิ้นไปผนังนั้น, pack แบบ left/center/right วนรอบ

#### 9. Resolve semantic → physical (line 268)

```python
resolution = self._resolver.resolve(corrected_placements, room_spec)
```

#### 10. Repair collisions (line 271–291)

```python
_MAX_REPAIR = 5
for attempt in range(_MAX_REPAIR):
    if not collisions:
        break

    for c in collisions:
        conflict = Conflict(OVERLAP, "...", furniture_ids)
        RepairStep._try_shift(conflict, physical, room)

    collisions = self._recheck_collisions(physical, room)
```

#### 11. Enrich + filter + backfill (line 306–393)

```python
enriched = self._enrich_from_current(physical, current_layout)

# Filter: ลบชิ้นที่ LLM หลอนเพิ่ม
enriched = [e for e in enriched if e.furniture_id in allowed_ids]

# Backfill: ชิ้นที่ LLM ทิ้งไป
for original in current_layout:
    if original.furniture_id not in placed_ids:
        if is_dependent_type(original.type):
            # e.g. chair, coffee_table → re-resolve กับ anchor
            re_resolve_with_pairing(original, enriched)
        else:
            # ลองใช้ตำแหน่งเดิม, ถ้าชนก็ shift
            place_or_shift(original, enriched)
```

**Dependent types** ที่ต้อง re-resolve:
```python
_DEPENDENT_TYPES = {"chair", "office_chair", "dining_chair", "coffee_table"}
```

เพราะชิ้นเหล่านี้ต้องอยู่ข้าง anchor (เก้าอี้ต้องข้างโต๊ะ)

### Emits

```
modifier_started      {modification: "..."}
step_progress         {progress: 0.15, "Analysing furniture..."}
step_progress         {progress: 0.40, "Planning feng shui layout..."}
step_progress         {progress: 0.70, "Resolving positions..."}
step_progress         {progress: 0.90, "Finalising..."}
modifier_completed    {changed_furniture: "all", collisions_after: 0}
```

---

## เปรียบเทียบ Modifier vs Rearrange vs Pipeline

| Feature | Pipeline (new_layout) | RearrangeAgent | ModifierAgent |
|---|---|---|---|
| Step 1 (data builder) | ✅ | ❌ (ใช้ room_spec ตรง) | ❌ |
| RAG retrieval | ✅ | ❌ | ❌ |
| Furniture selection | ✅ (จาก catalog) | ❌ (ใช้ของเดิม) | ❌ |
| LLM plan_layout | ✅ | ✅ | ❌ (แค่แก้ semantic ของ target) |
| SpatialResolver | ✅ | ✅ | ✅ (แค่ target) |
| WallAssigner | ✅ (ใน Step 2) | ✅ | ❌ |
| Rule checker (ฮวงจุ้ย) | ✅ | ❌ (collision only) | ❌ |
| Repair loop | up to 3× (pipeline) | up to 5× | up to 6× |
| Explainer (Thai) | ✅ LLM | ❌ | ✅ LLM (MODIFIER_EXPLANATION_PROMPT) |
| Scoring (100-point) | ✅ | ❌ | ❌ |
| Backfill dropped items | ❌ | ✅ | N/A |
| Allowed_ids filter | ❌ | ✅ | N/A |

## จุดที่ควรรู้

1. **Rearrange บังคับ LLM วางครบ** ด้วย hard_constraints + allowed_ids filter + backfill — 3 layers กันชิ้นหาย
2. **ใน Modifier ชิ้นอื่นไม่ขยับ** — ถ้าเกิด collision repair จะขยับเฉพาะ target
3. **Dependent type re-resolve** — coffee_table/chair ถูกจัดการพิเศษเมื่อ LLM ทิ้ง
4. **ขนาดถูก override เสมอ** — LLM อาจเปลี่ยนขนาดใน response; backend overrides จาก catalog/current_layout
5. **wall_dir override ลบ offset_from_wall** — เมื่อ user สั่งชัด ให้ชิดผนังติด (offset=0)
