# 13 — Constants Reference

รวมค่าคงที่ทั้งหมดในระบบไว้ในหน้าเดียว

## Clearance / Distance

| Constant | Value | Location | ใช้ตอน |
|---|---|---|---|
| `MIN_CLEARANCE` | 0.6m | [step3_rule_checker.py:38](../src/modules/layout/application/pipeline/steps/step3_rule_checker.py#L38) | ช่องว่างขั้นต่ำระหว่างเฟอร์นิเจอร์ (rule check) |
| `DOOR_CLEARANCE` | 0.9m | [step3_rule_checker.py:40](../src/modules/layout/application/pipeline/steps/step3_rule_checker.py#L40) | Clearance หน้าประตู (rule check) |
| `MIN_WALKWAY` | 0.7m | [step3_rule_checker.py:42](../src/modules/layout/application/pipeline/steps/step3_rule_checker.py#L42) | ความกว้างทางเดิน |
| `MIN_SHIFT_CLEARANCE` | 0.15m | [step4_repair.py:38](../src/modules/layout/application/pipeline/steps/step4_repair.py#L38) | Gap หลัง shift |
| `_DOOR_CLEAR` | 1.5m | [step4_repair.py:207](../src/modules/layout/application/pipeline/steps/step4_repair.py#L207), [spatial_resolver.py:204](../src/modules/layout/application/services/spatial_resolver.py#L204) | Walking zone หน้าประตู |
| `_DOOR_PAD` | 0.5m | [step4_repair.py:207](../src/modules/layout/application/pipeline/steps/step4_repair.py#L207) | Padding ด้านข้างประตู |
| `_WALL_TOL` | 0.1m | [spatial_resolver.py:471](../src/modules/layout/application/services/spatial_resolver.py#L471) | Tolerance ตรวจชิดผนัง |
| `_DOOR_ADJACENT_GAP` | 0.1m | [spatial_resolver.py:132](../src/modules/layout/application/services/spatial_resolver.py#L132) | Gap shoe_cabinet/coat_rack จากประตู |
| `BACK_TO_DOOR_ANGLE` | 60° | [step3_rule_checker.py:577](../src/modules/layout/application/pipeline/steps/step3_rule_checker.py#L577) | Threshold หันหลังให้ประตู |

## Shift / Bump Steps

| Constant | Value | Location | ใช้ตอน |
|---|---|---|---|
| `SHIFT_INCREMENTS` | `[0.3, 0.5, 0.8, 1.0, 1.3, 1.6, 2.0]` | [step4_repair.py:36](../src/modules/layout/application/pipeline/steps/step4_repair.py#L36) | Distance steps ใน Step 4 repair |
| `SHIFT_DIRECTIONS` | 8 cardinal + diagonal | [step4_repair.py:39](../src/modules/layout/application/pipeline/steps/step4_repair.py#L39) | ทิศที่ลอง shift |
| `_BUMP_STEPS` | `[0.1, 0.2, 0.3, 0.5, 0.8, 1.0, 1.5]` | [spatial_resolver.py:201](../src/modules/layout/application/services/spatial_resolver.py#L201) | Bump distances ใน SpatialResolver |
| Door-adjacent fine steps | `[0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0, 1.2, 1.5, 2.0]` | [spatial_resolver.py:568](../src/modules/layout/application/services/spatial_resolver.py#L568) | Slide along door wall |
| `_NUDGE_DISTANCE` | 0.3m | [modifier_agent.py:41](../src/modules/layout/application/modifier/modifier_agent.py#L41) | Nudge step ใน Modifier |

## Loop Limits

| Constant | Value | Location | ใช้ตอน |
|---|---|---|---|
| `max_repair_loops` | 3 | [models.py:168](../src/modules/layout/application/pipeline/models.py#L168) | Pipeline Step 3↔4 loop |
| `_MAX_REPAIR` (rearrange) | 5 | [rearrange_agent.py:276](../src/modules/layout/application/modifier/rearrange_agent.py#L276) | Rearrange repair attempts |
| `_MAX_REPAIR_ATTEMPTS` | 6 | [modifier_agent.py:39](../src/modules/layout/application/modifier/modifier_agent.py#L39) | Modifier nudge attempts |

## LLM Config

### RouterAgent

| Constant | Value |
|---|---|
| `model` | `LLM_MODEL_ROUTER` (settings) |
| `temperature` | 0.0 |
| `max_tokens` | 200 |
| `timeout` | 15s |
| confidence threshold (fallback) | 0.5 |
| conversation history used | last 4 turns |
| max chars per turn | 120 |

### FengShuiLLMAgent

| Constant | Value |
|---|---|
| `model` | `LLM_MODEL_LAYOUT` (settings) |
| `temperature` | 0.1 |
| `max_tokens` | 4096 |
| `timeout` | 60s |
| `max_retries` | 3 |

### Pipeline (default)

| Constant | Value | Location |
|---|---|---|
| `llm_model` | `"anthropic/claude-3.5-sonnet"` | [models.py:169](../src/modules/layout/application/pipeline/models.py#L169) |
| `llm_temperature` | 0.3 | [models.py:170](../src/modules/layout/application/pipeline/models.py#L170) |
| `step_timeout_seconds` | 60.0 | [models.py:171](../src/modules/layout/application/pipeline/models.py#L171) |
| `total_timeout_seconds` | 300.0 | [models.py:172](../src/modules/layout/application/pipeline/models.py#L172) |

## Feng Shui Scoring

| Component | Max Points | Location |
|---|---|---|
| Command Position | 30 | [feng_shui_score.py:9](../src/modules/layout/domain/value_objects/feng_shui_score.py#L9) |
| Five Elements | 20 | [feng_shui_score.py:10](../src/modules/layout/domain/value_objects/feng_shui_score.py#L10) |
| Chi Flow | 25 | [feng_shui_score.py:11](../src/modules/layout/domain/value_objects/feng_shui_score.py#L11) |
| Sha Chi Avoidance | 25 | [feng_shui_score.py:12](../src/modules/layout/domain/value_objects/feng_shui_score.py#L12) |
| **Total Max** | **100** | — |

### Grade Thresholds (FengShuiScore)

| Grade | Total Score |
|---|---|
| A | ≥ 90 |
| B | ≥ 70 |
| C | ≥ 50 |
| D | ≥ 40 |
| F | < 40 |

### Grade Thresholds (Step 5 Explainer)

| Grade | Total Score | Location |
|---|---|---|
| Excellent | ≥ 80 | [step5_explainer.py:36](../src/modules/layout/application/pipeline/steps/step5_explainer.py#L36) |
| Good | ≥ 60 | [step5_explainer.py:37](../src/modules/layout/application/pipeline/steps/step5_explainer.py#L37) |
| Fair | ≥ 40 | [step5_explainer.py:38](../src/modules/layout/application/pipeline/steps/step5_explainer.py#L38) |
| Needs work | < 40 | — |

### Five Elements Ideal Balance

| Element | % | Location |
|---|---|---|
| Wood | 25% | [feng_shui_scorer.py:133](../src/modules/layout/application/services/feng_shui_scorer.py#L133) |
| Fire | 15% | |
| Earth | 25% | |
| Metal | 20% | |
| Water | 15% | |

### Element Associations

| Furniture Type | Element |
|---|---|
| bed, desk, bookshelf, wardrobe, nightstand, plant | Wood |
| lamp | Fire |
| sofa, coffee_table, dining_table, rug | Earth |
| chair, tv_stand | Metal |
| mirror | Water |

## Pair Rules (SpatialResolver)

| Dependent | Anchor | Gap | Location |
|---|---|---|---|
| chair | desk | 0.05m | [spatial_resolver.py:187](../src/modules/layout/application/services/spatial_resolver.py#L187) |
| office_chair | desk | 0.05m | |
| dining_chair | dining_table | 0.05m | |
| coffee_table | sofa | 0.10m | |

## Wall Rotations

### `_WALL_ROTATION` (for wall-hugging furniture)

| Wall | Rotation |
|---|---|
| north | 0° |
| south | 180° |
| west | 90° |
| east | 270° |

Location: [spatial_resolver.py:111](../src/modules/layout/application/services/spatial_resolver.py#L111)

### `_FACING_ROTATION` (for free-floating furniture)

| Facing | Rotation |
|---|---|
| south | 0° |
| north | 180° |
| east | 270° |
| west | 90° |

Location: [spatial_resolver.py:166](../src/modules/layout/application/services/spatial_resolver.py#L166)

### Anchor Front → Front Side

| Rotation | Front Side |
|---|---|
| 0 | north |
| 180 | south |
| 90 | east |
| 270 | west |

Used in pair placement priority

## Furniture Type Sets

### Force Inward (SpatialResolver, line 137)

```python
_FORCE_INWARD_TYPES = {
    "bed", "chair", "office_chair", "dining_chair",
    "desk", "sofa", "tv_stand", "wardrobe",
    "bookshelf", "nightstand", "dresser", ...
}
```

### Door Adjacent (SpatialResolver, line 129)

```python
_DOOR_ADJACENT_TYPES = {"shoe_cabinet", "coat_rack"}
```

### Dependent Types (RearrangeAgent, line 314)

```python
_DEPENDENT_TYPES = {
    "chair", "office_chair", "dining_chair", "coffee_table"
}
```

### Center Types (WallAssigner)

```python
_CENTER_TYPES = {"area_rug", "coffee_table", "ottoman", "room_divider"}
```

## Opposite Wall Map

```python
_OPPOSITE = {
    "north": "south", "south": "north",
    "east": "west", "west": "east",
}
```

Used in: rearrange_agent.py, router.py, wall_assigner.py

## Side Walls Map

```python
_SIDE_WALLS = {
    "north": ("west", "east"),
    "south": ("west", "east"),
    "east":  ("south", "north"),
    "west":  ("south", "north"),
}
```

Used in: router.py (clarification merge), wall_assigner.py

## Thai Direction Keywords

```python
_DIR_KEYWORDS = {
    "ทิศเหนือ": "north", "ทิศใต้": "south",
    "ทิศตะวันออก": "east", "ทิศตะวันตก": "west",
    "ตะวันออก": "east", "ตะวันตก": "west",
    "เหนือ": "north", "ใต้": "south",
    "north": "north", "south": "south",
    "east": "east", "west": "west",
}
```

Location: [rearrange_agent.py:44](../src/modules/layout/application/modifier/rearrange_agent.py#L44)

## Block Door Keywords

```python
_BLOCK_DOOR_KEYWORDS = {
    "ขวางประตู", "across from door", "opposite door", ...
}

_DOOR_KEYWORDS = {
    "ชิดประตู", "near door", "by the door", ...
}
```

**สำคัญ**: ต้องเช็ค BLOCK_DOOR ก่อน DOOR (เพราะ "ขวางประตู" มี "ประตู" อยู่)

## Conflict Type → Rule ID Mapping

```python
_CONFLICT_TO_RULE = {
    ConflictType.BAD_COMMAND_POSITION: "cmd_001",
    ConflictType.ELEMENT_IMBALANCE: "elem_001",
    ConflictType.SHA_CHI_ALIGNMENT: "sha_001",
    ConflictType.BACK_TO_DOOR: "cmd_002",
    ConflictType.BLOCKED_CHI_FLOW: "chi_001",
}
```

Location: [step3_rule_checker.py:128](../src/modules/layout/application/pipeline/steps/step3_rule_checker.py#L128)

## Room Type → Essential Furniture

```python
{
    RoomType.BEDROOM: ["bed", "nightstand", "wardrobe"],
    RoomType.LIVING_ROOM: ["sofa", "coffee_table", "tv_stand"],
    RoomType.OFFICE: ["desk", "office_chair", "bookshelf"],
    RoomType.DINING_ROOM: ["dining_table", "dining_chair"],
    RoomType.STUDIO_APARTMENT: ["sofa_bed", "compact_wardrobe", "folding_desk"],
}
```

Location: [entities/room.py:27](../src/modules/layout/domain/entities/room.py#L27)

## Budget Maps

```python
budget_map = {"ประหยัด": "low", "กลาง": "medium", "สูง": "high"}
```

Location: [router.py:194](../src/api/v1/chat/router.py#L194)

## Usable Area Ratio

```python
usable_area = room.width * room.depth * 0.7
```

30% reserved สำหรับทางเดิน/open space

## จุดที่ควรรู้

1. **ค่า clearance ไม่ sync** — step 3 รูบ 0.9m, step 4 ใช้ 1.5m ตามปกติ (intentional: repair safer)
2. **Pipeline max_repair_loops = 3** แต่ rerun Step 3 ก่อน break → จริงๆ ตรวจถึง 4 ครั้ง
3. **Modifier nudge ต่างจาก pipeline shift** — Modifier เลื่อนแค่ 0.3m/ครั้ง, pipeline มี 7 steps
4. **Element ideal sum = 100%** (25+15+25+20+15)
5. **_BUMP_STEPS เพิ่มขึ้นเป็น exponential roughly** — small → 0.1, large → 1.5
6. **_WALL vs _FACING rotation ต่างกัน** — อย่าสับสน (ดู [09-coordinates.md](./09-coordinates.md))
