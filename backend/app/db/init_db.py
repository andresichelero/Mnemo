"""Database initialisation — creates tables and seeds default settings."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base
from app.models.setting import Setting
from app.db.session import engine, async_session_factory

logger = structlog.get_logger()

DEFAULT_SETTINGS: dict[str, str] = {
    "watched_folders": "[]",
    "ollama_base_url": "http://localhost:11434",
    "ollama_model": "gemma3:4b",
    "telnyx_api_key": "",
    "telnyx_embedding_model": "thenlper/gte-large",
    "processing_mode": "idle",
    "idle_threshold_cpu": "10",
    "idle_check_seconds": "30",
    "auto_organize": "false",
    "mobile_server_port": "8765",
    "max_retries": "3",
    "thumbnail_size": "256",
    "max_upload_size_mb": "20",
    "max_daily_processing": "500",
    "enable_api_docs": "true",
}


async def init_db() -> None:
    """Create all tables and seed default settings if they don't exist."""
    logger.info("database.init", action="creating_tables")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("database.init", action="seeding_settings")

    async with async_session_factory() as session:
        await _seed_settings(session)
        await session.commit()

    logger.info("database.init", action="complete")


async def _seed_settings(session: AsyncSession) -> None:
    """Insert default settings only if they don't already exist."""
    for key, value in DEFAULT_SETTINGS.items():
        result = await session.execute(select(Setting).where(Setting.key == key))
        existing = result.scalar_one_or_none()
        if existing is None:
            session.add(Setting(key=key, value=value))
            logger.debug("database.seed_setting", key=key, value=value[:30])
