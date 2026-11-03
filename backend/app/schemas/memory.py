"""Pydantic schemas for M4 Memory Loop, Pending Queue, Foreshadowing, Summaries, and RAG."""

from __future__ import annotations

from typing import Literal
from pydantic import AliasChoices, BaseModel, Field

MemoryItemCategory = Literal[
    "fact", "char_state", "cognitive", "relationship", "foreshadowing",
    "constraint_check",
]
# 可逐条停用的记忆类型。约束检查是对正文的判断，不提供停用。
DisableableMemoryCategory = Literal[
    "fact", "char_state", "cognitive", "relationship", "foreshadowing",
]
ConfirmStatus = Literal["pending", "confirmed", "locked", "discarded"]
ForeshadowStatus = Literal["planted", "hinted", "recovered", "abandoned"]
SummaryLevel = Literal["chapter", "arc", "volume", "novel"]


class PendingQueueItem(BaseModel):
    item_type: MemoryItemCategory
    id: int
    chapter_id: int | None = None
    chapter_title: str = ""
    chapter_display_index: int | None = None
    summary_text: str
    source_quote: str = ""
    status: str
    is_disabled: bool = False
    raw_payload: dict[str, object]
    created_at: str


class PendingItemUpdateRequest(BaseModel):
    action: Literal["confirm", "discard", "edit"]
    updated_text: str | None = None


class MemoryItemDisableRequest(BaseModel):
    is_disabled: bool


class ChapterMemoryItem(BaseModel):
    """一条记忆的展示信息，供作者在面板中查看、停用与恢复。"""

    item_type: DisableableMemoryCategory
    id: int
    chapter_id: int | None = None
    chapter_title: str = ""
    chapter_display_index: int | None = None
    story_time: str = ""
    content: str
    source_quote: str = ""
    status: str
    is_disabled: bool = False
    is_effective: bool = False
    conflict: bool = False
    conflict_reason: str = ""
    meta: dict[str, object] = Field(default_factory=dict)
    created_at: str = ""


class BatchQueueActionRequest(BaseModel):
    action: Literal["confirm", "discard"] = "confirm"
    items: list[dict[str, object]] = Field(
        ..., description="List of {'item_type': str, 'id': int}"
    )


class ForeshadowCreate(BaseModel):
    description: str = Field(..., min_length=1)
    planted_chapter_id: int | None = None
    plan_recover_start: int | None = None
    plan_recover_end: int | None = None
    status: ForeshadowStatus = "planted"
    source_quote: str = ""
    confirm_status: Literal["pending", "confirmed", "discarded"] = "confirmed"


class ForeshadowUpdate(BaseModel):
    description: str | None = None
    plan_recover_start: int | None = None
    plan_recover_end: int | None = None
    status: ForeshadowStatus | None = None
    confirm_status: Literal["pending", "confirmed", "discarded"] | None = None


class ForeshadowResponse(BaseModel):
    id: int
    description: str
    planted_chapter_id: int | None = None
    planted_chapter_title: str = ""
    plan_recover_start: int | None = None
    plan_recover_end: int | None = None
    status: ForeshadowStatus
    related_chapter_ids: list[int]
    source_quote: str
    confirm_status: str
    created_at: str
    updated_at: str


class SummaryResponse(BaseModel):
    id: int
    level: SummaryLevel
    ref_id: int
    content: str
    is_stale: bool
    updated_at: str


class RagChunkHit(BaseModel):
    chunk_id: str
    chapter_id: int
    chapter_sort_order: float
    scene_id: int | None = None
    text: str
    rrf_score: float
    source: str  # "vector" | "fts" | "hybrid"


class RagSearchResponse(BaseModel):
    query: str
    embedding_model_mismatch: bool = False
    embedding_model_id: str = ""
    embedding_dimension: int = 0
    # Set when the ONNX encoder cannot be used. FTS hits are still returned.
    embedding_error: str | None = None
    # Set when finalization/rebuild could not publish vectors for some chapters.
    vector_index_pending_rebuild: bool = False
    vector_index_error: str | None = None
    hits: list[RagChunkHit]


class FinalizeChapterResponse(BaseModel):
    chapter_id: int
    status: str
    backup_filename: str
    chunks_indexed: int
    chapter_summary: str
    auto_confirmed_count: int
    pending_count: int
    # 记忆抽取结果：'ok' 全部成功 | 'partial' 部分条目被丢弃 | 'failed' 整批失败走兜底。
    # 前端据此显示“本章记忆抽取失败/部分失败”标记。
    extraction_status: str = "ok"
    # 向量索引是旁路：编码/写入失败时章节仍定稿，这里标记 'pending_rebuild'。
    vector_index_status: str = "ok"
    vector_index_error: str | None = None


# --- LLM Memory Extraction Structured Output Schemas ---

class LlmExtractedFact(BaseModel):
    content: str
    fact_type: str = "event"
    character_names: list[str] = Field(default_factory=list)
    location_names: list[str] = Field(default_factory=list)
    source_quote: str = ""


class LlmExtractedStateChange(BaseModel):
    character_name: str
    field: Literal[
        "location", "body", "emotion", "goal", "identity", "item", "appearance"
    ] = "emotion"
    value: str
    source_quote: str = ""


class LlmExtractedCognitive(BaseModel):
    secret: str
    knower_names: list[str] = Field(default_factory=list)
    learned_by: str = ""
    source_quote: str = ""


class LlmExtractedRelationship(BaseModel):
    char_a_name: str
    char_b_name: str
    rel_type: str
    intimacy: int = 5
    publicity: Literal["public", "mutual", "one_sided"] = "mutual"
    change_reason: str = ""
    source_quote: str = ""


class LlmExtractedForeshadow(BaseModel):
    description: str
    status: Literal["planted", "hinted", "recovered"] = "planted"
    plan_recover_start: int | None = None
    plan_recover_end: int | None = None
    source_quote: str = ""


class LlmConstraintCheck(BaseModel):
    """LLM verdict on one active constraint against the finalized chapter text."""

    constraint_id: int
    verdict: Literal["violated", "resolved"]
    evidence_quote: str = Field(default="", validation_alias=AliasChoices("evidence_quote", "source_quote"))
    description: str = ""


class LlmMemoryExtractionOutput(BaseModel):
    facts: list[LlmExtractedFact] = Field(default_factory=list)
    state_changes: list[LlmExtractedStateChange] = Field(default_factory=list)
    cognitive_records: list[LlmExtractedCognitive] = Field(default_factory=list)
    relationship_changes: list[LlmExtractedRelationship] = Field(default_factory=list)
    foreshadowing: list[LlmExtractedForeshadow] = Field(default_factory=list)
    constraint_checks: list[LlmConstraintCheck] = Field(default_factory=list)
