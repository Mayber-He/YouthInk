"""T23: false positives and wording fixes driven by the third live evaluation.

Samples are the v5 chapter 2 appearance card/prose and scene 3 beat (`live_eval_export3.md`).
No live LLM: all checks are pure functions on fixed text.
"""

from __future__ import annotations

from pathlib import Path

from app.services.repetition_guard import (
    RepetitionConfig,
    RepetitionReport,
    analyze_scene_repetition,
    extract_appearance_tags,
    extract_required_quotes,
)
from app.services.repetition_service import build_rewrite_instruction, build_time_hint

FIX = Path(__file__).parent / "fixtures"
APPEARANCE = (FIX / "t19_appearance_pei.txt").read_text(encoding="utf-8").strip()
V5_BEAT = (FIX / "t23_scene3_beat.txt").read_text(encoding="utf-8").strip()
V5_PREVIOUS = (FIX / "t23_previous_chapter.txt").read_text(encoding="utf-8").strip()
REQUIRED_LINE = "那你把你之前拍的也发我看看呗。"


# --------------------------------------------------------------- appearance tags

def test_generic_body_words_are_not_appearance_tags() -> None:
    tags = extract_appearance_tags(APPEARANCE)
    assert "眉心" in tags
    assert "站姿笔直" in tags
    for generic in ("个子", "高个子", "个子偏高", "头发", "眼睛", "脸", "声音"):
        assert generic not in tags


def test_short_appearance_keep_is_configurable(monkeypatch) -> None:
    # A 2-character tag outside the built-in list is dropped...
    assert extract_appearance_tags("颈侧") == []

    # ...but can be added via env without a code change; defaults stay in place.
    monkeypatch.setenv("YOUTHINK_REPEAT_APPEARANCE_SHORT_KEEP", "颈侧、唇角")
    cfg = RepetitionConfig.from_env()
    assert "颈侧" in cfg.appearance_short_keep
    assert "眉心" in cfg.appearance_short_keep

    tags = extract_appearance_tags("颈侧", short_keep=cfg.appearance_short_keep)
    assert "颈侧" in tags
    report = analyze_scene_repetition(
        "颈侧有一道浅疤。她偏过头，颈侧又露出来。颈侧那道疤很淡。",
        previous_chapter="",
        chapter_so_far="",
        config=cfg,
        appearances=["颈侧"],
    )
    assert any(hit.phrase == "颈侧" for hit in report.appearance_hits)


def test_gao_gezi_in_v5_prose_is_not_flagged_but_meixin_still_is() -> None:
    scene = (
        "高个子那个用胳膊肘捅了捅他。另一个高个子抬了抬下巴，"
        "队伍里那个高个子笑了。她眉心那道淡褶收紧半毫，停了一下，眉心又松开，"
        "最后眉心垂下去。"
    )
    report = analyze_scene_repetition(
        scene,
        previous_chapter="",
        chapter_so_far="",
        config=RepetitionConfig(),
        appearances=[APPEARANCE],
    )
    phrases = {hit.phrase for hit in report.appearance_hits}
    assert "眉心" in phrases
    assert "个子" not in phrases and "高个子" not in phrases
    assert not any("个子" in reason for reason in report.reasons)
    assert any("眉心" in reason for reason in report.reasons)


# --------------------------------------------------------------- required quotes

def test_nickname_in_corner_brackets_is_not_a_required_quote() -> None:
    quotes = extract_required_quotes(V5_BEAT, V5_PREVIOUS)
    assert quotes == [REQUIRED_LINE]
    assert "吃一口软糖" not in quotes


def test_short_unpunctuated_quote_is_not_extracted() -> None:
    beat = (
        "必须发生：「吃一口软糖」说“好”；"
        "她说“我们改天再说吧。”；她说“那你九月一号路上小心”"
    )
    previous = "「吃一口软糖」说“好”。\n她说：“我们改天再说吧。”\n她说：“那你九月一号路上小心。”"
    quotes = extract_required_quotes(beat, previous)
    assert quotes == ["我们改天再说吧。", "那你九月一号路上小心"]


def test_required_quote_is_exempt_only_through_double_quotes() -> None:
    report = analyze_scene_repetition(
        f"他想起那句话。\n她说：“{REQUIRED_LINE}”",
        previous_chapter=V5_PREVIOUS,
        chapter_so_far="",
        config=RepetitionConfig(),
        beat=V5_BEAT,
    )
    assert report.required_quotes == [REQUIRED_LINE]
    assert "吃一口软糖" not in report.required_quotes


# --------------------------------------------------------------- time rewrite prompt

def test_time_hits_narrow_the_keep_original_rule() -> None:
    report = RepetitionReport(time_hits=["昨天", "前天"], story_time_gap_days=7)
    report.reasons.append("与上一章相隔 7 天，疑似相对时间错位：昨天、前天")
    hint = build_time_hint("八月二十五日", "九月一日", 7)
    prompt = build_rewrite_instruction(report, time_hint=hint)

    assert "只替换被标出的时间词" in prompt
    assert "其余时间表述" in prompt and "必须原样保留" in prompt
    assert "上周/前几天/那天晚上" in prompt
    assert "不要写具体公历日期" in prompt
    # The old unconditional "keep time wording" sentence would contradict the replacement.
    assert "尤其是时间表述" not in prompt
    assert "优先使用具体日期" not in hint
    assert "改用具体日期" not in report.describe_for_model()


def test_no_time_hits_keeps_the_original_time_protection() -> None:
    prompt = build_rewrite_instruction(RepetitionReport())
    assert "时间表述" in prompt and "必须原样保留" in prompt
    assert "只替换被标出的时间词" not in prompt
    assert "那天晚上" in prompt


def test_time_hint_prefers_relative_words_not_calendar_dates() -> None:
    hint = build_time_hint("八月二十五日", "九月一日", 7)
    assert "具体日期" not in hint
    assert "除被标出的时间词外" in hint
    # When a relative word matches the gap, it is offered instead of a calendar date.
    two_days = build_time_hint("8月30日", "9月1日", 2)
    assert "可优先使用这类相对说法" in two_days
    assert "不要写具体公历日期" in two_days
