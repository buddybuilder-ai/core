# 01 — Overview & Architecture

## ระบบคืออะไร

BuddyBuilder คือระบบช่วยจัดเฟอร์นิเจอร์ในห้องตามหลักฮวงจุ้ย ประกอบด้วย
- **Backend** (FastAPI + Python) — layout engine, LLM orchestration, RAG
- **Frontend** (Next.js + Three.js/R3F) — 3D editor, chat UI
- **LLM** (OpenRouter / Groq / Ollama) — intent classification + semantic layout planning

User พิมพ์ข้อความเข้าไป → ระบบเข้าใจเจตนา → วาง/ย้ายเฟอร์นิเจอร์ใน 3D scene → อธิบายผลลัพธ์

## หลักการออกแบบ

**LLM คิดเชิง semantic, โค้ด deterministic คำนวณ geometry**

| ใคร | รับผิดชอบ |
|---|---|
| LLM | "เตียงควรอยู่ผนังไหน", "โซฟาควรชิดซ้าย/กลาง/ขวา", "หันหน้าไปทิศไหน" |
| โค้ด | พิกัด x/z, rotation, collision, bump-out, clearance, AABB |

เหตุผล: LLM เก่งเรื่องการตัดสินใจแต่ห่วยเลข. ถ้าให้ LLM คำนวณพิกัด → collision, หลุดห้อง, หลอนขนาด

## High-Level Flow

```
User ──▶ ChatInput (Next.js)
          │
          │ POST /api/chat/stream  (SSE)
          ▼
   ┌──────────────────────────────────────┐
   │  event_generator()                   │
   │   core/src/api/v1/chat/router.py     │
   └──────────────────────────────────────┘
          │
          │ 1. RouterAgent.classify() [LLM]
          │    → intent ∈ {new_layout, modify, rearrange_all,
          │                question, explain, set_mode}
          │
          │ 2. Empty-room guard (ห้องว่าง → ตอบ fallback)
          │
          │ 3. Clarification gate (ถามข้อมูลเพิ่มถ้าจำเป็น)
          │
          │ 4. Dispatch ตาม intent:
          ▼
   ┌────────────────────────────────────────────────┐
   │                                                │
   ▼            ▼            ▼            ▼         ▼
 new_layout   modify     rearrange    explain    question
 (pipeline)  (1-piece)     (all)    (LLM text)    (RAG)
   │            │            │            │         │
   │            │            │            │         │
   │  ┌─────────┴────────────┴──┐         │         │
   │  │ RearrangeAgent /        │         │         │
   │  │ ModifierAgent           │         │         │
   │  │                         │         │         │
   │  │ • Re-plan with LLM      │         │         │
   │  │ • LayoutResolver        │         │         │
   │  │ • Repair collisions     │         │         │
   │  └─────────┬───────────────┘         │         │
   │            │                         │         │
   ▼            ▼                         ▼         ▼
 5-step pipeline              ExplainerStep   RAG service
 (Steps 1→2→3↔4→5)            (LLM)         (LLM + docs)
          │
          ▼
   ┌──────────────────────────────────────┐
   │  SSE events streamed to frontend     │
   │  → setFurnitureItems() updates 3D    │
   │  → Auto-save to /api/projects/{id}   │
   └──────────────────────────────────────┘
```

## โครงสร้างโฟลเดอร์

