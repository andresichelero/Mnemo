"""Embedding model — tracks vector embeddings stored in ChromaDB."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Embedding(Base):
    __tablename__ = "embeddings"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    screenshot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("screenshots.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False, default="telnyx")
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    chroma_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # ── Relationships ───────────────────────────────────────────────
    screenshot: Mapped[Screenshot] = relationship(
        "Screenshot", back_populates="embedding"
    )

    def __repr__(self) -> str:
        return f"<Embedding {self.id[:8]}… provider={self.provider}>"


from app.models.screenshot import Screenshot  # noqa: E402
