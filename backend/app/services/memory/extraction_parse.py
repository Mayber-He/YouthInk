"""Per-item tolerant parsing and quote validation for chapter memory extraction.

Pure functions (no DB / no LLM) so they are unit-testable with fixed samples.

The model frequently returns items whose field names drift from
``app.schemas.memory`` (e.g. ``{"entity","change"}`` instead of
``{"character_name","field","value"}``). Validating the whole payload at once
hides this: ``LlmMemoryExtractionOutput`` has defaults for every list, so an
all-wrong payload "parses" into mostly-empty items and a whole chapter of
memory is silently lost.

Strategy here:
1. Parse the outer JSON leniently into six category lists.
2. Validate EACH element on its own against its sub-schema. Keep the ones that
   pass, drop the ones that fail (recording why). One bad item never discards
   its neighbours.
3. Require ``source_quote`` (``evidence_quote`` for constraint checks) to appear
   verbatim in the chapter text (whitespace/punctuation normalized). Items whose
   quote cannot be located are dropped as likely hallucinations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from pydantic import BaseModel, ValidationError

from app.schemas.memory import (
    LlmConstraintCheck,
    LlmExtractedCognitive,
    LlmExtractedFact,
    LlmExtractedForeshadow,
    LlmExtractedRelationship,
    LlmExtractedStateChange,
    LlmMemoryExtractionOutput,
)
from app.services.llm.json_parser import try_parse_json

# Same punctuation folding as writing_boundary: the model rarely reproduces a
# quote byte-for-byte (smart quotes, full/half-width punctuation, stray spaces),
# but the substance is there. We only want to reject invented quotes.
_PUNCT_FOLD = {
    ord("“"): '"', ord("”"): '"', ord("‘"): "'", ord("’"): "'",
    ord("「"): '"', ord("」"): '"', ord("『"): '"', ord("』"): '"',
    ord("，"): ",", ord("。"): ".", ord("！"): "!", ord("？"): "?",
    ord("；"): ";", ord("："): ":", ord("、"): ",",
    ord("（"): "(", ord("）"): ")", ord("—"): "-", ord("…"): ".",
}


def normalize_for_quote_match(text: str) -> str:
    """Fold common punctuation variants and strip all whitespace for comparison."""
    folded = (text or "").translate(_PUNCT_FOLD)
    return re.sub(r"\s+", "", folded)


# category key -> (sub-schema, quote field name, require_verbatim_quote)
#
# Resolution evidence must match literally, not just after punctuation folding.
# Violation judgments retain the previous non-empty-evidence policy.
_CATEGORY_SPECS: list[tuple[str, type[BaseModel], str, bool]] = [
    ("facts", LlmExtractedFact, "source_quote", True),
    ("state_changes", LlmExtractedStateChange, "source_quote", True),
    ("cognitive_records", LlmExtractedCognitive, "source_quote", True),
    ("relationship_changes", LlmExtractedRelationship, "source_quote", True),
    ("foreshadowing", LlmExtractedForeshadow, "source_quote", True),
    ("constraint_checks", LlmConstraintCheck, "evidence_quote", False),
]


@dataclass
class ExtractionParseResult:
    """Outcome of tolerant per-item parsing."""

    output: LlmMemoryExtractionOutput
    kept: int = 0
    dropped_invalid: int = 0
    dropped_quote: int = 0
    raw_items: int = 0
    # Human-readable drop reasons (category + short message), for logging / retry.
    drop_log: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        """'ok' | 'partial' | 'failed' for the frontend badge."""
        if self.raw_items == 0:
            return "failed"
        if self.kept == 0:
            return "failed"
        if self.dropped_invalid or self.dropped_quote:
            return "partial"
        return "ok"


def _coerce_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def parse_extraction_items(
    raw_text: str, chapter_text: str
) -> ExtractionParseResult:
    """Parse model output into a validated ``LlmMemoryExtractionOutput``.

    Each list element is validated independently. Invalid items and items whose
    quote is not found verbatim in ``chapter_text`` are dropped (not fatal).

    Raises ``ValueError`` only when the outer JSON itself cannot be parsed at all
    — the caller treats that as a batch failure and may retry.
    """
    try:
        parsed = try_parse_json(raw_text)
    except Exception as exc:  # noqa: BLE001 - normalize to ValueError for caller
        raise ValueError(f"outer JSON parse failed: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("extraction root is not a JSON object")

    chapter_norm = normalize_for_quote_match(chapter_text)
    result = ExtractionParseResult(output=LlmMemoryExtractionOutput())

    for key, schema_cls, quote_field, require_verbatim in _CATEGORY_SPECS:
        validated: list[Any] = []
        for idx, item in enumerate(_coerce_list(parsed.get(key))):
            result.raw_items += 1
            if not isinstance(item, dict):
                result.dropped_invalid += 1
                result.drop_log.append(f"{key}[{idx}]: not an object")
                continue
            try:
                obj = schema_cls.model_validate(item)
            except ValidationError as exc:
                result.dropped_invalid += 1
                msgs = "; ".join(
                    f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                    for e in exc.errors()[:3]
                )
                result.drop_log.append(f"{key}[{idx}]: invalid ({msgs})")
                continue

            quote = str(getattr(obj, quote_field, "") or "")
            if not quote.strip():
                result.dropped_quote += 1
                result.drop_log.append(f"{key}[{idx}]: empty {quote_field}")
                continue
            if require_verbatim and normalize_for_quote_match(quote) not in chapter_norm:
                result.dropped_quote += 1
                result.drop_log.append(
                    f"{key}[{idx}]: {quote_field} not found verbatim in chapter"
                )
                continue

            if key == "constraint_checks" and obj.verdict == "resolved":
                if quote not in chapter_text:
                    result.dropped_quote += 1
                    result.drop_log.append(f"{key}[{idx}]: resolution quote not literally in chapter")
                    continue
                if (re.search(r"未涉及|未违反|没有违反|不涉及", obj.description)
                        and not re.search(r"正式解除|已解除|已正式解除|已撤销|已废止", obj.description)):
                    result.dropped_invalid += 1
                    result.drop_log.append(f"{key}[{idx}]: non-involvement is not resolution")
                    continue

            validated.append(obj)
            result.kept += 1

        setattr(result.output, key, validated)

    return result
