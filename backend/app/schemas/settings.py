"""Pydantic schemas for global configuration, LLM profiles, prompts, and styles."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

from app.schemas.style_profile import StyleProfile

TaskCategory = Literal["writing", "planning", "extract"]


class LlmProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    base_url: str = Field(..., min_length=4, max_length=512)
    model: str = Field(..., min_length=1, max_length=128)
    api_key: str = Field(..., min_length=1, max_length=512)
    is_default: bool = False


class LlmProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    base_url: str | None = Field(default=None, min_length=4, max_length=512)
    model: str | None = Field(default=None, min_length=1, max_length=128)
    api_key: str | None = Field(default=None, max_length=512)
    is_default: bool | None = None


class LlmProfileResponse(BaseModel):
    id: int
    name: str
    base_url: str
    model: str
    api_key_masked: str
    is_default: bool
    created_at: str


class LlmConnectionTestRequest(BaseModel):
    profile_id: int | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    prompt: str = "请用一句话描绘一个夏日午后的高中教室。"


class LlmConnectionTestResponse(BaseModel):
    ok: bool
    model: str
    reply: str
    elapsed_ms: int
    input_tokens: int
    output_tokens: int


class TaskAssignmentUpdate(BaseModel):
    writing: int | None = None
    planning: int | None = None
    extract: int | None = None


class TaskAssignmentResponse(BaseModel):
    writing: int | None = None
    planning: int | None = None
    extract: int | None = None


class PromptTemplateItem(BaseModel):
    task_type: str
    description: str
    content: str
    version: str
    is_overridden: bool
    updated_at: str | None = None


class PromptTemplateUpdate(BaseModel):
    content: str = Field(..., min_length=1)
    version: str = "custom-1.0"


class StyleTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    pov: str = "第三人称限知"
    tense_feel: str = "当下进行感"
    tone: str = "清新治愈"
    sentence_pref: str = "长短交错"
    dialogue_ratio: str = "适中"
    desc_focus: str = "环境氛围、动作细节"
    pacing: str = "慢热细腻"
    example_paras: list[str] = Field(default_factory=list)
    forbidden_exprs: list[str] = Field(default_factory=list)
    style_profile: StyleProfile | None = None


class StyleTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    pov: str | None = None
    tense_feel: str | None = None
    tone: str | None = None
    sentence_pref: str | None = None
    dialogue_ratio: str | None = None
    desc_focus: str | None = None
    pacing: str | None = None
    example_paras: list[str] | None = None
    forbidden_exprs: list[str] | None = None
    style_profile: StyleProfile | None = None


class StyleTemplateResponse(StyleTemplateCreate):
    id: int
    is_builtin: bool
    created_at: str
    updated_at: str


class TrustModeSettings(BaseModel):
    enabled: bool = True
    auto_confirm_facts: bool = True
    auto_confirm_foreshadow_hint: bool = True
    auto_confirm_char_state: bool = False
    auto_confirm_relationship: bool = False
    auto_confirm_cognitive: bool = False
    auto_confirm_foreshadow_plant_recover: bool = False


class EmbeddingModelStatus(BaseModel):
    model_id: str
    ready: bool
    status: Literal["not_downloaded", "downloading", "ready", "error"]
    progress: float = 0.0
    download_source: Literal["modelscope", "hf_mirror", "huggingface"] = "modelscope"
    local_path: str
    message: str = ""
