"""Pydantic schemas for Scenes, Chapter Versions, Context Preview, AI Smell, and SSE Streaming (M3)."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

from app.schemas.outline import ChapterResponse


# --- Scenes (Chapter Beats) ---

class SceneCreate(BaseModel):
    beat: str = Field(..., min_length=1)
    pov_character: int | None = None
    location_id: int | None = None
    character_ids: list[int] = Field(default_factory=list)
    story_time: str = ""
    target_words: int = Field(default=800, ge=100, le=10000)
    sort_order: float | None = None


class SceneUpdate(BaseModel):
    beat: str | None = None
    pov_character: int | None = None
    location_id: int | None = None
    character_ids: list[int] | None = None
    story_time: str | None = None
    target_words: int | None = Field(default=None, ge=100, le=10000)
    sort_order: float | None = None


class SceneResponse(BaseModel):
    id: int
    chapter_id: int
    sort_order: float
    beat: str
    pov_character: int | None = None
    location_id: int | None = None
    character_ids: list[int]
    story_time: str
    target_words: int
    created_at: str
    updated_at: str


class AiGenerateScenesRequest(BaseModel):
    scene_count: int = Field(default=3, ge=1, le=8)
    instruction: str = ""


class LlmSceneItem(BaseModel):
    beat: str
    pov_character_name: str = ""
    location_name: str = ""
    character_names: list[str] = Field(default_factory=list)
    story_time: str = ""
    target_words: int = 800


class LlmSceneBatchOutput(BaseModel):
    scenes: list[LlmSceneItem]


# --- Chapter Versions & Content ---

class ChapterSaveRequest(BaseModel):
    content: str
    source: Literal["ai", "manual"] = "manual"
    create_new_version: bool = False


class ChapterVersionResponse(BaseModel):
    id: int
    chapter_id: int
    version: int
    content: str
    source: Literal["ai", "manual"]
    word_count: int
    created_at: str


class ChapterWorkspaceResponse(BaseModel):
    chapter: ChapterResponse
    latest_content: str
    latest_version: int
    scenes: list[SceneResponse]
    versions: list[ChapterVersionResponse]


# --- Context Assembly & Preview ---

class ContextBlockItem(BaseModel):
    key: str
    label: str
    priority: Literal["required", "optional"] = "required"
    enabled: bool = True
    tokens: int
    content: str


class ContextPreviewResponse(BaseModel):
    chapter_id: int
    scene_id: int | None = None
    total_tokens: int
    budget_tokens: int = 24000
    blocks: list[ContextBlockItem]


# --- SSE Stream Requests ---

class StreamWriteRequest(BaseModel):
    chapter_id: int
    scene_id: int | None = None
    mode: Literal["scene", "chapter"] = "scene"
    existing_content: str = ""
    disabled_context_keys: list[str] = Field(default_factory=list)
    custom_context: str = ""
    instruction: str = ""


class StreamRewriteRequest(BaseModel):
    chapter_id: int | None = None
    selected_text: str = Field(..., min_length=1)
    action_type: Literal["rewrite", "expand", "shorten", "polish", "tone_shift"] = "polish"
    target_character_id: int | None = None
    instruction: str = ""


# --- Local AI Smell Detection ---

class AiSmellScanRequest(BaseModel):
    text: str


class AiSmellHit(BaseModel):
    pattern: str
    matched_text: str
    category: str
    suggestion: str
    start_index: int
    end_index: int


class AiSmellScanResponse(BaseModel):
    total_hits: int
    hits: list[AiSmellHit]


# --- Selection Logic Critique ---

class SelectionCritiqueRequest(BaseModel):
    selected_text: str = Field(..., min_length=2)


class SelectionCritiqueResponse(BaseModel):
    has_issue: bool
    issue_type: str | None = None
    issue_label: str | None = None
    description: str = ""
    suggestion: str = ""
