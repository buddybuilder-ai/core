.PHONY: help install dev lint format test test-cov run migrate migrate-create docker-build docker-run docker-down chroma-start clean rag-rebuild rag-rebuild-best rag-test-chat rag-check

# Default target
help:
	@echo "BuddyBuilder AI - Development Commands"
	@echo ""
	@echo "Installation:"
	@echo "  make install      - Install production dependencies"
	@echo "  make dev          - Install development dependencies"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint         - Run linter (Ruff + MyPy)"
	@echo "  make format       - Format code with Ruff"
	@echo ""
	@echo "Testing:"
	@echo "  make test         - Run tests"
	@echo "  make test-cov     - Run tests with coverage report"
	@echo ""
	@echo "Database:"
	@echo "  make migrate      - Run database migrations"
	@echo "  make migrate-create msg='description' - Create new migration"
	@echo ""
	@echo "Development:"
	@echo "  make run          - Start development server"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build - Build Docker image"
	@echo "  make docker-run   - Start all services with docker-compose"
	@echo "  make docker-down  - Stop all services"
	@echo ""
	@echo "Utilities:"
	@echo "  make chroma-start - Start ChromaDB in Docker"
	@echo "  make clean        - Remove cache files"

# =============================================================================
# Installation
# =============================================================================

install:
	pip install -e .

dev:
	pip install -e ".[dev]"
	pre-commit install || true

# =============================================================================
# Code Quality
# =============================================================================

lint:
	ruff check src/ tests/
	mypy src/

format:
	ruff format src/ tests/
	ruff check --fix src/ tests/

# =============================================================================
# Testing
# =============================================================================

test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=src --cov-report=html --cov-report=term-missing
	@echo "Coverage report generated in htmlcov/index.html"

# =============================================================================
# Database
# =============================================================================

migrate:
	alembic upgrade head

migrate-create:
	alembic revision --autogenerate -m "$(msg)"

migrate-downgrade:
	alembic downgrade -1

# =============================================================================
# Development
# =============================================================================

run:
	PYTHONUNBUFFERED=1 WATCHFILES_FORCE_POLLING=true .venv/bin/uvicorn src.main:app --reload --reload-dir src --host 0.0.0.0 --port 8002 --timeout-graceful-shutdown 3

run-prod:
	PYTHONUNBUFFERED=1 .venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8002 --workers 4 --timeout-graceful-shutdown 3

kill:
	@lsof -ti:8002 | xargs kill -9 2>/dev/null && echo "Port 8002 cleared" || echo "Port 8002 already free"

# =============================================================================
# RAG / Vectorstore
# =============================================================================

RAG_DIR := ./rag_pipeline

rag-rebuild:
	@echo "🔨 Rebuilding vectorstore (contextual method)..."
	cd $(RAG_DIR) && python main.py --method contextual --rebuild

rag-rebuild-best:
	@echo "🔨 Rebuilding vectorstore (contextual + LLM context — best quality, slower)..."
	cd $(RAG_DIR) && python main.py --method contextual --llm-context --rebuild

rag-check:
	@echo "🔍 Checking vectorstore..."
	cd $(RAG_DIR) && python check_vectordb.py

rag-test-chat:
	@echo "💬 Starting interactive RAG chat tester..."
	python test_rag_chat.py

# =============================================================================
# Docker
# =============================================================================

docker-build:
	docker build -t buddybuilder-ai .

docker-run:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

docker-restart:
	docker-compose restart

# =============================================================================
# ChromaDB
# =============================================================================

chroma-start:
	docker run -d --name chromadb -p 8000:8000 chromadb/chroma

chroma-stop:
	docker stop chromadb && docker rm chromadb

# =============================================================================
# Utilities
# =============================================================================

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name htmlcov -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name .coverage -delete 2>/dev/null || true
	find . -type f -name coverage.xml -delete 2>/dev/null || true
	@echo "Cleaned up cache files"

# =============================================================================
# Pre-commit
# =============================================================================

pre-commit-install:
	pre-commit install

pre-commit-run:
	pre-commit run --all-files
