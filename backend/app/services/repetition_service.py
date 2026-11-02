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
    TIME_WORD_DAYS,
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
        + len(report.recall_misses) * 3
        + len(report.seam_spans) * 2
        + len(report.appearance_hits) * 2
    )


def build_time_hint(
    previous_time: str, current_time: str, gap_days: int | None
) -> str:
    """T13: concrete time anchor for the rewrite prompt; never guesses a missing date."""
    previous = (previous_time or "").strip() or "未指定"
    current = (current_time or "").strip() or "未指定"
    lines = [
        "【时间锚点】",
        f"上一章发生时间：{previous}",
        f"本章发生时间：{current}",
        f"相隔天数：{gap_days} 天" if gap_days is not None else "相隔天数：无法确定",
    ]
    if gap_days is None:
        lines.append("时间无法确定：不得猜补日期；正文原有的时间表述一律原样保留。")
    else:
        allowed = [w for w, days in TIME_WORD_DAYS.items() if days == gap_days]
        banned = [w for w, days in TIME_WORD_DAYS.items() if days != gap_days]
        if banned:
            lines.append(
                "禁止使用与实际相隔天数不符的相对时间词："
                + "/".join(banned)
                + ("。" if gap_days <= 1 else f"（相隔 {gap_days} 天时，这些词指称的时间不对）。")
            )
        if allowed:
            lines.append(
                "其中“" + "/".join(allowed) + "”与相隔天数一致，但仍应优先使用具体日期或准确间隔。"
            )
        lines.append(
            "正文原有的时间表述（如“那天晚上”）必须原样保留，不得替换成“前一晚/前晚/昨天/前天”等相对词。"
        )
    return "\n".join(lines)


def _norm_text(text: str) -> str:
    return "".join(c.lower() for c in (text or "") if c.isalnum())


def build_rewrite_instruction(report: RepetitionReport, *, time_hint: str = "") -> str:
    """T13/T17: conservative rewrite — only the flagged spans change, everything else is kept."""
    parts = [
        "下面这一场景正文存在与前文重复的问题。请做最小改动：只改写下列被标出的重复片段，"
        "其余字词、语序、人物动作和剧情必须原样保留；不得新增、删除或调换任何情节。",
        "尤其是时间表述（如“那天晚上”“上周”“隔了几天”等）必须原样保留，不得改成"
        "“前一晚/前晚/昨天/前天”等其他说法。",
    ]
    if report.required_quotes:
        parts.append(
            "【节拍要求的逐字呼应】\n"
            "以下句子是节拍要求的逐字呼应，必须原样保留，不得改写、删除或替换：\n"
            + "\n".join(f"- 「{q}」" for q in report.required_quotes)
        )
    if time_hint:
        parts.append(time_hint)
    described = report.describe_for_model().strip()
    if described:
        parts.append("需要改写的具体重复项：\n" + described)

    # T17: give the model a closed list it may quote from when recalling the previous chapter.
    # Lines already flagged as repeated are NOT offered as citable (except beat-required ones).
    blocked = {_norm_text(d.text) for d in report.dialogues}
    required_norm = {_norm_text(q) for q in report.required_quotes}
    citable = [
        q for q in report.citable_quotes
        if _norm_text(q) not in blocked or _norm_text(q) in required_norm
    ]
    if citable:
        parts.append(
            "【上一章可引用的原句清单】\n"
            "回忆上一章内容时，只能逐字引用下列原句，不得把它们拼成新台词：\n"
            + "\n".join(f"- 「{q}」" for q in citable)
            + "\n不确定就概括，不得补写表情或台词。"
        )
    else:
        parts.append(
            "【上一章可引用的原句清单】\n"
            "上一章没有可逐字引用的原句。不确定就概括，不得补写表情或台词。"
        )

    tail = (
        "改写要求：只替换被标出的重复片段本身，同一句里未被标出的字词不得改动；"
        "不要照抄上列被标出的重复项；"
    )
    if report.required_quotes:
        tail += "但【节拍要求的逐字呼应】中的句子必须原样保留，不得改写或删除；"
    tail += (
        "已在前文出现过的台词不要再说一遍，改为推进新的信息或用动作带过；"
        "保留原文最后一句的收尾方式，不要另加结尾。只输出修改后的完整场景正文，不要解释。"
    )
    parts.append(tail)
    return "\n".join(parts)


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
    beat: str = "",
    appearances: list[str] | None = None,
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
            beat=beat,
            appearances=appearances,
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
