"""REST API endpoints for the checklist-based Consistency Review (Phase 3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.deps import get_consistency_service
from app.schemas.consistency import (
    ApplyReviewRequest,
    ConsistencyReviewResponse,
    ConsistencyReviewSummary,
)
from app.schemas.writing import ChapterWorkspaceResponse
from app.services.memory.consistency import ConsistencyReviewService

router = APIRouter(prefix="/novels/{novel_uid}", tags=["consistency"])


@router.post("/consistency-reviews/{review_id}/apply", response_model=ChapterWorkspaceResponse)
def apply_consistency_revision(
    review_id: int,
    payload: ApplyReviewRequest,
    svc: ConsistencyReviewService = Depends(get_consistency_service),
) -> ChapterWorkspaceResponse:
    return svc.apply_revision(review_id, payload)


@router.post(
    "/chapters/{chapter_id}/consistency-review",
    response_model=ConsistencyReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
async def run_consistency_review(
    chapter_id: int,
    svc: ConsistencyReviewService = Depends(get_consistency_service),
) -> ConsistencyReviewResponse:
    """Run an LLM consistency review on the chapter's latest version.

    Flags-only: issues are reported with evidence and suggestions, never auto-applied.
    """
    return await svc.run_review(chapter_id)


@router.get(
    "/chapters/{chapter_id}/consistency-reviews",
    response_model=list[ConsistencyReviewSummary],
)
def list_consistency_reviews(
    chapter_id: int,
    svc: ConsistencyReviewService = Depends(get_consistency_service),
) -> list[ConsistencyReviewSummary]:
    """List past consistency review summaries for a chapter."""
    return svc.list_reviews(chapter_id)


@router.get(
    "/consistency-reviews/{review_id}",
    response_model=ConsistencyReviewResponse,
)
def get_consistency_review(
    review_id: int,
    svc: ConsistencyReviewService = Depends(get_consistency_service),
) -> ConsistencyReviewResponse:
    """Get a full consistency review report by id."""
    return svc.get_review(review_id)
