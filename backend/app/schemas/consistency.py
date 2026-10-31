"""Pydantic schemas for the checklist-based Consistency Review (Phase 3)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ConsistencyCheckType = Literal["constraint", "fact", "character"]
ConsistencyVerdict = Literal["violation", "suspicious"]


class ConsistencyIssue(BaseModel):
    """One non-passing checklist item found by the reviewer."""

    check_type: ConsistencyCheckType
    ref_id: int | None = None
    ref_label: str = ""
    verdict: ConsistencyVerdict
    evidence_quote: str = ""
    description: str = ""
    suggestion: str = ""


class LlmConsistencyOutput(BaseModel):
    issues: list[ConsistencyIssue] = Field(default_factory=list)


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


class ConsistencyReviewSummary(BaseModel):
    id: int
    chapter_id: int
    summary: str
    issue_count: int
    violation_count: int
    created_at: str
