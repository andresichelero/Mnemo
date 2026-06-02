"""File Watcher — Monitors folders for new images and inserts them into the DB.

Uses watchdog to listen for FileCreatedEvent and FileMovedEvent.
When a file is detected, it schedules an asyncio task to wait for the file
to stabilize (finish copying) before hashing and inserting it into the DB.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

import structlog
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from sqlalchemy.exc import IntegrityError

from app.db.session import async_session_factory
from app.models.screenshot import Screenshot
from app.services import image_service

logger = structlog.get_logger()


class ImageEventHandler(FileSystemEventHandler):
    """Handles watchdog file events and passes them to the async loop."""

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        # Track files being processed to avoid duplicate scheduling
        self._processing: set[str] = set()

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._handle_path(event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._handle_path(event.dest_path)
            
    def on_modified(self, event: FileSystemEvent) -> None:
        # Some OSes fire modified instead of created for slow copies
        if not event.is_directory:
            self._handle_path(event.src_path)

    def _handle_path(self, path_str: str) -> None:
        if not image_service.is_supported_image(path_str):
            return

        if path_str in self._processing:
            return

        self._processing.add(path_str)
        
        # Schedule the async processing task safely in the main event loop
        asyncio.run_coroutine_threadsafe(
            self._process_file_async(path_str),
            self.loop
        )

    async def _process_file_async(self, path_str: str) -> None:
        """Wait for the file to stabilize, then insert it into the DB."""
        try:
            if not await self._wait_for_stability(path_str):
                return

            path = Path(path_str)
            if not path.exists():
                return

            # Validate and get dimensions
            try:
                width, height = await image_service.validate_image(path)
            except ValueError as e:
                logger.warning("watcher.invalid_image", file=path.name, error=str(e))
                return

            # Deduplication
            file_hash = await image_service.get_file_hash(path)
            file_size = path.stat().st_size

            async with async_session_factory() as session:
                screenshot = Screenshot(
                    file_path=str(path),
                    file_hash=file_hash,
                    original_filename=path.name,
                    file_size=file_size,
                    width=width,
                    height=height,
                    status="pending"
                )
                session.add(screenshot)
                try:
                    await session.commit()
                    logger.info("watcher.ingested", file=path.name, size=file_size)
                except IntegrityError:
                    await session.rollback()
                    logger.debug("watcher.duplicate_ignored", file=path.name)
        except Exception as e:
            logger.error("watcher.error", file=path_str, error=str(e))
        finally:
            self._processing.discard(path_str)

    async def _wait_for_stability(self, path_str: str, max_wait: int = 30) -> bool:
        """Wait until the file size stops changing."""
        path = Path(path_str)
        if not path.exists():
            return False

        last_size = -1
        attempts = 0

        while attempts < max_wait:
            try:
                current_size = path.stat().st_size
                if current_size == last_size and current_size > 0:
                    return True
                last_size = current_size
            except FileNotFoundError:
                return False
            
            attempts += 1
            await asyncio.sleep(1.0)
            
        logger.warning("watcher.stability_timeout", file=path.name)
        return False


class FileWatcher:
    """Manages the watchdog observer for multiple configured directories."""

    def __init__(self):
        self.observer: Observer | None = None
        self._watched_paths: set[str] = set()

    def start(self, paths: list[str]) -> None:
        """Start watching the given paths."""
        if self.observer and self.observer.is_alive():
            self.stop()

        valid_paths = [p for p in paths if os.path.exists(p) and os.path.isdir(p)]
        if not valid_paths:
            logger.info("watcher.no_valid_paths", configured=paths)
            return

        self._watched_paths = set(valid_paths)
        
        loop = asyncio.get_running_loop()
        handler = ImageEventHandler(loop)
        
        self.observer = Observer()
        for path in valid_paths:
            self.observer.schedule(handler, path, recursive=False)
            
        self.observer.start()
        logger.info("watcher.started", paths=valid_paths)

    def stop(self) -> None:
        """Stop the watchdog observer."""
        if self.observer and self.observer.is_alive():
            logger.info("watcher.stopping")
            self.observer.stop()
            self.observer.join(timeout=5.0)
            logger.info("watcher.stopped")
            self.observer = None
            self._watched_paths.clear()

    def restart_if_needed(self, new_paths: list[str]) -> None:
        """Restart observer if the watched paths have changed."""
        valid_paths = {p for p in new_paths if os.path.exists(p) and os.path.isdir(p)}
        if valid_paths != self._watched_paths:
            logger.info("watcher.config_changed", old=list(self._watched_paths), new=list(valid_paths))
            self.start(list(valid_paths))

# Global singleton
file_watcher = FileWatcher()
