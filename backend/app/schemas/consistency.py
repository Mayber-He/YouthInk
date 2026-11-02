"""Pydantic schemas for the checklist-based Consistency Review (Phase 3)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

ConsistencyCheckType = Literal["constraint", "fact", "character", "common_sense", "continuity", "prose"]
ConsistencyVerdict = Literal["violation", "suspicious"]


class ConsistencyIssue(BaseModel):
    """One non-passing checklist item found by the reviewer."""

    check_type: ConsistencyCheckType
    ref_id: int | None = None
    ref_label: str = ""
    verdict: ConsistencyVerdict
    evidence_quote: str = ""
    historical_evidence: str = ""
    description: str = ""
    suggestion: str = ""
    suggested_rewrite: str = ""

    @field_validator("ref_id", mode="before")
    @classmethod
    def parse_ref_id(cls, v: Any) -> int | None:
        if v is None:
            return None
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            cleaned = v.replace("#", "").strip()
            if cleaned.isdigit():
                return int(cleaned)
        return None

    @field_validator(
        "ref_label", "evidence_quote", "historical_evidence",
        "description", "suggestion", "suggested_rewrite",
        mode="before",
    )
    @classmethod
    def none_to_empty(cls, v: Any) -> Any:
        """T14: models often emit null for optional text fields; keep the issue."""
        return "" if v is None else v


class LlmConsistencyOutput(BaseModel):
    issues: list[ConsistencyIssue] = Field(default_factory=list)


class ApplyReviewRequest(BaseModel):
    issue_index: int = Field(ge=0)
    expected_content: str


class ConsistencyReviewResponse(BaseModel):
    id: int
    chapter_id: int
    version_id: int | None
    summary: str
    issue_count: int
    violation_count: int
    issues: list[ConsistencyIssue]
    model: str = ""
    created_at: str
    is_stale: bool = False


class ConsistencyReviewSummary(BaseModel):
    id: int
    chapter_id: int
    summary: str
    issue_count: int
    violation_count: int
    created_at: str
    is_stale: bool = False
