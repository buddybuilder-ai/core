"""
ไฟล์ตั้งค่าสำหรับ RAG Pipeline (core/rag_pipeline/)

การโหลด config (priority สูง → ต่ำ):
  1. Environment variables (CLI / shell export)
  2. core/.env            ← project-specific (LLM_PROVIDER, OLLAMA, paths)
  3. Buddy Builder/.env   ← shared master config (embedding, RAG params)

แก้ค่าที่ใช้ร่วมกัน (embedding, RAG) ที่ Buddy Builder/.env เท่านั้น
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# อ่านจาก core/.env ที่เดียว (parent.parent = core/)
load_dotenv(Path(__file__).parent.parent / ".env")

# ==================== LLM Configuration ====================
# ตั้งค่า LLM Provider และ Parameters ที่นี่เพียงจุดเดียว

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()
"""LLM Provider: ollama, claude, huggingface"""

TEMPERATURE = float(os.getenv("TEMPERATURE", "0.3"))


MAX_TOKENS = int(os.getenv("MAX_TOKENS", "2000"))
"""จำนวน tokens สูงสุดในการตอบ"""

# Temperature สำหรับงานเฉพาะ (override TEMPERATURE ถ้าต้องการ)
CONTEXTUAL_TEMPERATURE = float(os.getenv("CONTEXTUAL_TEMPERATURE", "0.3"))
"""Temperature สำหรับ Contextual Chunking (ต่ำ = แม่นยำกว่า)"""

QUESTION_GEN_TEMPERATURE = float(os.getenv("QUESTION_GEN_TEMPERATURE", "0.4"))
"""Temperature สำหรับสร้างคำถาม (ปานกลาง = หลากหลายพอดี)"""

# ==================== Relevance Filtering ====================
# รับทั้ง RAG_RELEVANCE_THRESHOLD (shared) และ RELEVANCE_THRESHOLD (legacy)
RELEVANCE_THRESHOLD = float(
    os.getenv("RAG_RELEVANCE_THRESHOLD") or os.getenv("RELEVANCE_THRESHOLD") or "0.35"
)
"""L2 Distance Threshold สำหรับกรองคำถามนอก scope"""

FUZZY_MATCH_THRESHOLD = int(os.getenv("FUZZY_MATCH_THRESHOLD", "3"))
"""จำนวนตัวอักษรที่ต่างกันได้สำหรับ fuzzy matching (รองรับพิมพ์ผิด)
- 1 = เข้มงวด (ผิดได้ 1 ตัวอักษร)
- 2 = แนะนำ (ผิดได้ 2 ตัวอักษร)
- 3 = ผ่อนปรน (ผิดได้ 3 ตัวอักษร)
"""

# ==================== Ollama Configuration ====================
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
"""Ollama model name (เช่น llama3.2:3b, qwen2.5:7b, typhoon:8b)"""

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
"""Ollama API base URL"""

# ==================== Claude Configuration ====================
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
"""Anthropic API Key (สำหรับ Claude)"""

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
"""Claude model name"""

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

    if LLM_PROVIDER == "ollama":
        print(f"Ollama Model:        {OLLAMA_MODEL}")
        print(f"Ollama URL:          {OLLAMA_BASE_URL}")
    elif LLM_PROVIDER == "claude":
        print(f"Claude Model:        {CLAUDE_MODEL}")
        print(f"API Key:             {'Set' if ANTHROPIC_API_KEY else 'Not Set'}")

    print(f"\nEmbedding Model:     {EMBEDDING_MODEL}")
    print(f"ChromaDB Path:       {CHROMA_DB_PATH}")
    print(f"Chunk Size:          {CHUNK_CONFIG['chunk_size']}")
    print(f"Chunk Overlap:       {CHUNK_CONFIG['chunk_overlap']}")
    print("="*60 + "\n")


if __name__ == "__main__":
    print_config()
