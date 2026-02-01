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
# Windows:
.venv\Scripts\activate

# Install dependencies
make dev

# Setup environment
cp .env.example .env
# Edit .env with your OpenRouter API key and database credentials

# Run database migrations
make migrate

# Start development server
make run
```

The API will be available at `http://localhost:8000`

### Using Docker

```bash
# Start all services (PostgreSQL, ChromaDB, API)
make docker-run

# Stop services
make docker-down
```

## 📡 API Endpoints

### Chat (RAG Chatbot)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/chat/conversations` | Create new conversation |
| `POST` | `/api/v1/chat/conversations/{id}/messages` | Send message |
| `GET` | `/api/v1/chat/conversations/{id}` | Get conversation history |

### Layout (3D Generation)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/layout/generate` | Generate 3D room layout |
| `GET` | `/api/v1/layout/{id}` | Get generated layout |

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/health/ready` | Readiness check |

## 🔧 Development

### Available Commands

```bash
# Install dependencies
make install      # Production only
make dev          # With dev dependencies

# Code Quality
make lint         # Run linter (Ruff + MyPy)
make format       # Format code

# Testing
make test         # Run tests
make test-cov     # Run tests with coverage

# Database
make migrate              # Run migrations
make migrate-create msg="description"  # Create new migration

# Development
make run          # Start dev server with hot reload

# Docker
make docker-build # Build Docker image
make docker-run   # Start all services
make docker-down  # Stop services

# Cleanup
make clean        # Remove cache files
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
make test

# Run with coverage report
make test-cov

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
| **Application** | Use cases, orchestration |
| **Domain** | Business logic, entities |
| **Infrastructure** | External integrations (DB, LLM, Vector Store) |

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
