"""Pydantic schemas for the Explicit Constraint System (anti-hallucination hard constraints)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ConstraintTargetType = Literal["character", "location", "worldview", "chapter", "novel"]
ConstraintSeverity = Literal["hard", "soft"]
ConstraintStatus = Literal["active", "resolved", "violated"]


class ConstraintCreate(BaseModel):
    target_type: ConstraintTargetType
    target_id: int | None = None
    content: str = Field(..., min_length=1, max_length=2000)
    severity: ConstraintSeverity = "hard"
    valid_from_chapter_id: int | None = None
    valid_until_chapter_id: int | None = None
    source_quote: str = ""
    locked: bool = False


class ConstraintUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=2000)
    severity: ConstraintSeverity | None = None
    status: ConstraintStatus | None = None
    valid_from_chapter_id: int | None = None
    valid_until_chapter_id: int | None = None
    source_quote: str | None = None
    locked: bool | None = None


class ConstraintResponse(ConstraintCreate):
    id: int
    status: ConstraintStatus = "active"
    target_name: str = ""
    created_at: str
    updated_at: str
