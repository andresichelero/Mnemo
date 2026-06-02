"""Screenshot model — represents an ingested image file."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Screenshot(Base):
    __tablename__ = "screenshots"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending | processing | done | error
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # ── Relationships ───────────────────────────────────────────────
    analysis: Mapped[Analysis | None] = relationship(
        "Analysis", back_populates="screenshot", uselist=False, cascade="all, delete-orphan"
    )
    embedding: Mapped[Embedding | None] = relationship(
        "Embedding", back_populates="screenshot", uselist=False, cascade="all, delete-orphan"
    )
    folders: Mapped[list[ScreenshotFolder]] = relationship(
        "ScreenshotFolder", back_populates="screenshot", cascade="all, delete-orphan"
    )

    # ── Indexes ─────────────────────────────────────────────────────
    __table_args__ = (
        Index("idx_screenshots_status", "status"),
        Index("idx_screenshots_ingested_at", "ingested_at"),
        Index("idx_screenshots_file_hash", "file_hash"),
        Index("idx_screenshots_deleted_at", "deleted_at"),
    )

    def __repr__(self) -> str:
        return f"<Screenshot {self.id[:8]}… {self.original_filename} [{self.status}]>"


# Avoid circular import — these are strings resolved by SQLAlchemy
from app.models.analysis import Analysis  # noqa: E402
from app.models.embedding import Embedding  # noqa: E402
from app.models.screenshot_folder import ScreenshotFolder  # noqa: E402
