<!-- Generated: 2026-04-26 | Files scanned: ~90 | Token estimate: ~900 -->

# Backend — User Prompt Flow (Step-by-Step)

## กระบวนการหลังจาก User ส่ง Prompt มา

### Endpoint: POST /api/v1/chat/stream

**ไฟล์:** `src/api/v1/chat/router.py:69` — `chat_stream()`

---

### ขั้นตอนที่ 1 — Mood Detection + Intent Classification

```
request.message
    │
    ├── detect_mood(message)          → mood: "neutral"|"frustrated"|"excited"
    │   src/modules/layout/application/agent/personality.py
    │
    └── RouterAgent.classify(message, has_existing_layout, history[-4:])
        src/modules/layout/infrastructure/llm/router_agent.py
        │
        ├── LLM call (LLM_MODEL_ROUTER, max_tokens=200, temperature=0)
        └── Returns RouterResult { intent, confidence, extracted_params }
```

**SSE emitted:** `ROUTER_CLASSIFIED` → `{ intent, confidence, extracted_params }`

**Intents ที่เป็นไปได้:**
| Intent | ความหมาย |
|--------|---------|
| `new_layout` | ขอ layout ใหม่ทั้งหมด |
| `modify` | แก้ไขเฟอร์นิเจอร์ชิ้นเดียว |
| `rearrange_all` | จัดวางใหม่ทั้งห้อง |
| `explain` | อธิบาย layout ปัจจุบัน |
| `question` | ถามเรื่องฮวงจุ้ย/ออกแบบ |
| `set_mode` | เปลี่ยน personality mode |

---

### ขั้นตอนที่ 2 — Guard Checks

**2a. Empty-room guard**
- ถ้า intent เป็น `new_layout/rearrange_all/modify` แต่ไม่มี `current_layout`
- **SSE emitted:** `ANSWER` พร้อม error message ภาษาไทย → return

**2b. Clarification gate**
- `get_pending_questions(intent, clarification_answers, has_existing_layout)`
- `src/modules/layout/application/services/clarification_gate.py`
- ถ้ายังมีคำถามที่ยังไม่ได้ตอบ
- **SSE emitted:** `CLARIFICATION_NEEDED` → `{ questions, original_message }` → return

---

### ขั้นตอนที่ 3 — Dispatch by Intent

#### 3a. `set_mode`
```
detect_mode_switch(message) → new_mode
SSE: MODE_CHANGED → { mode }
```

#### 3b. `new_layout`
```
PipelineOrchestrator.run(room_spec, mode)
src/modules/layout/application/pipeline/orchestrator.py
    │
    Step 1: StructuredDataBuilderStep   — parse room_spec → structured data
    Step 2: LayoutGeneratorStep         — LLM generate furniture placements
    Step 3: RuleCheckerStep             — check feng shui rules
    Step 4: RepairStep                  — auto-fix conflicts (loops back to Step 3)
    Step 5: ExplainerStep               — LLM generate Thai explanation
    │
    └── SSE stream: STEP_STARTED, STEP_COMPLETED, LAYOUT_READY, ANSWER, etc.
```

#### 3c. `modify`
```
ModifierAgent.apply(current_layout, room_spec, modification_request, extracted_params)
src/modules/layout/application/modifier/modifier_agent.py
└── SSE stream events
```

#### 3d. `rearrange_all`
```
_apply_clarification_answers(room_spec, clarification_answers)  ← merge answers
RearrangeAgent.apply(current_layout, room_spec, modification_request)
src/modules/layout/application/modifier/rearrange_agent.py
└── SSE stream events
```

#### 3e. `explain`
```
ExplainerStep(PipelineConfig).execute(state)
src/modules/layout/application/pipeline/steps/
└── SSE stream events
```

#### 3f. `question` (fallback)
```
_answer_question(message, mode, mood, conversation_history)
    └── FengShuiRAGService.ask(question, mode, history)
        src/modules/layout/application/services/rag_service.py
        │
        ├── Layer 1: _has_domain_keywords()  — keyword + fuzzy match
        ├── Layer 2: _check_relevance()      — ChromaDB L2 distance ≤ threshold
        ├── _classify_query()                — LLM classify: feng_shui|interior_design|both
        ├── _enrich_retrieval_query()        — prepend Kua number if in history
        ├── _retrieve_context()              — ChromaDB MMR retrieval
        ├── _build_messages()               — system prompt + history + RAG context
        └── LLM call → answer string
SSE: ANSWER → { answer }
```

---

### ขั้นตอนที่ 4 — SSE Response Stream

ทุก event ส่งเป็น format:
```
event: <event_type>
data: {"type": "<event_type>", ...payload}

```

---

## RAG-Only Endpoint: POST /api/v1/chat/rag

`src/api/v1/chat/router.py:337` — `chat_rag_only()`

ข้ามขั้นตอน RouterAgent ทั้งหมด ไปเรียก `FengShuiRAGService.ask_stream()` โดยตรง
ใช้สำหรับหน้า Chatbot เท่านั้น (ไม่สร้าง layout)

SSE events:
- `answer_delta` — streaming token chunks
- `answer` — final answer + source_documents

---

## Routes Summary

```
POST /api/v1/chat/stream                → RouterAgent → dispatch → SSE
POST /api/v1/chat/rag                   → FengShuiRAGService.ask_stream → SSE
POST /api/v1/chat/message               → FengShuiRAGService.ask → JSON
POST /api/v1/chat/process-single-image  → detect_objects_2.py subprocess → JSON
POST /api/v1/chat/mobile-upload/{id}    → detect_objects_2.py subprocess → polling session
GET  /api/v1/chat/check-upload-status   → poll upload_sessions dict
GET  /api/v1/chat/get-ip                → socket local IP
```
