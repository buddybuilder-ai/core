# 05 — Spatial Resolver

หัวใจของการแปลง **semantic placement** → **พิกัดจริง**

File: [spatial_resolver.py](../src/modules/layout/application/services/spatial_resolver.py)

## แนวคิด

LLM ให้มา: `"bed ที่ผนังเหนือ, alignment center, offset 0.05m, หันไปทิศใต้"`

SpatialResolver คำนวณออกมาเป็น:
```python
PhysicalPlacement(
    furniture_id="bed_queen_001",
    x=2.0, y=0, z=-1.7,        # พิกัด Three.js centre-origin
    rotation=0,                # องศา
    bbox=AABB(min_x, min_z, max_x, max_z),
)
```

## Data Structures

### SemanticPlacement (input, line 36)

```python
@dataclass
class SemanticPlacement:
    furniture_id: str
    furniture_type: str
    size: FurnitureSize              # w, length, h (frozen)
    target_wall: str                 # "north"|"south"|"east"|"west"|"center"
    alignment: str                   # "left"|"center"|"right"
    offset_from_wall: float          # เมตร
    priority: int                    # 1 = สำคัญที่สุด (จัดก่อน)
    orientation: str = ""            # override rotation (optional)
    facing: str = ""                 # หันหน้าไปทิศ (optional)
    along_wall_z: float = None       # exact Z position (ใช้กับ nightstand)
```

### PhysicalPlacement (output, line 67)

```python
@dataclass
class PhysicalPlacement:
    furniture_id: str
    x: float                          # centre X (Three.js)
    y: float = 0.0                    # always 0 (floor level)
    z: float                          # centre Z (Three.js)
    rotation: int                     # 0 | 90 | 180 | 270
    bbox: AABB                        # footprint in room space
```

### FurnitureSize (line 21)

```python
@dataclass(frozen=True)
class FurnitureSize:
    w: float          # ความกว้าง (รอย axis X ก่อนหมุน)
    length: float     # ความลึก (along axis Z ก่อนหมุน) — ชื่อแปลก แต่นี่คือ "depth"
    h: float          # ความสูง (Y)
```

### RoomSpec (line 88)

```python
@dataclass
class RoomSpec:
    width: float
    depth: float
    doors: list[DoorPosition]
    windows: list[WindowPosition]
```

## Wall Rotation Lookup (line 111–116)

```python
_WALL_ROTATION = {
    "north": 0,       # ที่ผนังเหนือ → หันหน้าใต้ (+Z) = เข้าห้อง
    "south": 180,     # ที่ผนังใต้ → หันเหนือ (-Z) = เข้าห้อง
    "west": 90,       # ที่ผนังตะวันตก → หันตะวันออก (+X) = เข้าห้อง
    "east": 270,      # ที่ผนังตะวันออก → หันตะวันตก (-X) = เข้าห้อง
}
```

**กฎ**: "เฟอร์นิเจอร์ที่ผนัง X" → หน้าหันเข้าห้อง

อ้างอิง Three.js convention: Y-rotation=0° → model's default front faces **+Z (south)**

## Facing Rotation Lookup (line 166–171)

```python
_FACING_ROTATION = {
    "south": 0,       # หน้าหัน south → rotation = 0
    "north": 180,
    "east": 270,
    "west": 90,
}
```

**ต่างจาก _WALL_ROTATION:** อันนั้นบอก "วางที่ผนังไหน", อันนี้บอก "หน้าหันทิศไหน"

ตัวอย่าง: โซฟาอยู่กลางห้อง หันหน้าไปเหนือ (ดู TV ที่ผนังเหนือ)
- ไม่ใช้ `_WALL_ROTATION["north"]=0` (เพราะไม่ได้วางชิดผนัง)
- ใช้ `_FACING_ROTATION["north"]=180`

## Force-Inward Types (line 137–159)

```python
_FORCE_INWARD_TYPES = {
    "bed", "chair", "office_chair", "dining_chair",
    "desk", "sofa", "tv_stand", "wardrobe",
    "bookshelf", "nightstand", "dresser", ...
}
```

