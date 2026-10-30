"""Local AI smell vocabulary and regex scanner (Design Doc Section 7.4)."""

from __future__ import annotations

import re

from app.builtin.ai_smell_words import BUILTIN_AI_SMELL_RULES
from app.schemas.writing import AiSmellHit, AiSmellScanResponse


def scan_ai_smell(
    text: str, extra_forbidden: list[str] | None = None
) -> AiSmellScanResponse:
    """Scan prose locally using built-in rules and style template forbidden expressions."""
    if not text.strip():
        return AiSmellScanResponse(total_hits=0, hits=[])

    hits: list[AiSmellHit] = []
    seen_spans: set[tuple[int, int]] = set()

    for rule in BUILTIN_AI_SMELL_RULES:
        pattern_str = rule["pattern"]
        if rule["is_regex"]:
            for m in re.finditer(pattern_str, text):
                span = (m.start(), m.end())
                if span not in seen_spans:
                    seen_spans.add(span)
                    hits.append(
                        AiSmellHit(
                            pattern=pattern_str,
                            matched_text=m.group(0),
                            category=rule["category"],
                            suggestion=rule["suggestion"],
                            start_index=m.start(),
                            end_index=m.end(),
                        )
                    )
        else:
            start = 0
            while True:
                idx = text.find(pattern_str, start)
                if idx == -1:
                    break
                end = idx + len(pattern_str)
                span = (idx, end)
                if span not in seen_spans:
                    seen_spans.add(span)
                    hits.append(
                        AiSmellHit(
                            pattern=pattern_str,
                            matched_text=pattern_str,
                            category=rule["category"],
                            suggestion=rule["suggestion"],
                            start_index=idx,
                            end_index=end,
                        )
                    )
                start = end

    for expr in extra_forbidden or []:
        cleaned = expr.strip()
        if not cleaned:
            continue
        start = 0
        while True:
            idx = text.find(cleaned, start)
            if idx == -1:
                break
            end = idx + len(cleaned)
            span = (idx, end)
            if span not in seen_spans:
                seen_spans.add(span)
                hits.append(
                    AiSmellHit(
                        pattern=cleaned,
                        matched_text=cleaned,
                        category="风格禁用词",
                        suggestion=f"避免使用禁用表达「{cleaned}」，改为具体动作或感官细节",
                        start_index=idx,
                        end_index=end,
                    )
                )
            start = end

    hits.sort(key=lambda h: h.start_index)
    return AiSmellScanResponse(total_hits=len(hits), hits=hits)
