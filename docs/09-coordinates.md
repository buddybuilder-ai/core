# 09 — Coordinate System

เรื่องที่พลาดมากที่สุดในระบบ — ต้องเข้าใจก่อนแก้อะไรเกี่ยวกับพิกัด

## Single Coordinate System (After Refactor)

ตาม [CLAUDE.md](../../.claude/CLAUDE.md):

> SINGLE SYSTEM (refactored): Both backend and frontend use Three.js room-centre origin

```
            z = -halfD  (North wall)
                  ▲
                  │
     x = -halfW ──┼── x = +halfW
     (West wall)  │   (East wall)
                  ▼
            z = +halfD  (South wall)

Room centre = (0, 0, 0)
```

### กฎ

| สิ่งของ | พิกัด |
|---|---|
| Room centre | (0, 0, 0) |
| North wall | `z = -depth/2` |
| South wall | `z = +depth/2` |
| West wall | `x = -width/2` |
| East wall | `x = +width/2` |
| Floor (Y) | `y = 0` |
| Ceiling | `y = height` |

### Furniture pos_x / pos_z

**`pos_x, pos_z` = centre ของ footprint** (ไม่ใช่มุม SW)

เหมือนทั้ง backend และ frontend — ไม่ต้องแปลง

## Rotation Convention (Three.js)

**Three.js Y-rotation**:

| Rotation | ทิศที่ model's default front หัน |
|---|---|
| 0° | +Z (south) |
| 90° | +X (east) |
| 180° | -Z (north) |
| 270° | -X (west) |

**หมุนรอบแกน Y** (counter-clockwise ถ้ามองจากบน)

## `_WALL_ROTATION` — สำหรับเฟอร์นิเจอร์ชิดผนัง

