"""Analysis model — LLM-generated analysis for a screenshot."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    screenshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("screenshots.id", ondelete="CASCADE"), nullable=False
    )
    model_used: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt_version: Mapped[str] = mapped_column(
        String(10), nullable=False, default="v1"
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array string
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    contains_text: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Relationships ───────────────────────────────────────────────
    screenshot: Mapped[Screenshot] = relationship(
        "Screenshot", back_populates="analysis"
    )

    # ── Indexes ─────────────────────────────────────────────────────
    __table_args__ = (
        Index("idx_analyses_screenshot_id", "screenshot_id"),
        Index("idx_analyses_category", "category"),
    )

    def __repr__(self) -> str:
        return f"<Analysis {self.id[:8]}… [{self.category}]>"


from app.models.screenshot import Screenshot  # noqa: E402
