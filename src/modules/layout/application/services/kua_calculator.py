"""Kua number calculator and auspicious direction lookup.

Kua number determines personal auspicious directions based on
birth year and gender (Eight Mansions / Ba Zhai feng shui).

Directions: N, NE, E, SE, S, SW, W, NW
Wall mapping: N→north, S→south, E→east, W→west
(NE/SE/SW/NW are diagonal — mapped to nearest cardinal wall)
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Kua direction table (from Excel reference)
# Columns: sheng_chi, tien_yi, nien_yen, fu_wei, ho_hai, wu_kwei, liu_sha, chueh_ming
# ---------------------------------------------------------------------------

_KUA_DIRECTIONS: dict[int, dict[str, str]] = {
    1: {
        "sheng_chi": "SE",
        "tien_yi": "E",
        "nien_yen": "S",
        "fu_wei": "N",
        "ho_hai": "W",
        "wu_kwei": "NE",
        "liu_sha": "NW",
        "chueh_ming": "SW",
    },
    2: {
        "sheng_chi": "NE",
        "tien_yi": "W",
        "nien_yen": "NW",
        "fu_wei": "SW",
        "ho_hai": "E",
        "wu_kwei": "SE",
        "liu_sha": "S",
        "chueh_ming": "N",
    },
    3: {
        "sheng_chi": "S",
        "tien_yi": "N",
        "nien_yen": "SE",
        "fu_wei": "E",
        "ho_hai": "SW",
        "wu_kwei": "NW",
        "liu_sha": "NE",
        "chueh_ming": "W",
    },
    4: {
        "sheng_chi": "N",
        "tien_yi": "S",
        "nien_yen": "E",
        "fu_wei": "SE",
        "ho_hai": "NW",
        "wu_kwei": "SW",
        "liu_sha": "W",
        "chueh_ming": "NE",
    },
    6: {
        "sheng_chi": "W",
        "tien_yi": "NE",
        "nien_yen": "SW",
        "fu_wei": "NW",
        "ho_hai": "SE",
        "wu_kwei": "E",
        "liu_sha": "N",
        "chueh_ming": "S",
    },
    7: {
        "sheng_chi": "NW",
        "tien_yi": "SW",
        "nien_yen": "NE",
        "fu_wei": "W",
        "ho_hai": "S",
        "wu_kwei": "N",
        "liu_sha": "SE",
        "chueh_ming": "E",
    },
    8: {
        "sheng_chi": "SW",
        "tien_yi": "NW",
        "nien_yen": "W",
        "fu_wei": "NE",
        "ho_hai": "N",
        "wu_kwei": "S",
        "liu_sha": "E",
        "chueh_ming": "SE",
    },
    9: {
        "sheng_chi": "E",
        "tien_yi": "SE",
        "nien_yen": "N",
        "fu_wei": "S",
        "ho_hai": "NE",
        "wu_kwei": "W",
        "liu_sha": "SW",
        "chueh_ming": "NW",
    },
}

# Map compass direction → cardinal wall (nearest)
_DIR_TO_WALL: dict[str, str] = {
    "N": "north",
    "NE": "north",  # diagonal → north or east; prefer north (headboard)
    "E": "east",
    "SE": "east",  # diagonal → east or south; prefer east
    "S": "south",
    "SW": "south",  # diagonal → south or west; prefer west (bed command)
    "W": "west",
    "NW": "north",  # diagonal → north or west; prefer north
}

# Auspicious direction priority order (best → acceptable)
_AUSPICIOUS_ORDER = ["sheng_chi", "tien_yi", "nien_yen", "fu_wei"]

# Keywords that map user intent → kua direction key
_INTENT_KEYWORDS: dict[str, list[str]] = {
    "tien_yi": [
        "สุขภาพ",
        "health",
        "โรค",
        "ป่วย",
        "แข็งแรง",
        "ฟื้นตัว",
        "หาย",
    ],
    "nien_yen": [
        "ความรัก",
        "love",
        "ความสัมพันธ์",
        "คู่รัก",
        "ครอบครัว",
        "แต่งงาน",
        "relationship",
        "romance",
    ],
    "fu_wei": [
        "ความสงบ",
        "สมาธิ",
        "peace",
        "calm",
        "จิตใจ",
        "mental",
        "สงบ",
    ],
    "sheng_chi": [
        "โชค",
        "เงิน",
        "ความสำเร็จ",
        "การงาน",
        "luck",
        "wealth",
        "career",
        "success",
        "money",
    ],
}


def detect_kua_priority(message: str) -> str:
    """Detect which kua direction the user wants based on message keywords.

    Returns one of: "sheng_chi", "tien_yi", "nien_yen", "fu_wei".
    Defaults to "sheng_chi" if no keyword matched.
    """
    msg = message.lower()
    for direction_key, keywords in _INTENT_KEYWORDS.items():
        if any(kw in msg for kw in keywords):
            return direction_key
    return "sheng_chi"


# Thai names and benefits for each auspicious direction
_DIRECTION_INFO: dict[str, dict[str, str]] = {
    "sheng_chi": {
        "name": "เซิงชี่",
        "benefit": "โชคลาภ ความมั่งคั่ง และความสำเร็จในการงาน",
    },
    "tien_yi": {
        "name": "เทียนอี้",
        "benefit": "สุขภาพดี ฟื้นตัวจากโรคเร็ว และความแข็งแรง",
    },
    "nien_yen": {
        "name": "เนียนเอี้ยน",
        "benefit": "ความสัมพันธ์ดี ความรัก และความสามัคคีในครอบครัว",
    },
    "fu_wei": {
        "name": "ฝูเว่ย",
        "benefit": "ความสงบ การเติบโตส่วนตัว และจิตใจมั่นคง",
    },
}


def calculate_kua(birth_year: int, gender: str) -> int:
    """Calculate Kua number from birth year (CE) and gender.

    Args:
        birth_year: Year of birth in CE (e.g. 1990).
        gender: 'male' or 'female' (case-insensitive).

    Returns:
        Kua number 1-9 (never 5; 5 is replaced by 2 for male, 8 for female).
    """
    # Step 1-2: reduce birth year digits to single digit
    base = _reduce(sum(int(d) for d in str(birth_year)))

    # Step 3: calculate by gender
    g = gender.lower().strip()
    if g in ("male", "m", "ชาย"):
        kua = _reduce(11 - base)
    else:
        kua = _reduce(base + 4)

    # Step 4: replace 5 with 2 (male) or 8 (female)
    if kua == 5:
        kua = 2 if g in ("male", "m", "ชาย") else 8

    return kua


def kua_auspicious_walls(kua: int) -> list[str]:
    """Return cardinal walls in auspicious order for bed headboard placement.

    Args:
        kua: Kua number (1-9, not 5).

    Returns:
        List of wall names ['north','east',...] from most to least auspicious.
        Returns empty list if kua is unknown.
    """
    directions = _KUA_DIRECTIONS.get(kua, {})
    walls: list[str] = []
    seen: set[str] = set()
    for key in _AUSPICIOUS_ORDER:
        direction = directions.get(key, "")
        wall = _DIR_TO_WALL.get(direction, "")
        if wall and wall not in seen:
            seen.add(wall)
            walls.append(wall)
    # Append remaining cardinal walls as fallback
    for wall in ("north", "east", "south", "west"):
        if wall not in seen:
            walls.append(wall)
    return walls


def kua_best_direction_info(kua: int, priority: str = "sheng_chi") -> dict[str, str]:
    """Return info about the chosen auspicious direction for a given kua number.

    Args:
        kua: Kua number (1-9, not 5).
        priority: One of "sheng_chi", "tien_yi", "nien_yen", "fu_wei".

    Returns:
        Dict with keys: wall, wall_th, direction_name, benefit
    """
    if priority not in _DIRECTION_INFO:
        priority = "sheng_chi"
    directions = _KUA_DIRECTIONS.get(kua, {})
    direction = directions.get(priority, "N")
    wall = _DIR_TO_WALL.get(direction, "north")
    wall_th = {"north": "เหนือ", "south": "ใต้", "east": "ตะวันออก", "west": "ตะวันตก"}.get(wall, wall)
    info = _DIRECTION_INFO[priority]
    return {
        "wall": wall,
        "wall_th": wall_th,
        "direction_name": info["name"],
        "benefit": info["benefit"],
        "priority": priority,
    }


def kua_inauspicious_walls(kua: int) -> set[str]:
    """Return cardinal walls that are inauspicious (ho_hai, wu_kwei, liu_sha, chueh_ming).

    Used to avoid placing bed headboard on these walls when possible.
    """
    directions = _KUA_DIRECTIONS.get(kua, {})
    inauspicious_keys = ["ho_hai", "wu_kwei", "liu_sha", "chueh_ming"]
    walls: set[str] = set()
    for key in inauspicious_keys:
        direction = directions.get(key, "")
        wall = _DIR_TO_WALL.get(direction, "")
        if wall:
            walls.add(wall)
    return walls


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _reduce(n: int) -> int:
    """Reduce a number by summing its digits until single digit."""
    while n >= 10:
        n = sum(int(d) for d in str(n))
    return n
