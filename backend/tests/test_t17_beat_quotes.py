"""T17: beat-required quote exemption + recall-reference validation.

Fixed samples are the real scene 3 initial draft and the relevant chapter 1 excerpt from the
live evaluation (`docs/loop/live_eval_export2.md`). No live LLM: the rewrite is mocked.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from app.services.repetition_guard import (
    RepetitionConfig,
    analyze_scene_repetition,
    extract_required_quotes,
)
from app.services.repetition_service import build_rewrite_instruction, run_repetition_pipeline
from test_repetition_guard import client, two_chapters

FIX = Path(__file__).parent / "fixtures"
SCENE3 = (FIX / "t17_scene3_initial.txt").read_text(encoding="utf-8")
CH1 = (FIX / "t17_ch1_excerpt.txt").read_text(encoding="utf-8")

BEAT = (
    "目标：让江澈凭锁屏壁纸与电话措辞确认学姐就是网友，并决定暂不点破。\n"
    "必须发生：电话里她逐字说出“那你把你之前拍的也发我看看呗。”；他判断相认等于替她揭开隐私，决定不点破\n"
    "本场禁止出现：裴南栀察觉他的判断、回头追问或作出回应"
)
REQUIRED_LINE = "那你把你之前拍的也发我看看呗。"


def _run(coro):
    return asyncio.run(coro)


def test_scene3_initial_really_contains_required_line_and_bad_recall() -> None:
    assert REQUIRED_LINE in SCENE3
    assert REQUIRED_LINE in CH1
    assert "不行才要看嘛" in SCENE3 and "不行才要看嘛" not in CH1
    assert "歪头的小表情" in SCENE3 and "歪头的小表情" not in CH1


def test_beat_quote_verified_in_previous_chapter_is_exempt() -> None:
    report = analyze_scene_repetition(
        SCENE3, previous_chapter=CH1, chapter_so_far="",
        beat=BEAT, config=RepetitionConfig(),
    )
    assert report.required_quotes == [REQUIRED_LINE]
    # The exact beat line is no longer a reused dialogue or a >=10-char reused span.
    assert all(REQUIRED_LINE not in d.text for d in report.dialogues)
    assert all(REQUIRED_LINE not in s.text for s in report.spans)
    assert not any("整句台词" in reason for reason in report.reasons)
    assert not any("≥10 字的重复片段" in reason for reason in report.reasons)
    # The scene still triggers for the independent recall fabrication, not for the callback.
    assert report.triggered
    assert any("回忆引用" in reason for reason in report.reasons)


def test_beat_quote_not_verbatim_in_reference_is_not_exempt() -> None:
    previous = "他说：“我们今天先不走。”"
    beat = "必须发生：“我们今天先不走吧。”"
    scene = "他说：“我们今天先不走。”"
    assert extract_required_quotes(beat, previous, "") == []
    report = analyze_scene_repetition(
        scene, previous_chapter=previous, chapter_so_far="",
        beat=beat, config=RepetitionConfig(),
    )
    assert any("我们今天先不走" in d.text for d in report.dialogues)
    assert report.triggered


def test_beat_quote_present_in_chapter_so_far_is_also_exempt() -> None:
    beat = "必须发生：“我们改天再说吧。”"
    so_far = "他说：“我们改天再说吧。”"
    scene = "他又说：“我们改天再说吧。”"
    report = analyze_scene_repetition(
        scene, previous_chapter="", chapter_so_far=so_far,
        beat=beat, config=RepetitionConfig(),
    )
    assert report.required_quotes == ["我们改天再说吧。"]
    assert report.dialogues == []
    assert not any("整句台词" in reason for reason in report.reasons)


def test_recall_heuristic_detects_invented_chat_line_and_expression() -> None:
    report = analyze_scene_repetition(
        SCENE3, previous_chapter=CH1, chapter_so_far="",
        beat=BEAT, config=RepetitionConfig(),
    )
    misses = {(m.text, m.kind) for m in report.recall_misses}
    assert ("不行才要看嘛", "quoted") in misses
    assert ("歪头的小表情", "expression") in misses
    # This one really is in chapter 1, so it must not be reported.
    assert all("我拍得不行" not in m.text for m in report.recall_misses)
    assert report.triggered


def test_recall_heuristic_accepts_real_quotes_and_expressions() -> None:
    scene = (
        "他想起那天凌晨的对话，一字不差：她发来“我拍得不行”，"
        "后面还跟了一个转圈的表情。"
    )
    report = analyze_scene_repetition(
        scene, previous_chapter=CH1, chapter_so_far="",
        beat="", config=RepetitionConfig(),
    )
    assert report.recall_misses == []
    assert not report.triggered


def test_rewrite_prompt_protects_beat_quotes_and_lists_citable_lines() -> None:
    report = analyze_scene_repetition(
        SCENE3, previous_chapter=CH1, chapter_so_far="",
        beat=BEAT, config=RepetitionConfig(),
    )
    prompt = build_rewrite_instruction(report)
    assert "【节拍要求的逐字呼应】" in prompt
    assert "以下句子是节拍要求的逐字呼应，必须原样保留" in prompt
    assert f"「{REQUIRED_LINE}」" in prompt
    assert "【上一章可引用的原句清单】" in prompt
    assert "「我拍得不行。」" in prompt
    assert "不确定就概括，不得补写表情或台词" in prompt
    # The protected callback is not described as something to delete.
    assert "但【节拍要求的逐字呼应】中的句子必须原样保留" in prompt


def test_pipeline_rewrites_once_when_recall_reference_is_invented() -> None:
    seen = []

    async def rewrite(_text: str, report) -> str:
        seen.append(report)
        return "江澈把表格递过去，学姐接了，指了指西边的路。他道了谢，拎起行李袋离开。"

    out = _run(run_repetition_pipeline(
        SCENE3,
        previous_chapter=CH1,
        chapter_so_far="",
        must_not_include=[],
        config=RepetitionConfig(auto_rewrite=True),
        rewrite_fn=rewrite,
        beat=BEAT,
    ))
    assert len(seen) == 1
    assert seen[0].required_quotes == [REQUIRED_LINE]
    assert out["action"] == "rewritten"
    assert out["triggered"] is True
    assert "拎起行李袋" in out["final_text"]
    assert any("回忆引用" in reason for reason in out["reasons"])


def test_endpoint_wires_scene_beat_into_check_and_rewrite_prompt(
    client, two_chapters, monkeypatch
) -> None:
    uid, _c2, c3, _scene = two_chapters
    beat = (
        "必须发生：他在电话里听到“那你九月一号路上小心”；"
        "他决定不点破\n本场禁止出现：点破身份"
    )
    scene_id = client.post(
        f"/api/v1/novels/{uid}/chapters/{c3}/scenes",
        json={"beat": beat, "target_words": 800},
    ).json()["id"]

    prompts: list[str] = []

    async def fake_post(_self, url, **kw):
        prompts.append(next(m["content"] for m in kw["json"]["messages"] if m["role"] == "user"))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "他挂了电话，把表格递过去，没有多说。"}}],
                  "usage": {"prompt_tokens": 5, "completion_tokens": 5}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    scene_text = (
        "他听见电话里说：“那你九月一号路上小心。”\n\n"
        "这段回忆一字不差，她还说：“这句第 1 章没有。”"
    )
    res = client.post(
        f"/api/v1/novels/{uid}/chapters/{c3}/scenes/{scene_id}/repetition-check",
        json={"scene_text": scene_text, "chapter_so_far": "", "auto_rewrite": True},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["action"] == "rewritten"
    assert body["report"]["required_quotes"] == ["那你九月一号路上小心"]
    assert len(prompts) == 1
    assert "【节拍要求的逐字呼应】" in prompts[0]
    assert "「那你九月一号路上小心」" in prompts[0]
    assert "【上一章可引用的原句清单】" in prompts[0]
    assert "不确定就概括，不得补写表情或台词" in prompts[0]
