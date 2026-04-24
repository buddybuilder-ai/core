# 07 — Collision Detection & Repair

AABB-based collision + shift/rotate repair logic

## AABB (Axis-Aligned Bounding Box)

File: [geometry/collision.py](../src/modules/layout/infrastructure/geometry/collision.py)

### Data (line 17–32)

```python
@dataclass(frozen=True)
class AABB:
    min_x: float
    min_z: float
    max_x: float
    max_z: float
```

### Properties

```python
width    = max_x - min_x
depth    = max_z - min_z
center_x = (min_x + max_x) / 2
center_z = (min_z + max_z) / 2
area     = width * depth
```

### Factory Methods

**`from_position_and_size(x, z, w, d)`** (line 154)
- ใช้เมื่อมี top-left corner + size
- `max_x = x + w`

**`from_center_and_size(cx, cz, w, d)`** (line 169) ⭐
- ใช้ทั่วไปในระบบ (เพราะ BuddyBuilder ใช้ centre-origin)
- `min_x = cx - w/2`, `max_x = cx + w/2`
- ใน [CLAUDE.md](../../.claude/CLAUDE.md) ระบุว่าใช้ method นี้ทุกที่ใน spatial_resolver.py

---

## Core Methods

### `intersects(other)` (line 71)

```python
def intersects(self, other: AABB) -> bool:
    return NOT (
        self.max_x <= other.min_x or
        other.max_x <= self.min_x or
        self.max_z <= other.min_z or
        other.max_z <= self.min_z
    )
```

**กฎ Separating Axis**: ถ้าแยกได้บน axis ใดแม้อันเดียว → ไม่ทับ

**Edge touching ไม่นับว่าทับ** (เพราะใช้ `<=` ไม่ใช่ `<`)

### `touches(other)` (line 87)

True ถ้า box แชร์ขอบแต่ไม่ overlap (edge sharing)

### `distance_to(other)` (line 106)

Euclidean distance ระหว่างจุดที่ใกล้ที่สุด:
```python
dx = max(other.min_x - self.max_x, self.min_x - other.max_x, 0)
dz = max(other.min_z - self.max_z, self.min_z - other.max_z, 0)
return sqrt(dx² + dz²)
```

- ถ้าทับ → return 0
- ถ้าห่าง → return gap

ใช้ใน [step3_rule_checker.py](../src/modules/layout/application/pipeline/steps/step3_rule_checker.py) เช็ค `CLEARANCE_VIOLATION`

### `expanded(amount)` (line 119)

คืน AABB ที่ขยายออก `amount` ทุกด้าน:
```python
return AABB(
    min_x - amount, min_z - amount,
    max_x + amount, max_z + amount,
)
```

ใช้เช็ค clearance zone

### `intersection(other)` (line 135)

คืน AABB ของพื้นที่ทับ (หรือ None ถ้าไม่ทับ)

### `contains_point(x, z)` (line 59)

เช็คว่าจุด (x, z) อยู่ในกรอบไหม

---

## Clearance Constants (รวม)

