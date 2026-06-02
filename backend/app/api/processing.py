"""Processing API — stats and background processing triggers.

Endpoints:
    GET  /processing/status            Queue size and system idle status
    POST /processing/trigger           Force manual processing of queue
    POST /processing/reprocess-errors  Re-queue failed screenshots
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.screenshot import Screenshot
from app.schemas.schemas import ProcessingStatus, ProcessingTrigger, ProcessingTriggerResponse, ReprocessResponse
from app.services.llm_service import LLMService
from app.services.embedding_service import EmbeddingService
from app.services.settings_service import settings_service
from app.config import settings

router = APIRouter(prefix="/processing", tags=["processing"])


@router.get("/status", response_model=ProcessingStatus)
async def get_processing_status(session: AsyncSession = Depends(get_session)):
    """Get statistics about the processing queue."""
    pending_count = (
        await session.execute(
            select(func.count()).where(Screenshot.status == "pending")
        )
    ).scalar() or 0

    error_count = (
        await session.execute(
            select(func.count()).where(Screenshot.status == "error")
        )
    ).scalar() or 0
    
    # Optional: check if services are alive
    all_settings = await settings_service.get_all(session)
    llm = LLMService(
        all_settings.get("ollama_base_url", settings.ollama_base_url), 
        all_settings.get("ollama_model", settings.ollama_model)
    )
    ollama_ok = await llm.check_connection()
    await llm.close()

    embedding = EmbeddingService(
        all_settings.get("telnyx_api_key", settings.telnyx_api_key), 
        all_settings.get("telnyx_embedding_model", settings.telnyx_embedding_model),
        all_settings.get("ollama_base_url", settings.ollama_base_url),
        all_settings.get("local_embedding_model", "nomic-embed-text")
    )
    telnyx_ok = await embedding.check_connection()
    await embedding.close()

    return ProcessingStatus(
        queue_size=pending_count,
        currently_processing=None, # Updated by worker if integrated via memory cache
        is_idle=True, # Handled by the background idle_detector, assuming True for API stub
        ollama_connected=ollama_ok,
        telnyx_connected=telnyx_ok,
        processed_today=0, # Could be implemented via date filtering on ingested_at
        errors_today=error_count,
    )


@router.post("/trigger", response_model=ProcessingTriggerResponse)
async def trigger_processing(
    req: ProcessingTrigger | None = None,
    session: AsyncSession = Depends(get_session)
):
    """Trigger manual processing queue logic (mock for the actual background job).
    
    In a complete implementation, this would signal the APScheduler to run the job now.
    """
    limit = req.limit if req else 5
    # Since background workers run via APScheduler, you might just use a signalling mechanism here.
    # For now, it returns 0.
    return ProcessingTriggerResponse(triggered=0)


@router.post("/reprocess-errors", response_model=ReprocessResponse)
async def reprocess_errors(session: AsyncSession = Depends(get_session)):
    """Reset all 'error' status screenshots to 'pending'."""
    stmt = (
        update(Screenshot)
        .where(Screenshot.status == "error", Screenshot.deleted_at.is_(None))
        .values(status="pending", error_message=None)
    )
    result = await session.execute(stmt)
    await session.flush()
    return ReprocessResponse(requeued=result.rowcount)
