"""Tests for image_service — thumbnails, hashing, validation, base64."""

from pathlib import Path

import pytest
from PIL import Image

from app.services.image_service import (
    encode_base64,
    generate_thumbnail,
    get_file_hash,
    get_image_dimensions,
    is_supported_image,
    validate_image,
)


@pytest.fixture
def sample_image(tmp_path: Path) -> Path:
    """Create a 200x300 test PNG image."""
    img_path = tmp_path / "test_screenshot.png"
    img = Image.new("RGB", (200, 300), color=(128, 64, 32))
    img.save(img_path, format="PNG")
    return img_path


@pytest.fixture
def sample_rgba_image(tmp_path: Path) -> Path:
    """Create an RGBA test image."""
    img_path = tmp_path / "test_rgba.png"
    img = Image.new("RGBA", (400, 600), color=(128, 64, 32, 200))
    img.save(img_path, format="PNG")
    return img_path


class TestIsSupported:
    def test_supported_extensions(self):
        assert is_supported_image("photo.png")
        assert is_supported_image("photo.jpg")
        assert is_supported_image("photo.jpeg")
        assert is_supported_image("photo.webp")
        assert is_supported_image("photo.PNG")

    def test_unsupported_extensions(self):
        assert not is_supported_image("file.txt")
        assert not is_supported_image("file.pdf")
        assert not is_supported_image("file.mp4")


class TestFileHash:
    @pytest.mark.asyncio
    async def test_deterministic(self, sample_image: Path):
        h1 = await get_file_hash(sample_image)
        h2 = await get_file_hash(sample_image)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    @pytest.mark.asyncio
    async def test_different_files(self, sample_image: Path, sample_rgba_image: Path):
        h1 = await get_file_hash(sample_image)
        h2 = await get_file_hash(sample_rgba_image)
        assert h1 != h2


class TestValidateImage:
    @pytest.mark.asyncio
    async def test_valid_image(self, sample_image: Path):
        w, h = await validate_image(sample_image)
        assert w == 200
        assert h == 300

    @pytest.mark.asyncio
    async def test_invalid_file(self, tmp_path: Path):
        bad = tmp_path / "not_image.png"
        bad.write_text("not an image")
        with pytest.raises(ValueError, match="Invalid image"):
            await validate_image(bad)

    @pytest.mark.asyncio
    async def test_file_size_limit(self, sample_image: Path, monkeypatch):
        # Mock MAX_FILE_SIZE_BYTES to 1 byte
        import app.services.image_service as mod
        monkeypatch.setattr(mod, "MAX_FILE_SIZE_BYTES", 1)
        
        with pytest.raises(ValueError, match="File too large"):
            await validate_image(sample_image)


class TestGenerateThumbnail:
    @pytest.mark.asyncio
    async def test_generates_webp(self, sample_image: Path, tmp_path: Path):
        out = tmp_path / "thumb.webp"
        result = await generate_thumbnail(sample_image, out, size=128)
        assert result.exists()
        assert result.suffix == ".webp"

        with Image.open(result) as img:
            assert img.size == (128, 128)
            assert img.format == "WEBP"

    @pytest.mark.asyncio
    async def test_handles_rgba(self, sample_rgba_image: Path, tmp_path: Path):
        out = tmp_path / "thumb_rgba.webp"
        result = await generate_thumbnail(sample_rgba_image, out, size=64)
        assert result.exists()
        with Image.open(result) as img:
            assert img.size == (64, 64)

    @pytest.mark.asyncio
    async def test_creates_parent_dirs(self, sample_image: Path, tmp_path: Path):
        out = tmp_path / "deep" / "nested" / "thumb.webp"
        result = await generate_thumbnail(sample_image, out)
        assert result.exists()


class TestEncodeBase64:
    @pytest.mark.asyncio
    async def test_returns_base64_string(self, sample_image: Path):
        b64 = await encode_base64(sample_image)
        assert isinstance(b64, str)
        assert len(b64) > 100

        # Should be valid base64
        import base64 as b64_module
        decoded = b64_module.b64decode(b64)
        assert len(decoded) > 0

    @pytest.mark.asyncio
    async def test_resizes_large_images(self, tmp_path: Path):
        # Create a large image
        large = tmp_path / "large.png"
        Image.new("RGB", (4000, 3000)).save(large, format="PNG")

        b64 = await encode_base64(large, max_size=1280)
        assert isinstance(b64, str)


class TestGetDimensions:
    @pytest.mark.asyncio
    async def test_returns_dimensions(self, sample_image: Path):
        dims = await get_image_dimensions(sample_image)
        assert dims == (200, 300)

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self, tmp_path: Path):
        bad = tmp_path / "bad.png"
        bad.write_text("nope")
        assert await get_image_dimensions(bad) is None
