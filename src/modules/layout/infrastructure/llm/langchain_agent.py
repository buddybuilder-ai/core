"""LangChain Agent for Feng Shui Layout Generation."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_openai import ChatOpenAI

from src.config.settings import get_settings
from src.modules.layout.infrastructure.llm.prompts import (
    FENG_SHUI_SYSTEM_PROMPT,
    FURNITURE_SELECTION_PROMPT,
    LAYOUT_PLANNING_PROMPT,
    SCORING_PROMPT,
)

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """Configuration for the LLM agent.

    Attributes:
        model: Model name to use via OpenRouter.
        temperature: Sampling temperature (0.0-1.0).
        max_tokens: Maximum tokens in response.
        timeout: Request timeout in seconds.
    """
    model: str = ""
    temperature: float = 0.1
    max_tokens: int = 4096
    timeout: int = 60

    def __post_init__(self) -> None:
        """Load defaults from settings if not provided."""
        if not self.model:
            settings = get_settings()
            self.model = settings.LLM_MODEL_LAYOUT
            self.temperature = settings.LLM_TEMPERATURE_LAYOUT


@dataclass
class LLMResponse:
    """Response from the LLM agent.

    Attributes:
        success: Whether the request succeeded.
        content: The response content (text or parsed JSON).
        raw_response: Raw response text from LLM.
        tokens_used: Number of tokens used.
        error: Error message if failed.
    """
    success: bool
    content: Any = None
    raw_response: str = ""
    tokens_used: int = 0
    error: str | None = None


class FengShuiLLMAgent:
    """LangChain-based LLM agent for Feng Shui layout generation.

    This agent uses OpenRouter to access various LLM models for:
    - Furniture selection based on room requirements
    - Layout planning with Feng Shui principles
    - Layout scoring and recommendations
    """

    def __init__(self, config: LLMConfig | None = None) -> None:
        """Initialize the LLM agent.

        Args:
            config: LLM configuration. Uses defaults from settings if not provided.
        """
        self.config = config or LLMConfig()
        settings = get_settings()

        # Initialize LangChain ChatOpenAI with OpenRouter
        self._llm = ChatOpenAI(
            model=self.config.model,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            timeout=self.config.timeout,
            openai_api_key=settings.OPENROUTER_API_KEY,
            openai_api_base=settings.OPENROUTER_BASE_URL,
        )

        self._system_message = SystemMessage(content=FENG_SHUI_SYSTEM_PROMPT)
        logger.info(f"Initialized FengShuiLLMAgent with model: {self.config.model}")

    async def select_furniture(
        self,
        room_type: str,
        usable_area: float,
        budget_level: str,
        max_items: int,
        catalog: list[dict[str, Any]],
    ) -> LLMResponse:
        """Use LLM to select furniture for the room.

        Args:
            room_type: Type of room (bedroom, office, etc.).
            usable_area: Available floor area in square meters.
            budget_level: Budget level (low, medium, high).
            max_items: Maximum number of items to select.
            catalog: Available furniture catalog.

        Returns:
            LLMResponse with selected furniture list.
        """
        # Format catalog for prompt
        catalog_text = self._format_catalog(catalog)

        prompt = FURNITURE_SELECTION_PROMPT.format(
            room_type=room_type,
            usable_area=usable_area,
            budget_level=budget_level,
            max_items=max_items,
            catalog=catalog_text,
        )

        return await self._invoke_with_json_output(
            prompt,
            output_schema={
                "selected_items": [
                    {
                        "id": "string - furniture ID from catalog",
                        "reason": "string - why selected",
                        "element": "string - feng shui element",
                        "placement_zone": "string - recommended zone",
                    }
                ],
                "element_balance": {
                    "wood": "int - count",
                    "fire": "int - count",
                    "earth": "int - count",
                    "metal": "int - count",
                    "water": "int - count",
                },
                "recommendations": ["string - additional recommendations"],
            },
        )

    async def plan_layout(
        self,
        room_type: str,
        width: float,
        depth: float,
        usable_area: float,
        doors: list[dict[str, Any]],
        windows: list[dict[str, Any]],
        furniture_list: list[dict[str, Any]],
        command_positions: list[dict[str, Any]],
    ) -> LLMResponse:
        """Use LLM to plan furniture layout using semantic placement format.

        The LLM outputs wall/alignment intent rather than raw x/z coordinates.
        Response is validated with SemanticPlacementSchema; invalid items are
        skipped with a warning.  If the LLM returns the old xyz format (detected
        by presence of "pos_x"), items are converted to approximate semantic
        format for backward compatibility.

        Args:
            room_type: Type of room.
            width: Room width in meters.
            depth: Room depth in meters.
            usable_area: Available floor area.
            doors: Door positions.
            windows: Window positions.
            furniture_list: Furniture to place.
            command_positions: Identified command positions.

        Returns:
            LLMResponse with content["placements"] as semantic placement dicts.
        """
        from src.modules.layout.application.services.layout_resolver import (
            SemanticPlacementSchema,
        )

        prompt = LAYOUT_PLANNING_PROMPT.format(
            room_type=room_type,
            width=width,
            depth=depth,
            area=width * depth,
            usable_area=usable_area,
            doors=json.dumps(doors, indent=2) if doors else "None",
            windows=json.dumps(windows, indent=2) if windows else "None",
            furniture_list=self._format_furniture_list(furniture_list),
            command_positions=json.dumps(command_positions, indent=2),
        )

        output_schema = {
            "placements": [
                {
                    "furniture_id": "string",
                    "furniture_type": "string - bed|desk|sofa|wardrobe|chair|...",
                    "size": {"w": "float", "l": "float", "h": "float"},
                    "target_wall": "north|south|east|west|center",
                    "alignment": "left|center|right",
                    "offset_from_wall": "float (meters)",
                    "priority": "int (1=first)",
                    "orientation": "string - human readable hint",
                }
            ],
            "chi_flow_notes": "string - notes about energy flow",
            "warnings": ["string - any concerns"],
        }

        response = await self._invoke_with_json_output(prompt, output_schema)
        if not response.success or not isinstance(response.content, dict):
            return response

        raw_placements = response.content.get("placements", [])

        # Backward compat: detect old xyz format and convert
        if raw_placements and "pos_x" in raw_placements[0]:
            logger.info("plan_layout: detected old xyz format — converting to semantic")
            raw_placements = [
                self._convert_xyz_to_semantic(p, width, depth)
                for p in raw_placements
            ]

        # Validate each placement; skip invalid ones
        valid: list[dict[str, Any]] = []
        for raw in raw_placements:
            try:
                schema = SemanticPlacementSchema.model_validate(raw)
                valid.append(schema.model_dump())
            except Exception as exc:
                fid = raw.get("furniture_id", "<unknown>")
                logger.warning(f"plan_layout: skipping invalid placement {fid!r}: {exc}")

        response.content["placements"] = valid
        return response

    def _convert_xyz_to_semantic(
        self, old: dict[str, Any], room_width: float, room_depth: float
    ) -> dict[str, Any]:
        """Convert old {pos_x, pos_z, rotation} format to approximate semantic format.

        Uses position heuristics to guess target_wall/alignment.
        """
        fid = old.get("furniture_id", "unknown_01")
        ftype = fid.split("_")[0]
        pos_x = float(old.get("pos_x", room_width / 2))
        pos_z = float(old.get("pos_z", room_depth / 2))
        w = float(old.get("width", 1.0))
        l = float(old.get("depth", 1.0))
        h = float(old.get("height", 1.0))

        dist_south = pos_z
        dist_north = room_depth - (pos_z + l)
        dist_west  = pos_x
        dist_east  = room_width - (pos_x + w)
        min_dist = min(dist_south, dist_north, dist_west, dist_east)
        center_threshold = min(room_width, room_depth) * 0.2

        if min_dist > center_threshold:
            target_wall = "center"
            alignment = "center"
            offset = 0.0
        elif min_dist == dist_south:
            target_wall = "south"
            rel = pos_x / max(room_width - w, 0.001)
            alignment = "left" if rel < 0.33 else ("right" if rel > 0.66 else "center")
            offset = round(dist_south, 2)
        elif min_dist == dist_north:
            target_wall = "north"
            rel = pos_x / max(room_width - w, 0.001)
            alignment = "left" if rel < 0.33 else ("right" if rel > 0.66 else "center")
            offset = round(dist_north, 2)
        elif min_dist == dist_west:
            target_wall = "west"
            rel = pos_z / max(room_depth - l, 0.001)
            alignment = "left" if rel < 0.33 else ("right" if rel > 0.66 else "center")
            offset = round(dist_west, 2)
        else:
            target_wall = "east"
            rel = pos_z / max(room_depth - l, 0.001)
            alignment = "left" if rel < 0.33 else ("right" if rel > 0.66 else "center")
            offset = round(dist_east, 2)

        return {
            "furniture_id": fid,
            "furniture_type": ftype,
            "size": {"w": w, "l": l, "h": h},
            "target_wall": target_wall,
            "alignment": alignment,
            "offset_from_wall": max(0.0, offset),
            "priority": old.get("priority", 99),
            "orientation": old.get("feng_shui_reasoning", ""),
        }

    async def score_layout(
        self,
        room_type: str,
        width: float,
        depth: float,
        furniture_placements: list[dict[str, Any]],
        deterministic_score: int = 0,
    ) -> LLMResponse:
        """Use LLM to judge aesthetic/usability quality (0-30 points).

        The deterministic portion (0-70) is computed by collision_checker and
        feng_shui_checker.  This method asks the LLM only for the remaining 30
        points covering visual balance, natural light usage, and furniture
        proportion.  The caller combines both scores:
            total = deterministic_score + aesthetic_score

        Args:
            room_type: Type of room.
            width: Room width in meters.
            depth: Room depth in meters.
            furniture_placements: List of placed furniture with positions.
            deterministic_score: Pre-computed code score (0-70) for context.

        Returns:
            LLMResponse with aesthetic_score (0-30) and recommendations.
        """
        prompt = SCORING_PROMPT.format(
            room_type=room_type,
            width=width,
            depth=depth,
            furniture_placements=self._format_placements(furniture_placements),
            deterministic_score=deterministic_score,
        )

        return await self._invoke_with_json_output(
            prompt,
            output_schema={
                "aesthetic_score": "int (0-30)",
                "aesthetic_breakdown": {
                    "visual_balance": "int (0-10)",
                    "natural_light_usage": "int (0-10)",
                    "furniture_proportion": "int (0-10)",
                },
                "recommendations": ["string - top improvements"],
            },
        )

    async def _invoke_with_json_output(
        self,
        prompt: str,
        output_schema: dict[str, Any],
    ) -> LLMResponse:
        """Invoke LLM and parse JSON output.

        Args:
            prompt: The user prompt.
            output_schema: Expected JSON schema for guidance.

        Returns:
            LLMResponse with parsed content.
        """
        try:
            # Add JSON instruction to prompt
            json_instruction = f"""

