"""Furniture relationship rules — used to build inter-item hints for the LLM planner.

When the LLM plans a layout it only receives individual pieces + room geometry.
This module detects which pieces are present and generates relationship hints so
the LLM knows to:
  - place TV stand opposite the sofa / bed
  - place nightstands beside the bed
  - put coffee table in front of the sofa
  - cluster dining chairs around the dining table
  etc.

Usage:
    hints = build_relationship_hints(furniture_list)
    # hints → list of plain-language strings, e.g.:
    #   "tv_stand_01 should be placed on the wall opposite sofa_01 so the screen faces the seating"
    # Pass these as extra_context or user_preferences["relationship_hints"] to plan_layout().
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Relationship definitions
# ---------------------------------------------------------------------------
# Each rule is checked if ALL items in "requires" are present in the list.
# "description" is a template — {a} / {b} are replaced with furniture IDs.
# "priority_boost" items should be placed before items they support (lower priority #).

_RULES: list[dict[str, Any]] = [
    # ── TV / screen ──────────────────────────────────────────────────────────
    {
        "requires": ["tv_stand", "sofa"],
        "description": "{a} (TV stand) must face {b}: place {a} on the OPPOSITE wall from {b} so the screen faces the seating area directly.",
        "a_type": "tv_stand",
        "b_type": "sofa",
    },
    {
        "requires": ["tv_stand", "armchair"],
        "description": "{a} (TV stand) should face the seating — place it on the wall opposite {b} (armchair).",
        "a_type": "tv_stand",
        "b_type": "armchair",
    },
    {
        "requires": ["tv_stand", "bed"],
        "description": "{a} (TV stand) should be placed on the wall at the foot of {b} (bed) so the screen faces the bed.",
        "a_type": "tv_stand",
        "b_type": "bed",
    },

    # ── Nightstand / bedside table ────────────────────────────────────────────
    {
        "requires": ["nightstand", "bed"],
        "description": "{a} (nightstand) must be placed BESIDE {b} (bed) — flush against the same wall, on the left or right side of the bed. Do NOT place it on a different wall.",
        "a_type": "nightstand",
        "b_type": "bed",
    },
    {
        "requires": ["bedside_table", "bed"],
        "description": "{a} (bedside table) must be placed BESIDE {b} (bed) on the left or right side.",
        "a_type": "bedside_table",
        "b_type": "bed",
    },

    # ── Coffee table ──────────────────────────────────────────────────────────
    {
        "requires": ["coffee_table", "sofa"],
        "description": "{a} (coffee table) should be placed directly IN FRONT OF {b} (sofa), not against a wall — leave 40–60 cm gap between them.",
        "a_type": "coffee_table",
        "b_type": "sofa",
    },

    # ── Dining set ────────────────────────────────────────────────────────────
    {
        "requires": ["dining_chair", "dining_table"],
        "description": "{a} (dining chair) must be placed AROUND {b} (dining table), not against a wall.",
        "a_type": "dining_chair",
        "b_type": "dining_table",
    },

    # ── Desk + chair ─────────────────────────────────────────────────────────
    {
        "requires": ["chair", "desk"],
        "description": "{a} (chair) should be placed IN FRONT OF {b} (desk), facing the same direction as the desk.",
        "a_type": "chair",
        "b_type": "desk",
    },

    # ── Sofa + armchair grouping ─────────────────────────────────────────────
    {
        "requires": ["armchair", "sofa"],
        "description": "{a} (armchair) should be grouped with {b} (sofa) in a conversational arrangement — place on adjacent or opposite wall, NOT behind a door.",
        "a_type": "armchair",
        "b_type": "sofa",
    },

    # ── Wardrobe near bed ─────────────────────────────────────────────────────
    {
        "requires": ["wardrobe", "bed"],
        "description": "{a} (wardrobe) should be on the same wall as {b} (bed) or the adjacent wall — do NOT place it on the wall directly opposite the bed.",
        "a_type": "wardrobe",
        "b_type": "bed",
    },

    # ── Mirror placement ──────────────────────────────────────────────────────
    {
        "requires": ["mirror", "bed"],
        "description": "{a} (mirror) must NOT face the bed directly — place it on a side wall instead.",
        "a_type": "mirror",
        "b_type": "bed",
    },
    {
        "requires": ["mirror", "wardrobe"],
        "description": "{a} (mirror) should be on the same wall as or adjacent to {b} (wardrobe) for a functional dressing area.",
        "a_type": "mirror",
        "b_type": "wardrobe",
    },

    # ── Plant near window ─────────────────────────────────────────────────────
    {
        "requires": ["plant"],
        "description": "{a} (plant) should be placed near a window for natural light — use target_wall matching one of the window walls.",
        "a_type": "plant",
        "b_type": None,
    },

    # ── Bookcase / bookshelf against wall ────────────────────────────────────
    {
        "requires": ["bookshelf"],
        "description": "{a} (bookshelf) belongs against a wall — NOT in the center of the room.",
        "a_type": "bookshelf",
        "b_type": None,
    },
    {
        "requires": ["bookcase"],
        "description": "{a} (bookcase) belongs against a wall — NOT in the center of the room.",
        "a_type": "bookcase",
        "b_type": None,
    },

    # ── Studio Apartment: sofa_bed as sleep+seating zone ─────────────────────
    {
        "requires": ["sofa_bed", "compact_wardrobe"],
        "description": "{b} (compact_wardrobe) must be on the SAME wall as {a} (sofa_bed) or the adjacent side wall — never on the opposite wall.",
        "a_type": "sofa_bed",
        "b_type": "compact_wardrobe",
    },
    {
        "requires": ["sofa_bed", "tv_stand"],
        "description": "{b} (tv_stand) must be on the wall OPPOSITE {a} (sofa_bed) so the screen faces the sofa_bed directly.",
        "a_type": "sofa_bed",
        "b_type": "tv_stand",
    },
    {
        "requires": ["sofa_bed", "folding_desk"],
        "description": "{b} (folding_desk) should be on a SIDE wall — NOT on the same wall as {a} (sofa_bed) and NOT on the opposite wall. Keep work zone separate from sleep zone.",
        "a_type": "sofa_bed",
        "b_type": "folding_desk",
    },
    {
        "requires": ["sofa_bed", "room_divider"],
        "description": "{b} (room_divider) should be placed in the CENTER of the room, between {a} (sofa_bed / sleep zone) and the living/work zone — use target_wall=center.",
        "a_type": "sofa_bed",
        "b_type": "room_divider",
    },
    {
        "requires": ["room_divider"],
        "description": "{a} (room_divider) should be placed in the CENTER of the room to visually separate zones — use target_wall=center, NOT against any wall.",
        "a_type": "room_divider",
        "b_type": None,
    },
    {
        "requires": ["shoe_cabinet"],
        "description": "{a} (shoe_cabinet) should be near the entrance door wall — use the same wall as the door or an adjacent corner.",
        "a_type": "shoe_cabinet",
        "b_type": None,
    },
    {
        "requires": ["coat_rack"],
        "description": "{a} (coat_rack) should be near the entrance door — use the same wall or adjacent corner to the door.",
        "a_type": "coat_rack",
        "b_type": None,
    },
]

# Category token aliases — maps partial furniture_id tokens to canonical type
_TYPE_ALIASES: dict[str, str] = {
    "tv":         "tv_stand",
    "television": "tv_stand",
    "screen":     "tv_stand",
    "night":      "nightstand",
    "bedside":    "bedside_table",
    "coffee":     "coffee_table",
    "dining":     "dining_table",  # will be overridden if 'chair' also in token
    "arm":        "armchair",
    "book":       "bookshelf",
    # Studio apartment
    "sofa_bed":   "sofa_bed",
    "compact_wardrobe": "compact_wardrobe",
    "folding_desk": "folding_desk",
    "room_divider": "room_divider",
    "shoe_cabinet": "shoe_cabinet",
    "coat_rack":  "coat_rack",
}


def _canonical_type(fid: str, name: str) -> str:
    """Return the canonical furniture type for a given id/name string."""
    text = (fid + " " + name).lower().replace("-", "_").replace(" ", "_")

    # Compound checks first (more specific)
    if "dining_chair" in text or ("dining" in text and "chair" in text):
        return "dining_chair"
    if "dining_table" in text or ("dining" in text and "table" in text):
        return "dining_table"
    if "coffee_table" in text or ("coffee" in text and "table" in text):
        return "coffee_table"
    if "tv_stand" in text or ("tv" in text and "stand" in text):
        return "tv_stand"
    if "nightstand" in text or "night_stand" in text or "bedside" in text:
        return "nightstand"
    if "armchair" in text or "arm_chair" in text:
        return "armchair"
    if "bookshelf" in text or "bookcase" in text:
        return "bookshelf"
    # Studio apartment types — check before generic "sofa", "wardrobe", "desk", "bed"
    if "sofa_bed" in text or "sofabed" in text:
        return "sofa_bed"
    if "compact_wardrobe" in text:
        return "compact_wardrobe"
    if "folding_desk" in text:
        return "folding_desk"
    if "room_divider" in text:
        return "room_divider"
    if "shoe_cabinet" in text:
        return "shoe_cabinet"
    if "coat_rack" in text:
        return "coat_rack"
    if "wardrobe" in text or "closet" in text:
        return "wardrobe"
    if "mirror" in text:
        return "mirror"
    if "plant" in text:
        return "plant"
    if "sofa" in text or "couch" in text:
        return "sofa"
    if "chair" in text:
        return "chair"
    if "desk" in text:
        return "desk"
    if "bed" in text:
        return "bed"
    if "dresser" in text or "chest" in text:
        return "dresser"
    if "lamp" in text:
        return "lamp"
    if "rug" in text:
        return "rug"
    if "table" in text:
        return "table"
    if "shelf" in text:
        return "bookshelf"

    # Fallback: first token of fid
    return fid.split("_")[0]


def build_relationship_hints(
    furniture_list: list[dict[str, Any]],
) -> list[str]:
    """Generate inter-furniture relationship hints from the furniture list.

    Args:
        furniture_list: List of dicts with at least "id" and "name" keys.

    Returns:
        List of plain-language hint strings for the LLM planner.
        Empty list if no relationships apply.
    """
    if not furniture_list:
        return []

    # Build type→[id, ...] index
    type_to_ids: dict[str, list[str]] = {}
    for item in furniture_list:
        fid = item.get("id") or item.get("furniture_id") or ""
        name = item.get("name") or ""
        ctype = _canonical_type(fid, name)
        type_to_ids.setdefault(ctype, []).append(fid)

    hints: list[str] = []

    for rule in _RULES:
        required_types = rule["requires"]
        a_type = rule["a_type"]
        b_type = rule.get("b_type")

        # Check all required types are present
        if not all(t in type_to_ids for t in required_types):
            continue

        a_ids = type_to_ids.get(a_type, [])
        b_ids = type_to_ids.get(b_type, []) if b_type else []

        if not a_ids:
            continue

        # Generate one hint per a_id (handle multiple nightstands, chairs, etc.)
        for a_id in a_ids:
            if b_ids:
                b_id = b_ids[0]  # pair with the first matching item
                hint = rule["description"].format(a=a_id, b=b_id)
            else:
                hint = rule["description"].format(a=a_id, b="")
            hints.append(hint)

    return hints
