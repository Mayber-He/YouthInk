"""Pydantic schemas for Volumes, Arcs, Chapters, and Outline Tree (M2)."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

ChapterStatus = Literal["pending", "outline", "draft", "final"]


class VolumeCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=128)
    synopsis: str = ""
    goal: str = ""
    sort_order: float | None = None


class VolumeUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=128)
    synopsis: str | None = None
    goal: str | None = None
    sort_order: float | None = None


class VolumeResponse(BaseModel):
    id: int
    novel_id: int
    sort_order: float
    title: str
    synopsis: str
    goal: str
    created_at: str
    updated_at: str


class ArcCreate(BaseModel):
    volume_id: int
    title: str = Field(..., min_length=1, max_length=128)
    goal: str = ""
    core_conflict: str = ""
    start_chapter: int | None = None
    end_chapter: int | None = None
    sort_order: float | None = None


class ArcUpdate(BaseModel):
    volume_id: int | None = None
    title: str | None = Field(default=None, min_length=1, max_length=128)
    goal: str | None = None
    core_conflict: str | None = None
    start_chapter: int | None = None
    end_chapter: int | None = None
    sort_order: float | None = None


class ArcResponse(BaseModel):
    id: int
    volume_id: int
    sort_order: float
    title: str
    goal: str
    core_conflict: str
    start_chapter: int | None = None
    end_chapter: int | None = None
    created_at: str
    updated_at: str


class ChapterCreate(BaseModel):
    arc_id: int
    title: str = Field(..., min_length=1, max_length=128)
    synopsis: str = ""
    story_time: str = ""
    sort_order: float | None = None
    after_chapter_id: int | None = None
    before_chapter_id: int | None = None
    locked: bool = False


class ChapterUpdate(BaseModel):
    arc_id: int | None = None
    title: str | None = None
    synopsis: str | None = None
    status: ChapterStatus | None = None
    story_time: str | None = None
    sort_order: float | None = None
    locked: bool | None = None


class ChapterResponse(BaseModel):
    id: int
    arc_id: int
    sort_order: float
    display_index: int = 1
    title: str
    synopsis: str
    status: ChapterStatus
    word_count: int
    story_time: str
    locked: bool
    created_at: str
    updated_at: str


class ReorderFloatRequest(BaseModel):
    target_id: int
    prev_sort_order: float | None = None
    next_sort_order: float | None = None


class ArcTreeNode(ArcResponse):
    chapters: list[ChapterResponse] = Field(default_factory=list)


class VolumeTreeNode(VolumeResponse):
    arcs: list[ArcTreeNode] = Field(default_factory=list)


class OutlineTreeResponse(BaseModel):
    volumes: list[VolumeTreeNode]
    total_chapters: int


# --- AI Outline Generation Schemas ---

class AiGenerateStructureRequest(BaseModel):
    volume_count: int = Field(default=3, ge=1, le=10)
    arcs_per_volume: int = Field(default=2, ge=1, le=6)
    instruction: str = ""


class AiGenerateArcChaptersRequest(BaseModel):
    chapter_count: int = Field(default=5, ge=1, le=20)
    instruction: str = ""


class LlmArcPlanItem(BaseModel):
    title: str
    goal: str = ""
    core_conflict: str = ""
    start_chapter: int | None = None
    end_chapter: int | None = None


class LlmVolumePlanItem(BaseModel):
    title: str
    synopsis: str = ""
    goal: str = ""
    arcs: list[LlmArcPlanItem] = Field(default_factory=list)


class LlmStructureOutput(BaseModel):
    volumes: list[LlmVolumePlanItem]


class LlmChapterPlanItem(BaseModel):
    title: str
    synopsis: str = ""
    story_time: str = ""


class LlmChapterBatchOutput(BaseModel):
    chapters: list[LlmChapterPlanItem]
