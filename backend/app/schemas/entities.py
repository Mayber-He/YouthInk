"""Pydantic schemas for Worldview, Characters, Locations, and Main Plot (M2)."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

WorldviewCategory = Literal["era", "city", "school", "rules", "culture", "term"]
CharacterRole = Literal["female_lead", "male_lead", "major", "minor", "extra"]


# --- Worldview ---

class WorldviewCreate(BaseModel):
    category: WorldviewCategory = "school"
    content: str = Field(..., min_length=1)
    locked: bool = False


class WorldviewUpdate(BaseModel):
    category: WorldviewCategory | None = None
    content: str | None = None
    locked: bool | None = None


class WorldviewResponse(BaseModel):
    id: int
    category: WorldviewCategory
    content: str
    locked: bool
    created_at: str
    updated_at: str


# --- Characters ---

class CharacterCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    aliases: list[str] = Field(default_factory=list)
    role: CharacterRole = "major"
    gender: str = ""
    initial_age: str = ""
    appearance: str = ""
    personality: str = ""
    speech_style: str = ""
    background: str = ""
    arc_design: str = ""
    locked: bool = False


class CharacterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    aliases: list[str] | None = None
    role: CharacterRole | None = None
    gender: str | None = None
    initial_age: str | None = None
    appearance: str | None = None
    personality: str | None = None
    speech_style: str | None = None
    background: str | None = None
    arc_design: str | None = None
    locked: bool | None = None


class CharacterResponse(CharacterCreate):
    id: int
    created_at: str
    updated_at: str


class CharacterTimelineSnapshot(BaseModel):
    character_id: int
    up_to_chapter_sort: float | None = None
    effective_appearance: str
    current_states: dict[str, str]
    # 每个状态字段的来源章节，供写作上下文标注（第N章·story_time）。
    state_sources: dict[str, dict[str, object]] = Field(default_factory=dict)
    relationships: list[dict[str, object]]
    known_secrets: list[dict[str, object]]
    character_memories: list[dict[str, object]] = Field(default_factory=list)


# --- Locations ---

class LocationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    aliases: list[str] = Field(default_factory=list)
    type: str = "校园场所"
    description: str = ""
    sensory_details: str = ""
    related_chars: list[int] = Field(default_factory=list)
    locked: bool = False


class LocationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    aliases: list[str] | None = None
    type: str | None = None
    description: str | None = None
    sensory_details: str | None = None
    related_chars: list[int] | None = None
    locked: bool | None = None


class LocationResponse(LocationCreate):
    id: int
    created_at: str
    updated_at: str


# --- Main Plot ---

class TurningPointItem(BaseModel):
    desc: str
    chapter_sort: float | int | None = None


class MainPlotUpdate(BaseModel):
    core_conflict: str | None = None
    romance_arc: str | None = None
    growth_arc: str | None = None
    key_turning_pts: list[TurningPointItem] | None = None
    locked: bool | None = None


class MainPlotResponse(BaseModel):
    id: int
    novel_id: int
    core_conflict: str
    romance_arc: str
    growth_arc: str
    key_turning_pts: list[TurningPointItem]
    locked: bool
    updated_at: str


# --- AI Generation & Rewrite Requests / LLM Output Schemas ---

class AiGenerateSettingRequest(BaseModel):
    instruction: str = ""
    count: int = Field(default=4, ge=1, le=12)


class AiRewriteItemRequest(BaseModel):
    instruction: str = Field(..., min_length=1, description="用户修改意见")


class LlmWorldviewItem(BaseModel):
    category: WorldviewCategory = "school"
    content: str


class LlmWorldviewBatchOutput(BaseModel):
    items: list[LlmWorldviewItem]


class LlmCharacterItem(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)
    role: CharacterRole = "major"
    gender: str = ""
    initial_age: str = ""
    appearance: str = ""
    personality: str = ""
    speech_style: str = ""
    background: str = ""
    arc_design: str = ""
    constraints: list[str] = Field(
        default_factory=list,
        description="从背景/身份反向推导的硬约束（绝不能写的内容），如身份隐含的无知领域",
    )


class LlmCharacterBatchOutput(BaseModel):
    characters: list[LlmCharacterItem]


class LlmLocationItem(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)
    type: str = "校园场所"
    description: str = ""
    sensory_details: str = ""


class LlmLocationBatchOutput(BaseModel):
    locations: list[LlmLocationItem]


class LlmMainPlotOutput(BaseModel):
    core_conflict: str
    romance_arc: str
    growth_arc: str
    key_turning_pts: list[TurningPointItem] = Field(default_factory=list)
