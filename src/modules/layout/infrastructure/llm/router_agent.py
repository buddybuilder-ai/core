"""Router Agent — classifies user intent with a single fast LLM call.

Supported intents:
    new_layout  — user wants a brand new furniture layout
    modify      — user wants to change an existing layout
    question    — user asks about feng shui / design principles
    explain     — user wants explanation of the current layout

Uses a small, fast model (LLM_MODEL_ROUTER) with max_tokens=200 so
latency is minimal before routing to the appropriate handler.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.config.settings import get_settings

logger = logging.getLogger(__name__)

_VALID_INTENTS = {"new_layout", "modify", "rearrange_all", "question", "explain", "set_mode"}
_FALLBACK_INTENT = "question"

_SYSTEM_PROMPT = """\
You are an intent classifier for a feng shui interior design assistant.

Classify the user message into exactly one of:
- "new_layout": user wants a brand new furniture layout for a room
- "modify": user wants to change a SPECIFIC piece of furniture in an existing layout (move/resize/swap/remove/add ONE item, OR rotate/orient a specific item e.g. "หันหัวเตียงไปทิศเหนือ", "turn bed north", "rotate wardrobe to face east", "ย้ายโซฟา", "move sofa")
- "rearrange_all": user wants ALL existing furniture repositioned/reorganized at once (e.g. "จัดห้องใหม่", "จัดวางใหม่ทั้งหมด", "จัดให้ถูกฮ้วงจุ้ย", "ปรับห้องให้ถูกหลัก", "rearrange", "reorganize the room", "redo the layout", "จัดห้องให้ลงตัว") — NOT when only one specific item is mentioned
- "question": user asks about feng shui or design principles (including greetings)
- "explain": user wants an explanation of the current layout
- "set_mode": user wants to change the personality mode of the assistant
  (e.g. "เปลี่ยนเป็นโหมดครู", "switch to fun mode", "use mentor mode", "โหมดสนุก")

Context clues:
- If has_existing_layout is false, use "new_layout" even if the message mentions placing specific furniture (e.g. "วางเตียงทางซ้าย", "put the sofa on the right"). Those are placement preferences for a new layout, not modifications.
- "modify" is ONLY valid when has_existing_layout is true AND user asks to change a specific item. Rotating/orienting ONE item (e.g. "หันหัวเตียง", "หันหน้า", "turn X toward Y") → always "modify".
- "rearrange_all" is ONLY valid when has_existing_layout is true AND user wants to reorganize ALL furniture. If the message names a specific piece (bed, sofa, wardrobe, etc.) → use "modify" instead.
- If has_existing_layout is false and user asks to "explain", classify as "question" instead.
- Short greetings ("hi", "hello", "สวัสดี") → "question".

Respond ONLY with a valid JSON object — no other text:
{
  "intent": "<new_layout|modify|rearrange_all|question|explain|set_mode>",
  "confidence": <float 0.0-1.0>,
  "extracted_params": {}
}

