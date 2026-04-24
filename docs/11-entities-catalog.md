# 11 — Data Entities & Catalog

Domain entities + furniture catalog + clarification questions

## Domain Entities

Directory: [core/src/modules/layout/domain/](../src/modules/layout/domain/)

### Room

File: [entities/room.py](../src/modules/layout/domain/entities/room.py)

#### RoomType (enum, line 15)

```python
class RoomType(Enum):
    BEDROOM = "bedroom"
    LIVING_ROOM = "living_room"
    OFFICE = "office"
    DINING_ROOM = "dining_room"
    KITCHEN = "kitchen"
    BATHROOM = "bathroom"
    STUDIO_APARTMENT = "studio_apartment"
```

Property: `essential_furniture()` (line 27)
```python
@property
def essential_furniture(self) -> list[str]:
    return {
        RoomType.BEDROOM: ["bed", "nightstand", "wardrobe"],
        RoomType.LIVING_ROOM: ["sofa", "coffee_table", "tv_stand"],
        RoomType.STUDIO_APARTMENT: ["sofa_bed", "compact_wardrobe", "folding_desk"],
        # ...
    }[self]
```

#### WallSide (enum, line 41)

```python
class WallSide(Enum):
    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"

    @property
    def opposite(self) -> WallSide:
        return {
            NORTH: SOUTH, SOUTH: NORTH,
            EAST: WEST, WEST: EAST,
        }[self]

    @property
    def is_horizontal(self) -> bool:
        return self in {NORTH, SOUTH}
```

#### DoorPosition (dataclass, line 67)

```python
@dataclass
class DoorPosition:
    wall: WallSide
    offset: float          # meters from corner (along wall)
    width: float = 0.9
    swing_inward: bool = True

    def get_swing_area(self) -> AABB:
        """Approximate door swing as 90° arc rectangle"""
        # 1.0m × 1.0m at door center
```

**Offset**: ระยะจากมุม — ทิศตามกฎ WallSide:
- North/South wall: offset นับจาก **west corner → east**
- East/West wall: offset นับจาก **south corner → north**

#### WindowPosition (dataclass, line 147)

```python
@dataclass
class WindowPosition:
    wall: WallSide
    offset: float
    width: float
    height: float = 1.2
    sill_height: float = 0.9   # จากพื้น
```

#### Room (dataclass)

```python
@dataclass
class Room:
    width: float              # x-axis extent
    depth: float              # z-axis extent
    height: float = 2.7

    room_type: RoomType
    doors: list[DoorPosition]
    windows: list[WindowPosition]

    # Derived properties
    @property
    def area(self) -> float:
        return self.width * self.depth

    @property
    def usable_area(self) -> float:
        return self.area * 0.7    # 30% for walkways
```

---

### PhysicalPlacement

File: [entities/placement.py](../src/modules/layout/domain/entities/placement.py)

```python
@dataclass
class PhysicalPlacement:
    furniture_id: str
    x: float           # centre X
    y: float = 0.0     # floor
    z: float           # centre Z
    rotation: int      # 0 | 90 | 180 | 270
    dimensions: Dimensions
    bbox: AABB         # computed footprint
```

### Dimensions (value object)

```python
@dataclass(frozen=True)
class Dimensions:
    width: float      # natural (pre-rotation)
    depth: float
    height: float
```

---

### FengShuiScore

File: [value_objects/feng_shui_score.py](../src/modules/layout/domain/value_objects/feng_shui_score.py)

```python
@dataclass(frozen=True)
class FengShuiScore:
    command_position: int      # 0–30
    five_elements: int         # 0–20
    chi_flow: int              # 0–25
    sha_chi_avoidance: int     # 0–25

    @property
    def total(self) -> int:
        return self.command_position + self.five_elements + self.chi_flow + self.sha_chi_avoidance

    @property
    def percentage(self) -> float:
        return self.total       # max is 100 already

    @property
    def grade(self) -> str:
        if self.total >= 90: return "A"
        if self.total >= 70: return "B"
        if self.total >= 50: return "C"
        if self.total >= 40: return "D"
        return "F"

    @property
    def is_acceptable(self) -> bool:
        return self.total >= 40

    @property
    def is_good(self) -> bool:
        return self.total >= 70

    @property
    def is_excellent(self) -> bool:
        return self.total >= 90
```

### Coordinates

File: [value_objects/coordinates.py](../src/modules/layout/domain/value_objects/coordinates.py)

```python
@dataclass(frozen=True)
class Position3D:
    x: float
    y: float
    z: float

@dataclass(frozen=True)
class BoundingBox:
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float
```

---

## Furniture Catalog

File: [infrastructure/tools/furniture_catalog_data.py](../src/modules/layout/infrastructure/tools/furniture_catalog_data.py)

### CatalogFurniture

