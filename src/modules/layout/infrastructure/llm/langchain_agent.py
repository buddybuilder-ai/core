"""LangChain Agent for Feng Shui Layout Generation."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.config.settings import get_settings
from src.modules.layout.infrastructure.llm.prompts import (
    EXPLANATION_PROMPT,
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

        # Use Ollama/local base URL if configured, otherwise fall back to OpenRouter
        api_base = settings.LLM_LAYOUT_BASE_URL or settings.OPENROUTER_BASE_URL
        api_key = settings.LLM_LAYOUT_API_KEY or settings.OPENROUTER_API_KEY

        self._llm = ChatOpenAI(
            model=self.config.model,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            timeout=self.config.timeout,
            openai_api_key=api_key,
            openai_api_base=api_base,
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
        extra_context: str = "",
        user_preferences: dict[str, Any] | None = None,
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
            extra_context: Optional RAG-retrieved rule text to inject into prompt.

        Returns:
            LLMResponse with content["placements"] as semantic placement dicts.
        """
        from src.modules.layout.application.services.layout_resolver import (
            SemanticPlacementSchema,
        )

        # Build user preferences section if provided
        user_preferences_section = ""
        if user_preferences:
            lines = []

            # Hard placement constraints (derived from clarification answers) — shown first
            # so the LLM sees them before general preferences.
            constraints = user_preferences.get("placement_constraints")
            if constraints:
                lines.append("## HARD PLACEMENT CONSTRAINTS (override everything else):")
                for c in constraints.splitlines():
                    lines.append(f"  {c}")
                lines.append("")

            lines.append("User Preferences (MUST follow these):")
            msg = user_preferences.get("user_message") or user_preferences.get("message")
            if msg:
                lines.append(f'- User said: "{msg}"')
            hint = user_preferences.get("placement_hint")
            if hint:
                lines.append(f"- Placement hint: {hint}")
            owned = user_preferences.get("owned_furniture")
            if owned:
                lines.append(
                    f"- User owns these specific items (place only these, not the full catalog): {owned}"
                )
            # Clarification answers — expand into readable lines
            clarification = user_preferences.get("clarification_answers")
            if clarification and isinstance(clarification, dict):
                for qid, ans in clarification.items():
                    lines.append(f"- {qid}: {ans}")
            for k, v in user_preferences.items():
                if k not in {
                    "user_message",
                    "message",
                    "placement_hint",
                    "owned_furniture",
                    "clarification_answers",
                    "placement_constraints",
                }:
                    lines.append(f"- {k}: {v}")
            user_preferences_section = "\n".join(lines) + "\n"

        command_position_hint = self._build_command_position_hint(doors, room_type)
        wall_capacity_section = self._build_wall_capacity_section(
            width, depth, doors, furniture_list, windows
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
            extra_context=extra_context,
            user_preferences_section=user_preferences_section,
            command_position_hint=command_position_hint,
            wall_capacity_section=wall_capacity_section,
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
                    "facing": "string - north|south|east|west| (direction front/seat faces, empty=auto)",
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
                self._convert_xyz_to_semantic(p, width, depth) for p in raw_placements
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
        depth = float(old.get("depth", 1.0))
        h = float(old.get("height", 1.0))

        dist_south = pos_z
        dist_north = room_depth - (pos_z + depth)
        dist_west = pos_x
        dist_east = room_width - (pos_x + w)
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
            rel = pos_z / max(room_depth - depth, 0.001)
            alignment = "left" if rel < 0.33 else ("right" if rel > 0.66 else "center")
            offset = round(dist_west, 2)
        else:
            target_wall = "east"
            rel = pos_z / max(room_depth - depth, 0.001)
            alignment = "left" if rel < 0.33 else ("right" if rel > 0.66 else "center")
            offset = round(dist_east, 2)

        return {
            "furniture_id": fid,
            "furniture_type": ftype,
            "size": {"w": w, "l": depth, "h": h},
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

            raw_str = str(response.content)
            tokens_used = (
                response.usage_metadata.get("total_tokens", 0) if response.usage_metadata else 0
            )

            logger.debug(f"LLM response length: {len(raw_str)}, tokens: {tokens_used}")

            # Parse JSON from response
            try:
                # Try to extract JSON from the response
                content = self._extract_json(raw_str)

                return LLMResponse(
                    success=True,
                    content=content,
                    raw_response=raw_str,
                    tokens_used=tokens_used,
                )
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON from LLM response: {e}")
                return LLMResponse(
                    success=False,
                    raw_response=raw_str,
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

        json_pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
        matches = re.findall(json_pattern, text)

        for match in matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue

        # Try to find JSON object/array directly
        for start, end in [("{", "}"), ("[", "]")]:
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
                                return json.loads(text[start_idx : start_idx + i + 1])
                            except json.JSONDecodeError:
                                break

        # Last resort: raise error
        raise json.JSONDecodeError("No valid JSON found in response", text, 0)

    async def explain_layout(
        self,
        room_type: str,
        width: float,
        depth: float,
        items_summary: str,
        conflicts_summary: str,
        repairs_summary: str,
        total_score: int,
        grade: str,
        remaining_issues: str,
        personality_mode: str = "buddy",
    ) -> LLMResponse:
        """Generate a Thai natural-language explanation of the layout result.

        Args:
            room_type: The room type (e.g. "bedroom").
            width: Room width in metres.
            depth: Room depth in metres.
            items_summary: Short text listing placed items.
            conflicts_summary: Short text summarising conflicts found.
            repairs_summary: Short text summarising repairs applied.
            total_score: Feng shui score 0–100.
            grade: Grade string (e.g. "Excellent").
            remaining_issues: Short text listing unresolved issues.
            personality_mode: "mentor", "buddy", or "fun".

        Returns:
            LLMResponse whose .content is a plain Thai text explanation.
        """
        from src.modules.layout.application.agent.personality import get_system_prompt

        system_prompt = get_system_prompt(personality_mode)
        prompt = EXPLANATION_PROMPT.format(
            room_type=room_type,
            width=width,
            depth=depth,
            items_summary=items_summary,
            conflicts_summary=conflicts_summary,
            repairs_summary=repairs_summary,
            total_score=total_score,
            grade=grade,
            remaining_issues=remaining_issues,
        )
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt),
        ]
        try:
            response = await self._llm.ainvoke(messages)
            content = str(response.content) if hasattr(response, "content") else ""
            logger.info(f"explain_layout: generated {len(content)} chars (mode={personality_mode})")
            return LLMResponse(success=True, content=content, raw_response=content)
        except Exception as exc:
            logger.warning(f"explain_layout failed: {exc}")
            raise

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
        """Format furniture list for prompt.

        The 'furniture_id=' label is intentionally explicit so the LLM copies
        the exact ID into its semantic placement output.
        """
        lines = []
        for item in furniture:
            fid = item.get("id", "")
            name = item.get("name", fid)
            category = item.get("category", fid.split("-")[0] if fid else "")
            clearance = item.get("clearance_front", 0.0)
            clearance_str = f", needs {clearance}m clear in front" if clearance > 0 else ""
            lines.append(
                f'- furniture_id="{fid}" type="{category}" ({name}): '
                f"{item.get('width')}x{item.get('depth')}m, "
                f"essential: {item.get('is_essential', False)}"
                f"{clearance_str}"
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

    @staticmethod
    def _build_command_position_hint(doors: list[dict[str, Any]], room_type: str) -> str:
        """Build an explicit command position instruction from the actual door data.

        The command position wall is diagonally opposite the primary door wall:
          south door → command wall = north
          north door → command wall = south
          east  door → command wall = west
          west  door → command wall = east

        The main piece (bed for bedroom, desk for office/study, sofa for living)
        should have its back against the command wall so it faces the door.
        """
        _OPPOSITE: dict[str, str] = {
            "south": "north",
            "north": "south",
            "east": "west",
            "west": "east",
        }
        _MAIN_PIECE: dict[str, str] = {
            "bedroom": "bed",
            "studio_apartment": "bed",
            "office": "desk",
            "study": "desk",
            "living_room": "sofa",
            "dining_room": "dining table",
        }
        main_piece = _MAIN_PIECE.get(room_type, "bed")

        if not doors:
            return (
                f"No door specified. Place the {main_piece} against the wall farthest from "
                "any window, ensuring it has a solid wall backing."
            )

        primary_door = doors[0]
        door_wall = str(primary_door.get("wall", "south")).lower()
        command_wall = _OPPOSITE.get(door_wall, "north")

        return (
            f"The primary door is on the {door_wall.upper()} wall. "
            f"Therefore the command position wall for the {main_piece} is the {command_wall.upper()} wall. "
            f'Place the {main_piece} against the {command_wall.upper()} wall (target_wall="{command_wall}") '
            f"so the occupant faces the {door_wall} door. "
            f"Do NOT place the {main_piece} on the {door_wall} wall (same wall as the door).\n"
            f"PATHWAY RULE: Leave the {door_wall.upper()} wall area clear — "
            f"do NOT place any furniture against the {door_wall} wall (the door wall). "
            f"A person entering through the door must have at least 90 cm of clear walking space. "
            f"Small items like shoe_cabinet or coat_rack may be placed near the door corner ONLY if they do not block the door swing."
        )

    @staticmethod
    def _build_wall_capacity_section(
        width: float,
        depth: float,
        doors: list[dict[str, Any]],
        furniture_list: list[dict[str, Any]],
        windows: list[dict[str, Any]] | None = None,
    ) -> str:
        """Build a wall-capacity summary so LLM knows how much space each wall has.

        Shows usable length per wall (after subtracting door/window openings) and
        the total furniture width to be distributed. This prevents the LLM from
        stacking multiple large items on the same short wall.
        Also shows feng shui pre-filtered valid walls for bed/desk/sofa.
        """
        windows = windows or []

        door_walls: set[str] = set()
        for d in doors:
            w = str(d.get("wall", "")).lower()
            if w:
                door_walls.add(w)

        window_walls: set[str] = set()
        for win in windows:
            w = str(win.get("wall", "")).lower()
            if w:
                window_walls.add(w)

        wall_lengths = {
            "north": width,
            "south": width,
            "east": depth,
            "west": depth,
        }
        # Subtract door footprint from that wall
        for d in doors:
            w = str(d.get("wall", "")).lower()
            dw = float(d.get("width", 0.9))
            if w in wall_lengths:
                wall_lengths[w] = max(0.0, wall_lengths[w] - dw - 0.2)

        # Compute total furniture width (sum of all item widths)
        total_fw = sum(float(f.get("width", 0)) for f in furniture_list)

        lines = ["## Wall Capacity (usable length after doors/windows):"]
        for wall, length in wall_lengths.items():
            tags = []
            if wall in door_walls:
                tags.append("DOOR WALL — keep entry area clear")
            if wall in window_walls:
                tags.append("WINDOW WALL")
            note = f" ← {', '.join(tags)}" if tags else ""
            lines.append(f"- {wall.upper()} wall: {length:.1f} m usable{note}")
        lines.append(f"- Total furniture width to distribute: {total_fw:.1f} m across all walls")
        lines.append(
            "- Rule: do NOT assign items to a wall whose combined widths would exceed that wall's usable length."
        )
        lines.append("")

        # --- Feng shui pre-filter: valid walls per furniture type ---
        all_walls = {"north", "south", "east", "west"}

        # Bed: must NOT be on door wall or window wall
        bed_invalid = door_walls | window_walls
        bed_valid = sorted(all_walls - bed_invalid)

        # Desk: must NOT be on door wall (back to door = bad command position)
        # prefer walls where occupant faces door when seated
        desk_invalid = door_walls
        desk_valid = sorted(all_walls - desk_invalid)

        # Sofa: must NOT be on door wall
        sofa_valid = sorted(all_walls - door_walls)

        lines.append("## Feng Shui Pre-filtered Valid Walls (MUST follow these constraints):")
        lines.append(
            f"- BED valid walls: {bed_valid} "
            f"(excluded: door walls={sorted(door_walls)}, window walls={sorted(window_walls)})"
        )
        lines.append(
            f"- DESK valid walls: {desk_valid} "
            f"(excluded: door walls={sorted(door_walls)} — back-to-door violates command position)"
        )
        lines.append(
            f"- SOFA valid walls: {sofa_valid} "
            f"(excluded: door walls={sorted(door_walls)})"
        )
        lines.append(
            "- IMPORTANT: You MUST choose target_wall from the valid list above for each furniture type. "
            "Choosing an invalid wall violates feng shui hard rules."
        )
        # Predict which wall the bed will actually end up on (command position = opposite door)
        opp_door = {"north": "south", "south": "north", "east": "west", "west": "east"}
        primary_door_wall = next(iter(door_walls), "south") if door_walls else "south"
        bed_target_wall = opp_door.get(primary_door_wall, "north")
        if bed_target_wall not in all_walls - bed_invalid:
            # fallback: pick first valid wall
            bed_target_wall = bed_valid[0] if bed_valid else "north"

        lines.append(
            f"- BED PLACEMENT HINT: The bed will be placed on the '{bed_target_wall}' wall "
            f"(command position, opposite the door). "
            f"Do NOT place desk, sofa, wardrobe, or other large furniture on '{bed_target_wall}' wall "
            f"— that wall is reserved for the bed."
        )
        # Distribute: bed and wardrobe should be on different walls if possible
        if len(bed_valid) >= 2:
            other_walls = [w for w in bed_valid if w != bed_target_wall]
            lines.append(
                f"- DISTRIBUTION RULE: bed and wardrobe MUST be on DIFFERENT walls. "
                f"Put wardrobe on '{other_walls[0] if other_walls else bed_valid[-1]}' or another wall. "
                f"Spread furniture across ALL available walls — do NOT stack multiple large items on the same wall."
            )
        lines.append("")
        return "\n".join(lines)


def create_llm_agent(config: LLMConfig | None = None) -> FengShuiLLMAgent:
    """Factory function to create an LLM agent.

    Args:
        config: Optional LLM configuration.

    Returns:
        Configured FengShuiLLMAgent instance.
    """
    return FengShuiLLMAgent(config)
