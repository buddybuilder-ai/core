# =============================================================================
# BuddyBuilder AI - Development Commands (PowerShell)
# =============================================================================
# Usage: .\dev.ps1 <command>
# Example: .\dev.ps1 dev

param(
    [Parameter(Position=0)]
    [string]$Command = "help"
)

function Show-Help {
    Write-Host "BuddyBuilder AI - Development Commands" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Usage: .\dev.ps1 <command>" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Installation:" -ForegroundColor Green
    Write-Host "  install      - Install production dependencies"
    Write-Host "  dev          - Install development dependencies"
    Write-Host ""
    Write-Host "Code Quality:" -ForegroundColor Green
    Write-Host "  lint         - Run linter (Ruff + MyPy)"
    Write-Host "  format       - Format code with Ruff"
    Write-Host ""
    Write-Host "Testing:" -ForegroundColor Green
    Write-Host "  test         - Run tests"
    Write-Host "  test-cov     - Run tests with coverage report"
    Write-Host ""
    Write-Host "Database:" -ForegroundColor Green
    Write-Host "  migrate      - Run database migrations"
    Write-Host ""
    Write-Host "Development:" -ForegroundColor Green
    Write-Host "  run          - Start development server"
    Write-Host ""
    Write-Host "Docker:" -ForegroundColor Green
    Write-Host "  docker-build - Build Docker image"
    Write-Host "  docker-run   - Start all services"
    Write-Host "  docker-down  - Stop all services"
}

switch ($Command.ToLower()) {
    "help" {
        Show-Help
    }
    "install" {
        Write-Host "Installing production dependencies..." -ForegroundColor Cyan
        pip install -e .
    }
    "dev" {
        Write-Host "Installing development dependencies..." -ForegroundColor Cyan
        pip install -e ".[dev]"
    }
    "lint" {
        Write-Host "Running linter..." -ForegroundColor Cyan
        ruff check src/ tests/
        mypy src/
    }
    "format" {
        Write-Host "Formatting code..." -ForegroundColor Cyan
        ruff format src/ tests/
        ruff check --fix src/ tests/
    }
    "test" {
        Write-Host "Running tests..." -ForegroundColor Cyan
        pytest tests/ -v
    }
    "test-cov" {
        Write-Host "Running tests with coverage..." -ForegroundColor Cyan
        pytest tests/ -v --cov=src --cov-report=html --cov-report=term-missing
    }
    "migrate" {
        Write-Host "Running migrations..." -ForegroundColor Cyan
        alembic upgrade head
    }
    "run" {
        Write-Host "Starting development server..." -ForegroundColor Cyan
        uvicorn src.main:app --reload --host 0.0.0.0 --port 8002
    }
    "docker-build" {
        Write-Host "Building Docker image..." -ForegroundColor Cyan
        docker build -t buddybuilder-ai .
    }
    "docker-run" {
        Write-Host "Starting Docker services..." -ForegroundColor Cyan
        docker-compose up -d
    }
    "docker-down" {
        Write-Host "Stopping Docker services..." -ForegroundColor Cyan
        docker-compose down
    }
    default {
        Write-Host "Unknown command: $Command" -ForegroundColor Red
        Write-Host ""
        Show-Help
    }
}
