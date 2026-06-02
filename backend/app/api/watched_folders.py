"""Watched Folders API — CRUD for directory paths the app should monitor."""

from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services.settings_service import settings_service

router = APIRouter(prefix="/watched-folders", tags=["watched_folders"])


class WatchedFolderList(BaseModel):
    paths: list[str]


class WatchedFolderCreate(BaseModel):
    path: str


@router.get("", response_model=WatchedFolderList)
async def list_watched_folders(session: AsyncSession = Depends(get_session)):
    """List all configured watched folders."""
    paths_str = await settings_service.get(session, "watched_folders", "[]")
    try:
        paths = json.loads(paths_str)
    except json.JSONDecodeError:
        paths = []
    return WatchedFolderList(paths=paths)


@router.post("", response_model=WatchedFolderList)
async def add_watched_folder(
    body: WatchedFolderCreate, 
    session: AsyncSession = Depends(get_session)
):
    """Add a new directory path to monitor."""
    if not os.path.exists(body.path) or not os.path.isdir(body.path):
        raise HTTPException(status_code=400, detail="Path does not exist or is not a directory")

    paths_str = await settings_service.get(session, "watched_folders", "[]")
    try:
        paths = json.loads(paths_str)
    except json.JSONDecodeError:
        paths = []

    if body.path not in paths:
        paths.append(body.path)
        await settings_service.update(session, {"watched_folders": json.dumps(paths)})

    return WatchedFolderList(paths=paths)


@router.delete("", response_model=WatchedFolderList)
async def remove_watched_folder(
    path: str, 
    session: AsyncSession = Depends(get_session)
):
    """Remove a directory path from monitoring."""
    paths_str = await settings_service.get(session, "watched_folders", "[]")
    try:
        paths = json.loads(paths_str)
    except json.JSONDecodeError:
        paths = []

    if path in paths:
        paths.remove(path)
        await settings_service.update(session, {"watched_folders": json.dumps(paths)})

    return WatchedFolderList(paths=paths)