For "modify" intent, extracted_params must be:
{
  "action": "<move|resize|swap|remove|add>",
  "target_furniture": "<furniture type e.g. bed|desk|sofa|wardrobe|chair>",
  "details": "<free text describing the change>"
}
For "set_mode" intent, extracted_params must be:
{
  "mode": "<mentor|buddy|fun>"
}
For all other intents, extracted_params = {}."""


@dataclass
class RouterConfig:
    """Configuration for the RouterAgent.

    Attributes:
        model: Model name (via OpenRouter). Defaults to settings.LLM_MODEL_ROUTER.
        temperature: Sampling temperature. 0.0 for deterministic classification.
        max_tokens: Keep small — we only need a short JSON response.
        timeout: Request timeout in seconds.
    """

    model: str = ""
    temperature: float = 0.0
    max_tokens: int = 200
    timeout: int = 15

    def __post_init__(self) -> None:
        if not self.model:
            settings = get_settings()
            self.model = settings.LLM_MODEL_ROUTER


@dataclass
class RouterResult:
    """Result from the RouterAgent.

    Attributes:
        intent: Classified intent.
        confidence: Confidence score (0.0–1.0).
        extracted_params: Extra info parsed for the intent (e.g. modify action).
        error: Error message if classification failed.
    """

    intent: str
    confidence: float
    extracted_params: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class RouterAgent:
    """Single-LLM-call intent classifier.

    Usage:
        agent = RouterAgent()
        result = await agent.classify(message, has_existing_layout, history)
        # result.intent in {"new_layout", "modify", "question", "explain"}
    """

    def __init__(self, config: RouterConfig | None = None) -> None:
        self.config = config or RouterConfig()
        settings = get_settings()

        # Support groq/ollama/openrouter based on LLM_MODEL_ROUTER prefix
        router_model = self.config.model
        if router_model.startswith("groq/"):
            api_base = settings.GROQ_BASE_URL
            api_key = settings.GROQ_API_KEY
            model_name = router_model[len("groq/"):]
        elif router_model.startswith("ollama/"):
            api_base = f"{settings.OLLAMA_BASE_URL}/v1"
            api_key = "ollama"
            model_name = router_model[len("ollama/"):]
        else:
            api_base = settings.OPENROUTER_BASE_URL
            api_key = settings.OPENROUTER_API_KEY
            model_name = router_model

        self._llm = ChatOpenAI(
            model=model_name,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            timeout=self.config.timeout,
            openai_api_key=api_key,
            openai_api_base=api_base,
        )
        logger.debug(f"RouterAgent initialised with model: {model_name} via {api_base}")

    async def classify(
        self,
        message: str,
        has_existing_layout: bool,
        conversation_history: list[dict[str, str]],
    ) -> RouterResult:
        """Classify user intent from the message.

        Args:
            message: The user's message.
            has_existing_layout: Whether the user has an existing layout.
            conversation_history: Recent turns for context (last 4 used).

        Returns:
            RouterResult with intent, confidence, and optional extracted params.
            Falls back to "question" if the LLM call fails.
        """
        history_text = self._format_history(conversation_history[-4:])

        user_content = (
            f"has_existing_layout: {str(has_existing_layout).lower()}\n"
            f"Last conversation turns:\n{history_text}\n\n"
            f"User message: {message}"
        )

        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]

        try:
            response = await self._llm.ainvoke(messages)
            raw = str(response.content) if hasattr(response, "content") else ""
            parsed = self._parse_json(raw)

            intent = str(parsed.get("intent", "")).lower().strip()
            if intent not in _VALID_INTENTS:
                logger.warning(
                    f"RouterAgent: invalid intent {intent!r}, falling back to {_FALLBACK_INTENT!r}"
                )
                return RouterResult(
                    intent=_FALLBACK_INTENT,
                    confidence=0.0,
                    error=f"Invalid intent from LLM: {intent!r}",
                )

            confidence = float(parsed.get("confidence", 0.5))
            extracted = dict(parsed.get("extracted_params", {}))

            if confidence < 0.5:
                logger.warning(
                    f"RouterAgent: low confidence {confidence:.2f} for {intent!r}, "
                    f"falling back to {_FALLBACK_INTENT!r}"
                )
                return RouterResult(
                    intent=_FALLBACK_INTENT,
                    confidence=confidence,
                    error=f"Low confidence: {confidence:.2f}",
                )

            # Keyword-based set_mode override — catches cases the LLM misses
            if intent != "set_mode":
                from src.modules.layout.application.agent.personality import detect_mode_switch

                switched = detect_mode_switch(message)
                if switched:
                    intent = "set_mode"
                    extracted = {"mode": switched}

            logger.info(
                f"RouterAgent: intent={intent!r} confidence={confidence:.2f} params={extracted}"
            )
            return RouterResult(
                intent=intent,
                confidence=confidence,
                extracted_params=extracted,
            )

        except Exception as exc:
            logger.error(f"RouterAgent classification failed: {exc}")
            return RouterResult(
                intent=_FALLBACK_INTENT,
                confidence=0.0,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_history(history: list[dict[str, str]]) -> str:
        if not history:
            return "(none)"
        lines = []
        for turn in history:
            role = turn.get("role", "user")
            content = turn.get("content", "")[:120]  # truncate long turns
            lines.append(f"  {role}: {content}")
        return "\n".join(lines)

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        """Extract the first JSON object from LLM response text."""
        # Direct parse
        try:
            return dict(json.loads(text))
        except (json.JSONDecodeError, TypeError):
            pass

        # JSON in code block
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if m:
            try:
                return dict(json.loads(m.group(1)))
            except (json.JSONDecodeError, TypeError):
                pass

        # Find first { ... } object
        start = text.find("{")
        if start != -1:
            depth = 0
            for i, ch in enumerate(text[start:]):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return dict(json.loads(text[start : start + i + 1]))
                        except (json.JSONDecodeError, TypeError):
                            break

        raise json.JSONDecodeError("No valid JSON found in router response", text, 0)
