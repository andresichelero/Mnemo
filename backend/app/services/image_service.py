"""Image service — Pillow-based utilities for thumbnails, hashing, and base64 encoding.

All image manipulation for Mnemo goes through this module:
- Thumbnail generation (WebP, aspect-ratio preserving, EXIF-aware)
- Base64 encoding for Ollama vision API
- Image validation (file size, magic bytes, decompression bomb protection)
- SHA-256 file hashing for deduplication

NOTE: All I/O and CPU-bound operations are offloaded to a thread pool
using run_in_executor to prevent blocking the FastAPI event loop.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import os
from functools import partial
from pathlib import Path

import structlog
from PIL import Image, ImageOps

logger = structlog.get_logger()

# Supported image extensions
SUPPORTED_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"})

# Prevent decompression bomb attacks, but allow long mobile scrolling screenshots
# 150 Megapixels is enough for ~ 2000 x 75000 pixels.
Image.MAX_IMAGE_PIXELS = 150_000_000

# Fallback max file size (30MB)
MAX_FILE_SIZE_BYTES = 30 * 1024 * 1024


async def _run_sync(fn, *args, **kwargs):
    """Run a synchronous blocking function in the thread pool executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(fn, *args, **kwargs))


def is_supported_image(path: str | Path) -> bool:
    """Check if a file has a supported image extension."""
    return Path(path).suffix.lower() in SUPPORTED_EXTENSIONS


async def get_file_hash(file_path: str | Path, chunk_size: int = 8192) -> str:
    """Compute SHA-256 hash of a file."""
    def _hash():
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(chunk_size):
                sha256.update(chunk)
        return sha256.hexdigest()

    return await _run_sync(_hash)


async def validate_image(file_path: str | Path) -> tuple[int, int]:
    """Validate that a file is a real image and within size limits.

    Returns:
        (width, height) tuple.

    Raises:
        ValueError: If file is too large or not a valid image.
    """
    def _validate():
        size_bytes = os.path.getsize(file_path)
        if size_bytes > MAX_FILE_SIZE_BYTES:
            raise ValueError(f"File too large: {size_bytes / 1024 / 1024:.1f}MB")

        try:
            with Image.open(file_path) as img:
                img.verify()
            # Re-open after verify to get correct dimensions considering EXIF
            with Image.open(file_path) as img:
                img = ImageOps.exif_transpose(img)
                return img.size
        except Exception as e:
            raise ValueError(f"Invalid image file: {file_path}") from e

    return await _run_sync(_validate)


async def generate_thumbnail(
    file_path: str | Path,
    output_path: str | Path,
    size: int = 256,
) -> Path:
    """Generate a square WebP thumbnail preserving aspect ratio."""
    def _thumb():
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with Image.open(file_path) as img:
            # Fix EXIF orientation (mobile cameras)
            img = ImageOps.exif_transpose(img)

            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            # Resize shortest side to `size`, preserving aspect ratio
            w, h = img.size
            if w < h:
                new_w = size
                new_h = int(h * (size / w))
            else:
                new_h = size
                new_w = int(w * (size / h))

            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            # Center crop to size x size
            left = (new_w - size) // 2
            top = (new_h - size) // 2
            img = img.crop((left, top, left + size, top + size))

            img.save(out_path, format="WEBP", quality=80)

        logger.debug("image.thumbnail_generated", source=str(file_path), output=str(out_path))
        return out_path

    return await _run_sync(_thumb)


async def encode_base64(file_path: str | Path, max_size: int = 1280) -> str:
    """Resize image to max_size on longest side, then encode as base64 string."""
    def _encode():
        with Image.open(file_path) as img:
            # Fix EXIF orientation
            img = ImageOps.exif_transpose(img)

            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            # Resize if larger than max_size
            w, h = img.size
            if max(w, h) > max_size:
                if w > h:
                    new_w = max_size
                    new_h = int(h * (max_size / w))
                else:
                    new_h = max_size
                    new_w = int(w * (max_size / h))
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            # Encode to JPEG in memory, then base64
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            return base64.b64encode(buffer.getvalue()).decode("utf-8")

    return await _run_sync(_encode)


async def get_image_dimensions(file_path: str | Path) -> tuple[int, int] | None:
    """Return (width, height) properly transposed, or None on error."""
    def _dims():
        try:
            with Image.open(file_path) as img:
                img = ImageOps.exif_transpose(img)
                return img.size
        except Exception:
            return None

    return await _run_sync(_dims)
