"""Screenshots API — CRUD, upload, image serving, and re-analysis.

Endpoints:
    GET    /screenshots              List with pagination and filters
    POST   /screenshots/upload       Upload a new image
    GET    /screenshots/{id}         Detail with analysis + folders
    GET    /screenshots/{id}/image   Serve original image or thumbnail
    POST   /screenshots/{id}/analyze Trigger re-analysis
    DELETE /screenshots/{id}         Soft-delete
    PATCH  /screenshots/{id}/folders Update folder assignments
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models.screenshot import Screenshot
from app.models.analysis import Analysis
from app.models.folder import Folder
from app.models.screenshot_folder import ScreenshotFolder
from app.schemas.schemas import (
    AnalyzeRequest,
    FolderAssignment,
    FolderOut,
    ScreenshotDetail,
    ScreenshotList,
    ScreenshotOut,
)
from app.services import image_service
from app.config import settings

logger = structlog.get_logger()

router = APIRouter(prefix="/screenshots", tags=["screenshots"])

# Maximum upload size in bytes (from master plan — 20 MB)
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


# ── Helpers ──────────────────────────────────────────────────────────


async def _get_screenshot_or_404(
    session: AsyncSession,
    screenshot_id: str,
    *,
    load_relations: bool = False,
) -> Screenshot:
    """Fetch a non-deleted screenshot by ID, optionally eager-loading relations."""
    stmt = select(Screenshot).where(
        Screenshot.id == screenshot_id,
        Screenshot.deleted_at.is_(None),
    )
    if load_relations:
        stmt = stmt.options(
            selectinload(Screenshot.analysis),
            selectinload(Screenshot.folders).selectinload(ScreenshotFolder.folder),
        )
    result = await session.execute(stmt)
    screenshot = result.scalar_one_or_none()
    if screenshot is None:
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return screenshot


# ── List ─────────────────────────────────────────────────────────────


@router.get("", response_model=ScreenshotList)
async def list_screenshots(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    status: str | None = Query(None),
    category: str | None = Query(None),
    folder_id: str | None = Query(None),
    has_text: bool | None = Query(None),
    order_by: str = Query("ingested_at"),
    order_dir: str = Query("desc"),
    session: AsyncSession = Depends(get_session),
):
    """Paginated list of screenshots with optional filters."""
    stmt = select(Screenshot).where(Screenshot.deleted_at.is_(None))

    # ── Filters ──
    if status:
        stmt = stmt.where(Screenshot.status == status)

    if category or has_text is not None:
        stmt = stmt.join(Analysis, Analysis.screenshot_id == Screenshot.id, isouter=True)
        if category:
            stmt = stmt.where(Analysis.category == category)
        if has_text is not None:
            stmt = stmt.where(Analysis.contains_text == has_text)

    if folder_id:
        stmt = stmt.join(
            ScreenshotFolder,
            ScreenshotFolder.screenshot_id == Screenshot.id,
        ).where(ScreenshotFolder.folder_id == folder_id)

    # ── Count ──
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar() or 0

    # ── Ordering ──
    order_col = getattr(Screenshot, order_by, Screenshot.ingested_at)
    if order_dir.lower() == "asc":
        stmt = stmt.order_by(order_col.asc())
    else:
        stmt = stmt.order_by(order_col.desc())

    # ── Pagination ──
    offset = (page - 1) * per_page
    stmt = stmt.offset(offset).limit(per_page)

    result = await session.execute(stmt)
    items = result.scalars().all()

    pages = max(1, -(-total // per_page))  # ceil division

    return ScreenshotList(
        items=[ScreenshotOut.model_validate(s) for s in items],
        total=total,
        page=page,
        pages=pages,
    )


# ── Detail ───────────────────────────────────────────────────────────


@router.get("/{screenshot_id}", response_model=ScreenshotDetail)
async def get_screenshot(
    screenshot_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get screenshot detail including analysis and folder assignments."""
    screenshot = await _get_screenshot_or_404(
        session, screenshot_id, load_relations=True
    )

    # Build folder list from the junction table
    folder_list = [
        FolderOut.model_validate(sf.folder)
        for sf in screenshot.folders
        if sf.folder and sf.folder.deleted_at is None
    ]

    return ScreenshotDetail(
        **ScreenshotOut.model_validate(screenshot).model_dump(),
        analysis=screenshot.analysis,
        folders=folder_list,
    )


# ── Image serving ────────────────────────────────────────────────────


