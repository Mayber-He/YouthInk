"""Pydantic schemas for Scenes, Chapter Versions, Context Preview, AI Smell, and SSE Streaming (M3)."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, model_validator

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
    # 事件清单字段（T3 新结构）。goal/entry_state/exit_state 为短语，
    # must_happen 最多 3 条、每条尽量 ≤25 字，must_not_include 为本场禁止出现的素材。
    goal: str = ""
    entry_state: str = ""
    must_happen: list[str] = Field(default_factory=list)
    exit_state: str = ""
    must_not_include: list[str] = Field(default_factory=list)
    # 旧字段：仍兼容老模型输出 / 老测试；若新字段为空则回退到 beat 原文。
    beat: str = ""
    pov_character_name: str = ""
    location_name: str = ""
    character_names: list[str] = Field(default_factory=list)
    story_time: str = ""
    target_words: int = 800

    def has_event_checklist(self) -> bool:
        return bool(self.goal or self.entry_state or self.must_happen or self.exit_state)


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


class StreamSupplementRequest(BaseModel):
    chapter_id: int
    content: str = Field(..., max_length=100000)
    insertion_index: int = Field(..., ge=0)
    instruction: str = Field(..., min_length=1, max_length=2000)
    disabled_context_keys: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def insertion_index_within_content(self) -> "StreamSupplementRequest":
        content_length = len(self.content.encode("utf-16-le")) // 2
        if self.insertion_index > content_length:
            raise ValueError("insertion_index must not exceed content length")
        if not self.instruction.strip():
            raise ValueError("instruction must not be blank")
        return self


# --- Model-Assisted AI-Style Review ---

class AiSmellScanRequest(BaseModel):
    text: str
    chapter_id: int | None = None


class LlmAiSmellFinding(BaseModel):
    quote: str = ""
    category: str = "写作表达"
    reason: str = ""
    suggestion: str = ""
    suggested_rewrite: str = ""


class LlmAiSmellOutput(BaseModel):
    hits: list[LlmAiSmellFinding] = Field(default_factory=list)


class AiSmellHit(BaseModel):
    matched_text: str
    category: str
    reason: str
    suggestion: str
    suggested_rewrite: str
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
