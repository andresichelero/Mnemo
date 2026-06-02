"""Embedding service — Telnyx Embeddings API integration.

Generates vector embeddings from text descriptions for semantic search.
Falls back gracefully when API key is not configured.
"""

from __future__ import annotations

import hashlib

import httpx
import structlog
from cachetools import TTLCache

logger = structlog.get_logger()

TELNYX_EMBEDDINGS_URL = "https://api.telnyx.com/v2/ai/embeddings"


class EmbeddingService:
    """Telnyx Embeddings API wrapper with caching and graceful fallback."""

    def __init__(self, api_key: str, model: str = "thenlper/gte-large"):
        self.api_key = api_key
        self.model = model
        self._client: httpx.AsyncClient | None = None
        # Cache embeddings by text hash — avoids re-calling API for identical text
        self._cache: TTLCache = TTLCache(maxsize=500, ttl=3600)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _text_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    async def check_connection(self) -> bool:
        """Verify the API key is valid by sending a minimal embedding request."""
        if not self.api_key:
            return False
        try:
            client = await self._get_client()
            resp = await client.post(
                TELNYX_EMBEDDINGS_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"input": "test", "model": self.model},
                timeout=10.0,
            )
            return resp.status_code == 200
        except Exception as e:
            logger.warning("embedding.connection_failed", error=str(e))
            return False

    async def generate_embedding(self, text: str) -> list[float] | None:
        """Generate a vector embedding for the given text.

        Returns:
            List of floats (the embedding vector), or None if:
            - API key is not configured
            - API call fails after retries
            - Text is empty

        The pipeline is never blocked by embedding failures.
        """
        if not self.api_key:
            logger.debug("embedding.skipped", reason="no_api_key")
            return None

        if not text or not text.strip():
            return None

        # Check cache first
        cache_key = self._text_hash(text)
        if cache_key in self._cache:
            logger.debug("embedding.cache_hit", hash=cache_key)
            return self._cache[cache_key]

        client = await self._get_client()
        backoff_delays = [1, 2, 4]

        for attempt in range(3):
            try:
                resp = await client.post(
                    TELNYX_EMBEDDINGS_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "input": text,
                        "model": self.model,
                    },
                )
                resp.raise_for_status()

                data = resp.json()
                embedding = data["data"][0]["embedding"]

                # Cache the result
                self._cache[cache_key] = embedding

                logger.info(
                    "embedding.generated",
                    dimensions=len(embedding),
                    text_length=len(text),
                )
                return embedding

            except Exception as e:
                logger.warning(
                    "embedding.retry",
                    attempt=attempt + 1,
                    error=str(e),
                )
                if attempt < len(backoff_delays):
                    import asyncio
                    await asyncio.sleep(backoff_delays[attempt])

        logger.error("embedding.failed", text_preview=text[:80])
        return None

    @staticmethod
    def build_embedding_text(description: str, tags: list[str], category: str) -> str:
        """Compose the text to embed from analysis fields.

        Combines description, tags, and category into a single string
        optimised for semantic search.
        """
        tags_str = ", ".join(tags) if tags else ""
        return f"{description}. Tags: {tags_str}. Category: {category}"
