"""Tests for settings_service — caching, updates, masking."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.setting import Setting
from app.services.settings_service import SettingsService


@pytest.fixture
async def db_session(tmp_path):
    """Create an in-memory SQLite session for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Seed some test settings
        session.add(Setting(key="test_key", value="test_value"))
        session.add(Setting(key="telnyx_api_key", value="sk-secret-12345"))
        await session.commit()

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_all(db_session: AsyncSession):
    service = SettingsService()
    settings = await service.get_all(db_session)
    assert "test_key" in settings
    assert settings["test_key"] == "test_value"


@pytest.mark.asyncio
async def test_get_single(db_session: AsyncSession):
    service = SettingsService()
    val = await service.get(db_session, "test_key")
    assert val == "test_value"


@pytest.mark.asyncio
async def test_get_default(db_session: AsyncSession):
    service = SettingsService()
    val = await service.get(db_session, "nonexistent", default="fallback")
    assert val == "fallback"


@pytest.mark.asyncio
async def test_cache_invalidation(db_session: AsyncSession):
    service = SettingsService()
    await service.get_all(db_session)
    assert service._cache_valid()

    service.invalidate()
    assert not service._cache_valid()


@pytest.mark.asyncio
async def test_mask_secrets():
    settings = {
        "test_key": "visible",
        "telnyx_api_key": "sk-secret-12345",
    }
    masked = SettingsService.mask_secrets(settings)
    assert masked["test_key"] == "visible"
    assert masked["telnyx_api_key"] == "sk-s****"
    # Original not mutated
    assert settings["telnyx_api_key"] == "sk-secret-12345"
