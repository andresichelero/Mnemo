"""Settings API — read and write configuration.

Endpoints:
    GET   /settings
    PATCH /settings
    GET   /settings/validate
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_session
from app.schemas.schemas import OllamaStatus, SettingsValidation, TelnyxStatus
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService
from app.services.settings_service import settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
async def get_settings(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Get all settings, with secrets masked."""
    all_settings = await settings_service.get_all(session)
    return settings_service.mask_secrets(all_settings)


@router.patch("")
async def update_settings(
    updates: dict[str, str],
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Partially update settings and invalidate the cache."""
    # Prevent overwriting masked API keys with the mask string
    filtered_updates = {
        k: v for k, v in updates.items()
        if not (v.startswith("****") or v.endswith("****"))
    }
    
    updated = await settings_service.update(session, filtered_updates)
    
    # Dynamically apply changes to background services
    from app.services.file_watcher import file_watcher
    from app.services.idle_detector import idle_detector
    import json
    
    if "watched_folders" in updated:
        try:
            paths = json.loads(updated["watched_folders"])
            file_watcher.stop()
            file_watcher.start(paths)
        except Exception:
            pass
            
    if "idle_threshold_cpu" in updated or "idle_check_seconds" in updated:
        threshold = float(updated.get("idle_threshold_cpu", "10"))
        window = float(updated.get("idle_check_seconds", "30"))
        idle_detector.update_config(threshold_cpu=threshold, idle_window_seconds=window)
        
    return settings_service.mask_secrets(updated)


@router.get("/validate", response_model=SettingsValidation)
async def validate_settings(session: AsyncSession = Depends(get_session)):
    """Test connections to LLM and Embedding services based on current settings."""
    all_settings = await settings_service.get_all(session)
    
    # Test Ollama
    llm = LLMService(
        base_url=all_settings.get("ollama_base_url", settings.ollama_base_url),
        model=all_settings.get("ollama_model", settings.ollama_model),
    )
    ollama_ok = await llm.check_connection()
    await llm.close()
    
    # Test Telnyx/Embeddings
    emb = EmbeddingService(
        api_key=all_settings.get("telnyx_api_key", settings.telnyx_api_key),
        model=all_settings.get("telnyx_embedding_model", settings.telnyx_embedding_model),
        ollama_base_url=all_settings.get("ollama_base_url", settings.ollama_base_url),
        local_model=all_settings.get("local_embedding_model", "nomic-embed-text"),
    )
    telnyx_ok = await emb.check_connection()
    await emb.close()
    
    return SettingsValidation(
        ollama=OllamaStatus(
            connected=ollama_ok,
            model_available=ollama_ok,
            model=all_settings.get("ollama_model", settings.ollama_model),
        ),
        telnyx=TelnyxStatus(
            connected=telnyx_ok,
            key_valid=bool(all_settings.get("telnyx_api_key")) and telnyx_ok,
        )
    )
