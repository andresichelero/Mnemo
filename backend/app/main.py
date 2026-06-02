"""Mnemo — FastAPI application factory and lifespan management.

This is the entry point for the backend server.
Run with: ``uvicorn app.main:app --reload`` (from the backend/ directory).
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

import logging

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import json

from app.config import settings
from app.db.init_db import init_db
from app.db.session import async_session_factory
from app.middleware.auth import APIKeyMiddleware
from app.services.settings_service import settings_service

__version__ = "0.1.0"

logger = structlog.get_logger()

_start_time: float = 0.0


def _configure_logging() -> None:
    """Set up structlog with pretty console output for dev."""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    global _start_time
    _start_time = time.monotonic()

    _configure_logging()

    # ── Startup ─────────────────────────────────────────────────
    logger.info("mnemo.startup", version=__version__)

    # Ensure data directories exist
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.chroma_abs_path.mkdir(parents=True, exist_ok=True)
    settings.thumbnails_abs_path.mkdir(parents=True, exist_ok=True)
    logger.info("mnemo.dirs", data=str(settings.data_dir))

    # Initialise database (create tables + seed defaults)
    await init_db()

    # Get or Generate API key and persist to DB
    async with async_session_factory() as session:
        db_api_key = await settings_service.get(session, "api_key")
        if not db_api_key:
            api_key = settings.ensure_api_key()
            await settings_service.update(session, {"api_key": api_key})
        else:
            api_key = db_api_key
            settings.api_key = api_key
            
    logger.info(
        "mnemo.auth",
        api_key=api_key,
        note="Save this API key — required for all /api/* requests via X-API-Key header",
    )

    from app.services.idle_detector import idle_detector
    from app.services.file_watcher import file_watcher
    from app.services.scheduler import scheduler_service

    async with async_session_factory() as session:
        idle_threshold = float(await settings_service.get(session, "idle_threshold_cpu", "10"))
        idle_check_seconds = float(await settings_service.get(session, "idle_check_seconds", "30"))
        idle_detector.start(threshold_cpu=idle_threshold, idle_window_seconds=idle_check_seconds)

        paths_str = await settings_service.get(session, "watched_folders", "[]")
        try:
            paths = json.loads(paths_str)
        except Exception:
            paths = []
        file_watcher.start(paths)

    scheduler_service.start()

    logger.info("mnemo.ready", port=settings.port, host=settings.host)

    yield

    # ── Shutdown ────────────────────────────────────────────────
    logger.info("mnemo.shutdown")
    
    scheduler_service.stop()
    file_watcher.stop()
    idle_detector.stop()


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""

    app = FastAPI(
        title="Mnemo",
        description="Privacy-First Screenshot Intelligence Organizer",
        version=__version__,
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url="/redoc" if settings.enable_docs else None,
        lifespan=lifespan,
    )

    limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # ── Middleware (order matters — outermost first) ─────────────
    # CORS — allow mobile and desktop clients
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API key authentication
    app.add_middleware(APIKeyMiddleware)

    # API router
    from app.api.router import api_router
    app.include_router(api_router)

    # ── Routes ──────────────────────────────────────────────────
    @app.get("/api/v1/health", tags=["system"])
    async def health():
        """Public health check — no auth required."""
        return {
            "status": "ok",
            "version": __version__,
            "uptime_seconds": round(time.monotonic() - _start_time, 1),
        }

    return app


app = create_app()
