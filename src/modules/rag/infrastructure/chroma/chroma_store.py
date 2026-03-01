"""ChromaDB thin wrapper — async-safe, graceful empty/unavailable handling.

This module provides a minimal async interface to ChromaDB.  It never raises
exceptions to callers: connection failures and query errors return empty results,
allowing the pipeline to continue with MockRagSearchTool as fallback.

Usage:
    store = ChromaStore()
    connected = await store.connect()   # False if Chroma is unavailable
    results = await store.query(["feng shui bedroom"], n_results=5)
"""

from __future__ import annotations

import logging
from typing import Any

from src.config.settings import get_settings

logger = logging.getLogger(__name__)


class ChromaStore:
    """Thin async wrapper around ChromaDB.

    Returns empty results if ChromaDB is unavailable or the collection is empty.
    The `connect()` method must be called before `query()` — but both are safe
    to call multiple times.

    Attributes:
        _connected: Whether a successful connection has been established.
    """

    def __init__(self) -> None:
        self._client: Any = None
        self._collection: Any = None
        self._connected: bool = False

    async def connect(self) -> bool:
        """Try to connect to ChromaDB.

        Returns:
            True if connection succeeded and collection is accessible,
            False if chromadb package is missing or server is unreachable.
        """
        try:
            import chromadb  # type: ignore[import]

            settings = get_settings()
            self._client = await chromadb.AsyncHttpClient(
                host=settings.CHROMA_HOST,
                port=settings.CHROMA_PORT,
            )
            self._collection = await self._client.get_or_create_collection(
                name=settings.CHROMA_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
            self._connected = True
            logger.info(
                f"ChromaStore: connected to {settings.CHROMA_HOST}:{settings.CHROMA_PORT}"
                f" collection={settings.CHROMA_COLLECTION!r}"
            )
            return True

        except ImportError:
            logger.debug("ChromaStore: chromadb package not installed — skipping")
            return False
        except Exception as exc:
            logger.debug(f"ChromaStore: connection failed ({exc}) — skipping")
            return False

    async def query(
        self, texts: list[str], n_results: int = 5
    ) -> list[dict[str, Any]]:
        """Query the collection with text queries.

        Args:
            texts: One or more query strings.
            n_results: Number of results to retrieve per query.

        Returns:
            List of result dicts with keys: id, document, metadata, distance.
            Returns empty list on any error.
        """
        if not self._connected or self._collection is None:
            return []
        try:
            raw = await self._collection.query(
                query_texts=texts,
                n_results=n_results,
                include=["documents", "metadatas", "distances"],
            )
            return self._parse_results(raw)
        except Exception as exc:
            logger.debug(f"ChromaStore.query() failed: {exc}")
            return []

    async def add_documents(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
        embeddings: list[list[float]] | None = None,
    ) -> bool:
        """Add documents to the collection.

        Args:
            ids: Unique IDs for each document chunk.
            documents: Text content of each chunk.
            metadatas: Metadata dicts (source, topic, language, etc.)
            embeddings: Pre-computed embeddings (optional; Chroma can compute them).

        Returns:
            True on success, False on error.
        """
        if not self._connected or self._collection is None:
            return False
        try:
            kwargs: dict[str, Any] = {
                "ids": ids,
                "documents": documents,
                "metadatas": metadatas,
            }
            if embeddings is not None:
                kwargs["embeddings"] = embeddings
            await self._collection.add(**kwargs)
            return True
        except Exception as exc:
            logger.warning(f"ChromaStore.add_documents() failed: {exc}")
            return False

    async def count(self) -> int:
        """Return the number of documents in the collection (0 if unavailable)."""
        if not self._connected or self._collection is None:
            return 0
        try:
            return await self._collection.count()
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_results(raw: dict[str, Any]) -> list[dict[str, Any]]:
        """Flatten ChromaDB query results into a list of dicts."""
        results: list[dict[str, Any]] = []
        ids_batch = raw.get("ids", [[]])
        docs_batch = raw.get("documents", [[]])
        metas_batch = raw.get("metadatas", [[]])
        dists_batch = raw.get("distances", [[]])

        for ids, docs, metas, dists in zip(ids_batch, docs_batch, metas_batch, dists_batch):
            for doc_id, doc, meta, dist in zip(ids, docs, metas, dists):
                results.append({
                    "id": doc_id,
                    "document": doc,
                    "metadata": meta or {},
                    "distance": dist,
                })
        return results
