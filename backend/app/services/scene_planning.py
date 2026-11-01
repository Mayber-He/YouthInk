"""T3: scene = event checklist. Pure helpers (no LLM/DB) for format + dedup.

Scenes are planned as an *event checklist* (goal / entry_state / must_happen /
exit_state / must_not_include / target_words) rather than prose beats. To stay
schema-compatible we serialize the checklist into the existing ``scenes.beat``
text column — no DB migration. Downstream (assembler, writing_boundary, write
prompts) keep reading ``beat`` unchanged.

This module also provides a deterministic adjacent-scene duplication check over
``must_happen`` using character n-gram overlap (Jaccard over 3-grams), so the
caller can ask the model to re-split once when two neighbours overlap too much.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


def _char_ngrams(text: str, n: int = 3) -> set[str]:
    cleaned = re.sub(r"\s+", "", text or "")
    if len(cleaned) < n:
        return {cleaned} if cleaned else set()
    return {cleaned[i : i + n] for i in range(len(cleaned) - n + 1)}


def ngram_similarity(a: str, b: str, n: int = 3) -> float:
    """Jaccard similarity of character n-gram sets. 0.0 (disjoint) .. 1.0 (equal)."""
    ga, gb = _char_ngrams(a, n), _char_ngrams(b, n)
    if not ga or not gb:
        return 0.0
    inter = len(ga & gb)
    union = len(ga | gb)
    return inter / union if union else 0.0


def format_scene_beat(
    goal: str,
    entry_state: str,
    must_happen: list[str],
    exit_state: str,
    must_not_include: list[str],
) -> str:
    """Serialize an event checklist into the text stored in ``scenes.beat``.

    Kept human-readable and stable so existing prompts that inline ``beat`` still
    make sense. Empty sections are omitted.
    """
    lines: list[str] = []
    if goal.strip():
        lines.append(f"目标：{goal.strip()}")
    if entry_state.strip():
        lines.append(f"起点状态：{entry_state.strip()}")
    mh = [m.strip() for m in must_happen if m.strip()][:3]
    if mh:
        lines.append("必须发生：" + "；".join(mh))
    if exit_state.strip():
        lines.append(f"终点状态：{exit_state.strip()}")
    mni = [m.strip() for m in must_not_include if m.strip()]
    if mni:
        lines.append("本场禁止出现：" + "；".join(mni))
    return "\n".join(lines)


@dataclass
class DuplicatePair:
    index_a: int  # 0-based scene index
    index_b: int
    item_a: str
    item_b: str
    similarity: float


def find_adjacent_duplicates(
    must_happen_per_scene: list[list[str]], threshold: float = 0.6
) -> list[DuplicatePair]:
    """Compare must_happen items of each scene against its immediate neighbour.

    Returns the pairs whose similarity >= threshold. Only adjacent scenes are
    compared (i vs i+1), matching the task spec ("相邻场景重复校验").
    """
    pairs: list[DuplicatePair] = []
    for i in range(len(must_happen_per_scene) - 1):
        cur = [m for m in must_happen_per_scene[i] if m.strip()]
        nxt = [m for m in must_happen_per_scene[i + 1] if m.strip()]
        for a in cur:
            for b in nxt:
                sim = ngram_similarity(a, b)
                if sim >= threshold:
                    pairs.append(DuplicatePair(i, i + 1, a, b, round(sim, 3)))
    return pairs


def describe_duplicates(pairs: list[DuplicatePair]) -> str:
    """Human-readable description fed back to the model for a re-split."""
    if not pairs:
        return ""
    lines = ["以下相邻场景的 must_happen 事件高度重复，请重新拆分使其互不重叠："]
    for p in pairs:
        lines.append(
            f"- 场景{p.index_a + 1} 的「{p.item_a}」与 场景{p.index_b + 1} 的「{p.item_b}」"
            f"（相似度 {p.similarity}）"
        )
    return "\n".join(lines)
