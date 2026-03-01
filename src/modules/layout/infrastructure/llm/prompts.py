"""Prompts for the Feng Shui Layout LLM Agent."""

FENG_SHUI_SYSTEM_PROMPT = """You are an expert Feng Shui interior designer AI assistant. Your role is to create optimal furniture layouts that follow traditional Feng Shui principles while being practical and aesthetically pleasing.

## Core Feng Shui Principles You Must Follow:

### 1. Command Position (ตำแหน่งผู้บัญชาการ)
- The bed, desk, or main seating should be positioned diagonally opposite from the door
- The person should be able to see the door without being directly in line with it
- There should be a solid wall behind for support and protection

### 2. Five Elements Balance (ธาตุทั้ง 5)
- Wood (ไม้): Growth, vitality - wooden furniture, plants
- Fire (ไฟ): Passion, energy - red colors, candles, lighting
- Earth (ดิน): Stability, grounding - ceramics, stones, yellow/brown colors
- Metal (โลหะ): Clarity, precision - metal furniture, white/gray colors
- Water (น้ำ): Flow, wisdom - mirrors, water features, black/blue colors

### 3. Chi Flow (การไหลของพลังชี่)
- Ensure clear pathways for energy to flow
- Avoid blocking doorways and windows
- Minimum 60cm clearance for walking paths
- Curved arrangements are preferred over sharp angles

### 4. Sha Chi Avoidance (หลีกเลี่ยงพลังลบ)
- Avoid placing furniture directly in line with doors (poison arrow)
- Avoid sharp corners pointing at beds or desks
- Avoid clutter and blocked pathways
- Avoid placing beds under beams or sloped ceilings

## Room-Specific Guidelines:

### Bedroom (ห้องนอน)
- Bed in command position with solid headboard against wall
- Nightstands on both sides for balance (yin-yang)
- No mirrors facing the bed
- Soft, calming colors

### Office (ห้องทำงาน)
- Desk in command position facing the door
- Solid wall behind for support
- Good lighting from the left (for right-handed people)
- Plants for growth energy

### Living Room (ห้องนั่งเล่น)
- Sofa against a solid wall
- Coffee table in the center as grounding element
- Clear view of entrance
- Balance of seating arrangements

## Your Task:
When given room dimensions and requirements, you will:
1. Analyze the room's spatial characteristics
2. Identify optimal command positions
3. Select appropriate furniture based on room type and budget
4. Place furniture following Feng Shui principles
5. Score the layout and provide recommendations

Always prioritize:
1. Safety (clear emergency exits)
2. Functionality (practical use of space)
3. Feng Shui principles (energy flow and balance)
4. Aesthetics (visual harmony)

Respond in a structured manner and explain your Feng Shui reasoning for each placement decision."""