```python
@dataclass(frozen=True)
class CatalogFurniture:
    id: str                              # unique
    name: str                            # display
    category: FurnitureCategory          # enum
    width: float                         # metres (natural)
    depth: float
    height: float
    budget_level: BudgetLevel            # low | medium | high
    room_types: tuple[RoomType, ...]     # which rooms this fits
    clearance_front: float               # 0.6 typically
    clearance_sides: float               # 0.3 typically
    is_essential: bool                   # must-have for room type
    feng_shui_element: str               # "wood" | "fire" | "earth" | "metal" | "water"
    placement_notes: str
    model_rotation_offset: int = 0       # degrees (for Three.js mismatch)
    model_url: str = ""                  # glTF URL for Three.js
```

### FurnitureCategory (enum)

```python
class FurnitureCategory(Enum):
    BED = "bed"
    SOFA = "sofa"
    SOFA_BED = "sofa_bed"
    CHAIR = "chair"
    OFFICE_CHAIR = "office_chair"
    DINING_CHAIR = "dining_chair"
    DESK = "desk"
    FOLDING_DESK = "folding_desk"
    DINING_TABLE = "dining_table"
    COFFEE_TABLE = "coffee_table"
    WARDROBE = "wardrobe"
    BOOKSHELF = "bookshelf"
    DRESSER = "dresser"
    NIGHTSTAND = "nightstand"
    TV_STAND = "tv_stand"
    RUG = "rug"
    AREA_RUG = "area_rug"
    LAMP = "lamp"
    PLANT = "plant"
    MIRROR = "mirror"
    SHOE_CABINET = "shoe_cabinet"
    COAT_RACK = "coat_rack"
    ROOM_DIVIDER = "room_divider"
    OTTOMAN = "ottoman"
```

### BudgetLevel (enum)

```python
class BudgetLevel(Enum):
    LOW = "low"        # ประหยัด
    MEDIUM = "medium"  # ปานกลาง
    HIGH = "high"      # สูง
```

### Example Items

#### Bedroom

```python
bed_single_001 = CatalogFurniture(
    id="bed_single_001", name="เตียงเดี่ยว",
    category=FurnitureCategory.BED,
    width=1.0, depth=2.0, height=0.6,
    budget_level=BudgetLevel.LOW,
    room_types=(RoomType.BEDROOM, RoomType.STUDIO_APARTMENT),
    clearance_front=0.6, clearance_sides=0.3,
    is_essential=True,
    feng_shui_element="wood",
    placement_notes="headboard against solid wall, not under window",
    model_rotation_offset=0,
    model_url="/models/bed_single.glb",
)

bed_queen_001 = CatalogFurniture(
    id="bed_queen_001", ...
    width=1.6, depth=2.0, height=0.6,
    ...
)

bed_king_001 = CatalogFurniture(
    id="bed_king_001", ...
    width=1.8, depth=2.0, height=0.6,
    ...
)
```

#### Studio Apartment

```python
sofa_bed_001 = CatalogFurniture(
    id="sofa_bed_001", name="โซฟาเตียง",
    category=FurnitureCategory.SOFA_BED,
    width=2.0, depth=0.9, height=0.8,
    room_types=(RoomType.STUDIO_APARTMENT,),
    is_essential=True,
)

folding_desk_001 = CatalogFurniture(
    id="folding_desk_001", name="โต๊ะพับ",
    category=FurnitureCategory.FOLDING_DESK,
    width=1.0, depth=0.5, height=0.75,
    ...
)

compact_wardrobe_001 = CatalogFurniture(
    id="compact_wardrobe_001", name="ตู้เสื้อผ้าคอมแพค",
    width=0.8, depth=0.6, height=2.0,
    ...
)
```

### FURNITURE_CATALOG dict

```python
FURNITURE_CATALOG: dict[str, CatalogFurniture] = {
    "bed_single_001": bed_single_001,
    "bed_queen_001": bed_queen_001,
    # ... ประมาณ 40-50 items
}
```

Access:
```python
from src.modules.layout.infrastructure.tools.furniture_catalog_data import FURNITURE_CATALOG

item = FURNITURE_CATALOG["bed_queen_001"]
print(item.width, item.height, item.model_rotation_offset)
```

---

## Clarification Questions

File: [tools/user_clarifier_tool.py](../src/modules/layout/infrastructure/tools/user_clarifier_tool.py)

### QuestionType (enum)

```python
class QuestionType(Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    YES_NO = "yes_no"
    OPEN_ENDED = "open_ended"
    NUMERIC = "numeric"
```

### QuestionPriority (enum)

```python
class QuestionPriority(Enum):
    REQUIRED = "required"         # ต้องตอบ (block pipeline)
    RECOMMENDED = "recommended"   # ไม่ตอบก็ได้ — ใช้ default
    OPTIONAL = "optional"         # ไม่ถามก็ได้
```

### ClarificationQuestion

```python
@dataclass(frozen=True)
class ClarificationQuestion:
    id: str
    question: str                           # ภาษาไทย
    question_type: QuestionType
    priority: QuestionPriority
    options: tuple[str, ...] = ()           # สำหรับ MULTIPLE_CHOICE
    default_value: str | None = None        # ใช้ถ้าผู้ใช้ไม่ตอบ (RECOMMENDED)
    context: str = ""                       # คำอธิบายเพิ่ม
    category: str = ""                      # "studio_apartment" | ...
```

### Questions for `studio_apartment`

