"""REST API endpoints for the Explicit Constraint System (anti-hallucination)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_constraint_repo, get_outline_repo
from app.db.repositories.constraint_repo import ConstraintRepository
from app.db.repositories.entity_repo import EntityRepository
from app.db.repositories.outline_repo import OutlineRepository
from app.db.repositories.writing_repo import WritingRepository
from app.schemas.constraints import (
    ConstraintCreate,
    ConstraintResponse,
    ConstraintStatus,
    ConstraintTargetType,
    ConstraintUpdate,
)

router = APIRouter(prefix="/novels/{novel_uid}", tags=["constraints"])


@router.get("/constraints", response_model=list[ConstraintResponse])
def list_constraints(
    target_type: ConstraintTargetType | None = Query(None),
    target_id: int | None = Query(None),
    status_filter: ConstraintStatus | None = Query(None, alias="status"),
    repo: ConstraintRepository = Depends(get_constraint_repo),
) -> list[ConstraintResponse]:
    """List constraints, optionally filtered by target and status."""
    return repo.list_constraints(
        target_type=target_type, target_id=target_id, status=status_filter
    )


@router.post("/constraints", response_model=ConstraintResponse, status_code=status.HTTP_201_CREATED)
def create_constraint(
    payload: ConstraintCreate,
    repo: ConstraintRepository = Depends(get_constraint_repo),
) -> ConstraintResponse:
    """Create a new hard/soft constraint."""
    return repo.create_constraint(payload)


@router.put("/constraints/{constraint_id}", response_model=ConstraintResponse)
def update_constraint(
    constraint_id: int,
    payload: ConstraintUpdate,
    repo: ConstraintRepository = Depends(get_constraint_repo),
) -> ConstraintResponse:
    """Update a constraint (edit content, resolve, change severity/window)."""
    return repo.update_constraint(constraint_id, payload)


@router.delete("/constraints/{constraint_id}", status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,  # 显式禁用：避免新版 FastAPI 从 `-> None` 注解推断 response_model 导致 204 断言失败
)
def delete_constraint(
    constraint_id: int,
    repo: ConstraintRepository = Depends(get_constraint_repo),
) -> None:
    """Delete a constraint."""
    repo.delete_constraint(constraint_id)


@router.get(
    "/chapters/{chapter_id}/active-constraints",
    response_model=list[ConstraintResponse],
)
def list_active_constraints_for_chapter(
    chapter_id: int,
    repo: ConstraintRepository = Depends(get_constraint_repo),
    outline_repo: OutlineRepository = Depends(get_outline_repo),
) -> list[ConstraintResponse]:
    """List constraints in effect for writing the given chapter.

    Scope: novel-wide + chapter-scoped + characters/locations active in the chapter.
    """
    ch = outline_repo.get_chapter(chapter_id)
    # Resolve active entities via scene data, mirroring the context assembler.
    novel_conn = repo.conn
    writing_repo = WritingRepository(novel_conn)
    entity_repo = EntityRepository(novel_conn)
    scenes = writing_repo.list_scenes(chapter_id)
    char_ids = sorted(
        {cid for s in scenes for cid in ([s.pov_character] if s.pov_character else []) + s.character_ids}
    )
    loc_ids = sorted({s.location_id for s in scenes if s.location_id})
    if not char_ids:
        char_ids = [c.id for c in entity_repo.list_characters() if c.role in ("female_lead", "male_lead", "major")]
    return repo.list_active_for_chapter(chapter_id, ch.sort_order, char_ids, loc_ids)