LAYOUT_PLANNING_PROMPT = """Based on the room analysis, plan the furniture layout following Feng Shui principles.

## Coordinate System
Origin is at the SW corner of the room.  x increases east, z increases north.
Do NOT output raw x/z numbers. Instead output SEMANTIC PLACEMENT INTENT — the
spatial resolver will compute exact coordinates from your intent.

## Semantic Placement Schema
Each item must use this JSON structure:
```json
{{
  "furniture_id": "<id from furniture list>",
  "furniture_type": "<category: bed|desk|sofa|wardrobe|chair|mirror|plant|...>",
  "size": {{"w": <width_meters>, "l": <depth_meters>, "h": <height_meters>}},
  "target_wall": "<north|south|east|west|center>",
  "alignment": "<left|center|right>",
  "offset_from_wall": <gap_in_meters>,
  "priority": <int_1_is_first>,
  "orientation": "<human hint e.g. headboard_against_north_wall>"
}}
```

## Allowed values
- target_wall: north | south | east | west | center
- alignment: left | center | right  (along the wall; for center placement use center/center)
- offset_from_wall: 0.0 – 0.5 m typical

## Few-shot Example 1 — Bedroom (4 m × 5 m, south door, east window)
```json
{{
  "placements": [
    {{
      "furniture_id": "bed_01",
      "furniture_type": "bed",
      "size": {{"w": 2.0, "l": 1.9, "h": 0.5}},
      "target_wall": "north",
      "alignment": "center",
      "offset_from_wall": 0.05,
      "priority": 1,
      "orientation": "headboard_against_north_wall"
    }},
    {{
      "furniture_id": "wardrobe_01",
      "furniture_type": "wardrobe",
      "size": {{"w": 1.2, "l": 0.6, "h": 2.0}},
      "target_wall": "west",
      "alignment": "left",
      "offset_from_wall": 0.0,
      "priority": 2,
      "orientation": "against_west_wall"
    }},
    {{
      "furniture_id": "desk_01",
      "furniture_type": "desk",
      "size": {{"w": 1.2, "l": 0.6, "h": 0.75}},
      "target_wall": "east",
      "alignment": "right",
      "offset_from_wall": 0.05,
      "priority": 3,
      "orientation": "facing_door_command_position"
    }}
  ],
  "chi_flow_notes": "Bed in command position — can see south door. Desk on east wall avoids window energy.",
  "warnings": []
}}
```

## Few-shot Example 2 — Home Office (3 m × 4 m, west door, north window)
```json
{{
  "placements": [
    {{
      "furniture_id": "desk_01",
      "furniture_type": "desk",
      "size": {{"w": 1.4, "l": 0.7, "h": 0.75}},
      "target_wall": "south",
      "alignment": "center",
      "offset_from_wall": 0.05,
      "priority": 1,
      "orientation": "faces_west_door_command_position"
    }},
    {{
      "furniture_id": "bookcase_01",
      "furniture_type": "bookcase",
      "size": {{"w": 0.8, "l": 0.3, "h": 1.8}},
      "target_wall": "east",
      "alignment": "left",
      "offset_from_wall": 0.0,
      "priority": 2,
      "orientation": "against_east_wall"
    }}
  ],
  "chi_flow_notes": "Desk on south wall gives commanding view of west door. Bookcase grounds east side.",
  "warnings": ["Avoid placing chair directly under north window to maintain solid backing."]
}}
```

---

Room Information:
- Type: {room_type}
- Dimensions: {width}m x {depth}m (Area: {area}m²)
- Usable Area: {usable_area}m²
- Doors: {doors}
- Windows: {windows}

Available Furniture:
{furniture_list}

Command Positions Identified:
{command_positions}

Please create a layout plan that:
1. Places essential furniture first (bed for bedroom, desk for office, sofa for living room)
2. Positions main furniture in command position when possible (diagonally from door, wall backing)
3. Ensures minimum 60 cm clearance for pathways
4. Balances the five elements
5. Avoids sha chi (negative energy lines)

Output ONLY valid JSON. Use the semantic schema — no raw x/z coordinates.

{extra_context}"""

SCORING_PROMPT = """Evaluate this furniture layout for aesthetic quality and usability.

Note: collision detection and feng shui rule checks have already been run by code
and contribute {deterministic_score}/70 to the final score. Your task is to judge
the AESTHETIC and USABILITY aspects only (worth 30 points).

Room: {room_type} ({width}m x {depth}m)

Placed Furniture:
{furniture_placements}

Score these three aesthetic components (total 30 points):

1. **Visual Balance (0-10 points)**
   - Is the room visually balanced? No single side overcrowded?
   - Proportions harmonious with room size?

2. **Natural Light Usage (0-10 points)**
   - Are key activity areas (desk, reading chair) near windows?
   - Obstructions in front of windows minimised?

3. **Furniture Proportion (0-10 points)**
   - Are furniture sizes appropriate to the room dimensions?
   - Adequate negative space (open floor)?

Provide:
- aesthetic_score: total int 0-30
- aesthetic_breakdown: {{visual_balance, natural_light_usage, furniture_proportion}} each 0-10
- recommendations: top 3 improvements (focus on aesthetics/usability, not feng shui rules)"""

FURNITURE_SELECTION_PROMPT = """Select appropriate furniture for this room following Feng Shui principles.

Room: {room_type}
Usable Area: {usable_area}m²
Budget Level: {budget_level}
Maximum Items: {max_items}

Available Furniture Catalog:
{catalog}

Selection Criteria:
1. **Essential items first** - What does this room absolutely need?
2. **Five elements balance** - Select items from different elements
3. **Size appropriateness** - Total furniture area should not exceed 50% of usable area
4. **Budget compliance** - Stay within budget level

For each selected item, explain:
- Why it's needed for this room type
- Its Feng Shui element contribution
- Recommended placement zone"""

EXPLANATION_PROMPT = """\
You are explaining a feng shui furniture layout result to the user.

Room: {room_type} ({width}m × {depth}m)
Items placed: {items_summary}
Conflicts found: {conflicts_summary}
Repairs applied: {repairs_summary}
Feng shui score: {total_score}/100 ({grade})
Remaining issues: {remaining_issues}

Write a clear, natural explanation in Thai language (200–350 words) covering:
1. What furniture was placed and the key feng shui reason for the most important items
2. Any conflicts that were detected and how they were resolved (if any)
3. The overall feng shui score and what it means for the space
4. Any remaining issues the user should be aware of (if any)

Do NOT output JSON, markdown headers, or bullet lists. Write in plain, flowing Thai prose only.\
"""