```
core/src/
├── api/v1/chat/
│   └── router.py                       # /api/chat/stream endpoint
│
└── modules/layout/
    ├── domain/                          # Pure domain entities
    │   ├── entities/
    │   │   ├── room.py                  # Room, DoorPosition, WindowPosition, WallSide, RoomType
    │   │   └── placement.py             # PhysicalPlacement
    │   └── value_objects/
    │       ├── coordinates.py           # Position3D, BoundingBox
    │       └── feng_shui_score.py       # FengShuiScore (4-component scoring)
    │
    ├── application/                     # Use cases / orchestration
    │   ├── pipeline/
    │   │   ├── orchestrator.py          # 5-step pipeline driver
    │   │   ├── models.py                # PipelineState, SSEEvent, Conflict, etc.
    │   │   └── steps/
    │   │       ├── step1_data_builder.py
    │   │       ├── step2_layout_generator.py
    │   │       ├── step3_rule_checker.py
    │   │       ├── step4_repair.py
    │   │       └── step5_explainer.py
    │   │
    │   ├── modifier/
    │   │   ├── modifier_agent.py        # Single-item changes
    │   │   └── rearrange_agent.py       # Re-plan all
    │   │
    │   ├── services/
    │   │   ├── spatial_resolver.py      # Semantic → physical coords
    │   │   ├── layout_resolver.py       # Orchestrates resolver + checks
    │   │   ├── wall_assigner.py         # Deterministic wall assignment
    │   │   ├── collision_checker.py
    │   │   ├── feng_shui_scorer.py      # 100-point scoring
    │   │   ├── clarification_gate.py
    │   │   ├── context_injector.py      # RAG
    │   │   └── furniture_relationships.py
    │   │
    │   └── agent/
    │       └── personality.py           # Mood/mode detection (keyword-based)
    │
    └── infrastructure/                  # I/O, LLM, external
        ├── llm/
        │   ├── router_agent.py          # Intent classifier (LLM)
        │   ├── langchain_agent.py       # FengShuiLLMAgent
        │   └── prompts.py               # All system/user prompts
        │
        ├── geometry/
        │   └── collision.py             # AABB class
        │
        └── tools/
            ├── furniture_catalog_data.py  # FURNITURE_CATALOG
            ├── user_clarifier_tool.py     # Clarification questions
            └── kua_calculator.py          # Chinese Bazi Kua
```

## Request/Response Cycle

### Request: `POST /api/chat/stream`

```typescript
{
  message: string,                      // ข้อความผู้ใช้
  mode: "buddy" | "mentor" | "fun",     // personality
  current_layout: LayoutItem[],         // เฟอร์นิเจอร์ที่อยู่ในห้องตอนนี้
  room_spec: {
    dimensions: { width, depth },
    room_type: string,
    doors: DoorPosition[],
    windows: WindowPosition[],
    direction: string,
    user_preferences: object
  },
  conversation_history: { role, content }[],
  clarification_answers: Record<string, string>
}
```

### Response: Server-Sent Events (SSE)

ทุก event มีรูปแบบ:
```
data: {"type": "<event_type>", ...payload}

```

Event type ที่เกิดบ่อย:
- `router_classified` — หลัง RouterAgent
- `step_started` / `step_progress` / `step_completed` — ทุก pipeline step
- `conflict_found` / `repair_applied` — ระหว่าง repair loop
- `modifier_completed` — หลัง modify/rearrange
- `pipeline_completed` — ครบ 5 step (มี layout_items + feng_shui_score + explanation)
- `answer` — สำหรับ intent=question/explain
- `clarification_needed` — ต้องถามเพิ่ม
- `mode_changed` — เปลี่ยน personality

ดูครบที่ [12-sse-events.md](./12-sse-events.md)

## จุดที่ใช้ LLM (3 จุดทั้งระบบ)

| # | Agent | Model | Max Tokens | ใช้ตอนไหน |
|---|---|---|---|---|
| 1 | `RouterAgent` | `LLM_MODEL_ROUTER` (เล็ก, เร็ว) | 200 | ทุก request |
| 2 | `FengShuiLLMAgent.plan_layout()` | `LLM_MODEL_LAYOUT` | 4096 | new_layout / rearrange / modify |
| 3 | `FengShuiLLMAgent.explain_layout()` | `LLM_MODEL_LAYOUT` | 4096 | Step 5 ของ pipeline |

ทุกอย่างที่เหลือเป็น deterministic code

## Next Steps

- อ่าน [02-chat-router.md](./02-chat-router.md) เพื่อเข้าใจ dispatch tree
- อ่าน [03-pipeline.md](./03-pipeline.md) เพื่อเข้าใจ 5-step flow
- อ่าน [05-spatial-resolver.md](./05-spatial-resolver.md) เพื่อเข้าใจการแปลง semantic → พิกัด
