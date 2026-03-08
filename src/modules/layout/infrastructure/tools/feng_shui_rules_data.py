"""Hardcoded feng shui knowledge base for mock RAG search."""

from dataclasses import dataclass
from enum import StrEnum


class RuleCategory(StrEnum):
    """Categories of feng shui rules."""

    COMMAND_POSITION = "command_position"
    FIVE_ELEMENTS = "five_elements"
    CHI_FLOW = "chi_flow"
    SHA_CHI = "sha_chi"
    ROOM_LAYOUT = "room_layout"
    FURNITURE_PLACEMENT = "furniture_placement"
    DOOR_WINDOW = "door_window"


@dataclass(frozen=True)
class FengShuiRule:
    """A feng shui rule with metadata.

    Attributes:
        id: Unique identifier for the rule.
        category: Category of the rule.
        title: Short title for the rule.
        description: Detailed description of the rule.
        room_types: Room types this rule applies to.
        furniture_types: Furniture types this rule applies to.
        priority: Priority weight (higher = more important).
        keywords: Keywords for search matching.
    """

    id: str
    category: RuleCategory
    title: str
    description: str
    room_types: tuple[str, ...]
    furniture_types: tuple[str, ...]
    priority: int
    keywords: tuple[str, ...]


# Feng Shui Knowledge Base
FENG_SHUI_RULES: list[FengShuiRule] = [
    # Command Position Rules
    FengShuiRule(
        id="cmd_001",
        category=RuleCategory.COMMAND_POSITION,
        title="Command Position Principle",
        description=(
            "Place important furniture (bed, desk, sofa) in the command position: "
            "diagonally across from the door, with a solid wall behind, and a clear "
            "view of the entrance. This position provides psychological security and "
            "allows you to see opportunities coming."
        ),
        room_types=("bedroom", "office", "living_room"),
        furniture_types=("bed", "desk", "sofa"),
        priority=100,
        keywords=("command", "position", "diagonal", "door", "wall", "security"),
    ),
    FengShuiRule(
        id="cmd_002",
        category=RuleCategory.COMMAND_POSITION,
        title="Bed Command Position",
        description=(
            "The bed should be placed so you can see the door while lying in bed, "
            "but not directly in line with the door. Avoid placing the bed with "
            "feet pointing toward the door (coffin position). Have a solid headboard "
            "against a solid wall."
        ),
        room_types=("bedroom",),
        furniture_types=("bed",),
        priority=95,
        keywords=("bed", "door", "headboard", "wall", "coffin", "position"),
    ),
    FengShuiRule(
        id="cmd_003",
        category=RuleCategory.COMMAND_POSITION,
        title="Desk Command Position",
        description=(
            "Position your desk so you face the door while working, with your back "
            "to a solid wall. Avoid sitting with your back to the door or window. "
            "This position increases focus and productivity."
        ),
        room_types=("office",),
        furniture_types=("desk",),
        priority=90,
        keywords=("desk", "door", "wall", "back", "work", "focus"),
    ),
    # Five Elements Rules
    FengShuiRule(
        id="elem_001",
        category=RuleCategory.FIVE_ELEMENTS,
        title="Five Elements Balance",
        description=(
            "Balance the five elements (Wood, Fire, Earth, Metal, Water) in your space. "
            "Each element should be represented through colors, materials, or shapes. "
            "Wood: green, plants, rectangular. Fire: red, candles, triangular. "
            "Earth: yellow/brown, ceramics, square. Metal: white/gray, metal objects, round. "
            "Water: black/blue, mirrors, wavy."
        ),
        room_types=("bedroom", "living_room", "office", "dining_room"),
        furniture_types=(),
        priority=80,
        keywords=("elements", "balance", "wood", "fire", "earth", "metal", "water", "color"),
    ),
    FengShuiRule(
        id="elem_002",
        category=RuleCategory.FIVE_ELEMENTS,
        title="Bedroom Elements",
        description=(
            "Bedrooms favor Earth and Wood elements for grounding and growth. "
            "Avoid excess Water (too watery, unstable) and Fire (too stimulating). "
            "Use warm, earthy tones. Limit electronics (Fire element) in the bedroom."
        ),
        room_types=("bedroom",),
        furniture_types=(),
        priority=75,
        keywords=("bedroom", "earth", "wood", "grounding", "calm", "electronics"),
    ),
    FengShuiRule(
        id="elem_003",
        category=RuleCategory.FIVE_ELEMENTS,
        title="Office Elements",
        description=(
            "Offices benefit from Metal and Water elements for clarity and flow. "
            "Metal brings focus and precision. Water brings career opportunities. "
            "Add a small water feature or plants for balance."
        ),
        room_types=("office",),
        furniture_types=(),
        priority=75,
        keywords=("office", "metal", "water", "clarity", "career", "focus"),
    ),
    # Chi Flow Rules
    FengShuiRule(
        id="chi_001",
        category=RuleCategory.CHI_FLOW,
        title="Clear Chi Pathways",
        description=(
            "Maintain clear pathways for chi (energy) to flow through the room. "
            "Avoid blocking natural walking paths with furniture. Chi should be able "
            "to meander gently through the space, not rush in a straight line or stagnate."
        ),
        room_types=("bedroom", "living_room", "office", "dining_room"),
        furniture_types=(),
        priority=85,
        keywords=("chi", "flow", "path", "energy", "clear", "meander"),
    ),
    FengShuiRule(
        id="chi_002",
        category=RuleCategory.CHI_FLOW,
        title="Avoid Stagnant Corners",
        description=(
            "Chi can stagnate in corners and unused spaces. Activate these areas with "
            "plants, lights, or meaningful objects. Avoid leaving corners completely empty "
            "or cluttered with unused items."
        ),
        room_types=("bedroom", "living_room", "office", "dining_room"),
        furniture_types=("plant", "lamp"),
        priority=70,
        keywords=("corner", "stagnant", "plant", "light", "activate"),
    ),
    FengShuiRule(
        id="chi_003",
        category=RuleCategory.CHI_FLOW,
        title="Door-to-Window Alignment",
        description=(
            "When a door and window align directly, chi rushes through too quickly. "
            "Place furniture or plants between them to slow the energy flow. "
            "Use curtains to soften window energy."
        ),
        room_types=("bedroom", "living_room", "office"),
        furniture_types=("sofa", "plant", "bookshelf"),
        priority=75,
        keywords=("door", "window", "align", "rush", "slow", "curtain"),
    ),
    # Sha Chi Rules
    FengShuiRule(
        id="sha_001",
        category=RuleCategory.SHA_CHI,
        title="Avoid Poison Arrows",
        description=(
            "Sha chi (killing energy) comes from sharp angles, corners, and straight lines "
            "pointing at you. Avoid furniture with sharp corners pointing at seating areas. "
            "Shield yourself from structural corners with plants or furniture placement."
        ),
        room_types=("bedroom", "living_room", "office"),
        furniture_types=("bed", "desk", "sofa"),
        priority=85,
        keywords=("sha", "chi", "poison", "arrow", "sharp", "corner", "angle"),
    ),
    FengShuiRule(
        id="sha_002",
        category=RuleCategory.SHA_CHI,
        title="Beam Avoidance",
        description=(
            "Exposed ceiling beams create oppressive sha chi. Avoid placing beds, desks, "
            "or sofas directly under beams. If unavoidable, use fabric to soften or "
            "symbolic cures like hanging crystals."
        ),
        room_types=("bedroom", "living_room", "office"),
        furniture_types=("bed", "desk", "sofa"),
        priority=80,
        keywords=("beam", "ceiling", "oppressive", "crystal", "cure"),
    ),
    FengShuiRule(
        id="sha_003",
        category=RuleCategory.SHA_CHI,
        title="Mirror Placement",
        description=(
            "Mirrors should not reflect the bed as this disturbs sleep and relationships. "
            "In feng shui, mirrors double energy - good if reflecting pleasant views, "
            "bad if reflecting clutter or the sleeper."
        ),
        room_types=("bedroom",),
        furniture_types=("mirror",),
        priority=85,
        keywords=("mirror", "bed", "reflect", "sleep", "double"),
    ),
    # Room Layout Rules
    FengShuiRule(
        id="layout_001",
        category=RuleCategory.ROOM_LAYOUT,
        title="Bedroom Layout Principles",
        description=(
            "Bedroom should feel restful and private. Place bed as far from door as possible "
            "while maintaining command position. Use pairs of nightstands for relationship harmony. "
            "Keep work materials and exercise equipment out of bedroom."
        ),
        room_types=("bedroom",),
        furniture_types=("bed", "nightstand", "wardrobe"),
        priority=85,
        keywords=("bedroom", "restful", "private", "nightstand", "pair"),
    ),
    FengShuiRule(
        id="layout_002",
        category=RuleCategory.ROOM_LAYOUT,
        title="Living Room Layout",
        description=(
            "Living room should welcome chi at the entrance. Create conversation groupings "
            "with seating facing each other. Main sofa should have a solid wall behind "
            "and view of the entrance."
        ),
        room_types=("living_room",),
        furniture_types=("sofa", "coffee_table", "armchair"),
        priority=80,
        keywords=("living", "welcome", "conversation", "grouping", "sofa"),
    ),
    FengShuiRule(
        id="layout_003",
        category=RuleCategory.ROOM_LAYOUT,
        title="Office Layout",
        description=(
            "Office should inspire productivity and success. Keep desk clutter-free. "
            "Place inspiring images in your line of sight. Ensure good lighting, "
            "especially natural light from the side, not behind you."
        ),
        room_types=("office",),
        furniture_types=("desk", "chair", "bookshelf"),
        priority=80,
        keywords=("office", "productivity", "clutter", "light", "inspire"),
    ),
    # Furniture Placement Rules
    FengShuiRule(
        id="furn_001",
        category=RuleCategory.FURNITURE_PLACEMENT,
        title="Nightstand Symmetry",
        description=(
            "Use matching nightstands on both sides of the bed for balance and harmony. "
            "This is especially important for couples but also creates visual balance "
            "for single occupants."
        ),
        room_types=("bedroom",),
        furniture_types=("nightstand",),
        priority=70,
        keywords=("nightstand", "symmetry", "pair", "balance", "couple"),
    ),
    FengShuiRule(
        id="furn_002",
        category=RuleCategory.FURNITURE_PLACEMENT,
        title="Coffee Table Placement",
        description=(
            "Coffee table should be proportional to sofa (about 2/3 the length). "
            "Leave enough space for comfortable movement around it. "
            "Round or oval tables promote better conversation flow."
        ),
        room_types=("living_room",),
        furniture_types=("coffee_table",),
        priority=65,
        keywords=("coffee", "table", "sofa", "proportion", "round"),
    ),
    FengShuiRule(
        id="furn_003",
        category=RuleCategory.FURNITURE_PLACEMENT,
        title="Wardrobe Placement",
        description=(
            "Place wardrobe against a solid wall, not blocking windows or doors. "
            "Avoid placing wardrobe directly facing the bed. "
            "Keep wardrobe organized as clutter blocks chi flow."
        ),
        room_types=("bedroom",),
        furniture_types=("wardrobe",),
        priority=65,
        keywords=("wardrobe", "closet", "wall", "organize", "clutter"),
    ),
    # Door and Window Rules
    FengShuiRule(
        id="door_001",
        category=RuleCategory.DOOR_WINDOW,
        title="Door Opening Space",
        description=(
            "Keep the area in front of doors completely clear. Doors should open fully "
            "without obstruction. This allows chi to enter freely and represents "
            "opportunities flowing into your life."
        ),
        room_types=("bedroom", "living_room", "office", "dining_room"),
        furniture_types=(),
        priority=90,
        keywords=("door", "clear", "open", "obstruction", "opportunity"),
    ),
    FengShuiRule(
        id="door_002",
        category=RuleCategory.DOOR_WINDOW,
        title="Window Treatment",
        description=(
            "Windows should have coverings that can be adjusted for privacy and light control. "
            "Open curtains during day to let in natural chi. "
            "Avoid placing tall furniture that blocks natural light."
        ),
        room_types=("bedroom", "living_room", "office"),
        furniture_types=(),
        priority=70,
        keywords=("window", "curtain", "light", "natural", "privacy"),
    ),
    FengShuiRule(
        id="door_003",
        category=RuleCategory.DOOR_WINDOW,
        title="Multiple Doors",
        description=(
            "Rooms with multiple doors can have scattered energy. Use furniture to create "
            "a clear focal point and anchor the space. Ensure main seating has view of "
            "the primary entrance."
        ),
        room_types=("living_room", "office"),
        furniture_types=("sofa", "desk"),
        priority=75,
        keywords=("doors", "multiple", "focal", "anchor", "entrance"),
    ),
    # ── Bedroom-specific rules (from validation table) ──────────────────────
    FengShuiRule(
        id="bed_001",
        category=RuleCategory.SHA_CHI,
        title="Bed Not Aligned With Door",
        description=(
            "Do not place the bed directly in line with the door (feet or head pointing "
            "straight at the door opening). This is the 'coffin position' — sha chi rushes "
            "directly at the sleeper. Shift the bed to one side so it is out of the direct door axis."
        ),
        room_types=("bedroom",),
        furniture_types=("bed",),
        priority=100,
        keywords=("bed", "door", "aligned", "coffin", "position", "sha", "chi"),
    ),
    FengShuiRule(
        id="bed_002",
        category=RuleCategory.SHA_CHI,
        title="Bed Not Aligned With Window",
        description=(
            "Avoid placing the bed directly in line with a window. Wind and chi rushing "
            "through a window at the sleeper disturbs rest and health. Move the bed "
            "so it is not on the direct window axis."
        ),
        room_types=("bedroom",),
        furniture_types=("bed",),
        priority=90,
        keywords=("bed", "window", "aligned", "wind", "chi", "health"),
    ),
    FengShuiRule(
        id="bed_003",
        category=RuleCategory.SHA_CHI,
        title="Bed Not Facing TV or Mirror",
        description=(
            "Do not place a TV or mirror directly facing the bed. Mirrors reflecting the "
            "sleeper bring a third-party energy into the relationship and disturb sleep. "
            "TVs emit yang energy that prevents rest. Cover or angle them away."
        ),
        room_types=("bedroom",),
        furniture_types=("bed", "mirror", "tv_stand"),
        priority=85,
        keywords=("bed", "mirror", "tv", "reflect", "yang", "sleep", "relationship"),
    ),
    FengShuiRule(
        id="bed_004",
        category=RuleCategory.SHA_CHI,
        title="Bed Not Under Air Conditioner",
        description=(
            "Do not place the bed directly under or in the direct airflow line of an "
            "air conditioner. Cold chi blowing continuously on the sleeper causes health "
            "issues and disturbs sleep quality."
        ),
        room_types=("bedroom",),
        furniture_types=("bed",),
        priority=85,
        keywords=("bed", "air", "conditioner", "airflow", "cold", "chi", "health"),
    ),
    FengShuiRule(
        id="bed_005",
        category=RuleCategory.ROOM_LAYOUT,
        title="Bed Must Not Be in Center of Room",
        description=(
            "The bed must have at least one side against a solid wall. A bed floating "
            "in the center of the room has no support energy behind it, leaving the "
            "sleeper feeling vulnerable and unsupported."
        ),
        room_types=("bedroom",),
        furniture_types=("bed",),
        priority=95,
        keywords=("bed", "center", "middle", "wall", "support", "floating"),
    ),
    FengShuiRule(
        id="bed_006",
        category=RuleCategory.DOOR_WINDOW,
        title="Door Must Not Face Window Directly",
        description=(
            "When a door and window are directly opposite each other, chi rushes straight "
            "through and escapes the room without circulating. Place furniture or a plant "
            "between them to slow and redirect the energy."
        ),
        room_types=("bedroom", "living_room", "office"),
        furniture_types=(),
        priority=80,
        keywords=("door", "window", "opposite", "chi", "rush", "escape"),
    ),
    FengShuiRule(
        id="bed_007",
        category=RuleCategory.SHA_CHI,
        title="No Heavy Furniture at Head of Bed",
        description=(
            "Do not place tall or heavy furniture (wardrobe, bookshelf) directly at the "
            "headboard end of the bed. The oppressive overhead mass creates pressure and "
            "anxiety, reducing sleep quality."
        ),
        room_types=("bedroom",),
        furniture_types=("bed", "wardrobe", "bookshelf"),
        priority=80,
        keywords=("bed", "headboard", "wardrobe", "heavy", "pressure", "oppressive"),
    ),
    FengShuiRule(
        id="bed_008",
        category=RuleCategory.FURNITURE_PLACEMENT,
        title="No Large Furniture Directly Against Bed",
        description=(
            "Large furniture pieces should not be placed flush against the side of the bed "
            "with no clearance. A minimum 60 cm walkway should exist on at least one "
            "side of the bed for good chi flow and practical access."
        ),
        room_types=("bedroom",),
        furniture_types=("bed",),
        priority=75,
        keywords=("bed", "clearance", "walkway", "large", "furniture", "chi", "flow"),
    ),
    FengShuiRule(
        id="bed_009",
        category=RuleCategory.COMMAND_POSITION,
        title="Desk Must Face Door and Not Face Window",
        description=(
            "The desk should face the door (command position) so the person working can "
            "see opportunities approaching. The desk should not face directly into a window "
            "as it creates glare and scattered energy; natural light should come from the side."
        ),
        room_types=("bedroom", "office"),
        furniture_types=("desk",),
        priority=85,
        keywords=("desk", "door", "window", "command", "position", "face", "glare"),
    ),
    FengShuiRule(
        id="bed_010",
        category=RuleCategory.COMMAND_POSITION,
        title="Bed Headboard in Auspicious Direction by Kua Number",
        description=(
            "According to Eight Mansions Feng Shui, the headboard direction should align "
            "with one of the four auspicious directions calculated from the occupant's "
            "Kua number. Best directions for sleep are Sheng Chi (prosperity), "
            "Tien Yi (health), Nien Yen (relationships), or Fu Wei (personal growth)."
        ),
        room_types=("bedroom",),
        furniture_types=("bed",),
        priority=70,
        keywords=("bed", "headboard", "kua", "direction", "auspicious", "eight", "mansions"),
    ),
]


