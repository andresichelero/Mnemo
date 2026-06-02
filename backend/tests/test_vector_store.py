"""Tests for vector_store — ChromaDB wrapper."""

import pytest

from app.services.vector_store import VectorStore


@pytest.fixture
def store(tmp_path) -> VectorStore:
    """Create a VectorStore backed by a temporary directory."""
    return VectorStore(persist_path=str(tmp_path / "chroma_test"))


@pytest.mark.asyncio
async def test_add_and_count(store: VectorStore):
    await store.add("s1", [0.1] * 1024, {"category": "photo"})
    assert await store.count() == 1


@pytest.mark.asyncio
async def test_add_and_query(store: VectorStore):
    # Create clearly distinct vectors
    vec_a = [1.0] + [0.0] * 1023
    vec_b = [0.0] * 1023 + [1.0]

    await store.add("s1", vec_a, {"category": "document"})
    await store.add("s2", vec_b, {"category": "code"})

    results = await store.query(vec_a, n_results=5)
    assert len(results) == 2
    # s1 should be most similar to vec_a
    assert results[0]["id"] == "s1"
    assert results[0]["score"] >= results[1]["score"]


@pytest.mark.asyncio
async def test_delete(store: VectorStore):
    await store.add("s1", [0.5] * 1024)
    assert await store.count() == 1
    await store.delete("s1")
    assert await store.count() == 0


@pytest.mark.asyncio
async def test_upsert(store: VectorStore):
    await store.add("s1", [0.1] * 1024)
    await store.add("s1", [0.9] * 1024)  # Should update, not duplicate
    assert await store.count() == 1


@pytest.mark.asyncio
async def test_warmup(store: VectorStore):
    # Should not raise even when empty
    await store.warmup()

    await store.add("s1", [0.5] * 1024)
    await store.warmup()  # Should not raise with data either


@pytest.mark.asyncio
async def test_reconcile(store: VectorStore):
    await store.add("s1", [0.1] * 1024)
    await store.add("s2", [0.2] * 1024)
    await store.add("orphan", [0.3] * 1024)

    # Only s1 and s2 are "known" — orphan should be removed
    result = await store.reconcile(known_ids={"s1", "s2"})
    assert result["orphaned_removed"] == 1
    assert await store.count() == 2
