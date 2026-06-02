"""Vector store — ChromaDB wrapper for persistent vector search.

All ChromaDB operations run via ``run_in_executor`` because
ChromaDB's PersistentClient is synchronous. This prevents
blocking FastAPI's async event loop.
"""

from __future__ import annotations

import asyncio
from functools import partial
from typing import Any

import chromadb
import structlog

logger = structlog.get_logger()


class VectorStore:
    """Wrapper around ChromaDB for screenshot embeddings."""

    COLLECTION_NAME = "screenshots"

    def __init__(self, persist_path: str):
        self.persist_path = persist_path
        self._client: chromadb.ClientAPI | None = None
        self._collection: chromadb.Collection | None = None
        self._write_lock = asyncio.Lock()

    def _ensure_client(self) -> chromadb.Collection:
        """Lazily initialise the ChromaDB client and collection."""
        if self._client is None:
            self._client = chromadb.PersistentClient(path=self.persist_path)
            self._collection = self._client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(
                "vector_store.initialized",
                path=self.persist_path,
                count=self._collection.count(),
            )
        return self._collection

    async def _run_sync(self, fn, *args, **kwargs):
        """Run a synchronous ChromaDB operation in a thread executor."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(fn, *args, **kwargs))

    async def add(
        self,
        screenshot_id: str,
        embedding: list[float],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add or update a screenshot embedding in ChromaDB."""
        def _add():
            coll = self._ensure_client()
            # ChromaDB requires non-empty metadata dicts
            meta = metadata or {}
            if not meta:
                meta = {"_placeholder": True}
            coll.upsert(
                ids=[screenshot_id],
                embeddings=[embedding],
                metadatas=[meta],
            )

        async with self._write_lock:
            await self._run_sync(_add)
        logger.debug("vector_store.added", screenshot_id=screenshot_id)

    async def query(
        self,
        embedding: list[float],
        n_results: int = 20,
        where: dict[str, Any] | None = None,
    ) -> list[dict]:
        """Query for similar screenshots by embedding vector.

        Returns:
            List of dicts with keys: id, score, metadata.
            Sorted by descending similarity (highest score first).
        """
        def _query():
            coll = self._ensure_client()
            kwargs: dict[str, Any] = {
                "query_embeddings": [embedding],
                "n_results": min(n_results, coll.count() or 1),
            }
            if where:
                kwargs["where"] = where
            return coll.query(**kwargs)

        results = await self._run_sync(_query)

        items = []
        if results and results.get("ids"):
            ids = results["ids"][0]
            distances = results["distances"][0] if results.get("distances") else [0] * len(ids)
            metadatas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(ids)

            for i, doc_id in enumerate(ids):
                # ChromaDB returns cosine distance; convert to similarity score
                score = 1.0 - distances[i] if distances[i] else 1.0
                items.append({
                    "id": doc_id,
                    "score": round(score, 4),
                    "metadata": metadatas[i],
                })

        return items

    async def delete(self, screenshot_id: str) -> None:
        """Remove a screenshot's embedding from ChromaDB."""
        def _delete():
            coll = self._ensure_client()
            coll.delete(ids=[screenshot_id])

        async with self._write_lock:
            await self._run_sync(_delete)
        logger.debug("vector_store.deleted", screenshot_id=screenshot_id)

    async def count(self) -> int:
        """Return the total number of embeddings stored."""
        def _count():
            coll = self._ensure_client()
            return coll.count()

        return await self._run_sync(_count)

    async def warmup(self) -> None:
        """Perform a warm-up query to pre-load the collection into memory."""
        def _warmup():
            coll = self._ensure_client()
            if coll.count() > 0:
                # Minimal query just to warm the index
                coll.peek(limit=1)

        await self._run_sync(_warmup)
        logger.info("vector_store.warmed_up")

    async def reconcile(self, known_ids: set[str]) -> dict[str, int]:
        """Check consistency: remove ChromaDB entries not in the known_ids set.

        Returns:
            Dict with keys: orphaned_removed, total_checked.
        """
        def _reconcile():
            coll = self._ensure_client()
            all_chroma = coll.get()
            chroma_ids = set(all_chroma["ids"]) if all_chroma.get("ids") else set()
            orphans = chroma_ids - known_ids
            if orphans:
                coll.delete(ids=list(orphans))
            return {"orphaned_removed": len(orphans), "total_checked": len(chroma_ids)}

        async with self._write_lock:
            result = await self._run_sync(_reconcile)
        
        if result["orphaned_removed"] > 0:
            logger.warning("vector_store.reconciled", **result)
        return result
