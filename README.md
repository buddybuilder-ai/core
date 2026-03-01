# 🏠 BuddyBuilder AI

AI-powered backend for interior design with conversational chatbot and 3D layout generation.

[![CI](https://github.com/buddybuilder-ai/core/actions/workflows/ci.yml/badge.svg)](https://github.com/buddybuilder-ai/core/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## ✨ Features

- 💬 **RAG Chatbot**: Interior design assistant powered by vector search and conversational AI
- 🏠 **3D Layout Generator**: AI-generated furniture placements with strict JSON output for 3D rendering
- 🔧 **Modular Architecture**: Clean separation following DDD principles, ready for microservices
- 🚀 **Production Ready**: Async FastAPI, PostgreSQL, comprehensive testing

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| **Framework** | FastAPI + Python 3.11+ |
| **AI Orchestration** | LangChain |
| **LLM Provider** | OpenRouter (multi-model access) |
| **Vector Database** | ChromaDB |
| **Database** | PostgreSQL + SQLModel |
| **Validation** | Pydantic v2 |

## 📦 Project Structure

```
src/
├── api/               # 🌐 Web Layer - FastAPI routes
│   └── v1/
│       ├── chat/      # Chatbot endpoints
│       └── layout/    # 3D Layout endpoints
├── modules/           # 🧠 AI Layer - Business Logic (DDD)
│   ├── rag/           # RAG Chatbot module
│   │   ├── domain/
│   │   ├── application/
│   │   └── infrastructure/
│   └── layout/        # 3D Layout module
│       ├── domain/
│       ├── application/
│       └── infrastructure/
├── schemas/           # 📋 Pydantic schemas (strict contracts)
│   ├── layout/        # 3D Layout JSON schemas
│   └── common/
├── config/            # ⚙️ Configuration
└── core/              # 🔧 Utilities
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Docker (optional, for ChromaDB)

### Installation

```bash
# Clone repository
git clone https://github.com/buddybuilder-ai/core.git
cd core

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Linux/Mac:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Windows (CMD):
.venv\Scripts\activate.bat
```

#### Install Dependencies

**Linux/Mac (Make):**
```bash
make dev
```

**Windows (PowerShell):**
```powershell
.\dev.ps1 dev
# หรือใช้ pip โดยตรง:
pip install -e ".[dev]"
```

#### Setup & Run

```bash
# Setup environment
cp .env.example .env
# Edit .env with your OpenRouter API key and database credentials

# Run database migrations
# Linux/Mac:
make migrate
# Windows:
.\dev.ps1 migrate

# Start development server
# Linux/Mac:
make run
# Windows:
.\dev.ps1 run
```

The API will be available at `http://localhost:8000`

### Using Docker

```bash
# Start all services (PostgreSQL, ChromaDB, API)
# Linux/Mac:
make docker-run
# Windows:
.\dev.ps1 docker-run

# Stop services
# Linux/Mac:
make docker-down
# Windows:
.\dev.ps1 docker-down
```

## 📡 API Endpoints

### Chat

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/chat/message` | Single-turn LLM chat (non-streaming) |
| `POST` | `/api/v1/chat/stream` | Streaming intent router (SSE) — classifies intent and dispatches to layout pipeline, modifier, explainer, or Q&A |

### Layout (SSE Streaming)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/layout/generate/stream` | Run 5-step agentic layout pipeline with real-time SSE events |
| `GET` | `/api/v1/layout/health` | Layout service health check |

#### `/layout/generate/stream` query params

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `max_repair_loops` | `int` | `3` | Max rule-check/repair iterations |
| `mode` | `string` | `buddy` | Personality mode: `buddy`, `mentor`, `fun` |

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/health/ready` | Readiness check |

## 🔧 Development

### Available Commands

| Task | Linux/Mac (Make) | Windows (PowerShell) |
|------|------------------|----------------------|
| Install (prod) | `make install` | `.\dev.ps1 install` |
| Install (dev) | `make dev` | `.\dev.ps1 dev` |
| Run server | `make run` | `.\dev.ps1 run` |
| Run linter | `make lint` | `.\dev.ps1 lint` |
| Format code | `make format` | `.\dev.ps1 format` |
| Run tests | `make test` | `.\dev.ps1 test` |
| Test + coverage | `make test-cov` | `.\dev.ps1 test-cov` |
| Run migrations | `make migrate` | `.\dev.ps1 migrate` |
| Docker up | `make docker-run` | `.\dev.ps1 docker-run` |
| Docker down | `make docker-down` | `.\dev.ps1 docker-down` |

#### Direct Commands (Alternative)

```bash
# Install dependencies
pip install -e .           # Production only
pip install -e ".[dev]"    # With dev dependencies

# Code Quality
ruff check src/ tests/     # Lint
ruff format src/ tests/    # Format
mypy src/                  # Type check

# Testing
pytest tests/ -v
pytest tests/ -v --cov=src --cov-report=html

# Database
alembic upgrade head       # Run migrations
alembic revision --autogenerate -m "description"  # Create migration

# Development
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### Code Style

This project uses:
- **Ruff** for linting and formatting
- **MyPy** for type checking
- **Pre-commit** for git hooks

```bash
# Install pre-commit hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

## 🧪 Testing

```bash
# Run all tests
# Linux/Mac:
make test
# Windows:
.\dev.ps1 test

# Run with coverage report
# Linux/Mac:
make test-cov
# Windows:
.\dev.ps1 test-cov

# Run specific test file
pytest tests/test_chat.py -v

# Run specific test
pytest tests/test_chat.py::test_send_message -v
```

## 📐 Architecture

### Modular Monolith Pattern

```
┌─────────────────────────────────────────────────────────────┐
│                     API Gateway Layer                        │
│              (FastAPI - Routing, Auth, Middleware)          │
├─────────────────────────┬───────────────────────────────────┤
│    RAG Module           │      Layout Module                 │
│  ┌────────────────┐     │    ┌─────────────────────┐        │
│  │ Domain Layer   │     │    │ Domain Layer        │        │
│  ├────────────────┤     │    ├─────────────────────┤        │
│  │ Application    │     │    │ Application         │        │
│  ├────────────────┤     │    ├─────────────────────┤        │
│  │ Infrastructure │     │    │ Infrastructure      │        │
│  └────────────────┘     │    └─────────────────────┘        │
├─────────────────────────┴───────────────────────────────────┤
│                   Shared Infrastructure                      │
│            (Database, Vector Store, LLM Client)             │
└─────────────────────────────────────────────────────────────┘
```

### Layer Responsibilities

| Layer | Responsibility |
|-------|---------------|
| **API** | HTTP handling, validation, auth |
| **Application** | Use cases, orchestration (PipelineOrchestrator, RouterAgent, ModifierAgent) |
| **Domain** | Business logic, entities |
| **Infrastructure** | External integrations (DB, LLM via OpenRouter, RAG via MockRagSearchTool) |

### Layout Pipeline (5-Step Agentic)

```
User Request
     │
     ▼
[Step 1] StructuredDataBuilder  — parse room spec, validate dimensions
     │
     ├─── RAG retrieval (ContextInjector) — inject feng shui rules into state
     │
     ▼
[Step 2] LayoutGenerator        — LLM selects furniture + plans placements
     │
     ▼
[Step 3] RuleChecker            — spatial + feng shui conflict detection
     │
     ├── conflicts? ──► [Step 4] Repair ──► loop back to Step 3
     │   (up to max_repair_loops)
     │
     ▼
[Step 5] Explainer              — LLM generates Thai explanation (Buddy/Mentor/Fun mode)
     │
     ▼
pipeline_completed SSE event → frontend
```

## 📄 Configuration

All configuration is done via environment variables. See [.env.example](.env.example) for all options.

### Key Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENROUTER_API_KEY` | OpenRouter API key | Required |
| `DATABASE_URL` | PostgreSQL connection URL | Required |
| `CHROMA_HOST` | ChromaDB host | `localhost` |
| `LLM_MODEL_RAG` | Model for chatbot | `anthropic/claude-3.5-sonnet` |
| `LLM_MODEL_LAYOUT` | Model for layout | `openai/gpt-4-turbo` |

## 🔐 Security

- Never commit `.env` files
- Use strong `SECRET_KEY` in production
- Configure CORS appropriately
- Use HTTPS in production

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Commit Convention

We follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation
- `style:` - Formatting
- `refactor:` - Code restructuring
- `test:` - Adding tests
- `chore:` - Maintenance

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/) - Modern web framework
- [LangChain](https://langchain.com/) - AI orchestration
- [OpenRouter](https://openrouter.ai/) - Multi-model LLM access
- [ChromaDB](https://www.trychroma.com/) - Vector database
