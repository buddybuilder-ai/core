"""Personality mode definitions for the Explainer agent.

Defines 3 personality modes (Mentor/Buddy/Fun) with Thai-language system
prompts, keyword-based mood detection, and mode-switch detection.

Usage:
    from src.modules.layout.application.agent.personality import (
        PersonalityMode, get_system_prompt, detect_mood, detect_mode_switch
    )

    system = get_system_prompt("mentor", detect_mood(user_message))
    new_mode = detect_mode_switch(user_message)  # "fun" | None
"""

from __future__ import annotations

from enum import Enum


class PersonalityMode(str, Enum):
    """The 3 supported personality modes."""

    MENTOR = "mentor"
    BUDDY = "buddy"
    FUN = "fun"


_PROMPTS: dict[str, str] = {
    "mentor": (
        "คุณคือผู้เชี่ยวชาญฮวงจุ้ยและนักออกแบบตกแต่งภายในมืออาชีพ "
        "อธิบายด้วยภาษาทางการ ละเอียด และอ้างอิงหลักการฮวงจุ้ยเสมอ "
        "เช่น 'เตียงวางชิดผนังทิศใต้ตามหลักฮวงจุ้ย เนื่องจาก...'"
    ),
    "buddy": (
        "คุณคือผู้ช่วยออกแบบตกแต่งภายในที่เป็นมิตร ใช้ภาษาปกติ "
        "อบอุ่น และให้กำลังใจ "
        "เช่น 'วางเตียงไว้ตรงนี้แหละ ดีเลย! เพราะว่า...'"
    ),
    "fun": (
        "คุณคือผู้ช่วยออกแบบที่สนุกสนาน ใช้มุกตลก อุปมาอุปไมย และ emoji อย่างเหมาะสม "
        "เช่น 'เตียงตรงนี้ปังมาก! เงินจะไหลมาเทมาเลย 💰'"
    ),
}

_MOOD_SOFTENERS: list[str] = [
    "หงุดหงิด", "เบื่อ", "ไม่ชอบ", "แย่", "เสียใจ",
    "frustrated", "annoyed", "ugh", "hate", "terrible",
]

_MOOD_ENERGIZERS: list[str] = [
    "ว้าว", "เยี่ยม", "สุดยอด", "ดีมาก", "ชอบมาก",
    "excited", "wow", "amazing", "love", "awesome", "great",
]

_MODE_KEYWORDS: dict[str, list[str]] = {
    "mentor": ["โหมดครู", "โหมดทางการ", "mentor", "formal", "professional", "ทางการ"],
    "buddy": ["โหมดเพื่อน", "โหมดปกติ", "buddy", "casual", "friendly"],
    "fun": ["โหมดสนุก", "โหมดฮา", "fun", "playful", "funny", "สนุก"],
}


def get_system_prompt(mode: str, mood: str = "neutral") -> str:
    """Return a Thai system prompt for the given personality mode.

    Appends a mood-specific tone modifier when the user seems frustrated
    or excited.

    Args:
        mode: One of "mentor", "buddy", "fun".  Falls back to "buddy".
        mood: One of "frustrated", "excited", "neutral".

    Returns:
        System prompt string to pass to the LLM.
    """
    base = _PROMPTS.get(mode, _PROMPTS["buddy"])
    if mood == "frustrated":
        base += " ใช้น้ำเสียงที่อ่อนโยนและเห็นอกเห็นใจเป็นพิเศษ"
    elif mood == "excited":
        base += " ใช้น้ำเสียงที่กระตือรือร้นและเต็มไปด้วยพลังงาน"
    return base


def detect_mood(message: str) -> str:
    """Keyword-based mood detection (no LLM call).

    Args:
        message: The user's raw message.

    Returns:
        "frustrated", "excited", or "neutral".
    """
    msg = message.lower()
    if any(kw in msg for kw in _MOOD_SOFTENERS):
        return "frustrated"
    if any(kw in msg for kw in _MOOD_ENERGIZERS):
        return "excited"
    return "neutral"


def detect_mode_switch(message: str) -> str | None:
    """Keyword-based mode-switch detection (no LLM call).

    Args:
        message: The user's raw message.

    Returns:
        New mode string ("mentor", "buddy", "fun") if detected, else None.
    """
    msg = message.lower()
    for mode, keywords in _MODE_KEYWORDS.items():
        if any(kw in msg for kw in keywords):
            return mode
    return None