def get_rules_by_category(category: RuleCategory) -> list[FengShuiRule]:
    """Get all rules in a specific category."""
    return [r for r in FENG_SHUI_RULES if r.category == category]


def get_rules_for_room_type(room_type: str) -> list[FengShuiRule]:
    """Get all rules applicable to a room type."""
    return [r for r in FENG_SHUI_RULES if room_type in r.room_types or len(r.room_types) == 0]


def get_rules_for_furniture(furniture_type: str) -> list[FengShuiRule]:
    """Get all rules applicable to a furniture type."""
    return [
        r
        for r in FENG_SHUI_RULES
        if furniture_type in r.furniture_types or len(r.furniture_types) == 0
    ]


def search_rules_by_keywords(keywords: list[str]) -> list[tuple[FengShuiRule, int]]:
    """Search rules by keywords, returning rules with match counts.

    Args:
        keywords: List of keywords to search for.

    Returns:
        List of (rule, match_count) tuples, sorted by match count descending.
    """
    results: list[tuple[FengShuiRule, int]] = []

    for rule in FENG_SHUI_RULES:
        match_count = 0
        rule_text = (
            rule.title.lower() + " " + rule.description.lower() + " " + " ".join(rule.keywords)
        )

        for keyword in keywords:
            if keyword.lower() in rule_text:
                match_count += 1

        if match_count > 0:
            results.append((rule, match_count))

    # Sort by match count descending, then by priority descending
    results.sort(key=lambda x: (x[1], x[0].priority), reverse=True)
    return results
