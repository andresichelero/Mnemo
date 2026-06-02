"""Scheduler — Manages background jobs via AsyncIOScheduler.

Jobs:
1. process_pending: Analyze and embed new screenshots (runs when idle).
2. scan_folders: Fallback watcher that checks for missed files.
3. generate_thumbnails: Batch thumbnail generation.
4. reconcile: Keeps SQLite and ChromaDB in sync.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import async_session_factory
from app.models.screenshot import Screenshot
from app.services import image_service
from app.services.embedding_service import EmbeddingService
from app.services.idle_detector import idle_detector
from app.services.llm_service import LLMService
from app.services.settings_service import settings_service
from app.services.vector_store import VectorStore

logger = structlog.get_logger()


class BackgroundSchedulerService:
    """Orchestrates APScheduler jobs for Mnemo."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._is_running = False

    def start(self) -> None:
        if self._is_running:
            return
            
        self.scheduler.add_job(self.process_pending, "interval", seconds=30, id="process_pending")
        self.scheduler.add_job(self.scan_folders, "interval", seconds=60, id="scan_folders")
        self.scheduler.add_job(self.generate_thumbnails, "interval", seconds=120, id="generate_thumbnails")
        self.scheduler.add_job(self.reconcile_vectors, "interval", hours=1, id="reconcile_vectors")
        
        self.scheduler.start()
        self._is_running = True
        logger.info("scheduler.started")

    def stop(self) -> None:
        if not self._is_running:
            return
            
        logger.info("scheduler.stopping")
        # Wait for running jobs to finish gracefully (up to 30s)
        self.scheduler.shutdown(wait=True)
        self._is_running = False
        logger.info("scheduler.stopped")

    # ── Job 1: Process Pending ──────────────────────────────────────────

    async def process_pending(self) -> None:
        """Analyze and embed screenshots in the 'pending' state."""
        async with async_session_factory() as session:
            mode = await settings_service.get(session, "processing_mode", "idle")
            if mode == "idle" and not idle_detector.is_idle():
                return

            stmt = select(Screenshot).where(Screenshot.status == "pending", Screenshot.deleted_at.is_(None)).limit(5)
            result = await session.execute(stmt)
            screenshots = result.scalars().all()

            if not screenshots:
                return

            ollama_base_url = await settings_service.get(session, "ollama_base_url", settings.ollama_base_url)
            ollama_model = await settings_service.get(session, "ollama_model", settings.ollama_model)
            telnyx_api_key = await settings_service.get(session, "telnyx_api_key", settings.telnyx_api_key)
            telnyx_model = await settings_service.get(session, "telnyx_embedding_model", settings.telnyx_embedding_model)

        llm = LLMService(base_url=ollama_base_url, model=ollama_model)
        if not await llm.check_connection():
            logger.warning("scheduler.llm_unavailable", model=ollama_model)
            await llm.close()
            return

        embedder = EmbeddingService(api_key=telnyx_api_key, model=telnyx_model, ollama_base_url=ollama_base_url)
        vector_store = VectorStore(str(settings.chroma_abs_path))

        for screenshot in screenshots:
            try:
                # 1. Lock record as processing
                async with async_session_factory() as session:
                    s = await session.get(Screenshot, screenshot.id)
                    s.status = "processing"
                    await session.commit()

                # 2. Analyze
                analysis_result = await llm.analyze_image(screenshot.file_path)
                
                # 3. Embed
                emb_text = EmbeddingService.build_embedding_text(
                    description=analysis_result.description,
                    tags=analysis_result.tags,
                    category=analysis_result.category
                )
                embedding = await embedder.generate_embedding(emb_text)

                # 4. Save Vector
                if embedding:
                    await vector_store.add(
                        screenshot_id=screenshot.id,
                        embedding=embedding,
                        metadata={
                            "category": analysis_result.category,
                            "has_text": analysis_result.contains_text,
                        }
                    )

                # 5. Save Analysis & Mark Done
                async with async_session_factory() as session:
                    s = await session.get(Screenshot, screenshot.id)
                    from app.models.analysis import Analysis
                    from app.models.embedding import Embedding
                    
                    # Remove old analysis/embedding if re-processing
                    await session.execute(select(Analysis).where(Analysis.screenshot_id == s.id)) # cascade takes care of this but ensuring clean state
                    
                    s.analysis = Analysis(
                        screenshot_id=s.id,
                        model_used=analysis_result.model_used,
                        prompt_version=analysis_result.prompt_version,
                        description=analysis_result.description,
                        tags=json.dumps(analysis_result.tags),
                        category=analysis_result.category,
                        contains_text=analysis_result.contains_text,
                        extracted_text=analysis_result.extracted_text,
                        language=analysis_result.language,
                    )
                    
                    if embedding:
                        s.embedding = Embedding(
                            screenshot_id=s.id,
                            provider="telnyx" if telnyx_api_key else "ollama",
                            model=telnyx_model if telnyx_api_key else "nomic-embed-text",
                            chroma_id=s.id, # Using screenshot_id as chroma_id
                        )

                    s.status = "done"
                    s.error_message = None
                    await session.commit()
                    logger.info("scheduler.processed", id=s.id)

            except Exception as e:
                logger.exception("scheduler.process_error", id=screenshot.id)
                async with async_session_factory() as session:
                    s = await session.get(Screenshot, screenshot.id)
                    if s:
                        s.status = "error"
                        s.error_message = str(e)
                        await session.commit()

        await llm.close()
        await embedder.close()

    # ── Job 2: Scan Folders ─────────────────────────────────────────────

    async def scan_folders(self) -> None:
        """Scan watched folders to catch any files missed by the watchdog."""
        async with async_session_factory() as session:
            paths_str = await settings_service.get(session, "watched_folders", "[]")
            try:
                paths = json.loads(paths_str)
            except json.JSONDecodeError:
                paths = []

        for folder in paths:
            if not os.path.exists(folder) or not os.path.isdir(folder):
                continue

            for file_name in os.listdir(folder):
                file_path = os.path.join(folder, file_name)
                if not os.path.isfile(file_path):
                    continue

                if not image_service.is_supported_image(file_path):
                    continue

                # Quick DB check by path to avoid hashing everything
                async with async_session_factory() as session:
                    existing = await session.execute(select(Screenshot).where(Screenshot.file_path == file_path))
                    if existing.scalar_one_or_none():
                        continue

                # Hash and insert
                try:
                    width, height = await image_service.validate_image(file_path)
                    file_hash = await image_service.get_file_hash(file_path)
                    file_size = os.path.getsize(file_path)

                    async with async_session_factory() as session:
                        screenshot = Screenshot(
                            file_path=file_path,
                            file_hash=file_hash,
                            original_filename=file_name,
                            file_size=file_size,
                            width=width,
                            height=height,
                            status="pending"
                        )
                        session.add(screenshot)
                        try:
                            await session.commit()
                            logger.info("scheduler.scanned_new", file=file_name)
                        except IntegrityError:
                            # Hash duplicate
                            await session.rollback()
                except Exception as e:
                    logger.warning("scheduler.scan_error", file=file_name, error=str(e))


    # ── Job 3: Generate Thumbnails ──────────────────────────────────────

    async def generate_thumbnails(self) -> None:
        """Generate missing thumbnails for done/pending screenshots."""
        async with async_session_factory() as session:
            # We can generate thumbnails for any image that doesn't have one, regardless of status
            stmt = select(Screenshot).where(Screenshot.thumbnail_path.is_(None), Screenshot.deleted_at.is_(None)).limit(20)
            result = await session.execute(stmt)
            screenshots = result.scalars().all()

        if not screenshots:
            return

        for screenshot in screenshots:
            try:
                thumb_name = f"thumb_{screenshot.id}.webp"
                thumb_path = settings.thumbnails_abs_path / thumb_name
                
                await image_service.generate_thumbnail(
                    file_path=screenshot.file_path,
                    output_path=thumb_path,
                    size=256
                )

                async with async_session_factory() as session:
                    s = await session.get(Screenshot, screenshot.id)
                    if s:
                        s.thumbnail_path = str(thumb_path)
                        await session.commit()

            except Exception as e:
                logger.warning("scheduler.thumb_error", id=screenshot.id, error=str(e))

    # ── Job 4: Reconcile Vectors ────────────────────────────────────────

    async def reconcile_vectors(self) -> None:
        """Ensure ChromaDB only contains embeddings for active screenshots."""
        async with async_session_factory() as session:
            # Get all non-deleted screenshot IDs that have an embedding record
            stmt = select(Screenshot.id).where(Screenshot.deleted_at.is_(None))
            result = await session.execute(stmt)
            valid_ids = set(result.scalars().all())

        vector_store = VectorStore(str(settings.chroma_abs_path))
        await vector_store.reconcile(valid_ids)


scheduler_service = BackgroundSchedulerService()
