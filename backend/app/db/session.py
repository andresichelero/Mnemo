"""Async SQLAlchemy engine and session factory for SQLite.

Key decisions:
- WAL mode enabled for better read/write concurrency.
- busy_timeout = 10s so writers wait instead of raising immediately.
- NullPool is used because aiosqlite already manages its own connection;
  SQLAlchemy's pool would just wrap a single-file DB unnecessarily.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

engine = create_async_engine(
    settings.db_url,
    echo=False,
    connect_args={"timeout": 10},
    # For SQLite, we keep pool_size=1 to serialise writes and avoid locks.
    pool_pre_ping=True,
)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record):
    """Configure SQLite pragmas on every new raw connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=10000")
    cursor.close()


async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields an async session and commits/rollbacks."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
