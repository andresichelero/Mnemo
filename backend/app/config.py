"""Mnemo configuration — reads from .env via pydantic-settings."""

from __future__ import annotations

import secrets
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class MnemoSettings(BaseSettings):
    """Central configuration for the Mnemo backend.

    Values are read from environment variables prefixed with ``MNEMO_``
    and from the ``.env`` file located next to this module.
    """

    model_config = SettingsConfigDict(
        env_prefix="MNEMO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Database ────────────────────────────────────────────────────
    db_url: str = "sqlite+aiosqlite:///data/mnemo.db"

    # ── ChromaDB ────────────────────────────────────────────────────
    chroma_path: str = "data/chroma"

    # ── Thumbnails ──────────────────────────────────────────────────
    thumbnails_path: str = "data/thumbnails"

    # ── Ollama ──────────────────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma3:4b"

    # ── Telnyx ──────────────────────────────────────────────────────
    telnyx_api_key: str = ""

    # ── Server ──────────────────────────────────────────────────────
    port: int = 8765
    host: str = "0.0.0.0"
    log_level: str = "INFO"

    # ── Security ────────────────────────────────────────────────────
    api_key: str = ""
    enable_docs: bool = True

    # ── Derived paths (resolved at startup) ─────────────────────────
    @property
    def project_root(self) -> Path:
        """Return the project root directory (two levels up from config.py)."""
        return Path(__file__).resolve().parent.parent

    @property
    def chroma_abs_path(self) -> Path:
        return self.project_root / self.chroma_path

    @property
    def thumbnails_abs_path(self) -> Path:
        return self.project_root / self.thumbnails_path

    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    def ensure_api_key(self) -> str:
        """Generate an API key if one is not set. Returns the active key."""
        if not self.api_key:
            self.api_key = secrets.token_urlsafe(32)
        return self.api_key


settings = MnemoSettings()
