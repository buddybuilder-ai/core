"""Document Loader — seeds ChromaDB with feng shui knowledge documents.

CLI utility only; not invoked by the pipeline at runtime.

Supported file types: .pdf, .md, .txt
Chunking: 500-token chunks with 50-token overlap (word-based approximation)
Metadata stored: source filename, topic (derived from filename), language

Usage:
    python -m src.modules.rag.document_loader \
        --paths docs/feng_shui_en.pdf docs/feng_shui_th.md \
        --language th

Or programmatically:
    import asyncio
    from src.modules.rag.document_loader import load_documents
    count = asyncio.run(load_documents(["docs/feng_shui.pdf"], language="en"))
    print(f"Loaded {count} chunks")
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Approximate word-count limits (1 token ≈ 0.75 words for English/Thai)
_CHUNK_WORDS = 375   # ≈ 500 tokens
_OVERLAP_WORDS = 38  # ≈ 50 tokens


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def load_documents(
    paths: list[str],
    chunk_size: int = _CHUNK_WORDS,
    chunk_overlap: int = _OVERLAP_WORDS,
    language: str = "en",
) -> int:
    """Load documents into ChromaDB.

    Args:
        paths: File paths (.pdf, .md, .txt).
        chunk_size: Approximate words per chunk.
        chunk_overlap: Approximate word overlap between consecutive chunks.
        language: Document language ("en" or "th") stored as metadata.

    Returns:
        Number of chunks successfully stored.  0 if ChromaDB is unavailable.
    """
    from src.modules.rag.infrastructure.chroma.chroma_store import ChromaStore

    store = ChromaStore()
    connected = await store.connect()
    if not connected:
        logger.warning("document_loader: ChromaDB unavailable — no documents loaded")
        return 0

    total_stored = 0
    for path_str in paths:
        path = Path(path_str)
        if not path.exists():
            logger.warning(f"document_loader: file not found — {path}")
            continue

        logger.info(f"document_loader: loading {path}")
        text = _read_file(path)
        if not text:
            continue

        chunks = _chunk_text(text, chunk_size, chunk_overlap)
        logger.info(f"  → {len(chunks)} chunks from {path.name}")

        ids, docs, metas = _prepare_records(chunks, path, language)
        ok = await store.add_documents(ids=ids, documents=docs, metadatas=metas)
        if ok:
            total_stored += len(chunks)
            logger.info(f"  ✓ Stored {len(chunks)} chunks from {path.name}")
        else:
            logger.warning(f"  ✗ Failed to store chunks from {path.name}")

    logger.info(f"document_loader: total chunks stored = {total_stored}")
    return total_stored


# ---------------------------------------------------------------------------
# File reading
# ---------------------------------------------------------------------------


def _read_file(path: Path) -> str:
    """Read a .pdf, .md, or .txt file and return plain text."""
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return _read_pdf(path)
    elif suffix in (".md", ".txt"):
        return path.read_text(encoding="utf-8", errors="replace")
    else:
        logger.warning(f"document_loader: unsupported file type {suffix!r} — {path}")
        return ""


def _read_pdf(path: Path) -> str:
    """Extract text from a PDF using PyPDF2 (optional dependency)."""
    try:
        import PyPDF2  # type: ignore[import]

        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)
    except ImportError:
        logger.warning(
            "document_loader: PyPDF2 not installed — cannot load PDF. "
            "Install it with: pip install PyPDF2"
        )
        return ""
    except Exception as exc:
        logger.warning(f"document_loader: failed to read PDF {path}: {exc}")
        return ""


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def _chunk_text(
    text: str, chunk_words: int, overlap_words: int
) -> list[str]:
    """Split text into overlapping word-count chunks."""
    # Normalise whitespace
    text = re.sub(r"\s+", " ", text).strip()
    words = text.split()

    if not words:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + chunk_words, len(words))
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        if end == len(words):
            break
        start += chunk_words - overlap_words

    return chunks


# ---------------------------------------------------------------------------
# Record preparation
# ---------------------------------------------------------------------------


def _prepare_records(
    chunks: list[str],
    path: Path,
    language: str,
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """Build ids, documents, and metadata dicts for ChromaDB insertion."""
    topic = _derive_topic(path.stem)
    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict[str, Any]] = []

    for i, chunk in enumerate(chunks):
        chunk_id = hashlib.md5(f"{path.name}:{i}:{chunk[:40]}".encode()).hexdigest()[:16]
        ids.append(chunk_id)
        docs.append(chunk)
        metas.append({
            "source": path.name,
            "topic": topic,
            "language": language,
            "chunk_index": i,
            "total_chunks": len(chunks),
        })

    return ids, docs, metas


def _derive_topic(stem: str) -> str:
    """Derive a human-readable topic from a filename stem."""
    return stem.replace("_", " ").replace("-", " ").lower()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load feng shui documents into ChromaDB"
    )
    parser.add_argument(
        "--paths", nargs="+", required=True, help="File paths to load (.pdf, .md, .txt)"
    )
    parser.add_argument(
        "--language", default="en", choices=["en", "th"], help="Document language"
    )
    parser.add_argument(
        "--chunk-size", type=int, default=_CHUNK_WORDS, help="Words per chunk"
    )
    parser.add_argument(
        "--chunk-overlap", type=int, default=_OVERLAP_WORDS, help="Overlap words"
    )
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = _parse_args()
    stored = asyncio.run(
        load_documents(
            paths=args.paths,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
            language=args.language,
        )
    )
    print(f"Stored {stored} chunks into ChromaDB.")
