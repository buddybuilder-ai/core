"""Application settings and configuration.

แก้ config ทั้งหมดได้ที่ core/.env ไฟล์เดียว
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_files() -> tuple[str, ...]:
    """หา core/.env — คำนวณจาก __file__ ใช้ได้ไม่ว่าจะรัน uvicorn จากที่ไหน"""
    # core/src/config/settings.py → parent×3 = core/
    core_env = Path(__file__).resolve().parent.parent.parent / ".env"
    return (str(core_env),) if core_env.exists() else (".env",)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=_env_files(),
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
    LLM_MODEL_ROUTER: str = "openai/gpt-4o-mini"
    LLM_TEMPERATURE_RAG: float = 0.7
    LLM_TEMPERATURE_LAYOUT: float = 0.4

    # ==========================================================================
    # Database Configuration
    # ==========================================================================
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/buddybuilder"

    # ==========================================================================
    # ChromaDB Vector Store (Local file-based — RAG from feng-shui-rag)
    # ==========================================================================
    CHROMA_DB_PATH: str = "../feng-shui-rag/vectorstore/chroma_db"
    """Path to local ChromaDB persistence directory (feng-shui RAG vectorstore)."""

    # ==========================================================================
    # Embedding Model
    # รับ EMBEDDING_MODEL (shared) หรือ EMBEDDING_MODEL_LOCAL (project-specific)
    # ==========================================================================
    EMBEDDING_MODEL_LOCAL: str = "BAAI/bge-m3"
    """HuggingFace embedding model สำหรับ local ChromaDB — ตั้งค่าที่ Buddy Builder/.env"""

    # ==========================================================================
    # RAG Configuration  ← ตั้งค่าที่ Buddy Builder/.env
    # ==========================================================================
    RAG_TOP_K: int = 5
    """Number of documents to retrieve per query."""

    RAG_SEARCH_TYPE: str = "mmr"
    """Retrieval search type: 'mmr' (diverse) or 'similarity' (precise)."""

    RAG_RELEVANCE_THRESHOLD: float = 1.0
    """L2 distance threshold for filtering out-of-scope queries (lower = stricter)."""

    # ==========================================================================
    # Security
    # ==========================================================================
    SECRET_KEY: str = "your-super-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # ==========================================================================
    # CORS Settings
    # ==========================================================================
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8080"]

    def __init__(self, **data: object) -> None:
        super().__init__(**data)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