```python
_STUDIO_QUESTIONS = [
    ClarificationQuestion(
        id="sleep_zone_preference",
        question="โซนนอนควรอยู่ส่วนไหน?",
        question_type=QuestionType.MULTIPLE_CHOICE,
        priority=QuestionPriority.REQUIRED,
        options=("ตรงข้ามประตู", "ซ้าย", "ขวา", "ไม่ชอบพิเศษ"),
        default_value="ตรงข้ามประตู",
        context="ตำแหน่งผู้บัญชาการตามหลักฮวงจุ้ย",
        category="studio_apartment",
    ),

    ClarificationQuestion(
        id="sofa_bed_or_separate",
        question="ใช้โซฟาเตียงหรือเตียงแยก?",
        question_type=QuestionType.MULTIPLE_CHOICE,
        priority=QuestionPriority.RECOMMENDED,
        options=("โซฟาเตียง", "เตียงแยก + โซฟา", "เตียงเดี่ยว"),
        default_value="โซฟาเตียง",
        category="studio_apartment",
    ),

    ClarificationQuestion(
        id="work_area_needed",
        question="ต้องการโซนทำงานไหม?",
        question_type=QuestionType.YES_NO,
        priority=QuestionPriority.RECOMMENDED,
        options=("ใช่", "ไม่ใช่"),
        default_value="ใช่",
        category="studio_apartment",
    ),

    ClarificationQuestion(
        id="budget_level",
        question="งบประมาณระดับไหน?",
        question_type=QuestionType.MULTIPLE_CHOICE,
        priority=QuestionPriority.RECOMMENDED,
        options=("ประหยัด", "กลาง", "สูง"),
        default_value="กลาง",
    ),
]
```

### UserClarifierTool

```python
class UserClarifierTool:
    def get_questions_for_room_type(self, room_type: str) -> list[ClarificationQuestion]:
        if room_type == "studio_apartment":
            return _STUDIO_QUESTIONS
        # elif room_type == "bedroom": ...
        return []
```

---

## Chat Request Schema

File: [schemas/chat_stream.py](../src/schemas/chat_stream.py)

```python
class ChatStreamRequest(BaseModel):
    message: str
    mode: Literal["buddy", "mentor", "fun"] = "buddy"
    current_layout: list[dict[str, Any]] = []
    room_spec: dict[str, Any] | None = None
    conversation_history: list[dict[str, str]] = []
    clarification_answers: dict[str, str] = {}
```

### LayoutItem (dict schema)

```python
{
    "furniture_id": str,       # unique per instance (e.g. "bed_queen_001")
    "instanceId": str,          # unique per placement (UUID — frontend tracks)
    "pos_x": float,             # centre X (Three.js)
    "pos_y": float = 0.0,
    "pos_z": float,             # centre Z
    "rotation": int,            # 0|90|180|270
    "dimensions": {
        "width": float,         # natural (pre-rotation)
        "depth": float,
        "height": float,
    },
    "category": str,            # "bed", "sofa", ...
    "name": str,                # display
    "model_url": str,           # glTF URL
    "model_rotation_offset": int,
    "is_essential": bool,
    "feng_shui_element": str,
}
```

### DoorPosition (dict schema)

```python
{
    "wall": "north"|"south"|"east"|"west",
    "offset": float,           # metres from corner
    "width": float,            # default 0.9
    "swing_inward": bool,      # default True
}
```

### WindowPosition (dict schema)

```python
{
    "wall": "north"|"south"|"east"|"west",
    "offset": float,
    "width": float,
    "height": float,           # default 1.2
    "sill_height": float,      # default 0.9
}
```

### RoomSpec (dict schema)

```python
{
    "room_type": "bedroom"|"studio_apartment"|...,
    "dimensions": {"width": float, "depth": float},
    "doors": [DoorPosition, ...],
    "windows": [WindowPosition, ...],
    "direction": "north"|"south"|"east"|"west",   # ทิศที่หน้าห้องหัน
    "budget_level": "low"|"medium"|"high",
    "user_preferences": {
        "user_message": str,
        "placement_constraints": str,
        "furniture_relationships": str,
        "birth_year": int,                        # optional (Kua)
        "gender": "male"|"female",                # optional (Kua)
        "clarification_answers": dict,
        # ...
    },
}
```

---

## จุดที่ควรรู้

1. **Frozen dataclasses** — Domain entities ไม่ mutable. ใช้ replace() ถ้าต้อง update field
2. **FURNITURE_CATALOG เป็น dict ของ id → CatalogFurniture** — ไม่ใช่ list
3. **model_rotation_offset ต้องตรวจกับ 3D model จริง** — ถ้าเฟอร์นิเจอร์หันผิดใน Three.js, ส่วนใหญ่ offset ผิด
4. **Studio apartment ไม่มี room_type specific essential furniture** — ใช้ compact items (sofa_bed, folding_desk)
5. **REQUIRED questions block pipeline, RECOMMENDED ใช้ default** — ดู `_apply_clarification_answers()` ใน router.py
6. **LayoutItem มี 2 ID**: `furniture_id` (catalog item) + `instanceId` (unique per placement, frontend tracks)
