"""Deterministic injection limits; semantic synonym filtering stays in the prompt."""

from collections.abc import Mapping, Sequence
import re
from typing import Any

from app.services.memory.extraction_parse import normalize_for_quote_match


def select_memory_rows(
    rows: Sequence[Mapping[str, Any]], summaries: Sequence[str], field: str, limit: int,
) -> list[Mapping[str, Any]]:
    """Preserve query priority; compare only complete summaries or clauses.

    Substrings can change meaning through negation or a different subject, so
    partial overlaps and paraphrases are retained rather than treated as duplicates.
    """
    summary_texts = {
        normalize_for_quote_match(part).strip(".!?;:")
        for text in summaries
        for part in [text, *re.split(r"[。！？；.!?;\n]+", text)]
    }
    selected = []
    seen: set[str] = set()
    for row in rows:
        key = normalize_for_quote_match(str(row[field]))
        if not key or key in seen or key.strip(".!?;:") in summary_texts:
            continue
        seen.add(key)
        selected.append(row)
        if len(selected) == limit:
            break
    return selected
