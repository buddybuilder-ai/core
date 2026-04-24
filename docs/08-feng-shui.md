# 08 — Feng Shui Rules & Scoring

กฎฮวงจุ้ยที่ระบบตรวจ + ระบบคะแนน 100 เต็ม

## 4 หลักการหลัก

| หลักการ | Max Score | Component | ตรวจสอบอะไร |
|---|---|---|---|
| Command Position | 30 | `command_position` | เตียง/โต๊ะ/โซฟาอยู่ตำแหน่งอำนาจ |
| Five Elements Balance | 20 | `five_elements_balance` | สมดุลธาตุทั้ง 5 |
| Chi Flow | 25 | `chi_flow` | ทางเดินของพลังงานโล่ง |
| Sha Chi Avoidance | 25 | `sha_chi_avoidance` | หลบพลังลบ |
| **Total** | **100** | — | — |

## Grade Thresholds

File: [feng_shui_score.py](../src/modules/layout/domain/value_objects/feng_shui_score.py)

```python
@property
def grade(self) -> str:
    if self.total >= 90: return "A"
    if self.total >= 70: return "B"
    if self.total >= 50: return "C"
    if self.total >= 40: return "D"
    return "F"
```

Step 5 ใช้ threshold ต่างกันเล็กน้อย:
```python
GRADE_EXCELLENT = 80
GRADE_GOOD = 60
GRADE_FAIR = 40
```

---

## Rule Checker (Step 3)

File: [step3_rule_checker.py](../src/modules/layout/application/pipeline/steps/step3_rule_checker.py)

### Universal Standards (ไม่ใช่ฮวงจุ้ย แต่เช็คก่อน)

| ID | Check | Type | Severity |
|---|---|---|---|
| — | `intersects()` | `OVERLAP` | CRITICAL |
| — | `distance_to() < 0.6` | `CLEARANCE_VIOLATION` | WARNING |
| — | Centre + footprint ออกนอกห้อง | `OUT_OF_BOUNDS` | CRITICAL |
| — | วางในโซน 0.9m รอบประตู | `DOOR_BLOCKED` | CRITICAL |

### Feng Shui Rules

#### Bed Rules

**bed_001 — เตียงในแนวประตู** (line 277–286)
```python
if _is_aligned_with_door(bed, door):
    conflict(SHA_CHI_ALIGNMENT, WARNING,
             "เตียงตรงกับประตู — พลังปะทะโดยตรง")
```

`_is_aligned_with_door()`:
- เช็คว่า center_x ของเตียงอยู่ในช่วง door width หรือไม่ (สำหรับประตูเหนือ-ใต้)
- หรือ center_z อยู่ในช่วง door (สำหรับประตูตะวันออก-ตะวันตก)

**bed_002 — เตียงในแนวหน้าต่าง** (line 288–300)
- คล้าย bed_001 แต่ใช้หน้าต่าง
- `SHA_CHI_ALIGNMENT` / WARNING

**bed_003 — TV/กระจกหันเข้าเตียง** (line 322–340)
```python
for other in items:
    if other.type in {"tv", "tv_stand", "mirror"}:
        if other_facing_bed_within(fw/2 + 0.3):
            conflict(SHA_CHI_ALIGNMENT, WARNING)
```

**bed_004 — AC เหนือเตียง** (line 342–360)
- เช็ค AC อยู่ในแนว X หรือ Z เดียวกันกับเตียง
- `SHA_CHI_ALIGNMENT` / INFO

**bed_005 — เตียงลอยกลางห้อง** (line 302–320)
```python
if not any_wall_within(bed, tolerance=0.2):
    conflict(BAD_COMMAND_POSITION, WARNING,
             "เตียงไม่พิงผนัง — ขาดพลังสนับสนุน")
```

**bed_006 — ประตู-หน้าต่างตรงกัน** (line 487–499)
```python
for door in doors:
    for window in windows:
        if door.wall == _OPPOSITE[window.wall]:
            if offset_overlap(door, window):
                conflict(BLOCKED_CHI_FLOW, WARNING,
                         "พลัง chi ไหลผ่านเร็วเกินไป")
```

**bed_007 — เฟอร์นิเจอร์ใหญ่ผนังเดียวกับหัวเตียง** (line 382–433)
```python
head_wall = infer_head_wall(bed.rotation, bed.pos)
for other in items:
    if other.type in {"wardrobe", "bookshelf", "tall_cabinet"}:
        if same_wall_tokenized(other, head_wall):
            conflict(SHA_CHI_ALIGNMENT, INFO,
                     "เฟอร์นิเจอร์ใหญ่กดทับพลังหัวเตียง")
```

Token-based wall matching (line 385–390):
```python
def same_wall(item, wall):
    tokens = re.split(r"[-_\s]+", item.wall.lower())
    return wall in tokens
```