เฟอร์นิเจอร์เหล่านี้ถ้า LLM ให้ facing แปลก (เช่น "โต๊ะหันเข้ากำแพง") → override เป็นหันเข้าห้อง

## Door-Adjacent Types (line 129)

```python
_DOOR_ADJACENT_TYPES = {"shoe_cabinet", "coat_rack"}
_DOOR_ADJACENT_GAP = 0.1
```

วางข้างประตูไม่ใช่หน้าประตู — มี logic พิเศษใน bump-out

## Pair Rules (line 186–191)

```python
_PAIR_RULES = [
    ("chair", "desk", 0.05),
    ("office_chair", "desk", 0.05),
    ("dining_chair", "dining_table", 0.05),
    ("coffee_table", "sofa", 0.10),
]
```

format: `(dependent_type, anchor_type, gap)`

ใช้ใน `_place_beside_anchor()` — วาง dependent ข้าง anchor โดยเว้นช่อง `gap`

---

## Main Method: `resolve()`

```python
def resolve(
    self,
    semantic_placements: list[SemanticPlacement],
    room: RoomSpec,
) -> list[PhysicalPlacement]:
```

### Flow

```
1. Sort by priority (1 ก่อน, 99 หลังสุด)
2. For each semantic placement:
   a. ถ้าเป็น dependent type → _place_beside_anchor()
   b. ถ้าเป็น door-adjacent → _place_beside_door()
   c. ชิ้นปกติ → _compute_initial_position()
3. _bump_out() ถ้าชนกับที่วางไว้แล้ว
4. Append to placed list
5. Return placed[]
```

### `_compute_initial_position()` (คำนวณพิกัดเริ่มต้น)

สำหรับ `target_wall="north"`, `alignment="center"`, `offset_from_wall=0.05`:

```python
room_half_w = room.width / 2       # = room-centre X
room_half_d = room.depth / 2

# North wall: z = -room_half_d (ในระบบ Three.js centre-origin)
# Furniture centre Z จากผนัง:
z = -room_half_d + (furniture.depth / 2) + offset_from_wall

# Alignment ตัดสิน X:
if alignment == "left":
    x = -room_half_w + (furniture.width / 2) + 0.1  # เว้นขอบ 0.1
elif alignment == "center":
    x = 0
elif alignment == "right":
    x = room_half_w - (furniture.width / 2) - 0.1

rotation = _WALL_ROTATION["north"]  # = 0
```

**สำคัญ**: ถ้า rotation = 90 หรือ 270 → swap width กับ depth ก่อนคำนวณ bbox:

```python
if rotation % 360 in (90, 270):
    footprint_w = furniture.length  # natural depth
    footprint_d = furniture.width   # natural width
else:
    footprint_w = furniture.width
    footprint_d = furniture.length
```

---

## Bump-Out Algorithm ⭐

Method: `_bump_out()` (line 449–714)

**ปัญหา:** วางชิ้นใหม่ชนกับชิ้นที่วางไปแล้ว หรือทับโซนประตู

**วิธีแก้:** ลอง shift ออกทีละ step ตามทิศที่ "smart" สำหรับชนิดนั้น

### Constants

```python
_BUMP_STEPS = [0.1, 0.2, 0.3, 0.5, 0.8, 1.0, 1.5]   # เมตร
_DOOR_CLEARANCE = 1.5   # walking zone in front of door
_WALL_TOL = 0.1         # tolerance detecting "hugs wall"
```

### Step 1: Detect wall proximity (line 470–475)

```python
on_south = (z - depth/2) - (-room_half_d) < _WALL_TOL
on_north = room_half_d - (z + depth/2) < _WALL_TOL
on_west  = (x - width/2) - (-room_half_w) < _WALL_TOL
on_east  = room_half_w - (x + width/2) < _WALL_TOL
```

### Step 2: Direction priority (line 599–630)

