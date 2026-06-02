"""Folders API — CRUD for visual organisation tags/buckets.

Endpoints:
    GET    /folders
    POST   /folders
    GET    /folders/{id}
    PATCH  /folders/{id}
    DELETE /folders/{id}
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.folder import Folder
from app.schemas.schemas import FolderCreate, FolderOut, FolderUpdate

router = APIRouter(prefix="/folders", tags=["folders"])


async def _get_folder_or_404(session: AsyncSession, folder_id: str) -> Folder:
    result = await session.execute(
        select(Folder).where(Folder.id == folder_id, Folder.deleted_at.is_(None))
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder


@router.get("", response_model=list[FolderOut])
async def list_folders(session: AsyncSession = Depends(get_session)):
    """List all non-deleted folders, sorted by name."""
    result = await session.execute(
        select(Folder)
        .where(Folder.deleted_at.is_(None))
        .order_by(Folder.name.asc())
    )
    return [FolderOut.model_validate(f) for f in result.scalars().all()]


@router.post("", response_model=FolderOut, status_code=201)
async def create_folder(
    body: FolderCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a new folder."""
    # Check for duplicate path name
    dup = await session.execute(
        select(Folder).where(
            Folder.name == body.name,
            Folder.deleted_at.is_(None)
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Folder with this name already exists")

    folder = Folder(**body.model_dump())
    session.add(folder)
    await session.flush()
    return FolderOut.model_validate(folder)


@router.get("/{folder_id}", response_model=FolderOut)
async def get_folder(
    folder_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get a folder by ID."""
    folder = await _get_folder_or_404(session, folder_id)
    return FolderOut.model_validate(folder)


@router.patch("/{folder_id}", response_model=FolderOut)
async def update_folder(
    folder_id: str,
    body: FolderUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update a folder."""
    folder = await _get_folder_or_404(session, folder_id)
    
    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(folder, key, value)
        
    await session.flush()
    return FolderOut.model_validate(folder)


@router.delete("/{folder_id}", status_code=204)
async def delete_folder(
    folder_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Soft-delete a folder."""
    folder = await _get_folder_or_404(session, folder_id)
    folder.deleted_at = datetime.now(timezone.utc)
    await session.flush()
