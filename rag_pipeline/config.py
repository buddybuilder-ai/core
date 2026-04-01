"""
ไฟล์ตั้งค่าสำหรับ RAG Pipeline (core/rag_pipeline/)

การโหลด config (priority สูง → ต่ำ):
  1. Environment variables (CLI / shell export)
  2. core/.env            ← project-specific (LLM_MODEL, API keys, paths)

เลือก LLM ที่ใช้โดยตั้งค่าตัวแปรเดียว:
  LLM_MODEL=ollama/qwen2.5:7b
  LLM_MODEL=groq/llama-3.3-70b-versatile
  LLM_MODEL=claude/claude-sonnet-4-20250514
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# อ่านจาก core/.env ที่เดียว (parent.parent = core/)
load_dotenv(Path(__file__).parent.parent / ".env")

# ==================== LLM Configuration ====================
# แก้แค่บรรทัดเดียวใน .env: LLM_MODEL=provider/model-name
_LLM_MODEL_RAW = os.getenv("LLM_MODEL", "ollama/qwen2.5:7b")
LLM_PROVIDER, _, LLM_MODEL_NAME = _LLM_MODEL_RAW.partition("/")
LLM_PROVIDER = LLM_PROVIDER.lower()
"""Provider ที่ parse ได้อัตโนมัติ: ollama | groq | claude"""

OLLAMA_MODEL = LLM_MODEL_NAME
"""ชื่อ model สำหรับ Ollama (alias ของ LLM_MODEL_NAME)"""

TEMPERATURE = float(os.getenv("TEMPERATURE", "0.3"))
"""อุณหภูมิทั่วไป: 0.0 = ตอบตรง | 1.0 = สร้างสรรค์"""

MAX_TOKENS = int(os.getenv("MAX_TOKENS", "2000"))
"""จำนวน tokens สูงสุดในการตอบ"""

# Temperature สำหรับงานเฉพาะ
CONTEXTUAL_TEMPERATURE = float(os.getenv("CONTEXTUAL_TEMPERATURE", "0.2"))
"""Temperature สำหรับ Contextual Chunking (step2b) — ต่ำ = แม่นยำ"""

QUESTION_GEN_TEMPERATURE = float(os.getenv("QUESTION_GEN_TEMPERATURE", "0.4"))
"""Temperature สำหรับสร้างคำถาม (step2c) — ปานกลาง = หลากหลายพอดี"""

# ==================== Relevance Filtering ====================
RELEVANCE_THRESHOLD = float(
    os.getenv("RAG_RELEVANCE_THRESHOLD") or os.getenv("RELEVANCE_THRESHOLD") or "0.35"
)
"""L2 Distance Threshold สำหรับกรองคำถามนอก scope"""

FUZZY_MATCH_THRESHOLD = int(os.getenv("FUZZY_MATCH_THRESHOLD", "3"))
"""จำนวนตัวอักษรที่ต่างกันได้สำหรับ fuzzy matching
- 1 = เข้มงวด | 2 = แนะนำ | 3 = ผ่อนปรน
"""

# ==================== API Keys (ใส่เฉพาะ provider ที่ใช้) ====================
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
"""Ollama endpoint"""

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
"""Groq API Key — https://console.groq.com/keys"""

GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
"""Groq endpoint (OpenAI-compatible)"""

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
"""Anthropic API Key — https://console.anthropic.com"""

# ==================== Embedding Configuration ====================
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-base")


# ==================== ChromaDB Configuration ====================
# Default: rag_pipeline/vectorstore/chroma_db (absolute, ไม่ขึ้นกับ cwd)
_default_chroma = str(Path(__file__).parent / "vectorstore" / "chroma_db")
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", _default_chroma)
"""Path สำหรับ Local ChromaDB"""

# Cloud ChromaDB (optional)
CHROMA_HOST = os.getenv("CHROMA_HOST", "")
CHROMA_API_KEY = os.getenv("CHROMA_API_KEY", "")
CHROMA_TENANT = os.getenv("CHROMA_TENANT", "")
CHROMA_DATABASE = os.getenv("CHROMA_DATABASE", "")

# ==================== Chunking Configuration ====================
CHUNK_CONFIG = {
    "chunk_size": int(os.getenv("CHUNK_SIZE", "1000")),
    "chunk_overlap": int(os.getenv("CHUNK_OVERLAP", "200")),
    "separators": ["\n\n", "\n", " ", ""],
}

# ==================== Retriever Configuration ====================
# รับทั้ง RAG_TOP_K (shared) และ TOP_K (legacy)
TOP_K = int(os.getenv("RAG_TOP_K") or os.getenv("TOP_K") or "5")
"""จำนวน chunks ที่ดึงมาต่อ query"""

# รับทั้ง RAG_SEARCH_TYPE (shared) และ SEARCH_TYPE (legacy)
SEARCH_TYPE = os.getenv("RAG_SEARCH_TYPE") or os.getenv("SEARCH_TYPE") or "mmr"
"""วิธีค้นหา: mmr (หลากหลาย) หรือ similarity (แม่นยำ)"""

# ==================== Conversation Memory ====================
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "10"))
"""จำนวนรอบการสนทนาที่เก็บไว้ใน memory"""

# ==================== LLM Generation Parameters ====================
TOP_P = float(os.getenv("TOP_P", "0.9"))
"""Top-p sampling (nucleus sampling) สำหรับ Ollama"""

REPEAT_PENALTY = float(os.getenv("REPEAT_PENALTY", "1.15"))
"""ลงโทษการพูดซ้ำ (1.0 = ไม่ลงโทษ, >1 = หลีกเลี่ยงซ้ำ)"""

# ==================== Hypothetical Questions ====================
QUESTIONS_PER_CHUNK = int(os.getenv("QUESTIONS_PER_CHUNK", "3"))
"""จำนวนคำถามสมมติที่สร้างต่อ chunk (step2c)"""
"""การตั้งค่าการแบ่ง chunks
- chunk_size: ขนาด chunk (ตัวอักษร)
- chunk_overlap: ส่วนที่ทับซ้อนระหว่าง chunks
"""


def print_config():
    """แสดงการตั้งค่าปัจจุบัน (สำหรับ debug)"""
    print("\n" + "="*60)
    print("RAG System Configuration")
    print("="*60)
    print(f"LLM Provider:        {LLM_PROVIDER}")
    print(f"Temperature:         {TEMPERATURE}")
    print(f"Max Tokens:          {MAX_TOKENS}")

    print(f"LLM Model:           {_LLM_MODEL_RAW}")

    if LLM_PROVIDER == "ollama":
        print(f"Ollama URL:          {OLLAMA_BASE_URL}")
    elif LLM_PROVIDER == "claude":
        print(f"API Key:             {'Set' if ANTHROPIC_API_KEY else 'Not Set'}")
    elif LLM_PROVIDER == "groq":
        print(f"Groq URL:            {GROQ_BASE_URL}")
        print(f"API Key:             {'Set' if GROQ_API_KEY else 'Not Set'}")

    print(f"\nEmbedding Model:     {EMBEDDING_MODEL}")
    print(f"ChromaDB Path:       {CHROMA_DB_PATH}")
    print(f"Chunk Size:          {CHUNK_CONFIG['chunk_size']}")
    print(f"Chunk Overlap:       {CHUNK_CONFIG['chunk_overlap']}")
    print("="*60 + "\n")


if __name__ == "__main__":
    print_config()
