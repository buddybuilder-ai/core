# 02 — Chat Router & Intent Dispatch

Endpoint: `POST /api/chat/stream`
File: [core/src/api/v1/chat/router.py](../src/api/v1/chat/router.py)

## Handler: `chat_stream()` (line 71)

เปิด `StreamingResponse` ส่ง SSE events ผ่าน `event_generator()` (line 90)

### Flow ทีละขั้น

```
1. detect_mood(message)          ← keyword-based, ไม่ใช้ LLM
2. RouterAgent.classify()        ← LLM call #1
3. Empty-room guard              ← ตรวจ current_layout ว่างไหม
4. Clarification gate            ← get_pending_questions()
5. _apply_clarification_answers  ← merge คำตอบเข้า room_spec
6. Dispatch ตาม intent           ← 6 handlers
```

## 1. Mood Detection (line 101)

```python
mood = detect_mood(request.message)
```

- อยู่ใน [agent/personality.py](../src/modules/layout/application/agent/personality.py)
- Keyword matching (ไม่ใช้ LLM): "เครียด", "กังวล", "happy", etc.
- ใช้ปรับโทนคำตอบใน question/explain handler

## 2. Intent Classification (line 104)

```python
router_agent = RouterAgent()
result = await router_agent.classify(
    message=request.message,
    has_existing_layout=bool(request.current_layout),
    conversation_history=request.conversation_history[-4:],
)
```

