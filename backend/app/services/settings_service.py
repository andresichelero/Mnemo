"""Settings service — cached read/write for runtime settings.

Settings live in the SQLite ``settings`` table as key-value pairs.
This service adds an in-memory cache with a 30-second TTL to avoid
hitting the DB on every access.
"""

from __future__ import annotations

import time
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.setting import Setting

logger = structlog.get_logger()

# Keys that should be masked in API responses (contain secrets)
_MASKED_KEYS = frozenset({"telnyx_api_key"})

CACHE_TTL_SECONDS = 30.0


class SettingsService:
    """Cached settings accessor."""

    def __init__(self):
        self._cache: dict[str, str] = {}
        self._cache_ts: float = 0.0

    def _cache_valid(self) -> bool:
        return bool(self._cache) and (time.monotonic() - self._cache_ts) < CACHE_TTL_SECONDS

    def invalidate(self) -> None:
        """Force the next read to hit the DB."""
        self._cache.clear()
        self._cache_ts = 0.0

    async def get_all(self, session: AsyncSession) -> dict[str, str]:
        """Return all settings as a dict. Uses cache if fresh."""
        if self._cache_valid():
            return dict(self._cache)

        result = await session.execute(select(Setting))
        rows = result.scalars().all()
        self._cache = {row.key: row.value for row in rows}
        self._cache_ts = time.monotonic()
        return dict(self._cache)

    async def get(self, session: AsyncSession, key: str, default: str = "") -> str:
        """Get a single setting value."""
        all_settings = await self.get_all(session)
        return all_settings.get(key, default)

    async def update(
        self, session: AsyncSession, updates: dict[str, str]
    ) -> dict[str, str]:
        """Update one or more settings. Returns the full updated settings dict."""
        for key, value in updates.items():
            result = await session.execute(select(Setting).where(Setting.key == key))
            existing = result.scalar_one_or_none()
            if existing:
                existing.value = str(value)
            else:
                session.add(Setting(key=key, value=str(value)))

        await session.flush()
        self.invalidate()
        logger.info("settings.updated", keys=list(updates.keys()))

        return await self.get_all(session)

    @staticmethod
    def mask_secrets(settings: dict[str, str]) -> dict[str, str]:
        """Return a copy of settings with secret values masked for API responses."""
        masked = dict(settings)
        for key in _MASKED_KEYS:
            if key in masked and masked[key]:
                value = masked[key]
                if len(value) > 4:
                    masked[key] = value[:4] + "****"
                else:
                    masked[key] = "****"
        return masked


# Module-level singleton
settings_service = SettingsService()
