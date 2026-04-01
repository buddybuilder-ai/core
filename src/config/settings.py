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
    # LLM Model — format: provider/model-name  (แก้แค่บรรทัดนี้ที่เดียว)
    # ตัวอย่าง:
    #   ollama/qwen2.5:7b
    #   groq/llama-3.3-70b-versatile
    #   groq/llama-3.1-8b-instant
    #   openrouter/anthropic/claude-3.5-sonnet
    # ==========================================================================
    LLM_MODEL: str = "openrouter/anthropic/claude-3.5-sonnet"
    """LLM backend — parse provider จาก prefix ก่อน /"""

    @property
    def LLM_PROVIDER(self) -> str:
        """Provider ที่ parse จาก LLM_MODEL (ollama | groq | openrouter | claude)"""
        return self.LLM_MODEL.partition("/")[0].lower()

    @property
    def LLM_MODEL_NAME(self) -> str:
        """Model name หลัง prefix provider/"""
        return self.LLM_MODEL.partition("/")[2]

    # ==========================================================================
    # OpenRouter Configuration
    # ==========================================================================
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # ==========================================================================
    # Ollama Configuration (ใช้เมื่อ LLM_MODEL=ollama/...)
    # ==========================================================================
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL_RAG: str = "qwen2.5:7b"
    """legacy — ใช้เมื่อ LLM_PROVIDER=ollama (ค่าถูก override โดย LLM_MODEL)"""

    # ==========================================================================
    # Groq Configuration (ใช้เมื่อ LLM_MODEL=groq/...)
    # ==========================================================================
    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"

    # ==========================================================================
    # RAG LLM Temperature
    # ==========================================================================
    LLM_TEMPERATURE_RAG: float = 0.7

    # ==========================================================================
    # Layout Pipeline LLM — OpenRouter เสมอ (ไม่ขึ้นกับ LLM_PROVIDER)
    # ==========================================================================
    LLM_MODEL_LAYOUT: str = "openai/gpt-4-turbo"
    LLM_MODEL_ROUTER: str = "openai/gpt-4o-mini"
    LLM_TEMPERATURE_LAYOUT: float = 0.4
    LLM_LAYOUT_BASE_URL: str = ""
    LLM_LAYOUT_API_KEY: str = ""

    # ==========================================================================
    # Database Configuration
    # ==========================================================================
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/buddybuilder"

    # ==========================================================================
    # ChromaDB Vector Store (Local file-based — RAG from feng-shui-rag)
    # ==========================================================================
    CHROMA_DB_PATH: str = "../feng-shui-rag/vectorstore/chroma_db"
    """Path to local ChromaDB persistence directory (feng-shui RAG vectorstore)."""
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8000
    CHROMA_COLLECTION: str = "feng_shui_rag"

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


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
