"""Routes for Outline structure (Volumes, Arcs, Chapters, Reorder, and AI Generation)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.deps import get_outline_repo, get_setting_generator
from app.db.repositories.outline_repo import OutlineRepository
from app.schemas.outline import (
    AiGenerateArcChaptersRequest,
    AiGenerateStructureRequest,
    ArcCreate,
    ArcResponse,
    ArcUpdate,
    ChapterCreate,
    ChapterResponse,
    ChapterUpdate,
    OutlineTreeResponse,
    ReorderFloatRequest,
    VolumeCreate,
    VolumeResponse,
    VolumeUpdate,
)
from app.services.setting_generator import SettingGeneratorService

router = APIRouter(prefix="/novels/{novel_uid}/outline", tags=["outline"])


@router.get("", response_model=OutlineTreeResponse)
def get_outline_tree(repo: OutlineRepository = Depends(get_outline_repo)) -> OutlineTreeResponse:
    return repo.get_outline_tree()


# --- Volumes ---

@router.post("/volumes", response_model=VolumeResponse, status_code=status.HTTP_201_CREATED)
def create_volume(
    payload: VolumeCreate,
    repo: OutlineRepository = Depends(get_outline_repo),
) -> VolumeResponse:
    return repo.create_volume(payload)


@router.put("/volumes/{vol_id}", response_model=VolumeResponse)
def update_volume(
    vol_id: int,
    payload: VolumeUpdate,
    repo: OutlineRepository = Depends(get_outline_repo),
) -> VolumeResponse:
    return repo.update_volume(vol_id, payload)


@router.delete("/volumes/{vol_id}", status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,  # 显式禁用：避免新版 FastAPI 从 `-> None` 注解推断 response_model 导致 204 断言失败
)
def delete_volume(
    vol_id: int,
    repo: OutlineRepository = Depends(get_outline_repo),
) -> None:
    repo.delete_volume(vol_id)


# --- Arcs ---

@router.post("/arcs", response_model=ArcResponse, status_code=status.HTTP_201_CREATED)
def create_arc(
    payload: ArcCreate,
    repo: OutlineRepository = Depends(get_outline_repo),
) -> ArcResponse:
    return repo.create_arc(payload)


@router.put("/arcs/{arc_id}", response_model=ArcResponse)
def update_arc(
    arc_id: int,
    payload: ArcUpdate,
    repo: OutlineRepository = Depends(get_outline_repo),
) -> ArcResponse:
    return repo.update_arc(arc_id, payload)


@router.delete("/arcs/{arc_id}", status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,  # 显式禁用：避免新版 FastAPI 从 `-> None` 注解推断 response_model 导致 204 断言失败
)
def delete_arc(
    arc_id: int,
    repo: OutlineRepository = Depends(get_outline_repo),
) -> None:
    repo.delete_arc(arc_id)


# --- Chapters ---

@router.post("/chapters", response_model=ChapterResponse, status_code=status.HTTP_201_CREATED)
def create_chapter(
    payload: ChapterCreate,
    repo: OutlineRepository = Depends(get_outline_repo),
) -> ChapterResponse:
    return repo.create_chapter(payload)


@router.put("/chapters/{chapter_id}", response_model=ChapterResponse)
def update_chapter(
    chapter_id: int,
    payload: ChapterUpdate,
    repo: OutlineRepository = Depends(get_outline_repo),
) -> ChapterResponse:
    return repo.update_chapter(chapter_id, payload)


@router.post("/chapters/reorder", response_model=ChapterResponse)
def reorder_chapter(
    payload: ReorderFloatRequest,
    repo: OutlineRepository = Depends(get_outline_repo),
) -> ChapterResponse:
    return repo.reorder_chapter(
        payload.target_id, payload.prev_sort_order, payload.next_sort_order
    )


@router.delete("/chapters/{chapter_id}", status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,  # 显式禁用：避免新版 FastAPI 从 `-> None` 注解推断 response_model 导致 204 断言失败
)
def delete_chapter(
    chapter_id: int,
    repo: OutlineRepository = Depends(get_outline_repo),
) -> None:
    repo.delete_chapter(chapter_id)


# --- AI Structure & Rolling Chapters Generation ---

@router.post("/generate-structure", response_model=OutlineTreeResponse)
async def generate_structure(
    payload: AiGenerateStructureRequest,
    svc: SettingGeneratorService = Depends(get_setting_generator),
) -> OutlineTreeResponse:
    return await svc.generate_outline_structure(
        instruction=payload.instruction,
    )


@router.post("/arcs/{arc_id}/generate-chapters", response_model=OutlineTreeResponse)
async def generate_arc_chapters(
    arc_id: int,
    payload: AiGenerateArcChaptersRequest,
    svc: SettingGeneratorService = Depends(get_setting_generator),
) -> OutlineTreeResponse:
    return await svc.generate_arc_chapters(
        arc_id=arc_id,
        chapter_count=payload.chapter_count,
        instruction=payload.instruction,
    )