| Constant | Value | ที่มา | ใช้ตอน |
|---|---|---|---|
| `MIN_CLEARANCE` | 0.6m | [step3](../src/modules/layout/application/pipeline/steps/step3_rule_checker.py#L38) | เช็คช่องว่างระหว่างเฟอร์นิเจอร์ |
| `DOOR_CLEARANCE` | 0.9m | [step3](../src/modules/layout/application/pipeline/steps/step3_rule_checker.py#L40) | Clearance รอบประตู (rule checker) |
| `MIN_WALKWAY` | 0.7m | [step3](../src/modules/layout/application/pipeline/steps/step3_rule_checker.py#L42) | ทางเดิน |
| `MIN_SHIFT_CLEARANCE` | 0.15m | [step4](../src/modules/layout/application/pipeline/steps/step4_repair.py#L38) | Gap หลัง shift |
| `_DOOR_CLEAR` | 1.5m | [step4](../src/modules/layout/application/pipeline/steps/step4_repair.py#L207) | Walking zone หน้าประตู (repair) |
| `_DOOR_PAD` | 0.5m | [step4](../src/modules/layout/application/pipeline/steps/step4_repair.py#L207) | Padding ข้างประตู |
| `_WALL_TOL` | 0.1m | [spatial_resolver](../src/modules/layout/application/services/spatial_resolver.py#L471) | Tolerance detect ชิดผนัง |
| `_DOOR_ADJACENT_GAP` | 0.1m | [spatial_resolver](../src/modules/layout/application/services/spatial_resolver.py#L132) | Gap shoe_cabinet จากประตู |

**หมายเหตุ**: clearance หน้าประตูต่างกันระหว่าง step 3 (rule check = 0.9m) กับ step 4 (repair = 1.5m)
- Step 3 เตือนเมื่อวางใกล้กว่า 0.9m
- Step 4 พยายามหาตำแหน่งที่ห่าง 1.5m (safer)

---

## Repair Algorithms

File: [step4_repair.py](../src/modules/layout/application/pipeline/steps/step4_repair.py)

### Available Actions

```python
class RepairActionType(Enum):
    SHIFT = "shift"      # เลื่อนตำแหน่ง
    ROTATE = "rotate"    # หมุน
    SWAP = "swap"        # สลับชิ้น (ไม่ค่อยใช้)
    REMOVE = "remove"    # ลบออก (ไม่ค่อยใช้)
```

### Constants

```python
SHIFT_INCREMENTS = [0.3, 0.5, 0.8, 1.0, 1.3, 1.6, 2.0]   # เมตร

SHIFT_DIRECTIONS = [
    # Cardinal
    (1, 0), (-1, 0), (0, 1), (0, -1),
    # Diagonal
    (1, 1), (-1, 1), (1, -1), (-1, -1),
]
```

---

## Shift Algorithm: `_try_shift()` (line 182–294)

### Input
- `conflict: Conflict` (มี `items_involved`)
- `physical: list[dict]` (layout items)
- `room: Room`

### Output
- `RepairAction` (success=True/False)
- Mutates `physical[target_item]`

### Flow

```
1. หา target item จาก conflict.furniture_ids[0]
2. Pre-compute door zones
3. Loop: for dist in SHIFT_INCREMENTS × for dir in SHIFT_DIRECTIONS:
   a. Compute new_x, new_z
   b. Bounds check (centre-based)
   c. Collision check (กับชิ้นอื่นที่ไม่ใช่ target)
   d. Door zone check
   e. ถ้าผ่าน → apply + return success
4. ถ้าวน loop หมดไม่เจอ → return failed action
```

### Detailed

```python
def _try_shift(conflict, physical, room):
    target_id = conflict.items_involved[0]
    target = find_by_id(physical, target_id)
    original = dict(target)

    # Pre-compute door clearance zones
    door_zones = []
    for door in room.doors:
        # Zone เฉพาะทิศประตู
        door_zones.append(compute_door_zone(door, _DOOR_CLEAR, _DOOR_PAD))

    for dist in SHIFT_INCREMENTS:
        for dx, dz in SHIFT_DIRECTIONS:
            # Normalize diagonals
            length = sqrt(dx**2 + dz**2)
            new_x = original.pos_x + (dx/length) * dist
            new_z = original.pos_z + (dz/length) * dist

            # Bounds (centre-based + footprint)
            fw, fd = get_footprint(target)  # swap if rotated
            if abs(new_x) + fw/2 > room.width/2: continue
            if abs(new_z) + fd/2 > room.depth/2: continue

            # Collision check with MIN_SHIFT_CLEARANCE
            new_box = AABB.from_center_and_size(new_x, new_z, fw, fd).expanded(MIN_SHIFT_CLEARANCE)
            if any(new_box.intersects(other_box(p)) for p in physical if p != target):
                continue

            # Door zone check
            if any(new_box.intersects(zone) for zone in door_zones):
                continue

            # Valid!
            target["pos_x"] = new_x
            target["pos_z"] = new_z
            return RepairAction(
                action_type=SHIFT,
                furniture_id=target_id,
                before={"pos_x": original.pos_x, "pos_z": original.pos_z},
                after={"pos_x": new_x, "pos_z": new_z},
                success=True,
            )

    return RepairAction(action_type=SHIFT, success=False)
```

### Door Zone Computation (line 207–235)

```python
def compute_door_zone(door, clear_dist, pad):
    # สร้าง rectangle หน้าประตูที่กว้าง door.width + 2*pad
    # ยาว clear_dist (เข้าห้องจากประตู)

    if door.wall == "south":
        return AABB(
            min_x = door.center_x - door.width/2 - pad,
            max_x = door.center_x + door.width/2 + pad,
            min_z = -room.depth/2,  # ชิดผนังใต้
            max_z = -room.depth/2 + clear_dist,  # ยื่นเข้าห้อง
        )
    # ...similar for other walls
```

---

## Rotate Algorithm: `_try_rotate()` (line 296–365)

ลองหมุน target เป็น 90°/180°/270°/0° (ข้าม current rotation)

```python
def _try_rotate(conflict, physical, room):
    target = find_by_id(physical, conflict.items_involved[0])
    current_rot = target.get("rotation", 0)
    natural_w = target.dimensions.width
    natural_d = target.dimensions.depth

    for new_rot in [90, 180, 270, 0]:
        if new_rot == current_rot:
            continue

        # คำนวณ footprint ใหม่
        if new_rot % 360 in (90, 270):
            fw, fd = natural_d, natural_w  # swap
        else:
            fw, fd = natural_w, natural_d

        # Bounds check ด้วย footprint ใหม่
        if out_of_bounds(target.pos_x, target.pos_z, fw, fd):
            continue

        # Collision
        new_box = AABB.from_center_and_size(target.pos_x, target.pos_z, fw, fd)
        if any(new_box.intersects(other_box(p)) for p in physical if p != target):
            continue

        # Valid!
        target["rotation"] = new_rot
        return RepairAction(
            action_type=ROTATE,
            before={"rotation": current_rot},
            after={"rotation": new_rot},
            success=True,
        )

    return RepairAction(success=False)
```

---

## Pair Re-anchoring (line 392–549)

เมื่อ shift หรือ rotate anchor (โต๊ะ) → dependent (เก้าอี้) ต้องตาม

### Dependent Rules (line 377–381)

```python
_DEPENDENT_RULES = {
    ("chair", "office_chair"): "desk",
    ("dining_chair",): "dining_table",
    ("coffee_table",): "sofa",
}
```

### Token-Based Matching (line 385–390)

```python
def _token_match(item_type, target_types):
    tokens = re.split(r"[-_\s]+", item_type.lower())
    return any(t in tokens for t in target_types)

# "office-chair" → tokens = ["office", "chair"] → match "chair"
# "sofa-bed" → tokens = ["sofa", "bed"] → NOT match "bed" alone
# (เพราะ primary token = "sofa")
```

### Snap to Anchor Front Face (line 392–549)

```python
def _resnap_dependents(physical, anchor_shifted):
    for dep in physical:
        if not is_dependent_of(dep, anchor_shifted):
            continue

        # 1. หา anchor's front face
        anchor_rot = anchor_shifted.rotation
        front_side = {
            0: "north",    # rotation=0 → หันเหนือ → front=north
            180: "south",
            90: "east",
            270: "west",
        }[anchor_rot]

        # 2. หาตำแหน่ง front ของ anchor
        anchor_box = AABB.from_center_and_size(
            anchor_shifted.pos_x, anchor_shifted.pos_z,
            anchor.footprint_w, anchor.footprint_d,
        )

        # 3. วาง dependent ข้าง front face
        sides = ["north", "south", "east", "west"]
        front_priority_idx = sides.index(front_side)
        ordered_sides = [front_side] + [s for s in sides if s != front_side]

        for side in ordered_sides:
            dep_pos = compute_side_position(anchor_box, side, dep, gap=0.05)
            dep_rot = facing_anchor_rotation(side, dep.model_rotation_offset)

            if valid(dep_pos, dep_rot):
                update(dep, dep_pos, dep_rot)
                break
```

### Rotation Correction (line 528)

```python
corrected_rot = (facing_rot - model_offset) % 360
```

เพราะ 3D model อาจ export โดย front ไม่ตรงกับ +Z:
- `model_rotation_offset=0` → model's +Z = front (mapping ตรง)
- `model_rotation_offset=90` → model's +X = front (ต้องชดเชย)

---

## Repair Loop Strategy

### Pipeline (`PipelineOrchestrator.run`)

```python
for iteration in range(config.max_repair_loops + 1):  # default 0, 1, 2, 3
    # Step 3: Rule Checker
    run_rule_checker()

    if not unresolved_conflicts:
        break  # ไม่มี conflict → ออก

    if iteration >= max_repair_loops:
        break  # วนครบ → give up

    # Step 4: Repair
    run_repair()
    # วนกลับไป Step 3 เพื่อ re-check (การ shift อาจสร้าง collision ใหม่)
```

### RearrangeAgent

```python
_MAX_REPAIR = 5
for attempt in range(_MAX_REPAIR):
    if not collisions: break
    for c in collisions:
        _try_shift(c, physical, room)
    collisions = recheck(physical, room)
```

### ModifierAgent

```python
_MAX_REPAIR_ATTEMPTS = 6
# วน shift เฉพาะ target ไม่แตะ bystander
```

---

## Overlap Safety Net (Step 5)

File: [step5_explainer.py:292-310](../src/modules/layout/application/pipeline/steps/step5_explainer.py#L292)

```python
def _count_actual_overlaps(layout_items) -> int:
    """Brute-force geometry check — independent of conflicts.resolved flag"""
    count = 0
    for i, a in enumerate(layout_items):
        for b in layout_items[i+1:]:
            box_a = aabb_from_item(a)
            box_b = aabb_from_item(b)
            if box_a.intersects(box_b):
                count += 1
    return count
```

ถ้า actual_overlaps > 0 แต่ conflicts ทั้งหมด resolved → override explanation เตือนว่ายังมี collision

---

## จุดที่ควรรู้

1. **AABB edge-touching ไม่ใช่ overlap** — ใช้ `<=` ใน intersects
2. **Centre-origin ทุกที่** — ใช้ `from_center_and_size` ไม่ใช่ `from_position_and_size`
3. **Rotation swap dimensions** — อย่าลืม swap w/d เมื่อ rotation 90°/270°
4. **Shift ตรวจ door zone เข้มกว่า rule checker** — `_DOOR_CLEAR=1.5m` vs `DOOR_CLEARANCE=0.9m`
5. **Repair ไม่รับประกัน converge** — หลัง max loops อาจยังมี conflict (log warning)
6. **Pair re-snap ถูกข้าม ถ้า primary token match ผิด** — sofa-bed ไม่ถูก treat เป็น bed เพราะ primary = sofa
7. **Bystander ไม่ถูกขยับใน Modifier** — เฉพาะ pipeline กับ rearrange ที่ allow shift ทุกชิ้น
