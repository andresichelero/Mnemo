"""Pydantic schemas for Screenshot, Analysis, Folder, and related entities."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


# ── Screenshot ──────────────────────────────────────────────────────


class ScreenshotBase(BaseModel):
    file_path: str
    original_filename: str
    file_size: int
    width: int | None = None
    height: int | None = None
    captured_at: datetime | None = None


class ScreenshotOut(BaseModel):
    id: str
    file_path: str
    file_hash: str
    original_filename: str
    file_size: int
    width: int | None = None
    height: int | None = None
    captured_at: datetime | None = None
    ingested_at: datetime
    status: str
    error_message: str | None = None
    thumbnail_path: str | None = None

    model_config = {"from_attributes": True}


class ScreenshotDetail(ScreenshotOut):
    analysis: AnalysisOut | None = None
    folders: list[FolderOut] = []

    model_config = {"from_attributes": True}


class ScreenshotList(BaseModel):
    items: list[ScreenshotOut]
    total: int
    page: int
    pages: int


# ── Analysis ────────────────────────────────────────────────────────


class AnalysisOut(BaseModel):
    id: str
    screenshot_id: str
    model_used: str
    prompt_version: str
    description: str
    tags: str  # JSON string — parsed by the client
    category: str
    contains_text: bool
    extracted_text: str | None = None
    language: str | None = None
    analyzed_at: datetime
    prompt_tokens: int | None = None

    model_config = {"from_attributes": True}


class AnalyzeRequest(BaseModel):
    force: bool = False


# ── Folder ──────────────────────────────────────────────────────────


class FolderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    path: str = Field(..., min_length=1)
    description: str | None = None
    color_hex: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    icon: str | None = None

    @field_validator("path")
    @classmethod
    def validate_path_safe(cls, v: str) -> str:
        if ".." in v:
            raise ValueError("Path must not contain '..'")
        return v


class FolderUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    color_hex: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    icon: str | None = None


class FolderOut(BaseModel):
    id: str
    name: str
    path: str
    description: str | None = None
    color_hex: str | None = None
    icon: str | None = None
    created_at: datetime
    is_auto: bool

    model_config = {"from_attributes": True}


# ── Folder assignment ───────────────────────────────────────────────


class FolderAssignment(BaseModel):
    folder_ids: list[str]


# ── Search ──────────────────────────────────────────────────────────


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(20, ge=1, le=100)
    min_score: float = Field(0.6, ge=0.0, le=1.0)
    folder_id: str | None = None
    category: str | None = None


class SearchResultItem(BaseModel):
    screenshot: ScreenshotOut
    score: float
    matched_by: str  # semantic | text


class SearchResponse(BaseModel):
    results: list[SearchResultItem]


class SearchSuggestResponse(BaseModel):
    suggestions: list[str]


# ── Processing ──────────────────────────────────────────────────────


class ProcessingStatus(BaseModel):
    queue_size: int
    currently_processing: str | None = None
    is_idle: bool
    ollama_connected: bool
    telnyx_connected: bool
    processed_today: int
    errors_today: int


class ProcessingTrigger(BaseModel):
    limit: int | None = None


class ProcessingTriggerResponse(BaseModel):
    triggered: int


class ReprocessResponse(BaseModel):
    requeued: int


# ── Settings ────────────────────────────────────────────────────────


class SettingsValidation(BaseModel):
    ollama: OllamaStatus
    telnyx: TelnyxStatus


class OllamaStatus(BaseModel):
    connected: bool
    model_available: bool
    model: str


class TelnyxStatus(BaseModel):
    connected: bool
    key_valid: bool


# ── Health ──────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    uptime_seconds: float


# ── Generic ─────────────────────────────────────────────────────────


class ErrorResponse(BaseModel):
    detail: str
    code: str = "ERROR"


# Resolve forward references
ScreenshotDetail.model_rebuild()
SettingsValidation.model_rebuild()
