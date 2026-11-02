"""T3: scene = event checklist. Pure helpers (no LLM/DB) for format + dedup.

Scenes are planned as an *event checklist* (goal / entry_state / must_happen /
exit_state / must_not_include / target_words) rather than prose beats. To stay
schema-compatible we serialize the checklist into the existing ``scenes.beat``
text column — no DB migration. Downstream (assembler, writing_boundary, write
prompts) keep reading ``beat`` unchanged.

This module also provides deterministic adjacent-scene checks using character
n-gram overlap (Jaccard over 3-grams): duplicated ``must_happen`` items, an
``exit_state`` that already contains the next scene's triggering event (T18), and
an ``exit_state`` too similar to the next scene's ``entry_state``. The caller can
ask the model to re-split once when any of these fire.
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
    narration_alias: str = "",
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
    if narration_alias.strip():
        lines.append(f"叙述称呼：{narration_alias.strip()}")
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


@dataclass
class BoundaryIssue:
    index_a: int  # 0-based scene index
    index_b: int  # index_a + 1
    kind: str     # "exit_contains_next_event" | "exit_entry_similar"
    text_a: str   # exit_state of scene A
    text_b: str   # next must_happen item, or entry_state of scene B
    similarity: float


def _norm_boundary(text: str) -> str:
    return re.sub(r"[^\w]", "", (text or "").lower())


def find_adjacent_boundary_issues(
    entry_states: list[str],
    exit_states: list[str],
    must_happen_per_scene: list[list[str]],
    threshold: float = 0.6,
) -> list[BoundaryIssue]:
    """T18: scene A's exit must stop BEFORE scene B's trigger and entry state.

    Two deterministic failures:
    (1) A's ``exit_state`` contains (or closely paraphrases) an item in B's
        ``must_happen`` — the model already wrote B's trigger at the end of A.
    (2) A's ``exit_state`` and B's ``entry_state`` are near-identical — B starts by
        restating where A ended instead of moving on.
    """
    issues: list[BoundaryIssue] = []
    count = min(len(exit_states), max(0, len(entry_states) - 1), len(must_happen_per_scene) - 1)
    for i in range(max(0, count)):
        exit_a = (exit_states[i] or "").strip()
        entry_b = (entry_states[i + 1] or "").strip()
        if not exit_a:
            continue
        norm_exit = _norm_boundary(exit_a)
        for item in must_happen_per_scene[i + 1]:
            item = (item or "").strip()
            norm_item = _norm_boundary(item)
            if not norm_item:
                continue
            sim = ngram_similarity(exit_a, item)
            contained = len(norm_item) >= 4 and norm_item in norm_exit
            if contained or sim >= threshold:
                issues.append(
                    BoundaryIssue(i, i + 1, "exit_contains_next_event", exit_a, item, round(sim, 3))
                )
        if entry_b:
            sim = ngram_similarity(exit_a, entry_b)
            if sim >= threshold:
                issues.append(
                    BoundaryIssue(i, i + 1, "exit_entry_similar", exit_a, entry_b, round(sim, 3))
                )
    return issues


def describe_boundary_issues(issues: list[BoundaryIssue]) -> str:
    """Human-readable description fed back to the model for a re-split."""
    if not issues:
        return ""
    lines = [
        "以下相邻场景的终点状态越过场景边界，或与下一场景起点重复，请重新拆分："
    ]
    for issue in issues:
        if issue.kind == "exit_contains_next_event":
            lines.append(
                f"- 场景{issue.index_a + 1} 的终点状态「{issue.text_a}」提前包含了"
                f"场景{issue.index_b + 1} 的触发事件「{issue.text_b}」"
                f"（相似度 {issue.similarity}）；终点状态必须停在触发事件之前"
            )
        else:
            lines.append(
                f"- 场景{issue.index_a + 1} 的终点状态「{issue.text_a}」与"
                f"场景{issue.index_b + 1} 的起点状态「{issue.text_b}」过于相似"
                f"（相似度 {issue.similarity}）；下一场应从新的状态开始"
            )
    return "\n".join(lines)
