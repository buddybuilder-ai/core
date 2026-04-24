# 12 — SSE Events Reference

Event types ทั้งหมดที่ backend stream ไปให้ frontend

## SSE Format

ทุก event ส่งเป็น:
```
data: {"type": "<event_type>", ...payload}

```

Frontend parse JSON จาก `data:` และ dispatch ตาม `type`

## SSEEventType Enum

File: [models.py:66](../src/modules/layout/application/pipeline/models.py#L66)

```python
class SSEEventType(Enum):
    # Pipeline lifecycle
    PIPELINE_STARTED = "pipeline_started"
    PIPELINE_COMPLETED = "pipeline_completed"
    PIPELINE_FAILED = "pipeline_failed"

    # Step lifecycle
    STEP_STARTED = "step_started"
    STEP_PROGRESS = "step_progress"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"

    # Conflicts & repairs
    CONFLICT_FOUND = "conflict_found"
    REPAIR_APPLIED = "repair_applied"
    LAYOUT_UPDATED = "layout_updated"

    # Router
    ROUTER_CLASSIFIED = "router_classified"

    # Modifier / Rearrange
    MODIFIER_STARTED = "modifier_started"
    MODIFIER_UPDATED = "modifier_updated"
    MODIFIER_COMPLETED = "modifier_completed"

    # User interaction
    MODE_CHANGED = "mode_changed"
    CLARIFICATION_NEEDED = "clarification_needed"
    ANSWER = "answer"
    ANSWER_DELTA = "answer_delta"
```

---

## Event Reference

### `router_classified`

ส่งทันทีหลัง RouterAgent จำแนก intent

```json
{
  "type": "router_classified",
  "intent": "rearrange_all",
  "confidence": 0.92,
  "extracted_params": {}
}
```

**Frontend action**: Log intent for debugging. ไม่แสดง UI

---

### `pipeline_started`

เริ่มรัน 5-step pipeline (เฉพาะ `new_layout`)

```json
{
  "type": "pipeline_started",
  "pipeline_id": "abc12345",
  "steps": ["structured_data_builder", "layout_generator", "rule_checker", "repair", "explainer"],
  "config": {
    "max_repair_loops": 3,
    "llm_model": "anthropic/claude-3.5-sonnet",
    "llm_temperature": 0.3
  }
}
```

**Frontend action**: แสดง progress UI (5 steps)

---

### `step_started`

เริ่มแต่ละ step

```json
{
  "type": "step_started",
  "step": "layout_generator",
  "pipeline_id": "abc12345"
}
```

---

### `step_progress`

ระหว่างรัน step (fine-grained updates)

```json
{
  "type": "step_progress",
  "step": "layout_generator",
  "message": "Calling LLM...",
  "progress": 0.5
}
```

`progress` range: 0.0 → 1.0

**ใช้ที่ไหน:**
- Step 1: data parsing progress
- RAG retrieval: 0.0 → 1.0
- Step 2: furniture selection, LLM call, resolution
- Rearrange: analysing/planning/resolving/finalising stages

---

### `step_completed`

Step เสร็จ

```json
{
  "type": "step_completed",
  "step": "layout_generator",
  "duration_ms": 2341,
  "data": {
    "items_placed": 5,
    "deterministic_score": 55
  }
}
```

---

### `step_failed`

Step พลาด

```json
{
  "type": "step_failed",
  "step": "layout_generator",
  "error": "LLM timeout after 60s"
}
```

**Frontend action**: แสดง error, ทำ pipeline_failed follow-up

---

### `conflict_found`

เจอ conflict ใน Step 3 Rule Checker

```json
{
  "type": "conflict_found",
  "conflict": {
    "id": "conf_12ab",
    "conflict_type": "overlap",
    "severity": "critical",
    "description": "bed_queen_001 overlaps with wardrobe_001",
    "items_involved": ["bed_queen_001", "wardrobe_001"],
    "suggestion": "Move bed or wardrobe to different walls",
    "resolved": false
  }
}
```

**Severity**: `critical` | `warning` | `info`

**Frontend action**: แสดงในลิสต์ conflict (อาจ highlight เฟอร์นิเจอร์ใน 3D)

---

### `repair_applied`

หลัง Step 4 แก้ conflict

```json
{
  "type": "repair_applied",
  "repair": {
    "id": "rep_34cd",
    "action_type": "shift",
    "conflict_id": "conf_12ab",
    "furniture_id": "bed_queen_001",
    "description": "Shifted bed 0.5m east",
    "before": {"pos_x": 0.0, "pos_z": -1.7},
    "after":  {"pos_x": 0.5, "pos_z": -1.7},
    "success": true
  }
}
```

`action_type`: `shift` | `rotate` | `swap` | `remove`

---

### `layout_updated`

Layout items ถูกอัปเดต (อาจ emit กลางทาง ใน Step 4 หรือใน Modifier)

```json
{
  "type": "layout_updated",
  "layout_items": [
    {
      "furniture_id": "bed_queen_001",
      "instanceId": "inst_001",
      "pos_x": 0.5, "pos_y": 0, "pos_z": -1.7,
      "rotation": 0,
      "dimensions": {"width": 1.6, "depth": 2.0, "height": 0.6},
      "category": "bed",
      "name": "Queen Bed",
      "model_url": "/models/bed.glb",
      "model_rotation_offset": 0
    },
    ...
  ]
}
```

**Frontend action**: Call `setFurnitureItems()` → Three.js re-render

---

### `pipeline_completed`

Pipeline เสร็จสมบูรณ์

```json
{
  "type": "pipeline_completed",
  "success": true,
  "pipeline_id": "abc12345",
  "layout_items": [...],
  "feng_shui_score": {
    "command_position": 25,
    "five_elements_balance": 15,
    "chi_flow": 20,
    "sha_chi_avoidance": 22
  },
  "conflicts": [...],
  "repair_actions": [...],
  "explanation": "ห้องของคุณจัดวางได้ดีมาก...",
  "step_results": [
    {"step": "structured_data_builder", "status": "completed", "duration_ms": 42},
    ...
  ],
  "total_duration_ms": 5432
}
```

**Frontend action**:
- แสดง explanation ใน chat
- อัปเดต score widget
- Persist layout ผ่าน `PATCH /api/projects/{id}`
- Mark pipeline progress UI as done

---

### `pipeline_failed`

Pipeline crash ที่ไม่ recoverable

```json
{
  "type": "pipeline_failed",
  "error": "LLM returned invalid JSON",
  "pipeline_id": "abc12345"
}
```

---

### `modifier_started`

RearrangeAgent หรือ ModifierAgent เริ่มทำงาน

```json
{
  "type": "modifier_started",
  "modification": "ย้ายโซฟาไปผนังตะวันตก"
}
```

---

### `modifier_updated`

(ใช้น้อย — เหมือน `layout_updated` แต่ใน modifier context)

---

### `modifier_completed`

Modifier/Rearrange เสร็จ

```json
{
  "type": "modifier_completed",
  "layout_items": [...],
  "changed_furniture": "sofa_001" | "all",
  "collisions_after": 0,
  "warning": "LLM planning failed: ..."  // optional
}
```

`changed_furniture`:
- `"<furniture_id>"` — Modifier (ย้ายชิ้นเดียว)
- `"all"` — Rearrange (จัดใหม่ทั้งหมด)

---

### `mode_changed`

User เปลี่ยน personality mode

```json
{
  "type": "mode_changed",
  "mode": "mentor"
}
```

**Frontend action**: Update mode state (โทนข้อความต่อไปจะเปลี่ยน)

---

### `clarification_needed`

ระบบต้องถามข้อมูลเพิ่ม

```json
{
  "type": "clarification_needed",
  "questions": [
    {
      "id": "sleep_zone_preference",
      "question": "โซนนอนควรอยู่ส่วนไหน?",
      "question_type": "multiple_choice",
      "priority": "required",
      "options": ["ตรงข้ามประตู", "ซ้าย", "ขวา", "ไม่ชอบพิเศษ"],
      "default_value": "ตรงข้ามประตู",
      "context": "ตำแหน่งผู้บัญชาการ"
    }
  ],
  "original_message": "จัดห้องให้หน่อย"
}
```

**Frontend action**:
- แสดง modal ถามคำถาม
- User ตอบ → ส่ง request ใหม่พร้อม `clarification_answers`
- Include `original_message` เดิมใน request ใหม่

---

### `answer`

Text answer สำหรับ `question` / `explain` intent

```json
{
  "type": "answer",
  "answer": "ตามหลักฮวงจุ้ย เตียงควรวาง..."
}
```

**Frontend action**: Append to chat as assistant message

---

### `answer_delta`

Token-by-token streaming (เฉพาะ `/chat/rag` endpoint)

```json
{
  "type": "answer_delta",
  "delta": "ตาม"
}
```

**Frontend action**: Accumulate chunks, render as they arrive

**หมายเหตุ**: ปัจจุบัน `/api/chat/stream` ไม่ stream เป็น token — ส่ง `answer` ทั้งก้อน

---

## Event Sequence Per Intent

### `new_layout`

```
1.  router_classified
2.  pipeline_started
3.  step_started           (data_builder)
4.  step_progress × N
5.  step_completed         (data_builder)
6.  step_progress          (rag_retrieval, 0.0)
7.  step_progress          (rag_retrieval, 1.0)
8.  step_started           (layout_generator)
9.  step_progress × N
10. step_completed         (layout_generator)
11. step_started           (rule_checker)
12. conflict_found × N
13. step_completed         (rule_checker)
[repair loop start — up to 3×]
14. step_started           (repair)
15. repair_applied × M
16. layout_updated
17. step_completed         (repair)
→ goto 11 if conflicts remain
[end loop]
18. step_started           (explainer)
19. step_completed         (explainer, explanation)
20. pipeline_completed
```

### `rearrange_all`

```
1. router_classified
2. modifier_started
3. step_progress (analysing, 0.15)
4. step_progress (planning, 0.40)
5. step_progress (resolving, 0.70)
6. step_progress (finalising, 0.90)
7. modifier_completed (with layout_items)
```

### `modify`

```
1. router_classified
2. modifier_started
3. layout_updated
4. modifier_completed
```

### `explain`

```
1. router_classified
2. step_started (explainer)
3. step_completed (explainer, explanation)
```

### `question`

```
1. router_classified
2. answer
```

### `set_mode`

```
1. router_classified
2. mode_changed
```

### `clarification_needed` (interrupt)

Can happen before any dispatch:
```
1. router_classified
2. clarification_needed
(flow ends — wait for user reply)
```

---

## SSE Helper: `SSEEvent.to_sse()`

File: [models.py](../src/modules/layout/application/pipeline/models.py)

```python
@dataclass
class SSEEvent:
    event_type: SSEEventType
    data: dict

    def to_sse(self) -> str:
        payload = {"type": self.event_type.value, **self.data}
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
```

## Response Headers

```python
StreamingResponse(
    event_generator(),
    media_type="text/event-stream",
    headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",   # disable nginx buffering
    },
)
```

## Frontend Handler

File: [app/hooks/use-chat.ts](../../app/hooks/use-chat.ts)

```typescript
const handleEvent = (event: SSEPayload) => {
  switch (event.type) {
    case "router_classified": ...
    case "pipeline_completed":
      setFurnitureItems(event.layout_items);
      setFengShuiScore(event.feng_shui_score);
      persistLayout(event.layout_items);
      break;
    case "modifier_completed":
      setFurnitureItems(event.layout_items);
      break;
    case "layout_updated":
      setFurnitureItems(event.layout_items);
      break;
    case "answer":
      addMessage({ role: "assistant", content: event.answer });
      break;
    case "clarification_needed":
      showClarificationModal(event.questions, event.original_message);
      break;
    case "mode_changed":
      setMode(event.mode);
      break;
    // ...
  }
};
```

## จุดที่ควรรู้

1. **`layout_updated` อาจเกิดหลายครั้งในหนึ่ง pipeline** — หลัง repair แต่ละรอบ
2. **`pipeline_completed` เป็น final authoritative state** — ใช้นี่ persist
3. **`conflict_found` emit ระหว่าง Step 3** — frontend อาจเก็บไว้แสดงตอนจบ
4. **Modifier ไม่ emit `pipeline_completed`** — ใช้ `modifier_completed` แทน
5. **`clarification_needed` หยุด flow** — frontend ต้อง re-call endpoint พร้อม answers
6. **Event order สำคัญ** — เช่น `step_started` ต้องมาก่อน `step_completed` เสมอ
7. **`answer_delta` ใช้แค่ RAG endpoint** — chat/stream ใช้ `answer` ทั้งก้อน
