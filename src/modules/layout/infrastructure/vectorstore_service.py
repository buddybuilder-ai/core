"""Vectorstore service for local ChromaDB with HuggingFace embeddings.

This service initialises the ChromaDB vectorstore that was built by the
feng-shui-rag pipeline (see feng-shui-rag/src/step3_vectorstore.py) and
exposes a LangChain retriever that the ChromaDbRagSearchTool can use.

The vectorstore lives at the path configured in Settings.CHROMA_DB_PATH
(default: ./vectorstore/chroma_db) and uses the HuggingFace multilingual
embedding model defined in Settings.EMBEDDING_MODEL_LOCAL.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_community.vectorstores import Chroma
    from langchain_core.vectorstores import VectorStoreRetriever

logger = logging.getLogger(__name__)


def _get_embeddings(model_name: str) -> "object":
    """Build a HuggingFaceEmbeddings instance, auto-selecting GPU/CPU.

    Args:
        model_name: HuggingFace model identifier (e.g. 'intfloat/multilingual-e5-base').

    Returns:
        A HuggingFaceEmbeddings object ready for use with ChromaDB.
    """
    from langchain_community.embeddings import HuggingFaceEmbeddings

    device = "cpu"
    try:
        import torch

        if torch.cuda.is_available():
            device = "cuda"
            logger.info("Vectorstore embeddings: using CUDA GPU")
        elif torch.backends.mps.is_available():
            device = "mps"
            logger.info("Vectorstore embeddings: using Apple Silicon MPS")
        else:
            logger.info("Vectorstore embeddings: using CPU")
    except ImportError:
        logger.info("torch not installed — vectorstore embeddings will use CPU")

    return HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={"device": device},
        encode_kwargs={"normalize_embeddings": True},
    )


def load_vectorstore(db_path: str, embedding_model: str) -> "Chroma":
    """Load an existing ChromaDB vectorstore from disk.

    Args:
        db_path: Absolute or relative path to the ChromaDB persistence directory.
        embedding_model: HuggingFace model name used when the store was built.

    Returns:
        A Chroma vectorstore instance.

    Raises:
        FileNotFoundError: If the vectorstore directory does not exist.
    """
    from langchain_community.vectorstores import Chroma

    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(
            f"ChromaDB vectorstore not found at '{db_path}'. "
            "Run the feng-shui-rag indexing pipeline first "
            "(feng-shui-rag/main.py or feng-shui-rag/src/step3_vectorstore.py)."
        )

    embeddings = _get_embeddings(embedding_model)
    logger.info("Loading ChromaDB vectorstore from '%s'", db_path)

    return Chroma(
        persist_directory=str(path),
        embedding_function=embeddings,
    )


def get_retriever(
    db_path: str,
    embedding_model: str,
    k: int = 5,
    search_type: str = "mmr",
) -> "VectorStoreRetriever":
    """Return a LangChain retriever backed by the local ChromaDB vectorstore.

    Args:
        db_path: Path to the ChromaDB persistence directory.
        embedding_model: HuggingFace model name.
        k: Number of documents to retrieve per query.
        search_type: 'mmr' (diverse) or 'similarity' (precise).

    Returns:
        A configured VectorStoreRetriever.
    """
    vectorstore = load_vectorstore(db_path, embedding_model)
    retriever = vectorstore.as_retriever(
        search_type=search_type,
        search_kwargs={"k": k},
    )
    logger.info("ChromaDB retriever ready (search_type=%s, k=%d)", search_type, k)
    return retriever


@lru_cache(maxsize=1)
def get_cached_vectorstore(db_path: str, embedding_model: str) -> "Chroma":
    """Return a module-level cached ChromaDB vectorstore (loads once per process).

    Using lru_cache means the heavy model-loading step only happens once,
    regardless of how many tools / requests share the same process.

    Args:
        db_path: Path to the ChromaDB persistence directory.
        embedding_model: HuggingFace model name.

    Returns:
        The cached Chroma vectorstore instance.
    """
    return load_vectorstore(db_path, embedding_model)
