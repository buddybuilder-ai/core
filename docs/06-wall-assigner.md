# 06 — Wall Assigner

Deterministic wall assignment — แทนที่ LLM reasoning เรื่อง "ชิ้นไหนผนังไหน" ด้วยโค้ดกฎตายตัว

File: [wall_assigner.py](../src/modules/layout/application/services/wall_assigner.py)

## ทำไมต้องมี

LLM พลาดเรื่อง spatial reasoning บ่อย:
- วางเตียงผนังประตู (อันตรายทางฮวงจุ้ย)
- วางตู้ผนังเดียวกับเตียง (ปิดทาง chi)
- วางโซฟากับ TV บนผนังเดียวกัน (ไม่ได้ดู)

WallAssigner ตัดปัญหานี้ด้วยกฎ priority-based หลัง LLM output

## Furniture Type Sets (line 30–67)

```python
_REAL_BED_TYPES = {"bed", "bed_single", "bed_queen", "bed_king", ...}
_SOFA_BED_TYPES = {"sofa_bed", "sofabed"}
_BED_LIKE_TYPES = _REAL_BED_TYPES | _SOFA_BED_TYPES

_SOFA_TYPES = {"sofa", "couch", "sectional"}
_DESK_TYPES = {"desk", "folding_desk", "writing_desk", "office_desk"}
_WARDROBE_TYPES = {"wardrobe", "closet", "compact_wardrobe"}
_SHELF_TYPES = {"bookshelf", "shelf", "bookcase"}
_STORAGE_TYPES = {"dresser", "chest", "cabinet", "storage"}

_CENTER_TYPES = {"area_rug", "coffee_table", "ottoman", "room_divider"}
_DOOR_ADJACENT_TYPES = {"shoe_cabinet", "coat_rack"}
_TV_TYPES = {"tv_stand", "tv"}
_SMALL_TYPES = {"nightstand", "side_table", "plant"}
_DINING_CHAIR_TYPES = {"dining_chair"}
```

## Compound Type Detection (line 52–67)

สำหรับ furniture ที่มี type รวม เช่น "sofa_bed":

```python
def _detect_compound_type(type_str: str) -> str:
    tokens = set(re.split(r"[-_\s]+", type_str.lower()))
    if "sofa" in tokens and "bed" in tokens:
        return "sofa_bed"
    if "compact" in tokens and "wardrobe" in tokens:
        return "compact_wardrobe"
    # ...
    return type_str
```

---

## Main Method: `assign()`

```python
def assign(
    self,
    placements: list[dict],
    room_spec: dict,
) -> list[dict]:
```

### Input
- LLM output (ที่ถูก override ขนาดแล้ว)
- room_spec (doors, windows, user_preferences → อาจมี Kua info)

### Output
- `placements` ที่มี `target_wall` + `alignment` ถูกต้อง

### Flow

```
1. Extract door_wall (primary door)
2. command_wall = _OPPOSITE[door_wall]
3. If user provides birth_year + gender → compute Kua walls
4. For each placement, assign wall ตามลำดับ priority (ข้อ 5 ด้านล่าง)
5. Track walls_used เพื่อกระจายเฟอร์นิเจอร์ (ไม่กระจุก)
```

## Assignment Priority (line 100–115)

ลำดับสำคัญ! ชิ้น priority สูงจะได้ผนังดีก่อน:

### 1. Bed → command position

```python
if type in _REAL_BED_TYPES:
    if user has kua:
        target_wall = kua_auspicious_walls[0] or command_wall
    else:
        target_wall = command_wall  # ตรงข้ามประตู

    # Hard constraint: ห้ามผนังประตู
    if target_wall == door_wall:
        target_wall = command_wall
```

### 2. Nightstand → ผนังเดียวกับเตียง

```python
if type == "nightstand":
    target_wall = bed.target_wall  # ผนังเดียวกันเพื่อความสมดุล
```

### 3. Sofa-bed → command หรือ side wall

```python
if type in _SOFA_BED_TYPES:
    if bed_also_placed:
        target_wall = side_wall_opposite_bed
    else:
        target_wall = command_wall  # ใช้เป็น primary sleep zone
```

### 4. Sofa → side wall ตรงข้ามเตียง

```python
if type in _SOFA_TYPES:
    bed_wall = bed.target_wall
    side_walls = _get_side_walls(bed_wall)
    target_wall = side_walls[0] if side_walls[0] not in walls_used else side_walls[1]
```

### 5. Desk → side wall หันประตู

```python
if type in _DESK_TYPES:
    # Position: facing door (เห็นคนเข้าออก)
    # Wall: side wall (ไม่ใช่ door wall, ไม่ใช่ bed wall)
    available = {"north", "south", "east", "west"} - {door_wall, bed_wall}
    target_wall = first_available(available)
    facing = door_wall  # หันไปทางประตู
```

### 6. TV stand → ตรงข้ามโซฟา/เตียง

```python
if type in _TV_TYPES:
    viewing_source = sofa or bed
    target_wall = _OPPOSITE[viewing_source.target_wall]
    # ตรวจสอบให้ TV หันเข้าที่นั่ง
```

