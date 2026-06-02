import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.scheduler import BackgroundSchedulerService
from app.models.screenshot import Screenshot

pytestmark = pytest.mark.asyncio

@patch("app.services.scheduler.idle_detector.is_idle", return_value=True)
@patch("app.services.scheduler.settings_service.get", AsyncMock(return_value="idle"))
@patch("app.services.scheduler.async_session_factory")
async def test_process_pending_no_screenshots(mock_session_factory, mock_is_idle):
    # Setup mock session to return empty list
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = []
    mock_session.execute.return_value = mock_result
    
    mock_session_factory.return_value.__aenter__.return_value = mock_session
    
    scheduler = BackgroundSchedulerService()
    # It should just return without doing anything
    await scheduler.process_pending()
    
    # ensure execute was called (to fetch pending)
    assert mock_session.execute.call_count == 1

@patch("app.services.scheduler.idle_detector.is_idle", return_value=False)
@patch("app.services.scheduler.settings_service.get", AsyncMock(return_value="idle"))
@patch("app.services.scheduler.async_session_factory")
async def test_process_pending_not_idle(mock_session_factory, mock_is_idle):
    scheduler = BackgroundSchedulerService()
    # Should abort early because mode is idle and is_idle is False
    await scheduler.process_pending()
    
    # execute shouldn't even be called to fetch (it's called 0 times on the mock session)
    # The session_factory is called 1 time to get the settings
    assert mock_session_factory.call_count == 1

async def test_scheduler_start_stop():
    scheduler = BackgroundSchedulerService()
    
    # Should start successfully
    scheduler.start()
    assert scheduler._is_running is True
    
    # Should not crash on double start
    scheduler.start()
    
    # Should stop
    scheduler.stop()
    assert scheduler._is_running is False
