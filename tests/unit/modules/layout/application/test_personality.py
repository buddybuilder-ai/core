"""Unit tests for the personality module."""

from src.modules.layout.application.agent.personality import (
    PersonalityMode,
    detect_mode_switch,
    detect_mood,
    get_system_prompt,
)


class TestPersonalityMode:
    def test_enum_values(self) -> None:
        assert PersonalityMode.MENTOR == "mentor"
        assert PersonalityMode.BUDDY == "buddy"
        assert PersonalityMode.FUN == "fun"

    def test_enum_is_str(self) -> None:
        assert isinstance(PersonalityMode.MENTOR, str)


class TestGetSystemPrompt:
    def test_mentor_prompt_contains_formal_keyword(self) -> None:
        prompt = get_system_prompt("mentor")
        assert "ทางการ" in prompt

    def test_buddy_prompt_contains_friendly_keyword(self) -> None:
        prompt = get_system_prompt("buddy")
        assert "มิตร" in prompt or "อบอุ่น" in prompt

    def test_fun_prompt_contains_playful_keyword(self) -> None:
        prompt = get_system_prompt("fun")
        assert "สนุก" in prompt or "emoji" in prompt

    def test_unknown_mode_falls_back_to_buddy(self) -> None:
        prompt_buddy = get_system_prompt("buddy")
        prompt_unknown = get_system_prompt("nonexistent")
        assert prompt_buddy == prompt_unknown

    def test_frustrated_mood_appends_soft_tone(self) -> None:
        base = get_system_prompt("buddy")
        frustrated = get_system_prompt("buddy", mood="frustrated")
        assert len(frustrated) > len(base)
        assert "อ่อนโยน" in frustrated

    def test_excited_mood_appends_energetic_tone(self) -> None:
        base = get_system_prompt("buddy")
        excited = get_system_prompt("buddy", mood="excited")
        assert len(excited) > len(base)
        assert "กระตือรือร้น" in excited

    def test_neutral_mood_no_suffix(self) -> None:
        base = get_system_prompt("mentor")
        neutral = get_system_prompt("mentor", mood="neutral")
        assert base == neutral

    def test_all_modes_return_non_empty_string(self) -> None:
        for mode in ("mentor", "buddy", "fun"):
            assert len(get_system_prompt(mode)) > 0


class TestDetectMood:
    def test_frustrated_thai_keyword(self) -> None:
        assert detect_mood("หงุดหงิดมากเลย") == "frustrated"

    def test_frustrated_english_keyword(self) -> None:
        assert detect_mood("I am frustrated with this") == "frustrated"

    def test_excited_thai_keyword(self) -> None:
        assert detect_mood("ว้าว สวยมากเลย") == "excited"

    def test_excited_english_keyword(self) -> None:
        assert detect_mood("wow this is amazing!") == "excited"

    def test_neutral_no_match(self) -> None:
        assert detect_mood("วางเตียงไว้ที่ไหนดี") == "neutral"

    def test_neutral_empty_string(self) -> None:
        assert detect_mood("") == "neutral"

    def test_case_insensitive(self) -> None:
        assert detect_mood("FRUSTRATED") == "frustrated"
        assert detect_mood("WOW") == "excited"

    def test_frustrated_takes_priority_over_no_match(self) -> None:
        assert detect_mood("แย่มากเลย ไม่ชอบเลย") == "frustrated"


class TestDetectModeSwitch:
    def test_mentor_thai(self) -> None:
        assert detect_mode_switch("เปลี่ยนเป็นโหมดครู") == "mentor"

    def test_mentor_english(self) -> None:
        assert detect_mode_switch("switch to mentor mode") == "mentor"

    def test_buddy_thai(self) -> None:
        assert detect_mode_switch("ใช้โหมดเพื่อน") == "buddy"

    def test_buddy_english(self) -> None:
        assert detect_mode_switch("use buddy mode") == "buddy"

    def test_fun_thai(self) -> None:
        assert detect_mode_switch("เปลี่ยนเป็นโหมดสนุก") == "fun"

    def test_fun_english(self) -> None:
        assert detect_mode_switch("switch to fun mode") == "fun"

    def test_no_match_returns_none(self) -> None:
        assert detect_mode_switch("วางเตียงไว้ที่ไหน") is None

    def test_empty_string_returns_none(self) -> None:
        assert detect_mode_switch("") is None

    def test_case_insensitive(self) -> None:
        assert detect_mode_switch("MENTOR") == "mentor"
        assert detect_mode_switch("FUN") == "fun"

    def test_formal_keyword_maps_to_mentor(self) -> None:
        assert detect_mode_switch("use formal style please") == "mentor"

    def test_playful_keyword_maps_to_fun(self) -> None:
        assert detect_mode_switch("be more playful") == "fun"
