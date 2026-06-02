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
TELNYX_EMBEDDINGS_URL = "https://api.telnyx.com/v2/ai/openai/embeddings"


class EmbeddingService:
    """Telnyx Embeddings API wrapper with caching and graceful fallback."""

    def __init__(
        self,
        api_key: str,
        model: str = "thenlper/gte-large",
        ollama_base_url: str = "http://localhost:11434",
        local_model: str = "nomic-embed-text",
    ):
        self.api_key = api_key
        self.model = model
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.local_model = local_model
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
        """Verify the API key is valid or fallback to local Ollama."""
        client = await self._get_client()
        if not self.api_key:
            # Fallback connection check
            try:
                resp = await client.get(f"{self.ollama_base_url}/api/tags", timeout=5.0)
                if resp.status_code == 200:
                    models = [m.get("name", "") for m in resp.json().get("models", [])]
                    return any(self.local_model in m for m in models)
            except Exception as e:
                logger.warning("embedding.local_connection_failed", error=str(e))
            return False

        try:
            resp = await client.post(
                TELNYX_EMBEDDINGS_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"input": "test", "model": self.model},
                timeout=10.0,
            )
            return resp.status_code == 200
        except Exception as e:
            logger.warning("embedding.telnyx_connection_failed", error=str(e))
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
                if self.api_key:
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
                    used_provider = "telnyx"
                else:
                    # Fallback offline
                    resp = await client.post(
                        f"{self.ollama_base_url}/api/embeddings",
                        json={
                            "prompt": text,
                            "model": self.local_model,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    embedding = data["embedding"]
                    used_provider = "ollama"

                # Cache the result
                self._cache[cache_key] = embedding

                logger.info(
                    "embedding.generated",
                    provider=used_provider,
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
