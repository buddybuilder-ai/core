# 10 — LLM Prompts & Schemas

รายละเอียด LLM agents ทั้ง 2 ตัวของระบบ + prompts

## Overview

| Agent | File | Model | Max Tokens | Temp |
|---|---|---|---|---|
| RouterAgent | [router_agent.py](../src/modules/layout/infrastructure/llm/router_agent.py) | `LLM_MODEL_ROUTER` | 200 | 0.0 |
| FengShuiLLMAgent | [langchain_agent.py](../src/modules/layout/infrastructure/llm/langchain_agent.py) | `LLM_MODEL_LAYOUT` | 4096 | 0.1 |

Model provider ขึ้นอยู่กับ prefix ของ setting:
- `groq/model-name` → Groq API
- `ollama/model-name` → Ollama (local)
- anything else → OpenRouter

---

## RouterAgent

Single-LLM-call intent classifier

### Config

```python
@dataclass
class RouterConfig:
    model: str = settings.LLM_MODEL_ROUTER
    temperature: float = 0.0        # deterministic
    max_tokens: int = 200           # short JSON
    timeout: int = 15
```

### System Prompt

```
You are an intent classifier for a feng shui interior design assistant.

Classify the user message into exactly one of:
- "new_layout": user wants a brand new furniture layout for a room
- "modify": user wants to change a SPECIFIC piece of furniture in an existing
  layout (move/resize/swap/remove/add ONE item, OR rotate/orient a specific item
  e.g. "หันหัวเตียงไปทิศเหนือ", "turn bed north", "rotate wardrobe to face east",
  "ย้ายโซฟา", "move sofa")
- "rearrange_all": user wants ALL existing furniture repositioned/reorganized
  at once (e.g. "จัดห้องใหม่", "จัดวางใหม่ทั้งหมด", "จัดให้ถูกฮ้วงจุ้ย",
  "ปรับห้องให้ถูกหลัก", "rearrange", "reorganize the room", "redo the layout",
  "จัดห้องให้ลงตัว") — NOT when only one specific item is mentioned
- "question": user asks about feng shui or design principles (including greetings)
- "explain": user wants an explanation of the current layout
- "set_mode": user wants to change the personality mode of the assistant
  (e.g. "เปลี่ยนเป็นโหมดครู", "switch to fun mode", "use mentor mode", "โหมดสนุก")

Context clues:
- If has_existing_layout is false, use "new_layout" even if the message mentions
  placing specific furniture (e.g. "วางเตียงทางซ้าย", "put the sofa on the right").
  Those are placement preferences for a new layout, not modifications.
- "modify" is ONLY valid when has_existing_layout is true AND user asks to
  change a specific item. Rotating/orienting ONE item → always "modify".
- "rearrange_all" is ONLY valid when has_existing_layout is true AND user wants
  to reorganize ALL furniture. If the message names a specific piece → "modify".
- If has_existing_layout is false and user asks to "explain" → classify as "question".
- Short greetings → "question".

Respond ONLY with a valid JSON object — no other text:
{
  "intent": "<new_layout|modify|rearrange_all|question|explain|set_mode>",
  "confidence": <float 0.0-1.0>,
  "extracted_params": {}
}

For "modify" intent, extracted_params must be:
{
  "action": "<move|resize|swap|remove|add>",
  "target_furniture": "<bed|desk|sofa|wardrobe|chair>",
  "details": "<free text describing the change>"
}
For "set_mode" intent, extracted_params must be:
{
  "mode": "<mentor|buddy|fun>"
}
For all other intents, extracted_params = {}.
```

### User Message Format

```
has_existing_layout: {true|false}
Last conversation turns:
  user: ...
  assistant: ...
  (up to 4 turns, each truncated to 120 chars)

User message: {message}
```

### Result Parsing

```python
@dataclass
class RouterResult:
    intent: str                       # one of 6 intents
    confidence: float                 # 0.0–1.0
    extracted_params: dict[str, Any]  # depends on intent
    error: str | None                 # set if LLM failed
```

### Fallback Logic

1. **JSON parse fail** → fallback to `"question"`
2. **Invalid intent** (ไม่อยู่ใน `_VALID_INTENTS`) → fallback to `"question"`
3. **confidence < 0.5** → fallback to `"question"`
4. **LLM exception (timeout, etc.)** → fallback to `"question"`

### Keyword Override

```python
# Post-LLM: ถ้า message มี mode keyword → force set_mode
if intent != "set_mode":
    switched = detect_mode_switch(message)
    if switched:
        intent = "set_mode"
        extracted = {"mode": switched}
```

เหตุผล: LLM บางทีไม่ classify "เปลี่ยนเป็นโหมดครู" เป็น set_mode เพราะสั้น

### JSON Extraction Strategies (line 249–280)

