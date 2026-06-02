"""Unified API router — aggregates all sub-routers under /api/v1."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.screenshots import router as screenshots_router
from app.api.folders import router as folders_router
from app.api.search import router as search_router
from app.api.processing import router as processing_router
from app.api.settings import router as settings_router
from app.api.watched_folders import router as watched_folders_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(screenshots_router)
api_router.include_router(folders_router)
api_router.include_router(search_router)
api_router.include_router(processing_router)
api_router.include_router(settings_router)
api_router.include_router(watched_folders_router)
