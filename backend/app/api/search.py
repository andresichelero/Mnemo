"""Search API — Semantic and textual search across screenshots.

Endpoints:
    POST /search           Semantic search via ChromaDB + SQLite filtering
    GET  /search/suggest   Autocomplete suggestions (tags, categories)
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.session import get_session
from app.models.analysis import Analysis
from app.models.screenshot import Screenshot
from app.models.screenshot_folder import ScreenshotFolder
from app.schemas.schemas import SearchRequest, SearchResponse, SearchResultItem, SearchSuggestResponse
from app.schemas.schemas import ScreenshotOut
from app.services.embedding_service import EmbeddingService
from app.services.vector_store import VectorStore

logger = structlog.get_logger()
router = APIRouter(prefix="/search", tags=["search"])


@router.post("", response_model=SearchResponse)
async def search(
    req: SearchRequest,
    session: AsyncSession = Depends(get_session),
):
    """Perform a semantic search across analyzed screenshots.
    
    Filters by category or folder if provided. Results are sorted by semantic score.
    """
    embedding_service = EmbeddingService(
        api_key=settings.api_key, 
        model=settings.telnyx_embedding_model, 
        ollama_base_url=settings.ollama_base_url,
        local_model=settings.local_embedding_model,
    )
    
    # 1. Generate embedding for query
    query_emb = await embedding_service.generate_embedding(req.query)
    
    if not query_emb:
        # Fallback to textual/FTS search (simple LIKE for now)
        stmt = (
            select(Screenshot)
            .join(Analysis)
            .where(Screenshot.deleted_at.is_(None))
            .where(
                (Analysis.description.ilike(f"%{req.query}%")) |
                (Analysis.tags.ilike(f"%{req.query}%")) |
                (Analysis.extracted_text.ilike(f"%{req.query}%"))
            )
            .options(
                selectinload(Screenshot.analysis),
                selectinload(Screenshot.folders).selectinload(ScreenshotFolder.folder)
            )
            .limit(req.limit)
        )
        
        if req.category:
            stmt = stmt.where(Analysis.category == req.category)
            
        if req.folder_id:
            stmt = stmt.join(ScreenshotFolder).where(ScreenshotFolder.folder_id == req.folder_id)

        result = await session.execute(stmt)
        items = result.scalars().all()
        
        return SearchResponse(
            results=[
                SearchResultItem(
                    screenshot=ScreenshotOut.model_validate(s),
                    score=1.0,
                    matched_by="text"
                )
                for s in items
            ]
        )

    # 2. Query Vector Store
    vector_store = VectorStore(str(settings.chroma_abs_path))
    
    where_filters = {}
    if req.category:
        where_filters["category"] = req.category

    # Query Chroma
    chroma_results = await vector_store.query(
        embedding=query_emb,
        n_results=req.limit * 2, # fetch more, filter by folder_id locally if needed
        where=where_filters if where_filters else None
    )

    if not chroma_results:
        return SearchResponse(results=[])

    # 3. Resolve Chroma IDs to SQLite records and filter by folder and threshold
    screenshot_ids = [res["id"] for res in chroma_results if res["score"] >= req.min_score]
    if not screenshot_ids:
        return SearchResponse(results=[])

    stmt = (
        select(Screenshot)
        .where(
            Screenshot.id.in_(screenshot_ids),
            Screenshot.deleted_at.is_(None)
        )
        .options(
            selectinload(Screenshot.analysis),
            selectinload(Screenshot.folders).selectinload(ScreenshotFolder.folder)
        )
    )

    if req.folder_id:
        stmt = stmt.join(ScreenshotFolder).where(ScreenshotFolder.folder_id == req.folder_id)

    db_results = await session.execute(stmt)
    screenshots_by_id = {s.id: s for s in db_results.scalars().all()}

    # Map back to ordered SearchResultItem
    results = []
    for cr in chroma_results:
        s = screenshots_by_id.get(cr["id"])
        if s and cr["score"] >= req.min_score:
            results.append(
                SearchResultItem(
                    screenshot=ScreenshotOut.model_validate(s),
                    score=cr["score"],
                    matched_by="semantic",
                )
            )
            if len(results) >= req.limit:
                break

    return SearchResponse(results=results)


@router.get("/suggest", response_model=SearchSuggestResponse)
async def suggest_tags(session: AsyncSession = Depends(get_session)):
    """Suggest top 50 unique tags for autocomplete."""
    result = await session.execute(select(Analysis.tags))
    rows = result.scalars().all()
    
    all_tags = set()
    import json
    for row in rows:
        try:
            parsed_tags = json.loads(row)
            all_tags.update(parsed_tags)
        except Exception:
            # handle cases where it's stored as python string representation
            try:
                import ast
                parsed_tags = ast.literal_eval(row)
                if isinstance(parsed_tags, list):
                    all_tags.update(parsed_tags)
            except Exception:
                pass
            
    sorted_tags = sorted(list(all_tags))
    return SearchSuggestResponse(suggestions=sorted_tags[:50])
