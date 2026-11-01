"""T5: orchestrate repetition check -> one rewrite -> re-check -> persist.

The decision logic is a pure async function taking injected callbacks, so it is tested with
mocks and never touches a real model. ``WritingService.check_scene_repetition`` wires it to the
real non-streaming model call and the DB.

Flow (never loops):
    1. analyze the new scene
    2. not triggered                       -> action "none"
    3. triggered and auto_rewrite disabled -> "kept_with_warning"
    4. triggered and auto_rewrite enabled  -> ask the model to rewrite THIS scene ONCE,
         listing the concrete repeated spans; re-analyze the rewrite
         - passes now                      -> "rewritten"   (final_text = rewrite)
         - still over threshold            -> "kept_with_warning" (final_text = the rewrite if
                                              it is no worse, otherwise the original)
         - rewrite call failed / empty     -> "rewrite_failed" (final_text = original)
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Awaitable, Callable

from app.services.repetition_guard import (
    RepetitionConfig,
    RepetitionReport,
    analyze_scene_repetition,
)

logger = logging.getLogger(__name__)

RewriteFn = Callable[[str, RepetitionReport], Awaitable[str]]
RecordFn = Callable[[str, str, RepetitionReport, dict], int]


def _severity(report: RepetitionReport) -> int:
    """Rough 'how bad' score used to avoid replacing text with a WORSE rewrite."""
    return (
        len(report.dialogues) * 3
        + len([s for s in report.spans if s.length >= 10]) * 2
        + len(report.action_hits)
        + len(report.forbidden_hits) * 3
        + len(report.time_hits) * 3
    )


def build_rewrite_instruction(report: RepetitionReport) -> str:
    return (
        "下面这一场景正文存在与前文重复的问题，请只重写这一个场景，保持原有剧情事件、人物关系与"
        "信息量不变，但换用全新的措辞、句式与细节来表达。必须避开以下具体重复项：\n"
        f"{report.describe_for_model()}\n"
        "要求：不要照抄上列任何原句；已在前文出现过的台词不要再说一遍，改为推进新的信息或用动作带过；"
        "最后一句用对话、动作或决定结束。只输出重写后的场景正文，不要解释。"
    )


async def run_repetition_pipeline(
    scene_text: str,
    *,
    previous_chapter: str,
    chapter_so_far: str,
    must_not_include: list[str],
    config: RepetitionConfig,
    rewrite_fn: RewriteFn,
    record_fn: RecordFn | None = None,
    auto_rewrite: bool | None = None,
    story_time_gap_days: int | None = None,
) -> dict:
    """Run the full flow. Returns a dict matching ``RepetitionCheckResponse``."""
    allow_rewrite = config.auto_rewrite if auto_rewrite is None else auto_rewrite
    thresholds = _thresholds(config)

    def _analyze(text: str) -> RepetitionReport:
        return analyze_scene_repetition(
            text,
            previous_chapter=previous_chapter,
            chapter_so_far=chapter_so_far,
            must_not_include=must_not_include,
            config=config,
            story_time_gap_days=story_time_gap_days,
        )

    def _record(stage: str, action: str, rep: RepetitionReport) -> int | None:
        if record_fn is None:
            return None
        try:
            return record_fn(stage, action, rep, thresholds)
        except Exception:  # logging must never break generation
            logger.exception("failed to persist repetition check")
            return None

    first = _analyze(scene_text)
    check_ids: list[int] = []
    # `triggered` in the result always describes the ORIGINAL text, whatever happens afterwards.
    orig = first.triggered

    if not first.triggered:
        cid = _record("initial", "none", first)
        return _result(first, "none", scene_text, [], [cid] if cid else [], orig)

    warnings = [f"重复检测命中：{r}" for r in first.reasons]

    if not allow_rewrite:
        cid = _record("initial", "kept_with_warning", first)
        return _result(first, "kept_with_warning", scene_text, warnings, [cid] if cid else [], orig)

    cid = _record("initial", "none", first)  # the pre-rewrite measurement itself
    if cid:
        check_ids.append(cid)

    try:
        rewritten = (await rewrite_fn(scene_text, first) or "").strip()
    except Exception as exc:
        logger.warning("scene rewrite failed: %s", exc)
        rewritten = ""

    if not rewritten:
        cid = _record("after_rewrite", "rewrite_failed", first)
        if cid:
            check_ids.append(cid)
        return _result(
            first, "rewrite_failed", scene_text,
            warnings + ["自动重写未成功，已保留原文，请手动处理。"], check_ids, orig,
        )

    second = _analyze(rewritten)
    if not second.triggered:
        cid = _record("after_rewrite", "rewritten", second)
        if cid:
            check_ids.append(cid)
        return _result(second, "rewritten", rewritten, [], check_ids, orig, list(first.reasons))

    # Still over threshold after the single allowed rewrite: keep, warn, do NOT retry.
    keep = rewritten if _severity(second) <= _severity(first) else scene_text
    final_report = second if keep is rewritten else first
    cid = _record("after_rewrite", "kept_with_warning", second)
    if cid:
        check_ids.append(cid)
    logger.warning(
        "scene still repetitive after one rewrite; keeping result (reasons=%s)", second.reasons
    )
    return _result(
        final_report, "kept_with_warning", keep,
        warnings + [f"重写一次后仍超阈值：{r}" for r in second.reasons],
        check_ids, orig,
    )


def _thresholds(cfg: RepetitionConfig) -> dict:
    d = asdict(cfg)
    d["action_phrases"] = list(cfg.action_phrases)
    return d


def _result(
    report: RepetitionReport,
    action: str,
    final_text: str,
    warnings: list[str],
    check_ids: list[int],
    original_triggered: bool,
    original_reasons: list[str] | None = None,
) -> dict:
    return {
        "triggered": original_triggered,
        "action": action,
        "final_text": final_text,
        # `reasons` explains what was wrong with the text the user originally got, even when a
        # rewrite has since fixed it; the rewrite's verdict is carried by `action`.
        "reasons": list(original_reasons if original_reasons is not None else report.reasons),
        "warnings": warnings,
        "report": json.loads(json.dumps(report.to_dict(), ensure_ascii=False)),
        "check_ids": check_ids,
    }
