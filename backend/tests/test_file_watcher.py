import asyncio
import os
import pytest
from unittest.mock import patch, MagicMock

from app.services.file_watcher import ImageEventHandler

pytestmark = pytest.mark.asyncio

async def test_wait_for_stability_success(tmp_path):
    # Create a dummy image
    test_file = tmp_path / "test.png"
    test_file.write_bytes(b"dummy image data")
    
    handler = ImageEventHandler(asyncio.get_running_loop())
    
    # It should become stable immediately because size doesn't change
    is_stable = await handler._wait_for_stability(str(test_file), max_wait=3)
    assert is_stable is True

async def test_wait_for_stability_timeout(tmp_path):
    test_file = tmp_path / "test.png"
    
    # Mock stat to return a constantly growing size
    class GrowingStat:
        def __init__(self):
            self.size = 10
        @property
        def st_size(self):
            self.size += 10
            return self.size

    with patch("pathlib.Path.stat", return_value=GrowingStat()):
        handler = ImageEventHandler(asyncio.get_running_loop())
        # Should timeout and return False
        is_stable = await handler._wait_for_stability(str(test_file), max_wait=2)
        assert is_stable is False

async def test_wait_for_stability_not_found():
    handler = ImageEventHandler(asyncio.get_running_loop())
    # File doesn't exist
    is_stable = await handler._wait_for_stability("/tmp/does_not_exist_mnemo.png", max_wait=1)
    assert is_stable is False

@patch("app.services.image_service.is_supported_image", return_value=True)
async def test_handler_ignores_duplicates(mock_supported, tmp_path):
    handler = ImageEventHandler(asyncio.get_running_loop())
    
    # Mock process to not actually do async work during this sync call
    with patch("asyncio.run_coroutine_threadsafe") as mock_run:
        handler._handle_path("/fake/path.png")
        assert mock_run.call_count == 1
        
        # Calling again with same path should be ignored (it's in _processing)
        handler._handle_path("/fake/path.png")
        assert mock_run.call_count == 1
