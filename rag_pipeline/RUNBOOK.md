# Buddy Builder — Runbook

คู่มือการรัน Core Backend, Tests, และ Vectorization Rebuild

---

## สารบัญ

1. [รัน Core Backend](#1-รัน-core-backend)
2. [รัน Tests](#2-รัน-tests)
3. [Rebuild Vectorstore](#3-rebuild-vectorstore)
4. [Quick Reference](#4-quick-reference)

---

## 1. รัน Core Backend

### ติดตั้ง (ครั้งแรก)

```bash
cd /Users/suthathongkong/Documents/Buddy\ Builder/core

# สร้าง virtual environment
python -m venv .venv
source .venv/bin/activate          # macOS/Linux
# .venv\Scripts\Activate.ps1       # Windows PowerShell

# ติดตั้ง dependencies
make dev

# ตั้งค่า environment
cp .env.example .env
# แก้ไข .env ใส่ OPENROUTER_API_KEY และ DATABASE_URL
```

### รัน Server

```bash
# Development (auto-reload)
make run
# เทียบเท่า: uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Production
make run-prod
# เทียบเท่า: uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### รันด้วย Docker (ทุก services พร้อมกัน)

```bash
make docker-run    # เริ่ม API + PostgreSQL + ChromaDB + Redis
make docker-down   # หยุดทุก services
make docker-logs   # ดู logs
```

### Database Migration

```bash
make migrate
# เทียบเท่า: alembic upgrade head
```

### Endpoints หลัก

| Method | Endpoint | คำอธิบาย |
|--------|----------|-----------|
| POST | `/api/v1/chat/message` | Chat (non-streaming) |
| POST | `/api/v1/chat/stream` | Chat (SSE streaming) |
| POST | `/api/v1/layout/generate/stream` | Layout pipeline (SSE) |
| GET | `/api/v1/layout/health` | Health check (layout) |
| GET | `/health` | Health check |
| GET | `/docs` | Swagger UI |

**API URL:** `http://localhost:8000`

---

## 2. รัน Tests

### รัน Tests ทั้งหมด

```bash
cd /Users/suthathongkong/Documents/Buddy\ Builder/core
source .venv/bin/activate

make test
# เทียบเท่า: pytest tests/ -v
```

### รัน Tests พร้อม Coverage Report

```bash
make test-cov
# เทียบเท่า: pytest tests/ -v --cov=src --cov-report=html --cov-report=term-missing
# HTML report จะอยู่ที่: htmlcov/index.html
```

### รัน Test เฉพาะไฟล์หรือ Function

```bash
# เฉพาะไฟล์
pytest tests/test_chat.py -v

# เฉพาะ function
pytest tests/test_chat.py::test_send_message -v

# เฉพาะ marker
pytest -m integration -v    # integration tests เท่านั้น
pytest -m "not slow" -v     # ข้าม slow tests
```

### ทดสอบ RAG แบบ Interactive

ใช้ `test_rag_chat.py` เสมอ — เป็น default สำหรับการทดสอบทุกอย่าง

```bash
cd /Users/suthathongkong/Documents/Buddy\ Builder/core
source .venv/bin/activate

python test_rag_chat.py
# หรือ: make rag-test-chat
```

คำสั่งทั้งหมด:
| คำสั่ง | ผล |
|--------|-----|
| พิมพ์คำถาม | ถาม RAG ด้วย mode ที่เลือก |
| `/mode buddy` | เปลี่ยนเป็น buddy (เพื่อนสนิท ตรงไปตรงมา) |
| `/mode mentor` | เปลี่ยนเป็น mentor (พี่สอนน้อง อธิบายหลักการครบ) |
| `/mode fun` | เปลี่ยนเป็น fun (สนุก มีพลังงาน) |
| `/sources` | toggle แสดง/ซ่อน source documents |
| `/debug` | toggle แสดง keyword match + L2 scores ทุกคำถาม |
| `/relevance <คำถาม>` | ทดสอบ 2-layer relevance check (ไม่เรียก LLM) |
| `/retrieve <คำถาม>` | ดู documents ที่จะ inject เข้า LLM |
| `/history` | ดู conversation history |
| `/clear` | ล้าง history |
| `/help` | แสดงคำสั่งทั้งหมด |
| `/exit` | ออก |

> ใช้ `FengShuiRAGService` — service เดียวกับที่ frontend เรียกจริง
> LLM: ขึ้นกับ `LLM_PROVIDER` ใน `core/.env` (ปัจจุบัน: `ollama`)
> ถ้าไม่มี Ollama — ยังใช้ `/relevance` และ `/retrieve` ได้ (ไม่เรียก LLM)

> **`main.py` ใช้สำหรับ rebuild เท่านั้น** — ไม่มี interactive chat แล้ว

### โครงสร้าง Tests

```
tests/
├── conftest.py              # Fixtures (app, client, db_session, mock_openrouter)
├── unit/
│   ├── schemas/
│   ├── api/v1/layout/
│   └── modules/layout/application/
├── integration/
└── e2e/
```

---

## 3. Rebuild Vectorstore

### โครงสร้าง RAG Pipeline

```
rag_pipeline/
├── main.py                          # Entry point
├── config.py                        # Configuration
├── rag_constants.py                 # System prompt + keywords + modes
├── step1_data_loader.py            # โหลด documents จาก data/raw/
├── step2_text_splitter.py          # Standard chunking
├── step2b_contextual_chunking.py   # Contextual chunking (แนะนำ)
├── step2c_hypothetical_questions.py # Hypothetical Q&A chunks
├── step3_vectorstore.py            # สร้าง ChromaDB
├── step4b_rag_with_memory.py       # ConversationRAGChain
├── check_vectordb.py               # ตรวจสอบ vectorstore
└── data/raw/                        # เอกสารต้นฉบับ (xlsx, csv, json, md)

vectorstore/chroma_db/              # ChromaDB ที่สร้างแล้ว (git-ignored)
```

### Rebuild Commands

```bash
cd /Users/suthathongkong/Documents/Buddy\ Builder/core
source .venv/bin/activate

# Contextual chunking (default — แนะนำ)
make rag-rebuild
# เทียบเท่า: cd rag_pipeline && python main.py --method contextual --rebuild

# Contextual + LLM Context (คุณภาพดีที่สุด แต่ช้ากว่า — ต้องมี Ollama ทำงานอยู่)
make rag-rebuild-best
# เทียบเท่า: cd rag_pipeline && python main.py --method contextual --llm-context --rebuild

# Standard chunking (เร็วที่สุด — ใช้เมื่อต้องการทดสอบเร็ว)
cd rag_pipeline && python main.py --method standard --rebuild

# Hypothetical Questions method
cd rag_pipeline && python main.py --method questions --rebuild
```

> **หมายเหตุเรื่อง Path:** vectorstore จะสร้างที่ `rag_pipeline/vectorstore/chroma_db/` เสมอ (hardcoded ใน `config.py`)
> ถ้าต้องการให้ core อ่าน vectorstore นี้ ให้ตั้งใน `core/.env`:
> ```bash
> CHROMA_DB_PATH=./rag_pipeline/vectorstore/chroma_db
> ```

### ขั้นตอน Rebuild

| ขั้นตอน | Script | คำอธิบาย |
|---------|--------|-----------|
| Step 1 | `step1_data_loader.py` | โหลดไฟล์จาก `data/raw/` (.xlsx, .csv, .json, .md) |
| Step 2 | `step2_text_splitter.py` หรือ `step2b` | แบ่งเป็น chunks |
| Step 3 | `step3_vectorstore.py` | สร้าง embeddings + บันทึกลง ChromaDB |

### ตรวจสอบ Vectorstore

```bash
# ดู contents ของ vectorstore
make rag-check
# เทียบเท่า: cd rag_pipeline && python check_vectordb.py
# แสดง: จำนวน documents, ตัวอย่าง, สรุปตาม source, ทดสอบ search
```

### Environment Variables ที่เกี่ยวข้อง

**Root `.env`** (`/Users/suthathongkong/Documents/Buddy Builder/.env`):

```bash
# Embedding model (เปลี่ยนแล้วต้อง rebuild เสมอ)
EMBEDDING_MODEL=BAAI/bge-m3              # 2.2GB (best)
# EMBEDDING_MODEL=intfloat/multilingual-e5-large  # 1.1GB
# EMBEDDING_MODEL=intfloat/multilingual-e5-base   # 280MB (เร็ว)

# Chunking
CHUNK_SIZE=1000
CHUNK_OVERLAP=200

# RAG Retrieval
RAG_TOP_K=5
RAG_SEARCH_TYPE=mmr                      # mmr (diverse) | similarity (exact)
RAG_RELEVANCE_THRESHOLD=1.0             # L2 distance threshold
FUZZY_MATCH_THRESHOLD=2
MAX_HISTORY=10
```

**Core `.env`** (`/Users/suthathongkong/Documents/Buddy Builder/core/.env`):

```bash
OPENROUTER_API_KEY=sk-or-v1-...
LLM_MODEL_RAG=anthropic/claude-3.5-sonnet
LLM_MODEL_LAYOUT=openai/gpt-4-turbo
LLM_MODEL_ROUTER=openai/gpt-4o-mini
CHROMA_DB_PATH=./rag_pipeline/vectorstore/chroma_db
EMBEDDING_MODEL_LOCAL=intfloat/multilingual-e5-base

# LLM สำหรับ contextual indexing (ถ้าใช้ --method contextual --llm-context)
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen2.5:7b
OLLAMA_BASE_URL=http://localhost:11434
```

> **หมายเหตุ:** เปลี่ยน `EMBEDDING_MODEL` แล้วต้อง rebuild vectorstore ใหม่ทุกครั้ง

---

## 4. Quick Reference

```bash
# --- Core Backend ---
cd core && source .venv/bin/activate
make run                   # Start dev server (port 8000)
make migrate               # Run DB migrations

# --- Tests ---
make test                  # All tests
make test-cov              # With HTML coverage report
python test_rag.py         # RAG integration tests
python test_rag_chat.py    # Interactive RAG chat (production service + modes)
# หรือ: make rag-test-chat

# --- Vectorstore ---
make rag-rebuild           # Rebuild (contextual — recommended)
make rag-rebuild-best      # Rebuild (contextual + LLM context — best quality)
make rag-check             # Inspect vectorstore contents

# --- Docker ---
make docker-run            # Start all services
make docker-down           # Stop all services

# --- Code Quality ---
make lint                  # Ruff + MyPy
make format                # Auto-format
make clean                 # Remove cache files
```