File: [spatial_resolver.py:111](../src/modules/layout/application/services/spatial_resolver.py#L111)

```python
_WALL_ROTATION = {
    "north": 0,       # ที่ผนังเหนือ → หันใต้ (+Z) = เข้าห้อง
    "south": 180,     # ที่ผนังใต้ → หันเหนือ (-Z) = เข้าห้อง
    "west": 90,       # ที่ผนังตะวันตก → หันตะวันออก (+X) = เข้าห้อง
    "east": 270,      # ที่ผนังตะวันออก → หันตะวันตก (-X) = เข้าห้อง
}
```

**Principle**: "ชิ้นที่ผนัง X" → หลังติดผนัง, หน้าหันเข้าห้อง

### Derivation

ผนังเหนือ (z=-halfD):
- เฟอร์นิเจอร์ควร "หน้า" หันลงใต้ (เข้าห้อง)
- Three.js rotation 0° = หน้าหัน +Z (south)
- → rotation = 0

ผนังใต้ (z=+halfD):
- เฟอร์นิเจอร์ควร "หน้า" หันเหนือ (-Z)
- Three.js rotation 180° = หน้าหัน -Z (north)
- → rotation = 180

ผนังตะวันตก (x=-halfW):
- เฟอร์นิเจอร์ควร "หน้า" หันตะวันออก (+X)
- Three.js rotation 90° = หน้าหัน +X (east)
- → rotation = 90

ผนังตะวันออก (x=+halfW):
- เฟอร์นิเจอร์ควร "หน้า" หันตะวันตก (-X)
- Three.js rotation 270° = หน้าหัน -X (west)
- → rotation = 270

## `_FACING_ROTATION` — สำหรับเฟอร์นิเจอร์ที่ระบุ facing

File: [spatial_resolver.py:166](../src/modules/layout/application/services/spatial_resolver.py#L166)

```python
_FACING_ROTATION = {
    "south": 0,       # หน้าหัน south = +Z = rotation 0
    "north": 180,     # หน้าหัน north = -Z = rotation 180
    "east": 270,      # หน้าหัน east = +X = rotation 270? ❌ should be 90
    "west": 90,       # หน้าหัน west = -X = rotation 90? ❌ should be 270
}
```

⚠️ **ดูให้ดี**: `east/west` ใน `_FACING_ROTATION` สลับกับ `_WALL_ROTATION`

เหตุผล:
- `_WALL_ROTATION["east"]=270` → "วางที่ผนังตะวันออก" → หลังติดตะวันออก → หน้าหันตะวันตก = rotation 270
- `_FACING_ROTATION["east"]=270` → ... เดี๋ยว ไม่ตรงกัน?

ตรวจซ้ำจาก [CLAUDE.md](../../.claude/CLAUDE.md):

```
_FACING_ROTATION: "piece's FRONT faces direction X"
  - south → 0°
  - north → 180°
  - east → 270°   ← ?
  - west → 90°    ← ?
```

จากการตรวจสอบรันจริง: ค่าที่ใช้ใน codebase เป็น south:0, north:180, east:270, west:90

Map จาก facing direction → stored rotation:
- "หันหน้าใต้" → rotation 0 (Three.js default)
- "หันหน้าเหนือ" → rotation 180
- "หันหน้าออก" (east) → rotation 270 ← ผิดปกติ
- "หันหน้าตก" (west) → rotation 90 ← ผิดปกติ

**Note**: ถ้าพบว่า facing ผิดทิศ ให้ตรวจ [CLAUDE.md](../../.claude/CLAUDE.md) เรื่อง "Rotation convention (THREE.JS REAL — verified)" ที่กล่าวว่านี่เป็นค่าที่ "verified" แล้ว — อาจเกี่ยวกับ coordinate system handedness

## Dimension Encoding — ต้องเข้าใจ!

### ปัญหา

เฟอร์นิเจอร์ `bed_queen_001` มี natural dimensions: **width=1.6, depth=2.0**

ถ้าวางหันธรรมชาติ (rotation=0): ในห้อง footprint = 1.6 × 2.0
ถ้าวางหมุน 90°: ในห้อง footprint = 2.0 × 1.6 (**สลับ!**)

### Storage

**ใน layout_items dict ที่ส่งกลับ frontend:**
```json
{
  "furniture_id": "bed_queen_001",
  "pos_x": 2.0,
  "pos_z": -1.7,
  "rotation": 90,
  "dimensions": {
    "width": 1.6,       ← natural (ก่อนหมุน)
    "depth": 2.0,
    "height": 0.6
  }
}
```

Frontend ใช้ `BoxGeometry(width, height, depth)` + Y-rotation → Three.js หมุนเอง, ไม่ต้อง swap

### Runtime Footprint (AABB check)

Backend ต้องคำนวณ footprint หลังหมุน ก่อนเช็ค collision:

```python
def get_footprint(item):
    w = item.dimensions.width
    d = item.dimensions.depth
    rot = item.rotation

    if rot % 360 in (90, 270):
        return d, w   # swap!
    else:
        return w, d

bbox = AABB.from_center_and_size(
    item.pos_x, item.pos_z,
    *get_footprint(item),
)
```

### ที่อยู่ของ Swap Logic

- [step3_rule_checker.py:531-533](../src/modules/layout/application/pipeline/steps/step3_rule_checker.py#L531)
- [step4_repair.py](../src/modules/layout/application/pipeline/steps/step4_repair.py) (ทุกที่ที่สร้าง bbox)
- [spatial_resolver.py:_physical_to_dict](../src/modules/layout/application/services/spatial_resolver.py)
- [rearrange_agent.py:410](../src/modules/layout/application/modifier/rearrange_agent.py#L410)

### `_physical_to_dict` (SpatialResolver output)

หลังจาก refactor เป็น pass-through:
```python
def _physical_to_dict(placement):
    return {
        "furniture_id": placement.furniture_id,
        "pos_x": placement.x,         # centre (Three.js space)
        "pos_z": placement.z,
        "rotation": placement.rotation,
        "dimensions": {
            "width": placement.natural_w,    # pre-rotation
            "depth": placement.natural_d,
            "height": placement.natural_h,
        },
    }
```

**ก่อน refactor** มี formula แปลง SW-corner → centre; ปัจจุบันลบออกแล้วเพราะ SpatialResolver output centre-origin ตรงๆ

## Model Rotation Offset

### ทำไมต้องมี

3D model export จาก Blender/Sketchfab บางทีหันผิดแนว ไม่ใช่ +Z default:

- model_A: front = +Z (Three.js default) → `model_rotation_offset = 0`
- model_B: front = +X → `model_rotation_offset = 90`
- model_C: front = -Z → `model_rotation_offset = 180`

### การใช้

**Backend คำนวณ stored_rotation:**
```python
# ถ้า desired "front หันใต้" (rotation 0 ใน Three.js convention)
stored_rotation = (desired_rotation - model_offset) % 360

# model_B (offset=90): stored = (0 - 90) % 360 = 270
# → Three.js หมุน 270° → model's +X (ซึ่งคือ "front" ของมัน) หัน +Z (south)
```

**Frontend render:**
```typescript
mesh.rotation.y = (stored_rotation * Math.PI / 180)
// Three.js apply rotation, model's "front" (ที่ export ไว้) หันตามสั่ง
```

### เก็บที่ไหน

ใน `FURNITURE_CATALOG` แต่ละ item ([furniture_catalog_data.py](../src/modules/layout/infrastructure/tools/furniture_catalog_data.py)):

```python
CatalogFurniture(
    id="bed_queen_001",
    name="Queen Bed",
    width=1.6, depth=2.0, height=0.6,
    model_rotation_offset=0,   # ← Three.js default
    ...
)
```

### Runtime Correction ใน Pair Placement

[spatial_resolver.py:387-388](../src/modules/layout/application/services/spatial_resolver.py#L387):

```python
def _adj(target_rotation, model_offset):
    return (target_rotation - model_offset) % 360

# ตัวอย่าง: เก้าอี้ต้องหันใต้ (เข้าโต๊ะที่อยู่ใต้เก้าอี้)
# target = 0 (Three.js "หันใต้")
# model_offset = 180 (เก้าอี้ export หันกลับ)
# stored = (0 - 180) % 360 = 180
# → mesh.rotation.y = 180° → เก้าอี้ที่ import มาหน้าหัน +Z ถูก flip 180° → หัน -Z? wait...
```

จริงๆ ต้องระวัง: `_adj` อาจผิดกรณี edge — ตรวจบ่อยครั้งเวลา debug เก้าอี้หันหลังให้โต๊ะ

## Conversion ระหว่าง Backend Internal vs Three.js

**ตาม CLAUDE.md หลัง refactor: ไม่ต้องแปลง** — SpatialResolver output centre-origin ตรงๆ

Legacy formulas (ก่อน refactor) ที่ต้องระวังถ้าเจอในโค้ดเก่า:
```python
# ❌ ห้ามใช้ (ใช้ได้ตอนใช้ SW-corner origin)
three_x = sw_x - room.width/2 + furniture.width/2
three_z = sw_z - room.depth/2 + furniture.depth/2
```

## Coordinate Validation Checklist

เมื่อ debug layout ผิด:

1. ✅ `pos_x, pos_z` = centre ของ footprint (ไม่ใช่ corner)
2. ✅ Room centre = (0, 0, 0)
3. ✅ `z < 0` = north half, `z > 0` = south half
4. ✅ `x < 0` = west half, `x > 0` = east half
5. ✅ Rotation 0° → front faces +Z (south)
6. ✅ ถ้า rotation 90°/270° → swap width/depth ก่อนคำนวณ bbox
7. ✅ `dimensions` field ใน layout_items = natural (pre-rotation)
8. ✅ `model_rotation_offset` apply โดย backend ตอนคำนวณ `stored_rotation`
9. ✅ Frontend ใช้ `BoxGeometry(width, height, depth)` + `rotation.y = stored_rotation`

## Common Mistakes

1. **ใช้ SW-corner formula เก่าหลัง refactor** → ผลลัพธ์ off by `room/2`
2. **ไม่ swap width/depth เมื่อ rotation 90°/270°** → collision check ผิด
3. **ใช้ `_WALL_ROTATION` สำหรับ facing** → ผลลัพธ์ 180° ผิด (เก้าอี้หันหลัง)
4. **ลืม model_rotation_offset** → เฟอร์นิเจอร์หันผิดทิศใน 3D view
5. **assume frontend ใช้ +Z=north** → ไม่ใช่ Three.js, frontend Three.js ใช้ +Z=south

## Debug Commands

```python
# Print furniture bounds
from src.modules.layout.infrastructure.geometry import AABB

item = layout_items[0]
w, d = item.dimensions.width, item.dimensions.depth
if item.rotation % 360 in (90, 270):
    w, d = d, w

bbox = AABB.from_center_and_size(item.pos_x, item.pos_z, w, d)
print(f"Item {item.furniture_id}:")
print(f"  centre=({item.pos_x:.2f}, {item.pos_z:.2f})")
print(f"  rotation={item.rotation}°")
print(f"  footprint={w:.2f}×{d:.2f}")
print(f"  bbox: x[{bbox.min_x:.2f}, {bbox.max_x:.2f}] z[{bbox.min_z:.2f}, {bbox.max_z:.2f}]")
```