**bed_008 — ไม่มีทางเดินรอบเตียง** (line 435–456)
```python
if not any_side_has_clearance(bed, MIN_CLEARANCE):
    conflict(CLEARANCE_VIOLATION, INFO)
```

**bed_009 — โต๊ะหันเข้าหน้าต่าง** (line 472–484)
- สำหรับโต๊ะ (desk), ไม่ใช่เตียง
- `SHA_CHI_ALIGNMENT` / INFO
- "มองหน้าต่างเบลอจากเสียงรบกวน"

**bed_011 — จอภาพตรงปลายหัวเตียง** (line 362–380)
```python
head_x, head_z = compute_head_position(bed)
for screen in items_with_type({"tv_stand", "monitor", "mirror"}):
    if screen_in_head_line(screen, head_x, head_z, within=1.0):
        conflict(SHA_CHI_ALIGNMENT, WARNING)
```

#### Desk/Sofa Rules

**back_to_door** (line 577–583)
```python
def _has_back_to_door(item, doors):
    for door in doors:
        door_angle = atan2(door.z - item.z, door.x - item.x)
        back_dir = (item.rotation + 180) % 360
        back_rad = radians(back_dir)

        angle_diff = abs(normalize_angle(back_rad - door_angle))
        if angle_diff < radians(60):
            return True
    return False
```

- `conflict(BACK_TO_DOOR, WARNING)` สำหรับ desk/office_chair/sofa
- **Principle**: ไม่นั่งหันหลังให้ประตู (ไม่เห็นคนเข้ามา)

---

## Scoring Formula

File: [services/feng_shui_scorer.py](../src/modules/layout/application/services/feng_shui_scorer.py)

### 1. Command Position (0–30)

Key furniture: **bed, desk, sofa**

คะแนนต่อชิ้น:
- +10 ถ้าอยู่ diagonal จากประตู (เห็นประตูโดยไม่ถูกประตูตรง)
- +5 ถ้ามี solid wall behind
- +5 ถ้าไม่หันหลังให้ประตู

สูงสุด 30 (3 ชิ้น × 10)

### 2. Five Elements Balance (0–20)

**Element associations** (line 115–130):
```python
_ELEMENT_MAP = {
    # Wood (25% ideal)
    "bed": Element.WOOD,
    "desk": Element.WOOD,
    "bookshelf": Element.WOOD,
    "wardrobe": Element.WOOD,
    "nightstand": Element.WOOD,
    "plant": Element.WOOD,

    # Fire (15%)
    "lamp": Element.FIRE,

    # Earth (25%)
    "sofa": Element.EARTH,
    "coffee_table": Element.EARTH,
    "dining_table": Element.EARTH,
    "rug": Element.EARTH,

    # Metal (20%)
    "chair": Element.METAL,
    "tv_stand": Element.METAL,

    # Water (15%)
    "mirror": Element.WATER,
}
```

**Ideal balance** (line 133–139):
```python
_IDEAL_BALANCE = {
    Element.WOOD: 0.25,
    Element.FIRE: 0.15,
    Element.EARTH: 0.25,
    Element.METAL: 0.20,
    Element.WATER: 0.15,
}
```

**Scoring**:
```python
actual_counts = count_by_element(items)
total = sum(actual_counts.values())
deviations = [abs(actual[e]/total - ideal[e]) for e in elements]
avg_deviation = mean(deviations)
score = 20 * (1 - avg_deviation)  # 0 deviation = 20, high deviation = 0
```

### 3. Chi Flow (0–25)

เช็ค:
- **Walkway clearance**: ≥60cm gaps ระหว่างเฟอร์นิเจอร์ → +points
- **Door unblocked**: ไม่มีของในโซนประตู → +points
- **Window unblocked**: ไม่มีของสูงบังหน้าต่าง → +points
- **Curved arrangement**: (concept — ปัจจุบัน approximate ด้วย non-linear arrangement)

### 4. Sha Chi Avoidance (0–25)

เช็คและหักคะแนน:
- -5 ต่อ SHA_CHI_ALIGNMENT conflict
- -10 ต่อ BACK_TO_DOOR สำหรับ desk/sofa
- -5 ต่อ BLOCKED_CHI_FLOW

Base: 25, minimum: 0

---

## RAG Enrichment (Step 3.4)

หลังตรวจ conflict ระบบ map `ConflictType` → `rule_id` → ดึงคำอธิบายจาก RAG:

