"""T14: per-issue tolerant parsing for the consistency-review LLM output.

The model occasionally emits one malformed issue (e.g. ``ref_label: null``) among
otherwise valid findings. Validating the whole payload at once turns that single
field into a 422 and loses the entire review. Here the outer JSON is parsed
leniently and each element of ``issues`` is validated on its own: valid issues are
kept, invalid ones are dropped with a reason, and the batch never fails because of
one bad item.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import ValidationError

from app.schemas.consistency import ConsistencyIssue
from app.services.llm.json_parser import try_parse_json


@dataclass
class ConsistencyParseResult:
    issues: list[ConsistencyIssue] = field(default_factory=list)
    raw_items: int = 0
    dropped_invalid: int = 0
    drop_log: list[str] = field(default_factory=list)


def _brief_error(exc: ValidationError) -> str:
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(part) for part in first.get("loc", ()))
    msg = str(first.get("msg", "invalid"))
    return f"{loc}: {msg}" if loc else msg


def parse_consistency_issues(raw_text: str) -> ConsistencyParseResult:
    """Parse ``{"issues": [...]}`` keeping every individually valid issue.

    Raises ``ValueError`` only when the outer JSON/structure itself is unusable
    (the caller may retry once). One invalid issue is never fatal.
    """
    try:
        parsed = try_parse_json(raw_text)
    except Exception as exc:  # noqa: BLE001 - normalized for the caller
        raise ValueError(f"outer JSON parse failed: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("consistency root is not a JSON object")
    raw_issues = parsed.get("issues", [])
    if raw_issues is None:
        raw_issues = []
    if not isinstance(raw_issues, list):
        raise ValueError("consistency 'issues' is not a JSON array")

    result = ConsistencyParseResult(raw_items=len(raw_issues))
    for index, item in enumerate(raw_issues):
        if not isinstance(item, dict):
            result.dropped_invalid += 1
            result.drop_log.append(f"issues[{index}]: not an object")
            continue
        try:
            result.issues.append(ConsistencyIssue.model_validate(item))
        except ValidationError as exc:
            result.dropped_invalid += 1
            result.drop_log.append(f"issues[{index}]: {_brief_error(exc)}")
    return result
