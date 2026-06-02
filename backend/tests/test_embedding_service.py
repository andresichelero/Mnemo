"""Tests for embedding_service — text composition and cache logic."""

import pytest

from app.services.embedding_service import EmbeddingService


class TestBuildEmbeddingText:
    def test_full_text(self):
        text = EmbeddingService.build_embedding_text(
            description="A bank statement showing transactions",
            tags=["finance", "bank", "statement"],
            category="document",
        )
        assert "A bank statement" in text
        assert "finance" in text
        assert "Category: document" in text

    def test_empty_tags(self):
        text = EmbeddingService.build_embedding_text(
            description="A photo",
            tags=[],
            category="photo",
        )
        assert "Tags: " in text
        assert "Category: photo" in text


class TestEmbeddingServiceInit:
    def test_no_api_key_skips(self):
        service = EmbeddingService(api_key="", model="test")
        # Without API key, generate_embedding should return None
        # (async test would be needed for the actual call)
        assert service.api_key == ""

    def test_cache_initialized(self):
        service = EmbeddingService(api_key="test-key", model="thenlper/gte-large")
        assert len(service._cache) == 0


class TestTextHash:
    def test_deterministic(self):
        service = EmbeddingService(api_key="", model="test")
        h1 = service._text_hash("hello world")
        h2 = service._text_hash("hello world")
        assert h1 == h2

    def test_different_inputs(self):
        service = EmbeddingService(api_key="", model="test")
        h1 = service._text_hash("hello")
        h2 = service._text_hash("world")
        assert h1 != h2
