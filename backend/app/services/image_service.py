"""Image service — Pillow-based utilities for thumbnails, hashing, and base64 encoding.

All image manipulation for Mnemo goes through this module:
- Thumbnail generation (WebP, aspect-ratio preserving)
- Base64 encoding for Ollama vision API
- Image validation (magic bytes check)
- SHA-256 file hashing for deduplication
"""

from __future__ import annotations

import base64
import hashlib
import io
from pathlib import Path

import structlog
from PIL import Image

logger = structlog.get_logger()

# Supported image extensions
SUPPORTED_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"})


def is_supported_image(path: str | Path) -> bool:
    """Check if a file has a supported image extension."""
    return Path(path).suffix.lower() in SUPPORTED_EXTENSIONS


def get_file_hash(file_path: str | Path, chunk_size: int = 8192) -> str:
    """Compute SHA-256 hash of a file, reading in chunks to handle large files."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            sha256.update(chunk)
    return sha256.hexdigest()


def validate_image(file_path: str | Path) -> tuple[int, int]:
    """Validate that a file is a real image by opening it with Pillow.

    Returns:
        (width, height) tuple.

    Raises:
        ValueError: If the file is not a valid image.
    """
    try:
        with Image.open(file_path) as img:
            img.verify()
        # Re-open after verify (verify() can leave file in bad state)
        with Image.open(file_path) as img:
            return img.size
    except Exception as e:
        raise ValueError(f"Invalid image file: {file_path}") from e


def generate_thumbnail(
    file_path: str | Path,
    output_path: str | Path,
    size: int = 256,
) -> Path:
    """Generate a square WebP thumbnail preserving aspect ratio.

    The image is resized so the shortest side equals ``size``,
    then center-cropped to ``size x size``.

    Returns:
        Path to the generated thumbnail.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(file_path) as img:
        # Convert to RGB if necessary (handles RGBA, palette, etc.)
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

        img.save(output_path, format="WEBP", quality=80)

    logger.debug("image.thumbnail_generated", source=str(file_path), output=str(output_path))
    return output_path


def encode_base64(file_path: str | Path, max_size: int = 1280) -> str:
    """Resize image to max_size on longest side, then encode as base64 string.

    This is used for sending images to Ollama's vision API.
    Resizing reduces analysis time dramatically without losing content quality.

    Returns:
        Base64-encoded string of the JPEG image.
    """
    with Image.open(file_path) as img:
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


def get_image_dimensions(file_path: str | Path) -> tuple[int, int] | None:
    """Return (width, height) without fully loading the image. Returns None on error."""
    try:
        with Image.open(file_path) as img:
            return img.size
    except Exception:
        return None
