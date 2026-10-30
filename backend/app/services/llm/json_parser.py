"""Multi-stage JSON parsing and repair pipeline (Dev Doc Section 4.5.2)."""

from __future__ import annotations

import json
import re
from typing import Any, Awaitable, Callable, TypeVar
from pydantic import BaseModel, ValidationError

from app.core.exceptions import AppError

T = TypeVar("T", bound=BaseModel)

_CODE_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")


def extract_json_candidate(raw_text: str) -> str:
    """Extract JSON substring from markdown code block or outermost braces/brackets."""
    trimmed = raw_text.strip()
    match = _CODE_BLOCK_RE.search(trimmed)
    if match:
        return match.group(1).strip()

    first_brace = trimmed.find("{")
    first_bracket = trimmed.find("[")
    starts = [i for i in (first_brace, first_bracket) if i != -1]
    if not starts:
        return trimmed
    start_idx = min(starts)
    end_char = "}" if trimmed[start_idx] == "{" else "]"
    end_idx = trimmed.rfind(end_char)
    if end_idx > start_idx:
        return trimmed[start_idx : end_idx + 1]
    return trimmed


def loose_repair_json_str(candidate: str) -> str:
    """Apply lightweight syntax repairs (trailing commas, BOM, smart quotes outside strings)."""
    cleaned = candidate.lstrip("\ufeff").strip()
    cleaned = _TRAILING_COMMA_RE.sub(r"\1", cleaned)
    return cleaned


def try_parse_json(raw_text: str) -> Any:
    """Stage 1~3 synchronous JSON parse: direct -> code block -> loose repair."""
    # Stage 1: direct
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass

    # Stage 2: extract markdown code block or outermost JSON
    candidate = extract_json_candidate(raw_text)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # Stage 3: loose syntax repair
    repaired = loose_repair_json_str(candidate)
    return json.loads(repaired)


async def parse_and_validate_json(
    raw_text: str,
    schema_cls: type[T],
    repair_fn: Callable[[str, str], Awaitable[str]] | None = None,
    max_retries: int = 2,
) -> T:
    """
    Full fallback pipeline:
    1. Direct json.loads
    2. Extract Markdown block
    3. Loose syntax repair
    4. Cheap model repair (up to max_retries)
    5. Raise AppError with raw output preserved
    """
    current_text = raw_text
    last_error = ""

    for attempt in range(max_retries + 1):
        try:
            parsed = try_parse_json(current_text)
            return schema_cls.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = str(exc)
            if repair_fn is None or attempt >= max_retries:
                break
            current_text = await repair_fn(current_text, last_error)

    raise AppError(
        code="LLM_JSON_PARSE_FAILED",
        message="模型返回格式解析失败，请重试或手动修改",
        detail={"error": last_error, "raw_output": raw_text},
        status_code=422,
    )
