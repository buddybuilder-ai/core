"""In-memory furniture catalog for feng shui layout agent."""

from dataclasses import dataclass
from enum import StrEnum


class FurnitureCategory(StrEnum):
    """Categories of furniture."""

    # Bedroom
    BED = "bed"
    NIGHTSTAND = "nightstand"
    WARDROBE = "wardrobe"
    DRESSER = "dresser"
    VANITY = "vanity"

    # Living Room
    SOFA = "sofa"
    ARMCHAIR = "armchair"
    COFFEE_TABLE = "coffee_table"
    TV_STAND = "tv_stand"
    BOOKSHELF = "bookshelf"

    # Office
    DESK = "desk"
    OFFICE_CHAIR = "chair"
    FILING_CABINET = "filing_cabinet"

    # Dining Room
    DINING_TABLE = "dining_table"
    DINING_CHAIR = "dining_chair"
    SIDEBOARD = "sideboard"

    # General
    PLANT = "plant"
    LAMP = "lamp"
    MIRROR = "mirror"
    RUG = "rug"

    # Studio Apartment
    SOFA_BED = "sofa_bed"
    COMPACT_WARDROBE = "compact_wardrobe"
    FOLDING_DESK = "folding_desk"
    COMPACT_DINING = "compact_dining"
    ROOM_DIVIDER = "room_divider"
    SHOE_CABINET = "shoe_cabinet"
    KITCHEN_COUNTER = "kitchen_counter"
    MINI_FRIDGE = "mini_fridge"
    MICROWAVE_STAND = "microwave_stand"
    COAT_RACK = "coat_rack"


