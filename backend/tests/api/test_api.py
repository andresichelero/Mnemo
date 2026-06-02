import pytest
from httpx import AsyncClient, ASGITransport
import os
import shutil

from app.main import app
from app.config import settings

pytestmark = pytest.mark.asyncio

from app.db.init_db import init_db

@pytest.fixture(scope="session", autouse=True)
async def setup_test_db():
    # Properly initialize DB including setting seeds
    await init_db()
    yield

@pytest.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Default header with API key
        client.headers.update({"X-API-Key": settings.ensure_api_key()})
        yield client

async def test_health_endpoint(async_client):
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

async def test_folders_crud(async_client):
    # Create
    create_response = await async_client.post(
        "/api/v1/folders", 
        json={"name": "Test Folder", "path": "/tmp/test", "color_hex": "#ff0000"}
    )
    assert create_response.status_code == 201
    folder_id = create_response.json()["id"]

    # List
    list_response = await async_client.get("/api/v1/folders")
    assert list_response.status_code == 200
    assert any(f["id"] == folder_id for f in list_response.json())

    # Update
    update_response = await async_client.patch(
        f"/api/v1/folders/{folder_id}", 
        json={"name": "Updated Folder"}
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Updated Folder"

    # Delete
    delete_response = await async_client.delete(f"/api/v1/folders/{folder_id}")
    assert delete_response.status_code == 204

async def test_settings_endpoints(async_client):
    response = await async_client.get("/api/v1/settings")
    assert response.status_code == 200
    data = response.json()
    assert "idle_threshold_cpu" in data
