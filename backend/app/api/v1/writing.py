"""Routes for Chapter Scenes, Versions, Context Preview, AI Smell Check, and Export (M3)."""

from __future__ import annotations

from typing import Literal
from urllib.parse import quote
from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import PlainTextResponse

from app.api.deps import (
    get_context_assembler,
    get_novel_repo,
    get_settings_repo,
    get_writing_repo,
    get_writing_service,
)
from app.db.repositories.novel_repo import NovelRepository
from app.db.repositories.settings_repo import SettingsRepository
from app.db.repositories.writing_repo import WritingRepository
from app.schemas.writing import (
    AiGenerateScenesRequest,
    AiSmellScanRequest,
    AiSmellScanResponse,
    ChapterSaveRequest,
    ChapterWorkspaceResponse,
    ContextPreviewResponse,
    SceneCreate,
    SceneResponse,
    SceneUpdate,
)
from app.services.ai_smell import scan_ai_smell
from app.services.context.assembler import ContextAssembler
from app.services.writing_service import WritingService

router = APIRouter(prefix="/novels/{novel_uid}", tags=["writing"])


# --- Chapter Workspace & Versions ---

@router.get("/chapters/{chapter_id}/workspace", response_model=ChapterWorkspaceResponse)
def get_chapter_workspace(
    chapter_id: int,
    repo: WritingRepository = Depends(get_writing_repo),
) -> ChapterWorkspaceResponse:
    return repo.get_chapter_workspace(chapter_id)


@router.put("/chapters/{chapter_id}/content", response_model=ChapterWorkspaceResponse)
def save_chapter_content(
    chapter_id: int,
    payload: ChapterSaveRequest,
    repo: WritingRepository = Depends(get_writing_repo),
) -> ChapterWorkspaceResponse:
    return repo.save_chapter_content(
        chapter_id,
        content=payload.content,
        source=payload.source,
        create_new_version=payload.create_new_version,
    )


@router.post(
    "/chapters/{chapter_id}/versions/{version_num}/restore",
    response_model=ChapterWorkspaceResponse,
)
def restore_chapter_version(
    chapter_id: int,
    version_num: int,
    repo: WritingRepository = Depends(get_writing_repo),
) -> ChapterWorkspaceResponse:
    return repo.restore_chapter_version(chapter_id, version_num)


# --- Scenes (Chapter Beats) ---

@router.get("/chapters/{chapter_id}/scenes", response_model=list[SceneResponse])
def list_scenes(
    chapter_id: int,
    repo: WritingRepository = Depends(get_writing_repo),
) -> list[SceneResponse]:
    return repo.list_scenes(chapter_id)


@router.post(
    "/chapters/{chapter_id}/scenes",
    response_model=SceneResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_scene(
    chapter_id: int,
    payload: SceneCreate,
    repo: WritingRepository = Depends(get_writing_repo),
) -> SceneResponse:
    return repo.create_scene(chapter_id, payload)


@router.put("/scenes/{scene_id}", response_model=SceneResponse)
def update_scene(
    scene_id: int,
    payload: SceneUpdate,
    repo: WritingRepository = Depends(get_writing_repo),
) -> SceneResponse:
    return repo.update_scene(scene_id, payload)


@router.delete("/scenes/{scene_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scene(
    scene_id: int,
    repo: WritingRepository = Depends(get_writing_repo),
) -> None:
    repo.delete_scene(scene_id)


@router.post("/chapters/{chapter_id}/scenes/generate", response_model=list[SceneResponse])
async def generate_scenes(
    chapter_id: int,
    payload: AiGenerateScenesRequest,
    svc: WritingService = Depends(get_writing_service),
) -> list[SceneResponse]:
    return await svc.generate_chapter_scenes(
        chapter_id=chapter_id,
        scene_count=payload.scene_count,
        instruction=payload.instruction,
    )


# --- Context Preview ---

@router.get("/chapters/{chapter_id}/context-preview", response_model=ContextPreviewResponse)
def get_context_preview(
    chapter_id: int,
    scene_id: int | None = Query(default=None),
    disabled_keys: str = Query(default=""),
    assembler: ContextAssembler = Depends(get_context_assembler),
) -> ContextPreviewResponse:
    disabled_list = [k.strip() for k in disabled_keys.split(",") if k.strip()]
    return assembler.build_context_preview(chapter_id, scene_id, disabled_list)


# --- Local AI Smell Scan ---

@router.post("/ai-smell-scan", response_model=AiSmellScanResponse)
def check_ai_smell(
    payload: AiSmellScanRequest,
    novel_repo: NovelRepository = Depends(get_novel_repo),
    settings_repo: SettingsRepository = Depends(get_settings_repo),
) -> AiSmellScanResponse:
    novel = novel_repo.get_novel_detail()
    styles = settings_repo.list_style_templates()
    matched = next((s for s in styles if s.id == novel.style_template_id), None)
    extra = matched.forbidden_exprs if matched else []
    return scan_ai_smell(payload.text, extra_forbidden=extra)


# --- Export (TXT / Markdown) ---

@router.get("/export")
def export_manuscript(
    format: Literal["txt", "md"] = Query(default="md"),
    repo: WritingRepository = Depends(get_writing_repo),
) -> PlainTextResponse:
    filename, body = repo.export_novel_manuscript(format)
    encoded_name = quote(filename)
    return PlainTextResponse(
        content=body,
        media_type="text/markdown; charset=utf-8"
        if format == "md"
        else "text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"
        },
    )
