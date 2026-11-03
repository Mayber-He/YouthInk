"""REST API endpoints for M4 Memory Loop: Finalize Chapter, Pending Queue, Foreshadowing, Summaries, and RAG."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import (
    get_chapter_finalizer,
    get_memory_repo,
    get_rag_retriever,
)
from app.db.repositories.memory_repo import MemoryRepository
from app.schemas.memory import (
    BatchQueueActionRequest,
    ChapterMemoryItem,
    DisableableMemoryCategory,
    FinalizeChapterResponse,
    ForeshadowCreate,
    ForeshadowResponse,
    ForeshadowUpdate,
    MemoryItemCategory,
    MemoryItemDisableRequest,
    PendingItemUpdateRequest,
    PendingQueueItem,
    RagSearchResponse,
    SummaryResponse,
)
from app.services.memory.finalizer import ChapterFinalizerService
from app.services.rag.retriever import HybridRagRetriever

router = APIRouter(prefix="/novels/{novel_uid}", tags=["memory"])


@router.post(
    "/chapters/{chapter_id}/finalize",
    response_model=FinalizeChapterResponse,
)
async def finalize_chapter(
    chapter_id: int,
    finalizer: ChapterFinalizerService = Depends(get_chapter_finalizer),
) -> FinalizeChapterResponse:
    """Execute 6-step chapter finalization: backup, chunking + vector/FTS, summary, extraction, Trust Mode dispatch."""
    return await finalizer.finalize_chapter(chapter_id)


@router.post("/memory/rebuild-index")
async def rebuild_memory_index(
    finalizer: ChapterFinalizerService = Depends(get_chapter_finalizer),
) -> dict[str, int]:
    """Rebuild all vector embeddings and FTS5 indexes for finalized chapters."""
    return await finalizer.rebuild_all_indexes()


@router.get("/memory/pending-queue", response_model=list[PendingQueueItem])
def list_pending_queue(
    item_type: str | None = Query(None),
    chapter_id: int | None = Query(None),
    status: str = Query("pending"),
    repo: MemoryRepository = Depends(get_memory_repo),
) -> list[PendingQueueItem]:
    """List pending (or confirmed/discarded) extracted memory items."""
    return repo.list_pending_queue(
        item_type=item_type, chapter_id=chapter_id, status_filter=status
    )


@router.put("/memory/pending-queue/{item_type}/{item_id}")
def update_pending_item(
    item_type: MemoryItemCategory,
    item_id: int,
    payload: PendingItemUpdateRequest,
    repo: MemoryRepository = Depends(get_memory_repo),
) -> dict[str, str]:
    """Confirm, edit, or discard a single pending memory item."""
    repo.update_pending_item(item_type, item_id, payload)
    return {"status": "ok"}


@router.post("/memory/pending-queue/batch")
def batch_update_pending(
    payload: BatchQueueActionRequest,
    repo: MemoryRepository = Depends(get_memory_repo),
) -> dict[str, int]:
    """Batch confirm or discard multiple pending memory items."""
    updated = repo.batch_update_pending(payload)
    return {"updated_count": updated}


@router.get("/memory/items", response_model=list[ChapterMemoryItem])
def list_memory_items(
    chapter_id: int = Query(..., description="只列出该章抽取/录入的记忆"),
    repo: MemoryRepository = Depends(get_memory_repo),
) -> list[ChapterMemoryItem]:
    """List a chapter's memory items, including disabled ones, with conflict hints."""
    return repo.list_chapter_memory_items(chapter_id)


@router.put("/memory/items/{item_type}/{item_id}")
def set_memory_item_disabled(
    item_type: DisableableMemoryCategory,
    item_id: int,
    payload: MemoryItemDisableRequest,
    repo: MemoryRepository = Depends(get_memory_repo),
) -> dict[str, object]:
    """Disable or restore one memory item without deleting it."""
    repo.set_memory_item_disabled(item_type, item_id, payload.is_disabled)
    return {"status": "ok", "is_disabled": payload.is_disabled}


@router.get("/memory/foreshadowing", response_model=list[ForeshadowResponse])
def list_foreshadowing(
    status: str | None = Query(None),
    repo: MemoryRepository = Depends(get_memory_repo),
) -> list[ForeshadowResponse]:
    """List foreshadowing ledger entries."""
    return repo.list_foreshadowing(status=status)


@router.post("/memory/foreshadowing", response_model=ForeshadowResponse)
def create_foreshadowing(
    payload: ForeshadowCreate,
    repo: MemoryRepository = Depends(get_memory_repo),
) -> ForeshadowResponse:
    """Create a manual foreshadowing entry."""
    return repo.create_foreshadowing(payload)


@router.put("/memory/foreshadowing/{fid}", response_model=ForeshadowResponse)
def update_foreshadowing(
    fid: int,
    payload: ForeshadowUpdate,
    repo: MemoryRepository = Depends(get_memory_repo),
) -> ForeshadowResponse:
    """Update foreshadowing status, recovery range, or description."""
    return repo.update_foreshadowing(fid, payload)


@router.delete("/memory/foreshadowing/{fid}")
def delete_foreshadowing(
    fid: int,
    repo: MemoryRepository = Depends(get_memory_repo),
) -> dict[str, str]:
    """Delete a foreshadowing entry."""
    repo.delete_foreshadowing(fid)
    return {"status": "deleted"}


@router.get("/memory/summaries", response_model=list[SummaryResponse])
def list_summaries(
    level: str | None = Query(None),
    repo: MemoryRepository = Depends(get_memory_repo),
) -> list[SummaryResponse]:
    """List multi-tier summaries (chapter / arc / volume / novel)."""
    return repo.list_summaries(level=level)


@router.get("/memory/search", response_model=RagSearchResponse)
async def search_memory_rag(
    q: str = Query(..., min_length=1),
    max_chapter_sort: float | None = Query(None),
    top_k: int = Query(5, ge=1, le=20),
    retriever: HybridRagRetriever = Depends(get_rag_retriever),
) -> RagSearchResponse:
    """Hybrid RAG search (Metadata filter + Vector + jieba FTS5 + RRF)."""
    return await retriever.search(
        query=q, max_chapter_sort=max_chapter_sort, top_k=top_k
    )
