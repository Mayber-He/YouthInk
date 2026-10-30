"""Pydantic schemas for novel management and project initiation."""

from __future__ import annotations

from pydantic import BaseModel, Field


class NovelCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=128)
    genre: str = "校园"
    tone: str = "清新治愈"
    pov: str = "第三人称限知"
    protagonist_concept: str = ""
    synopsis: str = ""
    target_words: int = Field(default=1000000, ge=1000, le=20000000)
    estimated_chapters: int = Field(default=400, ge=1, le=5000)
    words_per_chapter: int = Field(default=2500, ge=200, le=20000)
    romance_ending: str = "HE"
    growth_ending: str = "HE"
    ending_note: str = ""
    style_note: str = ""
    style_template_id: int | None = None


class NovelUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=128)
    genre: str | None = None
    tone: str | None = None
    pov: str | None = None
    protagonist_concept: str | None = None
    synopsis: str | None = None
    target_words: int | None = Field(default=None, ge=1000, le=20000000)
    estimated_chapters: int | None = Field(default=None, ge=1, le=5000)
    words_per_chapter: int | None = Field(default=None, ge=200, le=20000)
    romance_ending: str | None = None
    growth_ending: str | None = None
    ending_note: str | None = None
    style_note: str | None = None
    style_template_id: int | None = None


class NovelDetail(BaseModel):
    novel_uid: str
    id: int
    title: str
    genre: str | None = None
    tone: str | None = None
    pov: str | None = None
    protagonist_concept: str | None = None
    synopsis: str | None = None
    target_words: int
    estimated_chapters: int | None = None
    words_per_chapter: int
    romance_ending: str | None = None
    growth_ending: str | None = None
    ending_note: str | None = None
    style_note: str | None = None
    style_template_id: int | None = None
    total_chapters: int = 0
    finalized_chapters: int = 0
    current_words: int = 0
    pending_confirm_count: int = 0
    created_at: str
    updated_at: str


class BackupInfo(BaseModel):
    filename: str
    size_bytes: int
    created_at: str
