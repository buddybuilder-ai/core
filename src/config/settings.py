"""Application settings and configuration."""
from functools import lru_cache
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ==========================================================================
    # Application Settings
    # ==========================================================================
    APP_NAME: str = "BuddyBuilder AI"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # ==========================================================================
    # OpenRouter Configuration
    # ==========================================================================
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # ==========================================================================
    # LLM Models (via OpenRouter)
    # ==========================================================================
    LLM_MODEL_RAG: str = "anthropic/claude-3.5-sonnet"
    LLM_MODEL_LAYOUT: str = "openai/gpt-4-turbo"
    LLM_TEMPERATURE_RAG: float = 0.7
    LLM_TEMPERATURE_LAYOUT: float = 0.1

    # ==========================================================================
    # Database Configuration
    # ==========================================================================
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/buddybuilder"

    # ==========================================================================
    # ChromaDB Vector Store
    # ==========================================================================
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8000
    CHROMA_COLLECTION: str = "interior_knowledge"

    # ==========================================================================
    # Embedding Model
    # ==========================================================================
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # ==========================================================================
    # Security
    # ==========================================================================
    SECRET_KEY: str = "your-super-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # ==========================================================================
    # CORS Settings
    # ==========================================================================
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8080"]

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