### 7. Wardrobe → ผนังเหลือ

```python
if type in _WARDROBE_TYPES:
    # ไม่ใช่ bed wall (ปิด chi)
    # ไม่ใช่ door wall (ขวางทาง)
    available = {N, S, E, W} - {bed_wall, door_wall}
    target_wall = first_available(available)
```

### 8. Bookshelf → ผนังเหลือ

```python
# ตรรกะคล้ายกัน, หลีกเลี่ยง bed/door wall
```

### 9. Center items → "center"

```python
if type in _CENTER_TYPES:
    target_wall = "center"
```

### 10. Door-adjacent → ผนังประตู (มุม)

```python
if type in _DOOR_ADJACENT_TYPES:
    target_wall = door_wall
    alignment = "left" or "right"  # มุมใกล้ประตู
```

### 11. Default → ผนังว่างที่เหลือ

```python
# เรียงลำดับโดยดู walls_used count
target_wall = least_used_wall()
```

---

## Kua Integration (line 157–180)

### Kua Calculator

File: [tools/kua_calculator.py](../src/modules/layout/infrastructure/tools/kua_calculator.py)

```python
kua = calculate_kua(birth_year: int, gender: str) → int  # 1–9 (ไม่มี 5)

kua_auspicious_walls(kua: int) → list[str]
# ถูกต้อง 4 ทิศจาก 8 (ตาม Ba-Zi Feng Shui)

kua_inauspicious_walls(kua: int) → list[str]
# ต้องเลี่ยง 4 ทิศ
```

### Priority Direction Detection

```python
from kua_calculator import detect_kua_priority
priority = detect_kua_priority(user_message)
# returns: "primary" | "health" | "wealth" | "relationships" | None
```

Keyword matching:
- "เสริมสุขภาพ", "health" → health
- "เสริมเงินทอง", "wealth" → wealth
- "เสริมความรัก", "relationship" → relationships

### การใช้ใน WallAssigner

```python
if birth_year and gender:
    kua = calculate_kua(int(birth_year), gender)
    priority_dir = detect_kua_priority(user_message) or "primary"

    ausp = kua_auspicious_walls(kua)
    inausp = kua_inauspicious_walls(kua)

    # เตียง/โซนนอน → ใช้ ausp อันดับ 1
    # Hard constraint: ไม่วางบน inausp (ยกเว้นไม่มีทางเลือก)
```

**Hard constraint**: ห้าม bed บน door_wall เด็ดขาด (แม้ Kua จะบอกก็ตาม)

---

## Helper Functions

### `_get_side_walls(primary_wall)` (line 93)

```python
_SIDE_WALLS = {
    "north": ["west", "east"],    # ผนัง perpendicular
    "south": ["west", "east"],
    "east":  ["north", "south"],
    "west":  ["north", "south"],
}
```

### `_opposite_wall(wall)` (line 78)

```python
_OPPOSITE = {
    "north": "south", "south": "north",
    "east": "west", "west": "east",
}
```

### `_is_wall_available(wall, type)` (line 120)

เช็คว่าผนังว่างพอวางเฟอร์นิเจอร์ชนิดนี้ไหม (ตรวจ width + other constraints)

---

## Example: Studio Apartment

Input (จาก LLM):
```json
[
  {"furniture_id": "sofa_bed_001", "target_wall": "east", ...},
  {"furniture_id": "compact_wardrobe_001", "target_wall": "east", ...},
  {"furniture_id": "folding_desk_001", "target_wall": "north", ...},
  {"furniture_id": "shoe_cabinet_001", "target_wall": "center", ...},
]
```

Room: ประตูใต้, ไม่มี Kua

After WallAssigner:
```json
[
  {"furniture_id": "sofa_bed_001", "target_wall": "north", ...},  // command (opp of south door)
  {"furniture_id": "compact_wardrobe_001", "target_wall": "east", ...},  // side, ไม่ใช่ north (sofa_bed)
  {"furniture_id": "folding_desk_001", "target_wall": "west", ...},  // side opposite wardrobe
  {"furniture_id": "shoe_cabinet_001", "target_wall": "south", ...}  // door wall (corner)
]
```

## จุดที่ควรรู้

1. **LLM ยังต้องให้ข้อมูล** — WallAssigner เป็น **post-processor** ไม่ใช่แทน LLM ทั้งหมด
2. **Priority order mattter** — ถ้าสลับ bed กับ sofa, ผลลัพธ์ผิด
3. **User-facing Kua input** — ต้องมี `birth_year` + `gender` ใน `user_preferences` ถึงจะใช้ได้
4. **Alignment อาจถูก override** — WallAssigner อาจไม่แตะ alignment, แต่ RearrangeAgent pack เป็น left/center/right เมื่อ force ทุกชิ้นผนังเดียว
5. **ตอน Modifier ไม่เรียก WallAssigner** — เพราะ modify แค่ชิ้นเดียว, ใช้ semantic จาก LLM ตรงๆ