class BudgetLevel(StrEnum):
    """Budget levels for furniture."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class CatalogFurniture:
    """A furniture item in the catalog.

    Attributes:
        id: Unique identifier.
        name: Display name.
        category: Furniture category.
        width: Width in meters (x-axis).
        depth: Depth in meters (z-axis).
        height: Height in meters (y-axis).
        budget_level: Budget level (low, medium, high).
        room_types: Room types this furniture is suitable for.
        clearance_front: Required clearance in front (meters).
        clearance_sides: Required clearance on sides (meters).
        is_essential: Whether this is essential furniture for the room.
        feng_shui_element: Associated feng shui element.
        placement_notes: Notes about ideal placement.
    """

    id: str
    name: str
    category: FurnitureCategory
    width: float
    depth: float
    height: float
    budget_level: BudgetLevel
    room_types: tuple[str, ...]
    clearance_front: float = 0.6
    clearance_sides: float = 0.3
    is_essential: bool = False
    feng_shui_element: str = ""
    placement_notes: str = ""
    model_rotation_offset: int = 0
    """Degrees to ADD to the layout rotation before rendering.

    Use this to correct for the 3D model's "forward" direction not matching the
    system convention (rotation=0 → front faces +Z / south).

    Examples:
      model_rotation_offset=0   → model front already faces +Z at rest  (default)
      model_rotation_offset=180 → model was exported facing -Z (backward); add 180° to flip
      model_rotation_offset=90  → model was exported facing -X (left);    add 90°  to correct
      model_rotation_offset=270 → model was exported facing +X (right);   add 270° to correct
    """

    @property
    def floor_area(self) -> float:
        """Calculate floor area in square meters."""
        return self.width * self.depth

    @property
    def total_footprint(self) -> float:
        """Calculate total footprint including clearance."""
        total_width = self.width + (self.clearance_sides * 2)
        total_depth = self.depth + self.clearance_front + self.clearance_sides
        return total_width * total_depth


# Bedroom Furniture
BEDROOM_FURNITURE: list[CatalogFurniture] = [
    # Beds
    CatalogFurniture(
        id="bed_single_001",
        name="Single Bed",
        category=FurnitureCategory.BED,
        width=0.9,
        depth=1.9,
        height=0.45,
        budget_level=BudgetLevel.LOW,
        room_types=("bedroom",),
        clearance_front=0.6,
        clearance_sides=0.4,
        is_essential=True,
        feng_shui_element="wood",
        placement_notes="Place with headboard against solid wall, diagonal from door",
    ),
    CatalogFurniture(
        id="bed_queen_001",
        name="Queen Bed",
        category=FurnitureCategory.BED,
        width=1.6,
        depth=2.0,
        height=0.5,
        budget_level=BudgetLevel.MEDIUM,
        room_types=("bedroom",),
        clearance_front=0.6,
        clearance_sides=0.5,
        is_essential=True,
        feng_shui_element="wood",
        placement_notes="Place with headboard against solid wall, command position",
    ),
    CatalogFurniture(
        id="bed_king_001",
        name="King Bed",
        category=FurnitureCategory.BED,
        width=1.8,
        depth=2.0,
        height=0.55,
        budget_level=BudgetLevel.HIGH,
        room_types=("bedroom",),
        clearance_front=0.8,
        clearance_sides=0.6,
        is_essential=True,
        feng_shui_element="wood",
        placement_notes="Requires larger room, maintain command position",
    ),
    # Nightstands
    CatalogFurniture(
        id="nightstand_001",
        name="Standard Nightstand",
        category=FurnitureCategory.NIGHTSTAND,
        width=0.45,
        depth=0.4,
        height=0.55,
        budget_level=BudgetLevel.LOW,
        room_types=("bedroom",),
        clearance_front=0.3,
        clearance_sides=0.1,
        is_essential=False,
        feng_shui_element="wood",
        placement_notes="Place on both sides of bed for balance",
    ),
    CatalogFurniture(
        id="nightstand_002",
        name="Wide Nightstand",
        category=FurnitureCategory.NIGHTSTAND,
        width=0.6,
        depth=0.45,
        height=0.6,
        budget_level=BudgetLevel.MEDIUM,
        room_types=("bedroom",),
        clearance_front=0.3,
        clearance_sides=0.1,
        is_essential=False,
        feng_shui_element="wood",
        placement_notes="Place on both sides of bed for balance",
    ),
    # Wardrobes
    CatalogFurniture(
        id="wardrobe_single_001",
        name="Single Wardrobe",
        category=FurnitureCategory.WARDROBE,
        width=0.9,
        depth=0.6,
        height=2.0,
        budget_level=BudgetLevel.LOW,
        room_types=("bedroom",),
        clearance_front=0.7,
        clearance_sides=0.1,
        is_essential=True,
        feng_shui_element="wood",
        placement_notes="Place against wall, not facing bed directly",
    ),
    CatalogFurniture(
        id="wardrobe_double_001",
        name="Double Wardrobe",
        category=FurnitureCategory.WARDROBE,
        width=1.8,
        depth=0.6,
        height=2.0,
        budget_level=BudgetLevel.MEDIUM,
        room_types=("bedroom",),
        clearance_front=0.8,
        clearance_sides=0.1,
        is_essential=True,
        feng_shui_element="wood",
        placement_notes="Place against wall, not facing bed directly",
    ),
    # Dressers
    CatalogFurniture(
        id="dresser_001",
        name="6-Drawer Dresser",
        category=FurnitureCategory.DRESSER,
        width=1.2,
        depth=0.5,
        height=0.85,
        budget_level=BudgetLevel.MEDIUM,
        room_types=("bedroom",),
        clearance_front=0.6,
        clearance_sides=0.1,
        is_essential=False,
        feng_shui_element="wood",
        placement_notes="Place against wall, can have mirror above",
    ),
]

# Living Room Furniture
LIVING_ROOM_FURNITURE: list[CatalogFurniture] = [
    # Sofas
    CatalogFurniture(
        id="sofa_2seat_001",
        name="2-Seater Sofa",
        category=FurnitureCategory.SOFA,
        width=1.5,
        depth=0.85,
        height=0.85,
        budget_level=BudgetLevel.LOW,
        room_types=("living_room",),
        clearance_front=0.6,
        clearance_sides=0.3,
        is_essential=True,
        feng_shui_element="earth",
        placement_notes="Place with back against wall, facing door",
    ),
    CatalogFurniture(
        id="sofa_3seat_001",
        name="3-Seater Sofa",
        category=FurnitureCategory.SOFA,
        width=2.0,
        depth=0.9,
        height=0.85,
        budget_level=BudgetLevel.MEDIUM,
        room_types=("living_room",),
        clearance_front=0.8,
        clearance_sides=0.3,
        is_essential=True,
        feng_shui_element="earth",
        placement_notes="Place with back against wall, facing door",
    ),
    CatalogFurniture(
        id="sofa_lshape_001",
        name="L-Shaped Sectional",
        category=FurnitureCategory.SOFA,
        width=2.7,
        depth=2.0,
        height=0.85,
        budget_level=BudgetLevel.HIGH,
        room_types=("living_room",),
        clearance_front=0.8,
        clearance_sides=0.4,
        is_essential=True,
        feng_shui_element="earth",
        placement_notes="Requires larger room, creates conversation area",
    ),
    # Armchairs
    CatalogFurniture(
        id="armchair_001",
        name="Accent Armchair",
        category=FurnitureCategory.ARMCHAIR,
        width=0.75,
        depth=0.8,
        height=0.9,
        budget_level=BudgetLevel.MEDIUM,
        room_types=("living_room", "bedroom"),
        clearance_front=0.5,
        clearance_sides=0.2,
        is_essential=False,
        feng_shui_element="earth",
        placement_notes="Place angled toward conversation center",
    ),
    # Coffee Tables
    CatalogFurniture(
        id="coffee_table_rect_001",
        name="Rectangular Coffee Table",
        category=FurnitureCategory.COFFEE_TABLE,
        width=1.2,
        depth=0.6,
        height=0.45,
        budget_level=BudgetLevel.LOW,
        room_types=("living_room",),
        clearance_front=0.5,
        clearance_sides=0.4,
        is_essential=True,
        feng_shui_element="wood",
        placement_notes="Place centered in front of sofa",
    ),
    CatalogFurniture(
        id="coffee_table_round_001",
        name="Round Coffee Table",
        category=FurnitureCategory.COFFEE_TABLE,
        width=0.9,
        depth=0.9,
        height=0.45,
        budget_level=BudgetLevel.MEDIUM,
        room_types=("living_room",),
        clearance_front=0.5,
        clearance_sides=0.5,
        is_essential=True,
        feng_shui_element="metal",
        placement_notes="Round shape promotes conversation flow",
    ),
    # TV Stands
    CatalogFurniture(
        id="tv_stand_001",
        name="Media Console",
        category=FurnitureCategory.TV_STAND,
        width=1.5,
        depth=0.45,
        height=0.5,
        budget_level=BudgetLevel.MEDIUM,
        room_types=("living_room",),
        clearance_front=2.0,
        clearance_sides=0.2,
        is_essential=False,
        feng_shui_element="fire",
        placement_notes="Place across from seating, avoid facing window",
    ),
    # Bookshelves
    CatalogFurniture(
        id="bookshelf_001",
        name="5-Shelf Bookcase",
        category=FurnitureCategory.BOOKSHELF,
        width=0.8,
        depth=0.3,
        height=1.8,
        budget_level=BudgetLevel.LOW,
        room_types=("living_room", "office"),
        clearance_front=0.6,
        clearance_sides=0.1,
        is_essential=False,
        feng_shui_element="wood",
        placement_notes="Keep organized, activate empty corners",
    ),
]

# Office Furniture
OFFICE_FURNITURE: list[CatalogFurniture] = [
    # Desks
    CatalogFurniture(
        id="desk_standard_001",
        name="Standard Office Desk",
        category=FurnitureCategory.DESK,
        width=1.2,
        depth=0.6,
        height=0.75,
        budget_level=BudgetLevel.LOW,
        room_types=("office",),
        clearance_front=0.8,
        clearance_sides=0.4,
        is_essential=True,
        feng_shui_element="wood",
        placement_notes="Place facing door with wall behind",
    ),
    CatalogFurniture(
        id="desk_executive_001",
        name="Executive Desk",
        category=FurnitureCategory.DESK,
        width=1.6,
        depth=0.8,
        height=0.75,
        budget_level=BudgetLevel.HIGH,
        room_types=("office",),
        clearance_front=1.0,
        clearance_sides=0.5,
        is_essential=True,
        feng_shui_element="wood",
        placement_notes="Command position is essential",
    ),
    CatalogFurniture(
        id="desk_corner_001",
        name="L-Shaped Corner Desk",
        category=FurnitureCategory.DESK,
        width=1.5,
        depth=1.5,
        height=0.75,
        budget_level=BudgetLevel.MEDIUM,
        room_types=("office",),
        clearance_front=0.8,
        clearance_sides=0.3,
        is_essential=True,
        feng_shui_element="wood",
        placement_notes="Place in corner, maintain view of door",
    ),
    # Chairs
    CatalogFurniture(
        id="office_chair_001",
        name="Ergonomic Office Chair",
        category=FurnitureCategory.OFFICE_CHAIR,
        width=0.65,
        depth=0.65,
        height=1.2,
        budget_level=BudgetLevel.MEDIUM,
        room_types=("office",),
        clearance_front=0.6,
        clearance_sides=0.3,
        is_essential=True,
        feng_shui_element="metal",
        placement_notes="Pair with desk, back should face wall",
        model_rotation_offset=180,
    ),
    # Filing Cabinets
    CatalogFurniture(
        id="filing_cabinet_001",
        name="2-Drawer Filing Cabinet",
        category=FurnitureCategory.FILING_CABINET,
        width=0.4,
        depth=0.5,
        height=0.7,
        budget_level=BudgetLevel.LOW,
        room_types=("office",),
        clearance_front=0.5,
        clearance_sides=0.1,
        is_essential=False,
        feng_shui_element="metal",
        placement_notes="Place within reach of desk",
    ),
]

# Dining Room Furniture
DINING_ROOM_FURNITURE: list[CatalogFurniture] = [
    # Dining Tables
    CatalogFurniture(
        id="dining_table_4seat_001",
        name="4-Seater Dining Table",
        category=FurnitureCategory.DINING_TABLE,
        width=1.2,
        depth=0.8,
        height=0.75,
        budget_level=BudgetLevel.MEDIUM,
        room_types=("dining_room",),
        clearance_front=0.8,
        clearance_sides=0.8,
        is_essential=True,
        feng_shui_element="wood",
        placement_notes="Center in room, allow space for chair movement",
    ),
    CatalogFurniture(
        id="dining_table_6seat_001",
        name="6-Seater Dining Table",
        category=FurnitureCategory.DINING_TABLE,
        width=1.6,
        depth=0.9,
        height=0.75,
        budget_level=BudgetLevel.MEDIUM,
        room_types=("dining_room",),
        clearance_front=1.0,
        clearance_sides=1.0,
        is_essential=True,
        feng_shui_element="wood",
        placement_notes="Center in room, allow space for chair movement",
    ),
    CatalogFurniture(
        id="dining_table_round_001",
        name="Round Dining Table (4-seat)",
        category=FurnitureCategory.DINING_TABLE,
        width=1.1,
        depth=1.1,
        height=0.75,
        budget_level=BudgetLevel.HIGH,
        room_types=("dining_room",),
        clearance_front=0.9,
        clearance_sides=0.9,
        is_essential=True,
        feng_shui_element="metal",
        placement_notes="Round promotes equal conversation, good feng shui",
    ),
    # Dining Chairs
    CatalogFurniture(
        id="dining_chair_001",
        name="Standard Dining Chair",
        category=FurnitureCategory.DINING_CHAIR,
        width=0.45,
        depth=0.5,
        height=0.9,
        budget_level=BudgetLevel.LOW,
        room_types=("dining_room",),
        clearance_front=0.6,
        clearance_sides=0.1,
        is_essential=True,
        feng_shui_element="wood",
        placement_notes="Match number to table seating capacity",
    ),
    # Sideboards
    CatalogFurniture(
        id="sideboard_001",
        name="Dining Sideboard",
        category=FurnitureCategory.SIDEBOARD,
        width=1.5,
        depth=0.45,
        height=0.85,
        budget_level=BudgetLevel.MEDIUM,
        room_types=("dining_room",),
        clearance_front=0.6,
        clearance_sides=0.1,
        is_essential=False,
        feng_shui_element="wood",
        placement_notes="Place against wall, can hold mirror above",
    ),
]

# Accessories
ACCESSORIES: list[CatalogFurniture] = [
    CatalogFurniture(
        id="plant_large_001",
        name="Large Floor Plant",
        category=FurnitureCategory.PLANT,
        width=0.6,
        depth=0.6,
        height=1.5,
        budget_level=BudgetLevel.LOW,
        room_types=("bedroom", "living_room", "office", "dining_room"),
        clearance_front=0.3,
        clearance_sides=0.3,
        is_essential=False,
        feng_shui_element="wood",
        placement_notes="Activates corners, improves chi flow",
    ),
    CatalogFurniture(
        id="plant_medium_001",
        name="Medium Potted Plant",
        category=FurnitureCategory.PLANT,
        width=0.4,
        depth=0.4,
        height=0.8,
        budget_level=BudgetLevel.LOW,
        room_types=("bedroom", "living_room", "office", "dining_room"),
        clearance_front=0.2,
        clearance_sides=0.2,
        is_essential=False,
        feng_shui_element="wood",
        placement_notes="Good for desks and shelves",
    ),
    CatalogFurniture(
        id="lamp_floor_001",
        name="Floor Lamp",
        category=FurnitureCategory.LAMP,
        width=0.35,
        depth=0.35,
        height=1.6,
        budget_level=BudgetLevel.LOW,
        room_types=("bedroom", "living_room", "office"),
        clearance_front=0.3,
        clearance_sides=0.2,
        is_essential=False,
        feng_shui_element="fire",
        placement_notes="Illuminates dark corners, adds yang energy",
    ),
    CatalogFurniture(
        id="rug_medium_001",
        name="Medium Area Rug",
        category=FurnitureCategory.RUG,
        width=2.0,
        depth=1.5,
        height=0.02,
        budget_level=BudgetLevel.MEDIUM,
        room_types=("bedroom", "living_room"),
        clearance_front=0.0,
        clearance_sides=0.0,
        is_essential=False,
        feng_shui_element="earth",
        placement_notes="Grounds seating area, defines space",
    ),
]

# Studio Apartment Furniture
STUDIO_APARTMENT_FURNITURE: list[CatalogFurniture] = [
    # Sofa Bed - Essential sleeping/living
    CatalogFurniture(
        id="sofa_bed_001",
        name="Modern Sofa Bed",
        category=FurnitureCategory.SOFA_BED,
        width=1.9,
        depth=0.95,
        height=0.85,
        budget_level=BudgetLevel.MEDIUM,
        room_types=("studio_apartment",),
        clearance_front=0.8,
        clearance_sides=0.5,
        is_essential=True,
        feng_shui_element="earth",
        placement_notes="Place against wall, headboard should face command position",
    ),
    CatalogFurniture(
        id="sofa_bed_002",
        name="Compact Sofa Bed",
        category=FurnitureCategory.SOFA_BED,
        width=1.6,
        depth=0.85,
        height=0.8,
        budget_level=BudgetLevel.LOW,
        room_types=("studio_apartment",),
        clearance_front=0.8,
        clearance_sides=0.5,
        is_essential=True,
        feng_shui_element="earth",
        placement_notes="Space-saving option for smaller studios",
    ),
    # Compact Wardrobe - Essential storage
    CatalogFurniture(
        id="compact_wardrobe_001",
        name="Narrow Wardrobe",
        category=FurnitureCategory.COMPACT_WARDROBE,
        width=1.0,
        depth=0.55,
        height=2.0,
        budget_level=BudgetLevel.MEDIUM,
        room_types=("studio_apartment",),
        clearance_front=0.7,
        clearance_sides=0.3,
        is_essential=True,
        feng_shui_element="wood",
        placement_notes="Place against wall, not blocking chi flow",
    ),
    CatalogFurniture(
        id="compact_wardrobe_002",
        name="Corner Wardrobe",
        category=FurnitureCategory.COMPACT_WARDROBE,
        width=0.8,
        depth=0.8,
        height=2.0,
        budget_level=BudgetLevel.LOW,
        room_types=("studio_apartment",),
        clearance_front=0.6,
        clearance_sides=0.3,
        is_essential=True,
        feng_shui_element="wood",
        placement_notes="Fits in corners, maximizes space",
    ),
    # Folding Desk - Work zone
    CatalogFurniture(
        id="folding_desk_001",
        name="Wall-Mounted Folding Desk",
        category=FurnitureCategory.FOLDING_DESK,
        width=1.0,
        depth=0.5,
        height=0.75,
        budget_level=BudgetLevel.MEDIUM,
        room_types=("studio_apartment",),
        clearance_front=0.7,
        clearance_sides=0.3,
        is_essential=False,
        feng_shui_element="wood",
        placement_notes="Face room entrance, command position for work",
    ),
    CatalogFurniture(
        id="folding_desk_002",
        name="Compact Folding Table",
        category=FurnitureCategory.FOLDING_DESK,
        width=0.8,
        depth=0.45,
        height=0.75,
        budget_level=BudgetLevel.LOW,
        room_types=("studio_apartment",),
        clearance_front=0.6,
        clearance_sides=0.3,
        is_essential=False,
        feng_shui_element="wood",
        placement_notes="Portable, can be moved as needed",
    ),
    # Compact Dining
    CatalogFurniture(
        id="compact_dining_001",
        name="Drop-Leaf Dining Table",
        category=FurnitureCategory.COMPACT_DINING,
        width=0.9,
        depth=0.7,
        height=0.75,
        budget_level=BudgetLevel.MEDIUM,
        room_types=("studio_apartment",),
        clearance_front=0.6,
        clearance_sides=0.5,
        is_essential=False,
        feng_shui_element="earth",
        placement_notes="Central location for dining zone",
    ),
    # Room Divider
    CatalogFurniture(
        id="room_divider_001",
        name="3-Panel Room Divider",
        category=FurnitureCategory.ROOM_DIVIDER,
        width=1.5,
        depth=0.05,
        height=1.7,
        budget_level=BudgetLevel.LOW,
        room_types=("studio_apartment",),
        clearance_front=0.3,
        clearance_sides=0.3,
        is_essential=False,
        feng_shui_element="wood",
        placement_notes="Separates sleeping from living areas, maintains chi flow",
    ),
    CatalogFurniture(
        id="room_divider_002",
        name="Bookshelf Room Divider",
        category=FurnitureCategory.ROOM_DIVIDER,
        width=1.2,
        depth=0.3,
        height=1.8,
        budget_level=BudgetLevel.MEDIUM,
        room_types=("studio_apartment",),
        clearance_front=0.4,
        clearance_sides=0.3,
        is_essential=False,
        feng_shui_element="wood",
        placement_notes="Dual purpose: storage and space division",
    ),
    # Kitchen Zone
    CatalogFurniture(
        id="kitchen_counter_001",
        name="Mini Kitchen Counter",
        category=FurnitureCategory.KITCHEN_COUNTER,
        width=1.2,
        depth=0.6,
        height=0.9,
        budget_level=BudgetLevel.MEDIUM,
        room_types=("studio_apartment",),
        clearance_front=0.8,
        clearance_sides=0.4,
        is_essential=True,
        feng_shui_element="fire",
        placement_notes="Place away from bedroom zone, good ventilation",
    ),
    CatalogFurniture(
        id="mini_fridge_001",
        name="Compact Refrigerator",
        category=FurnitureCategory.MINI_FRIDGE,
        width=0.5,
        depth=0.55,
        height=0.85,
        budget_level=BudgetLevel.MEDIUM,
        room_types=("studio_apartment",),
        clearance_front=0.5,
        clearance_sides=0.3,
        is_essential=True,
        feng_shui_element="water",
        placement_notes="Near kitchen zone, away from fire element",
    ),
    # Storage
    CatalogFurniture(
        id="shoe_cabinet_001",
        name="Slim Shoe Cabinet",
        category=FurnitureCategory.SHOE_CABINET,
        width=0.8,
        depth=0.35,
        height=1.2,
        budget_level=BudgetLevel.LOW,
        room_types=("studio_apartment",),
        clearance_front=0.5,
        clearance_sides=0.3,
        is_essential=False,
        feng_shui_element="earth",
        placement_notes="Near entrance, keeps clutter contained",
    ),
    CatalogFurniture(
        id="coat_rack_001",
        name="Standing Coat Rack",
        category=FurnitureCategory.COAT_RACK,
        width=0.4,
        depth=0.4,
        height=1.75,
        budget_level=BudgetLevel.LOW,
        room_types=("studio_apartment",),
        clearance_front=0.5,
        clearance_sides=0.4,
        is_essential=False,
        feng_shui_element="wood",
        placement_notes="Near entrance for convenience",
    ),
]

# Complete catalog
FURNITURE_CATALOG: list[CatalogFurniture] = (
    BEDROOM_FURNITURE
    + LIVING_ROOM_FURNITURE
    + OFFICE_FURNITURE
    + DINING_ROOM_FURNITURE
    + ACCESSORIES
    + STUDIO_APARTMENT_FURNITURE
)


def get_furniture_by_room_type(room_type: str) -> list[CatalogFurniture]:
    """Get furniture suitable for a room type."""
    return [f for f in FURNITURE_CATALOG if room_type in f.room_types]


def get_furniture_by_category(category: FurnitureCategory) -> list[CatalogFurniture]:
    """Get furniture in a specific category."""
    return [f for f in FURNITURE_CATALOG if f.category == category]


def get_furniture_by_budget(budget_level: BudgetLevel) -> list[CatalogFurniture]:
    """Get furniture at a specific budget level."""
    return [f for f in FURNITURE_CATALOG if f.budget_level == budget_level]


def get_essential_furniture(room_type: str) -> list[CatalogFurniture]:
    """Get essential furniture for a room type."""
    return [f for f in FURNITURE_CATALOG if f.is_essential and room_type in f.room_types]


def get_furniture_by_id(furniture_id: str) -> CatalogFurniture | None:
    """Get a specific furniture item by ID."""
    for f in FURNITURE_CATALOG:
        if f.id == furniture_id:
            return f
    return None
