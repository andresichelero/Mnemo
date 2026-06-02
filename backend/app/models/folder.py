"""Folder model — user or AI-created organisation bucket."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Folder(Base):
    __tablename__ = "folders"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    color_hex: Mapped[str | None] = mapped_column(String(7), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    is_auto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # ── Relationships ───────────────────────────────────────────────
    screenshots: Mapped[list[ScreenshotFolder]] = relationship(
        "ScreenshotFolder", back_populates="folder", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_folders_deleted_at", "deleted_at"),
    )

    def __repr__(self) -> str:
        return f"<Folder {self.id[:8]}… {self.name}>"


from app.models.screenshot_folder import ScreenshotFolder  # noqa: E402
