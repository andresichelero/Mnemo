"""Dependency injection helpers for FastAPI endpoints."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session


async def get_db(session: AsyncSession = Depends(get_session)) -> AsyncGenerator[AsyncSession, None]:
    """Alias for the session dependency — makes endpoint signatures cleaner."""
    yield session