Please respond with a valid JSON object following this schema:
```json
{json.dumps(output_schema, indent=2)}
```

IMPORTANT: Respond ONLY with the JSON object, no additional text."""

            full_prompt = prompt + json_instruction

            messages = [
                self._system_message,
                HumanMessage(content=full_prompt),
            ]

            logger.debug(f"Invoking LLM with prompt length: {len(full_prompt)}")

            # Invoke the LLM
            response = await self._llm.ainvoke(messages)

            if not isinstance(response, AIMessage):
                return LLMResponse(
                    success=False,
                    error="Unexpected response type from LLM",
                )

            raw_response = response.content
            tokens_used = response.usage_metadata.get("total_tokens", 0) if response.usage_metadata else 0

            logger.debug(f"LLM response length: {len(raw_response)}, tokens: {tokens_used}")

            # Parse JSON from response
            try:
                # Try to extract JSON from the response
                content = self._extract_json(raw_response)

                return LLMResponse(
                    success=True,
                    content=content,
                    raw_response=raw_response,
                    tokens_used=tokens_used,
                )
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON from LLM response: {e}")
                return LLMResponse(
                    success=False,
                    raw_response=raw_response,
                    tokens_used=tokens_used,
                    error=f"Failed to parse JSON: {e}",
                )

        except Exception as e:
            logger.error(f"LLM invocation failed: {e}")
            return LLMResponse(
                success=False,
                error=str(e),
            )

    def _extract_json(self, text: str) -> Any:
        """Extract JSON from LLM response text.

        Args:
            text: Raw response text that may contain JSON.

        Returns:
            Parsed JSON object.
        """
        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON in code blocks
        import re
        json_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
        matches = re.findall(json_pattern, text)

        for match in matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue

        # Try to find JSON object/array directly
        for start, end in [('{', '}'), ('[', ']')]:
            start_idx = text.find(start)
            if start_idx != -1:
                # Find matching end
                depth = 0
                for i, char in enumerate(text[start_idx:]):
                    if char == start:
                        depth += 1
                    elif char == end:
                        depth -= 1
                        if depth == 0:
                            try:
                                return json.loads(text[start_idx:start_idx + i + 1])
                            except json.JSONDecodeError:
                                break

        # Last resort: raise error
        raise json.JSONDecodeError("No valid JSON found in response", text, 0)

    def _format_catalog(self, catalog: list[dict[str, Any]]) -> str:
        """Format furniture catalog for prompt."""
        lines = []
        for item in catalog[:20]:  # Limit to 20 items
            lines.append(
                f"- {item.get('id')}: {item.get('name')} "
                f"({item.get('category')}, {item.get('width')}x{item.get('depth')}m, "
                f"element: {item.get('feng_shui_element', 'unknown')}, "
                f"budget: {item.get('budget_level')})"
            )
        return "\n".join(lines)

    def _format_furniture_list(self, furniture: list[dict[str, Any]]) -> str:
        """Format furniture list for prompt."""
        lines = []
        for item in furniture:
            lines.append(
                f"- {item.get('name', item.get('id'))}: "
                f"{item.get('width')}x{item.get('depth')}m, "
                f"essential: {item.get('is_essential', False)}"
            )
        return "\n".join(lines)

    def _format_placements(self, placements: list[dict[str, Any]]) -> str:
        """Format furniture placements for prompt."""
        lines = []
        for p in placements:
            lines.append(
                f"- {p.get('name', p.get('id'))}: "
                f"position ({p.get('pos_x')}, {p.get('pos_z')}), "
                f"rotation {p.get('rotation')}°, "
                f"size {p.get('width')}x{p.get('depth')}m"
            )
        return "\n".join(lines)


def create_llm_agent(config: LLMConfig | None = None) -> FengShuiLLMAgent:
    """Factory function to create an LLM agent.

    Args:
        config: Optional LLM configuration.

    Returns:
        Configured FengShuiLLMAgent instance.
    """
    return FengShuiLLMAgent(config)
