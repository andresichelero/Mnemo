"""Screenshot ↔ Folder many-to-many association."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ScreenshotFolder(Base):
    __tablename__ = "screenshot_folders"

    screenshot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("screenshots.id", ondelete="CASCADE"),
        primary_key=True,
    )
    folder_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("folders.id", ondelete="CASCADE"),
        primary_key=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    assigned_by: Mapped[str] = mapped_column(
        String(10), nullable=False, default="user"
    )  # user | ai

    # ── Relationships ───────────────────────────────────────────────
    screenshot: Mapped[Screenshot] = relationship(
        "Screenshot", back_populates="folders"
    )
    folder: Mapped[Folder] = relationship(
        "Folder", back_populates="screenshots"
    )

    __table_args__ = (
        Index("idx_sf_folder_id", "folder_id"),
    )


from app.models.screenshot import Screenshot  # noqa: E402
from app.models.folder import Folder  # noqa: E402