**Wall-hugging items** (เช่น เตียงชิดผนังเหนือ):
```python
if on_north:
    priority_directions = [
        (1, 0), (-1, 0),        # slide along X (เลื่อนซ้าย-ขวา)
        # slide toward X center
        toward_x_center_direction,
        (0, 1),                 # push away from wall (last resort)
    ]
```

เหตุผล: ไม่ควร push เตียงออกจากผนัง ถ้าเลื่อนซ้าย-ขวาได้ก่อน

**Floating items** (กลางห้อง):
```python
# ทุกทิศ 8 direction + prioritize toward centre
priority_directions = all_8_dirs_sorted_by_distance_to_centre()
```

### Step 3: Door zone check

```python
def in_door_zone(x, z):
    for door in room.doors:
        # Zone 1: door opening (0 → 0.15m from wall)
        if in_opening_zone(x, z, door, 0, 0.15):
            return True
        # Zone 2: walking clearance (0.15 → 1.5m)
        if in_walking_zone(x, z, door, 0.15, _DOOR_CLEARANCE):
            return True
    return False
```

Padding ด้านข้างประตู: **0.5m** ซ้าย-ขวา

### Step 4: Try each (distance, direction) combination

```python
for dist in _BUMP_STEPS:
    for dx, dz in priority_directions:
        new_x = x + dx * dist
        new_z = z + dz * dist

        if out_of_bounds(new_x, new_z): continue
        if overlaps_placed(new_x, new_z): continue
        if in_door_zone(new_x, new_z): continue

        return (new_x, new_z)  # 
```

### Step 5: Alternative wall fallback (line 647–714)

ถ้าผนังเดิมเต็ม (ไม่มีที่ให้ bump) → ลองผนังอื่น:

```python
fallback_order = {
    "north": ["south", "west", "east"],
    "south": ["north", "west", "east"],
    "east": ["west", "north", "south"],
    "west": ["east", "north", "south"],
}

for alt_wall in fallback_order[original_wall]:
    new_pos = _compute_initial_position(furniture, alt_wall, alignment)
    if not overlaps(new_pos):
        return new_pos
    # slide along alt wall
    for shift in _BUMP_STEPS:
        ...
```

### Step 6: Door-adjacent special handling (line 530–590)

```python
if furniture.type in _DOOR_ADJACENT_TYPES:
    # ลองวางฝั่งตรงข้ามของประตูก่อน
    opposite_side_pos = compute_opposite_side(door)
    if not overlaps(opposite_side_pos):
        return opposite_side_pos

    # Slide ตามแนวผนังทีละ 0.05m
    fine_steps = [0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5,
                  0.6, 0.7, 0.8, 1.0, 1.2, 1.5, 2.0]
    for step in fine_steps:
        # try both sides of door
```

---

## Pair Placement: `_place_beside_anchor()` (line 345–447)

วาง dependent (เช่นเก้าอี้) ข้าง anchor (โต๊ะ)

### Flow

```python
def _place_beside_anchor(dependent, anchor, gap):
    # Step 1: คำนวณ model_rotation_offset
    model_offset = catalog[dependent.id].model_rotation_offset

    # Step 2: สร้าง 4 candidate sides
    candidates = {
        "north":  (anchor.max_z + gap + d.depth/2,    0),     # เหนือ anchor
        "south":  (anchor.min_z - gap - d.depth/2,    180),   # ใต้ anchor
        "east":   (anchor.max_x + gap + d.width/2,    270),   # ตะวันออก
        "west":   (anchor.min_x - gap - d.width/2,    90),    # ตะวันตก
    }

    # Step 3: หาฝั่งหน้าของ anchor (front_side)
    front_side = anchor_front_from_rotation(anchor.rotation)
    # rotation=0 → front=north, =180 → south, =90 → east, =270 → west

    # Step 4: เรียง priority (front ก่อน, opposite สุดท้าย)
    ordered = [front_side, side_1, side_2, opposite_side]

    # Step 5: ทดลองแต่ละฝั่ง
    for side in ordered:
        x, z, desired_rotation = candidates[side]

        # Adjust rotation ด้วย model_offset
        stored_rotation = (desired_rotation - model_offset) % 360

        if in_bounds(x, z) and not overlaps(x, z):
            return PhysicalPlacement(x=x, z=z, rotation=stored_rotation)

    # Step 6: Fallback → ปกติ (ไม่ pair กับ anchor)
    return _compute_initial_position(dependent, ...)
```