- ส่ง event `router_classified` ทันทีหลังจำแนก (line 111–118)
- ดูรายละเอียดที่ [10-llm-prompts.md](./10-llm-prompts.md#routeragent)

**Intents ที่เป็นไปได้:**

| Intent | เงื่อนไข | ส่งไป |
|---|---|---|
| `new_layout` | ห้องยังว่าง หรือผู้ใช้อยากได้ layout ใหม่ | `PipelineOrchestrator` |
| `modify` | มี layout + ขอแก้ชิ้นเดียว | `ModifierAgent` |
| `rearrange_all` | มี layout + ขอจัดใหม่ทั้งหมด | `RearrangeAgent` |
| `question` | ถามเรื่องฮวงจุ้ย | `_answer_question()` (RAG) |
| `explain` | ขอคำอธิบาย layout ปัจจุบัน | `ExplainerStep` |
| `set_mode` | เปลี่ยน personality | inline handler |

## 3. Empty-Room Guard (line 120–134)

```python
if result.intent in {"new_layout", "rearrange_all", "modify"} and not request.current_layout:
    # ห้องยังว่าง → ไม่รัน pipeline
    yield ANSWER: "ห้องยังว่างอยู่เลยครับ ลองเพิ่มเฟอร์นิเจอร์ก่อน..."
    return
```

เหตุผล: ถ้าห้องว่างแล้วรัน pipeline → LLM จะสุ่มเดาว่าควรมีเฟอร์นิเจอร์อะไร ไม่ตรงกับที่ผู้ใช้ต้องการ

## 4. Clarification Gate (line 136–150)

```python
pending_questions = get_pending_questions(
    intent=result.intent,
    clarification_answers=request.clarification_answers,
    has_existing_layout=bool(request.current_layout),
)
if pending_questions:
    yield CLARIFICATION_NEEDED
    return
```

จาก [services/clarification_gate.py](../src/modules/layout/application/services/clarification_gate.py):

**Bypass intents** (ไม่ต้องถาม): `rearrange_all`, `explain`, `question`, `set_mode`, `modify` — bypass เฉพาะเมื่อ `has_existing_layout=True`

**ถามเฉพาะ REQUIRED:** คำถาม `RECOMMENDED` ที่ user ไม่ตอบ จะใช้ `default_value` แทน (ไม่ loop ถามซ้ำ)

**Room type สำหรับถาม:** hardcoded เป็น `"studio_apartment"` (ดู [11-entities-catalog.md](./11-entities-catalog.md#clarification-questions))

## 5. Merge Clarification Answers (line 152–255)

`_apply_clarification_answers(room_spec, answers)` — แปลงคำตอบภาษาไทยเป็น `placement_hint` string ที่ LLM อ่านได้

### รายการคำถามหลัก

| Question ID | ถามว่า | Action |
|---|---|---|
| `sleep_zone_preference` | โซนนอนควรอยู่ไหน | แปลงเป็น `target_wall=<wall>` constraint |
| `sofa_bed_or_separate` | โซฟาเตียงหรือเตียงแยก | ล็อก furniture_id ที่ต้องใช้ |
| `work_area_needed` | ต้องการโต๊ะทำงานไหม | include/exclude `folding_desk` |
| `budget_level` | งบเท่าไร | `spec["budget_level"] = low/medium/high` |

### Logic การแปลง sleep_zone_preference

```python
_OPPOSITE_WALL = {
    "south": "north", "north": "south",
    "east": "west", "west": "east",
}
_SIDE_WALLS = {
    "south": ("west", "east"),  # ประตูใต้ → ซ้าย=west, ขวา=east
    "north": ("west", "east"),
    "east": ("south", "north"),
    "west": ("south", "north"),
}

door_wall = doors[0].wall  # ผนังประตูหลัก
opp = _OPPOSITE_WALL[door_wall]
sides = _SIDE_WALLS[door_wall]

if "ตรงข้ามประตู" in sleep_ans:
    → target_wall = opp (command position)
elif "ซ้าย" in sleep_ans:
    → target_wall = sides[0]
elif "ขวา" in sleep_ans:
    → target_wall = sides[1]
```

ผลลัพธ์ถูกเก็บเป็น string ใน `spec["user_preferences"]["placement_constraints"]`:

```
SLEEP ZONE: sofa_bed / bed MUST use target_wall=north
(wall opposite the south door — command position)
FURNITURE TYPE: use sofa_bed (id=sofa_bed_001 or sofa_bed_002)...
WORK ZONE: include a folding_desk on the west or east wall...
```

## 6. Dispatch Tree (line 257–343)

### `set_mode` (line 258–268)

```python
new_mode = extracted_params.get("mode") or detect_mode_switch(message) or "buddy"
yield MODE_CHANGED {"mode": new_mode}
```

Inline handler, ไม่รัน pipeline

### `new_layout` (line 270–285)

```python
room_spec = _apply_clarification_answers(request.room_spec, answers)
room_spec["user_preferences"]["user_message"] = request.message
orchestrator = PipelineOrchestrator(PipelineConfig())
async for event in orchestrator.run(room_spec, mode=request.mode):
    yield event.to_sse()
```

รัน **5-step pipeline เต็ม** ดู [03-pipeline.md](./03-pipeline.md)

### `modify` (line 287–301)

```python
modifier = ModifierAgent()
async for event in modifier.apply(
    current_layout=request.current_layout,
    room_spec=request.room_spec,
    modification_request=request.message,
    extracted_params=result.extracted_params,  # {action, target_furniture, details}
):
    yield event.to_sse()
```

ไม่รัน pipeline — แก้เฉพาะชิ้นที่ระบุ ดู [04-modifier-rearrange.md](./04-modifier-rearrange.md#modifieragent)

### `rearrange_all` (line 303–322)

```python
room_spec = _apply_clarification_answers(request.room_spec, answers)
room_spec["user_preferences"]["user_message"] = request.message
agent = RearrangeAgent()
async for event in agent.apply(
    current_layout=request.current_layout,
    room_spec=room_spec,
    modification_request=request.message,
):
    yield event.to_sse()
```

ดู [04-modifier-rearrange.md](./04-modifier-rearrange.md#rearrangeagent)

### `explain` (line 324–331)

```python
state = PipelineState(
    room_spec=request.room_spec or {},
    personality_mode=request.mode,
)
state.layout_items = request.current_layout
async for event in ExplainerStep(PipelineConfig()).execute(state):
    yield event.to_sse()
```

รันแค่ Step 5 — LLM เขียนคำอธิบาย layout ปัจจุบัน

### `question` (line 333–343, fallback)

```python
answer = await _answer_question(
    request.message, request.mode, mood, request.conversation_history,
)
yield ANSWER {"answer": answer}
```

- ใช้ `FengShuiRAGService` ค้นเอกสารฮวงจุ้ย + LLM ตอบ
- เป็น fallback เมื่อ RouterAgent confidence < 0.5 ด้วย

## Response Headers (line 345–353)

```python
return StreamingResponse(
    event_generator(),
    media_type="text/event-stream",
    headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # disable nginx buffering
    },
)
```

## Alternative Endpoint: `/chat/rag` (line 356)

RAG-only chat, ไม่แตะ layout pipeline
- ใช้ `FengShuiRAGService.ask_stream()`
- Yield `answer_delta` ทีละ token
- ใช้สำหรับ pure Q&A (ไม่ route ผ่าน RouterAgent)

## จุดที่ควรรู้

1. **Router fallback**: ถ้า LLM ส่ง intent แปลก หรือ confidence < 0.5 → fallback เป็น `question` (ไม่ break)
2. **Keyword override**: ถ้า user พิมพ์ "เปลี่ยนโหมด..." ตรงๆ → `detect_mode_switch()` จะ force intent เป็น `set_mode` แม้ LLM จะ classify เป็นอย่างอื่น (router_agent.py:207–214)
3. **clarification_answers ถือเป็น stateless** — frontend ต้องส่งกลับทุกครั้ง (ไม่เก็บ session state ที่ backend)
4. **user_message ถูก inject เข้า user_preferences** — LLM เห็นข้อความผู้ใช้ใน prompt ตลอด