LLM ไม่ค่อยทำตาม "only JSON" — ลอง parse 3 แบบ:

1. **Direct parse**: `json.loads(text)`
2. **Code block**: regex `` ```json ... ``` ``
3. **First `{...}` balanced**: walk character-by-character matching braces

---

## FengShuiLLMAgent

Main layout planner

### Config

```python
@dataclass
class LLMConfig:
    model: str = settings.LLM_MODEL_LAYOUT
    temperature: float = 0.1         # low variance
    max_tokens: int = 4096
    timeout: int = 60
    max_retries: int = 3
```

### Methods

1. `plan_layout()` — สำหรับ Step 2, Modifier, Rearrange
2. `explain_layout()` — สำหรับ Step 5
3. `select_furniture()` — legacy, ปัจจุบันใช้ `FurnitureSelector` แทน

---

## `plan_layout()` — Main Layout Planner

### Input

```python
async def plan_layout(
    room_type: str,
    width: float, depth: float,
    usable_area: float,
    doors: list[dict],              # [{wall, offset, width}]
    windows: list[dict],
    furniture_list: list[dict],     # [{id, name, width, depth, height, is_essential}]
    command_positions: list[dict],  # [{wall, x_range, z_range}]
    user_preferences: dict,         # มี user_message, placement_constraints, ...
    extra_context: dict = None,     # RAG context (optional)
) -> LLMResponse
```

### Output

```python
@dataclass
class LLMResponse:
    success: bool
    content: dict                   # {"placements": [...]}
    error: str | None
    raw_text: str
    usage: dict                     # token usage stats
```

### Placement Schema

```json
{
  "placements": [
    {
      "furniture_id": "bed_queen_001",
      "furniture_type": "bed",
      "size": {"w": 1.6, "l": 2.0, "h": 0.6},
      "target_wall": "north",
      "alignment": "center",
      "offset_from_wall": 0.05,
      "facing": "south",
      "priority": 1,
      "orientation": ""
    },
    ...
  ]
}
```

### Validation: `SemanticPlacementSchema` (Pydantic)

File: [services/layout_resolver.py](../src/modules/layout/application/services/layout_resolver.py)

```python
class SemanticPlacementSchema(BaseModel):
    furniture_id: str
    furniture_type: str
    size: dict  # {w, l, h}

    target_wall: Literal["north", "south", "east", "west", "center"]
    alignment: Literal["left", "center", "right"]
    offset_from_wall: float = Field(ge=0, le=5)
    priority: int = Field(ge=0, le=100)

    facing: str = ""
    orientation: str = ""
```

ไม่ผ่าน validation → item ถูก skip + log warning

---

## System Prompts

File: [infrastructure/llm/prompts.py](../src/modules/layout/infrastructure/llm/prompts.py)

### FENG_SHUI_SYSTEM_PROMPT

Core system prompt ใช้ทุกที่:

```
You are a feng shui interior design expert. Apply these 4 core principles:

1. Command Position
   - Bed, desk, sofa should be placed where person can see the door
     without being directly in line with it
   - Solid wall behind for support
   - Diagonal-from-door is ideal

2. Five Elements Balance (wood, fire, earth, metal, water)
   - Wood: bed, desk, shelves, plants
   - Fire: lamps, red accents
   - Earth: sofa, dining table, rugs (earthy colors)
   - Metal: chairs with metal frames, TV stand
   - Water: mirrors, fountains

3. Chi Flow (energy circulation)
   - Keep pathways at least 60cm wide
   - No sharp corners pointing at seating
   - Curved arrangements preferred over straight lines

4. Sha Chi Avoidance (negative energy)
   - Avoid bed facing door directly
   - Avoid sleeping under beams or sloped ceilings
   - Mirrors should not face the bed
   - TVs/screens should not face the bed in bedrooms

Bedroom Hard Rules:
- Bed must NOT be directly aligned with door opening (poison arrow)
- Bed headboard must be against a solid wall
- No mirror facing the bed
- No TV facing the bed (or cover when not watching)
- No bed under a window
- No bed directly under a ceiling beam
- Nightstands flanking the bed (ideally 2)
- Balance masculine/feminine energy via matching pair furniture
- No sharp corners pointing at the bed
```

### LAYOUT_PLANNING_PROMPT

User prompt template สำหรับ `plan_layout()`:

