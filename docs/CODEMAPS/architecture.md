<!-- Generated: 2026-04-26 | Files scanned: ~90 | Token estimate: ~600 -->

# Architecture — BuddyBuilder Core (FastAPI)

## System Overview

```
Frontend (Next.js app/)
    │
    ▼  HTTP/SSE
FastAPI (core/)
    ├── /api/v1/chat/stream   ← main chat entry (SSE)
    ├── /api/v1/chat/rag      ← RAG-only chatbot
    ├── /api/v1/chat/message  ← simple non-streaming chat
    ├── /api/v1/layout        ← layout CRUD
    ├── /api/v1/projects      ← project management
    ├── /api/v1/conversations ← conversation history
    └── /api/v1/auth          ← auth
         │
         ├── RouterAgent (LLM classify intent)
         │
         ├── PipelineOrchestrator  ← new_layout
         ├── ModifierAgent         ← modify single item
         ├── RearrangeAgent        ← rearrange all
         ├── ExplainerStep         ← explain layout
         └── FengShuiRAGService    ← question (RAG)
                  │
                  └── ChromaDB (vectorstore) + OpenRouter/Groq/Ollama LLM
```

## Module Boundaries

| Module | Path | Role |
|--------|------|------|
| API layer | `src/api/v1/` | HTTP routing, request parsing |
| Layout domain | `src/modules/layout/` | Core business logic |
| RAG module | `src/modules/rag/` | Document loading, Chroma setup |
| Shared | `src/modules/shared/` | Cross-module utilities |
| Schemas | `src/schemas/` | Pydantic request/response models |
| Config | `src/config/` | Settings via pydantic-settings |

## Key Entry Points

- `main.py` — FastAPI app factory
- `src/api/v1/router.py` — aggregates all sub-routers
- `src/api/v1/chat/router.py` — chat endpoints (stream, rag, message)