@router.get("/{screenshot_id}/image")
async def serve_image(
    screenshot_id: str,
    thumbnail: bool = Query(False),
    session: AsyncSession = Depends(get_session),
):
    """Stream the original image or its thumbnail."""
    screenshot = await _get_screenshot_or_404(session, screenshot_id)

    if thumbnail and screenshot.thumbnail_path:
        path = Path(screenshot.thumbnail_path)
    else:
        path = Path(screenshot.file_path)

    if not path.exists():
        raise HTTPException(status_code=404, detail="Image file not found on disk")

    return FileResponse(path, media_type="image/webp" if thumbnail else None)


# ── Upload ───────────────────────────────────────────────────────────


@router.post("/upload", response_model=ScreenshotOut, status_code=201)
async def upload_screenshot(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    """Upload a new image file. Validates magic bytes and deduplicates by hash."""
    # ── Size check (read into memory, bounded) ──
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum is {MAX_UPLOAD_BYTES // (1024*1024)}MB",
        )

    # ── Determine save path ──
    upload_dir = settings.data_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    original_name = file.filename or f"upload_{uuid.uuid4().hex[:8]}.png"
    safe_name = f"{uuid.uuid4().hex}_{original_name}"
    dest = upload_dir / safe_name

    # Write to disk
    dest.write_bytes(content)

    # ── Validate image (magic bytes + dimensions) ──
    try:
        width, height = await image_service.validate_image(dest)
    except ValueError as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(e))

    # ── Hash for deduplication ──
    file_hash = await image_service.get_file_hash(dest)

    # Check duplicates
    dup = await session.execute(
        select(Screenshot).where(Screenshot.file_hash == file_hash)
    )
    if dup.scalar_one_or_none():
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail="Duplicate image (matching hash)")

    # ── Create DB record ──
    screenshot = Screenshot(
        file_path=str(dest),
        file_hash=file_hash,
        original_filename=original_name,
        file_size=len(content),
        width=width,
        height=height,
        status="pending",
    )
    session.add(screenshot)
    await session.flush()

    logger.info(
        "screenshot.uploaded",
        id=screenshot.id,
        filename=original_name,
        size=len(content),
    )

    return ScreenshotOut.model_validate(screenshot)


# ── Analyze (trigger re-analysis) ────────────────────────────────────


@router.post("/{screenshot_id}/analyze", response_model=ScreenshotOut)
async def trigger_analysis(
    screenshot_id: str,
    body: AnalyzeRequest | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Re-queue a screenshot for LLM analysis."""
    screenshot = await _get_screenshot_or_404(session, screenshot_id)

    force = body.force if body else False

    if screenshot.status == "done" and not force:
        raise HTTPException(
            status_code=400,
            detail="Already analyzed. Use force=true to re-analyze.",
        )

    screenshot.status = "pending"
    screenshot.error_message = None
    await session.flush()

    logger.info("screenshot.requeued", id=screenshot_id)

    return ScreenshotOut.model_validate(screenshot)


# ── Delete (soft) ────────────────────────────────────────────────────


@router.delete("/{screenshot_id}", status_code=204)
async def delete_screenshot(
    screenshot_id: str,
    delete_file: bool = Query(False),
    session: AsyncSession = Depends(get_session),
):
    """Soft-delete a screenshot. Optionally remove the file from disk."""
    screenshot = await _get_screenshot_or_404(session, screenshot_id)
    screenshot.deleted_at = datetime.now(timezone.utc)
    await session.flush()

    if delete_file:
        path = Path(screenshot.file_path)
        path.unlink(missing_ok=True)
        if screenshot.thumbnail_path:
            Path(screenshot.thumbnail_path).unlink(missing_ok=True)

    logger.info(
        "screenshot.deleted",
        id=screenshot_id,
        file_removed=delete_file,
    )


# ── Folder assignments ───────────────────────────────────────────────


@router.patch("/{screenshot_id}/folders", response_model=ScreenshotDetail)
async def update_folder_assignments(
    screenshot_id: str,
    body: FolderAssignment,
    session: AsyncSession = Depends(get_session),
):
    """Replace all folder assignments for a screenshot."""
    screenshot = await _get_screenshot_or_404(
        session, screenshot_id, load_relations=True
    )

    # Validate all folder IDs exist
    for fid in body.folder_ids:
        result = await session.execute(
            select(Folder).where(Folder.id == fid, Folder.deleted_at.is_(None))
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail=f"Folder {fid} not found")

    # Remove existing assignments
    for sf in list(screenshot.folders):
        await session.delete(sf)
    await session.flush()

    # Add new assignments
    for fid in body.folder_ids:
        session.add(
            ScreenshotFolder(
                screenshot_id=screenshot_id,
                folder_id=fid,
                assigned_by="user",
            )
        )
    await session.flush()

    # Reload and return
    return await get_screenshot(screenshot_id, session=session)