```
Place ALL the following furniture in the room:
{furniture_list_formatted}

Room info:
- Type: {room_type}
- Size: {width}m × {depth}m (usable area: {usable_area} sqm)
- Doors: {doors_formatted}
- Windows: {windows_formatted}
- Command positions: {command_positions_formatted}

User preferences:
{user_preferences}

RAG context (reference knowledge):
{extra_context}

Output rules:
1. You MUST place every furniture item in the list — do NOT skip any
2. For each item, specify:
   - furniture_id (exact from list)
   - furniture_type
   - size (just copy from input)
   - target_wall: "north"|"south"|"east"|"west"|"center"
   - alignment: "left"|"center"|"right"
   - offset_from_wall: 0.0 to 0.3 meters
   - facing: "north"|"south"|"east"|"west" (direction front faces, optional)
   - priority: 1 = place first (command position items), higher = later

3. Follow these Furniture Grouping Rules:
   - Nightstand on same wall as bed
   - TV stand opposite sofa/bed
   - Coffee table in front of sofa
   - Office chair at desk's front face
   - Dining chairs around dining table

4. Follow these Alignment Rules:
   - Large items (bed, sofa) → alignment="center" typically
   - Avoid alignment="right" for large items (corner crowding)
   - Use "left"/"right" for smaller accent pieces

5. Respect user's explicit placement constraints in user_preferences

Output ONLY valid JSON:
{
  "placements": [...]
}
```

### MODIFIER_EXPLANATION_PROMPT

For ModifierAgent:

```
You moved this furniture:
- ID: {furniture_id}
- From: {before_summary}
- To: {after_summary}

User asked: "{user_message}"

Write a 1-2 sentence reply in Thai that:
- Echoes the user's own phrasing (if they said "ขวางประตู", use "ขวางประตู")
- Confirms what was done
- Does NOT mention feng shui warnings (sha chi, bad energy, etc.)
- Does NOT suggest alternative placements

Reply in casual Thai, no markdown, no JSON.
```

### EXPLANATION_PROMPT (Step 5)

```
Explain this room layout in Thai, using {personality_mode} personality:

Room: {room_type} {width}×{depth}m
Placed furniture:
{items_summary}

Conflicts detected: {conflicts_summary}
Repairs applied: {repairs_summary}

Feng shui score: {total_score}/100 (grade {grade})
- Command Position: {command_position}/30
- Five Elements: {five_elements}/20
- Chi Flow: {chi_flow}/25
- Sha Chi Avoidance: {sha_chi_avoidance}/25

{kua_line}

Remaining issues: {remaining_issues}

Personality styles:
- buddy: friendly, casual, emoji ok
- mentor: formal, informative, cite principles
- fun: playful, jokes allowed, lighter tone

Write in Thai, 3-5 sentences, clear and helpful.
```

---

## Error Handling

### Retry Logic

```python
# FengShuiLLMAgent uses max_retries=3
for attempt in range(max_retries):
    try:
        response = await llm.ainvoke(messages)
        parsed = parse_json(response)
        if validate_schema(parsed):
            return LLMResponse(success=True, content=parsed)
    except TimeoutError:
        if attempt == max_retries - 1:
            return LLMResponse(success=False, error="Timeout")
    except ValidationError as e:
        # ลอง parse แบบอื่น หรือ return failed
```

### Fallback Behavior

**Pipeline Step 2 — LLM fails:**
```python
# Heuristic fallback — stack all along south wall
x = 0.1
for f in furniture_list:
    place(f, x=x, z=room.depth - f.depth - 0.1, rotation=180)
    x += f.width + 0.1
```

**RearrangeAgent — LLM fails:**
```python
yield MODIFIER_COMPLETED {
    "warning": f"LLM planning failed: {error}",
    "collisions_after": 0
}
# ไม่เปลี่ยน layout
```

**ModifierAgent — LLM ไม่จำเป็น (ใช้แค่ explainer):**
ถ้า explainer fail → ไม่มี explanation แต่ layout อัปเดตปกติ

---

## Model Selection Guidelines

### Router (fast, cheap)
- `anthropic/claude-haiku-4-5` — แนะนำ
- `groq/llama-3.1-8b-instant`
- `ollama/llama3.2:3b`

เกณฑ์: ต้องเร็ว (< 2s), JSON output ได้, ราคาถูก

### Layout (quality matters)
- `anthropic/claude-sonnet-4-6` — ดีที่สุด
- `anthropic/claude-opus-4-7` — quality สูงสุด, ช้า
- `openai/gpt-4o-mini` — rough baseline

เกณฑ์: เข้าใจ spatial reasoning, JSON schema compliance, reasoning ได้ดี

---

## Prompt Engineering Notes

1. **Keep system prompt stable** — ย้ายข้อมูล dynamic ไป user message
2. **Use explicit JSON schemas** — LLM respect structure ดีกว่า free-form
3. **"You MUST" repetition works** — LLM ชอบ skip, ต้องย้ำหลายๆ รอบ
4. **Echo user phrasing ใน modifier** — ถ้า translate คำ → ผู้ใช้รู้สึกว่าระบบไม่เข้าใจ
5. **Personality modes แค่ใน explainer** — plan_layout ไม่ต้องมีโทน
6. **Low temperature (0.0-0.1)** — spatial reasoning ต้อง deterministic