### Front Priority Example

**โต๊ะหันทิศใต้** (rotation=0):
- Front face = south side of desk
- เก้าอี้ควรอยู่ทาง south ของโต๊ะ หันหน้าเข้าโต๊ะ (หัน north)
- เก้าอี้ rotation = 180°

**โต๊ะหันตะวันออก** (rotation=270):
- Front face = east side
- เก้าอี้อยู่ east, หันหน้า west (rotation = 90°)

ถ้าไม่มีที่ฝั่งหน้า → ลองฝั่งข้าง (perpendicular), สุดท้ายฝั่งหลัง (ตรงข้าม front)

---

## Dimension Encoding (Critical!)

### Storage vs Runtime

**Layout storage (ที่ส่งกลับ frontend):**
- `dimensions.width, depth, height` = natural size (ก่อนหมุน)
- `rotation` = 0/90/180/270

**Runtime footprint (ใช้ collision check):**
- สำหรับ rotation 0/180: footprint_w=natural_w, footprint_d=natural_d
- สำหรับ rotation 90/270: footprint_w=natural_d, footprint_d=natural_w (**swap!**)

### Reason

Three.js `BoxGeometry(width, height, depth)` รับ natural size + หมุนผ่าน Y-rotation. ไม่ต้อง swap ฝั่ง frontend

Backend ทำ AABB ใน room space ต้อง swap เอง

### ตัวอย่าง

เตียง natural = 1.6 × 2.0 (กว้าง × ยาว), rotation = 90:
- Footprint ในห้อง: 2.0 × 1.6 (ยาวเป็นแกน X, กว้างเป็นแกน Z)
- ส่งไป frontend: `dimensions.width=1.6, depth=2.0, rotation=90` → Three.js หมุนเอง

AABB ใช้ `AABB.from_center_and_size(x, z, footprint_w, footprint_d)` — footprint หลัง swap

ดู [09-coordinates.md](./09-coordinates.md) สำหรับรายละเอียดเพิ่ม

---

## Special Cases

### Nightstand with `along_wall_z`

ถ้า SemanticPlacement มี `along_wall_z` → ใช้ค่านั้นเป็น Z แทน alignment

```python
if semantic.along_wall_z is not None:
    z = semantic.along_wall_z
```

ใช้ตอน re-resolve ที่ anchor ขยับ — ต้องวาง nightstand ที่ตำแหน่ง Z เดิม

### Center placement

`target_wall = "center"`:
```python
x = 0
z = 0
rotation = semantic.orientation_rotation or 0
```

ใช้กับ `area_rug`, `coffee_table`, `ottoman`, `room_divider`

---

## จุดที่ควรรู้

1. **Priority มีผลกับ bump order** — ชิ้นที่ resolve ก่อน (priority=1) ได้ตำแหน่งดีกว่า ชิ้นอื่น bump หลบ
2. **`_WALL_ROTATION` vs `_FACING_ROTATION`** — อย่าสับสน; one คือ "วางที่ผนังไหน" อีกอันคือ "หันไปทิศไหน"
3. **Model offset คือที่มาของ bug หมุนผิดทิศ** — ถ้า 3D model export ผิดแนว, `model_rotation_offset` ในแคตาล็อกต้องแก้
4. **Bump-out ตัดสินใจตาม wall affinity** — เตียงชิดผนังไม่ถูก push ออก ถ้ายังเลื่อนซ้าย-ขวาได้
5. **Pair placement เคารพ front face** — เก้าอี้อยู่ด้านหน้าโต๊ะก่อนด้านข้าง