```python
_CONFLICT_TO_RULE = {
    ConflictType.BAD_COMMAND_POSITION: "cmd_001",
    ConflictType.ELEMENT_IMBALANCE: "elem_001",
    ConflictType.SHA_CHI_ALIGNMENT: "sha_001",
    ConflictType.BACK_TO_DOOR: "cmd_002",
    ConflictType.BLOCKED_CHI_FLOW: "chi_001",
}

for conflict in state.conflicts:
    rule_id = _CONFLICT_TO_RULE.get(conflict.conflict_type)
    if rule_id and rag_context["rule_descriptions"].get(rule_id):
        conflict.suggestion += "\n" + rag_context["rule_descriptions"][rule_id]
```

ผลลัพธ์: conflict.suggestion มีทั้งคำเตือนเบื้องต้น + คำอธิบายลึก (จาก RAG vector store)

---

## Kua (เลขกัว)

File: [tools/kua_calculator.py](../src/modules/layout/infrastructure/tools/kua_calculator.py)

### Calculate Kua

```python
def calculate_kua(birth_year: int, gender: str) -> int:
    # ตัดเลขปี → digit root
    year_sum = sum(digits(birth_year))
    digit_root = reduce_to_single_digit(year_sum)

    if gender == "male":
        kua = (10 - digit_root) % 9
    else:  # female
        kua = (digit_root + 5) % 9

    return kua if kua != 0 else 9  # no 0 in Kua (replaced with 9)
    # Special: no 5 — map to 2 (male) or 8 (female)
```

**Range**: 1, 2, 3, 4, 6, 7, 8, 9 (ไม่มี 5)

### Best Direction Info

```python
def kua_best_direction_info(kua: int) -> dict:
    """Returns {'wall_th': '...', 'benefit': '...'}"""
    _KUA_TABLE = {
        1: {"wall_th": "ตะวันออกเฉียงใต้", "benefit": "สุขภาพ"},
        2: {"wall_th": "ตะวันออกเฉียงเหนือ", "benefit": "ความรัก"},
        # ...
    }
    return _KUA_TABLE[kua]
```

### Auspicious / Inauspicious Walls

```python
def kua_auspicious_walls(kua: int) -> list[str]:
    # Returns ["north", "east", ...] (4 walls)

def kua_inauspicious_walls(kua: int) -> list[str]:
    # Returns ["south", "west", ...] (4 walls — ห้าม)
```

### Priority Detection

```python
def detect_kua_priority(user_message: str) -> str | None:
    lower = user_message.lower()
    if any(kw in lower for kw in ["สุขภาพ", "health"]):
        return "health"
    if any(kw in lower for kw in ["เงิน", "wealth", "รวย"]):
        return "wealth"
    # ...
```

Used by `WallAssigner` to pick specific auspicious wall

---

## Furniture Relationships

File: [services/furniture_relationships.py](../src/modules/layout/application/services/furniture_relationships.py)

### `build_relationship_hints(furniture_list)`

Auto-detect pairs และสร้าง hints:

```python
_RELATIONSHIPS = [
    ("tv_stand", "sofa", "TV should face sofa across the room"),
    ("tv_stand", "bed", "TV should face bed (bedroom)"),
    ("nightstand", "bed", "Nightstand beside bed — ideally 2 flanking"),
    ("coffee_table", "sofa", "Coffee table in front of sofa"),
    ("chair", "desk", "Chair positioned at desk's front face"),
    ("office_chair", "desk", "Office chair at desk front"),
    ("dining_chair", "dining_table", "Dining chairs around table"),
]

def build_relationship_hints(furniture_list):
    hints = []
    types = {f["id"].split("_")[0] for f in furniture_list}
    for type_a, type_b, hint in _RELATIONSHIPS:
        if type_a in types and type_b in types:
            hints.append(hint)
    return hints
```

### Alignment Rules

From [CLAUDE.md](../../.claude/CLAUDE.md):

> Sofa/bed should use `alignment="center"` — avoid `alignment="right"` for large items (causes corner crowding)

LLM prompt (LAYOUT_PLANNING_PROMPT) มี section นี้เพื่อ guide LLM

---

## จุดที่ควรรู้

1. **Severity แบ่งเป็น 3 ระดับ** — CRITICAL (ต้องแก้), WARNING (ควรแก้), INFO (น่าจะแก้)
2. **Repair step แก้เฉพาะ CRITICAL/WARNING** — INFO ปล่อยผ่าน
3. **Scoring ใช้ deterministic formula** — ไม่ใช้ LLM ในการตัดสินคะแนน
4. **RAG เอาแค่เสริม suggestion** — ไม่เปลี่ยน rule logic
5. **Kua เป็น optional** — ไม่มี birth_year ก็ใช้ default command position ได้
6. **Element count ใช้ furniture type** — ถ้ามี bed + desk + nightstand = Wood 3 ชิ้น, ยังขาด Fire/Water
7. **back_to_door threshold = 60°** — แคบกว่านี้ (< 60°) ถือว่าหันหลังให้ประตู
