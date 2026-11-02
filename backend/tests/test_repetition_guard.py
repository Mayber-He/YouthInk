"""T5: deterministic repetition detection + one-shot rewrite.

Samples are the real chapter 2 / chapter 3 texts of this project (tests/fixtures), where
chapter 3 re-says several chapter-2 lines. No live LLM: the rewrite step is a mock.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import reset_config_for_testing
from app.db.manager import ensure_global_db_initialized
from app.main import create_app
from app.services.repetition_guard import (
    RepetitionConfig,
    RepetitionReport,
    analyze_scene_repetition,
    count_action_phrases,
    find_reused_dialogues,
    find_reused_spans,
    forbidden_overlap,
    split_must_not_include,
)
from app.services.repetition_service import (
    build_rewrite_instruction,
    build_time_hint,
    run_repetition_pipeline,
)

FIX = Path(__file__).parent / "fixtures"
CH2 = (FIX / "repeat_chapter2.txt").read_text(encoding="utf-8")
CH3 = (FIX / "repeat_chapter3.txt").read_text(encoding="utf-8")

# Lines chapter 3 repeats from chapter 2 (verified verbatim in the fixtures).
REPEATED_LINES = [
    "那你九月一号路上小心",
    "现实里是另一个人",
    "我怎么跟你操心起这个来了",
]


def _split_scenes(text: str, k: int = 3) -> list[str]:
    lines = text.split("\n")
    m = max(1, len(lines) // k)
    return ["\n".join(lines[i * m:(i + 1) * m]) for i in range(k - 1)] + ["\n".join(lines[(k - 1) * m:])]


# ----------------------------------------------------------- fixtures sanity

def test_fixture_lines_really_occur_in_both_chapters() -> None:
    for line in REPEATED_LINES:
        assert line in CH2, line
        assert line in CH3, line


# ----------------------------------------------------------- (a) reused text

def test_chapter3_repeated_dialogue_is_detected_against_chapter2() -> None:
    reused = find_reused_dialogues(CH3, CH2)
    texts = " | ".join(r.text for r in reused)
    for line in REPEATED_LINES:
        assert line in texts, f"missed repeated line: {line}"


def test_chapter3_scenes_each_flag_when_they_restate_chapter2() -> None:
    cfg = RepetitionConfig()
    s1, _s2, s3 = _split_scenes(CH3)
    r1 = analyze_scene_repetition(s1, previous_chapter=CH2, chapter_so_far="", config=cfg)
    assert r1.triggered
    assert any("那你九月一号路上小心" in d.text for d in r1.dialogues)
    r3 = analyze_scene_repetition(s3, previous_chapter=CH2, chapter_so_far="", config=cfg)
    assert r3.triggered
    assert any("我怎么跟你操心起这个来了" in d.text for d in r3.dialogues)


def test_clean_scene_against_unrelated_previous_chapter_does_not_trigger() -> None:
    # Chapter 3 has no overlap with chapter 4-style fresh content: use a made-up unrelated text.
    fresh = "清晨的操场很安静。林鹿拎着早餐站在看台边，等了十分钟才看到人。\n\n“你迟到了。”她把豆浆递过去。"
    r = analyze_scene_repetition(fresh, previous_chapter=CH2, chapter_so_far="", config=RepetitionConfig())
    assert not r.triggered
    assert r.spans == [] and r.dialogues == []


def test_speaker_label_alone_does_not_count_as_repetition() -> None:
    prev = "「吃一口软糖」：今天天气真好呀我们出去玩吧\n「晚风不加糖」：好的我马上就出发"
    new = "「吃一口软糖」：完全不同的内容这里只是换了新话题而已\n「晚风不加糖」：嗯嗯我知道了那就这样决定吧"
    r = analyze_scene_repetition(new, previous_chapter=prev, chapter_so_far="", config=RepetitionConfig())
    assert not r.triggered
    cov, spans = find_reused_spans(new, prev)
    assert cov == 0.0 and spans == []


def test_repetition_against_chapter_so_far_is_detected_too() -> None:
    so_far = "他把手机往桌上一扣，盯着天花板上那块去年渗水留下的黄印看了很久很久。"
    scene = "过了一会儿他把手机往桌上一扣，盯着天花板上那块去年渗水留下的黄印。"
    r = analyze_scene_repetition(scene, previous_chapter="", chapter_so_far=so_far, config=RepetitionConfig())
    assert r.triggered
    assert any(s.source == "chapter_so_far" for s in r.spans)


# ----------------------------------------------------------- (b) action words

def test_stock_action_words_counted_across_chapter() -> None:
    so_far = "老风扇正对着床吹。\n风扇转过来，把日历纸吹起一个角。\n他听着风扇的咔哒声。"
    scene = "他关掉风扇，屋里一下安静了。"
    hits = count_action_phrases(scene, so_far, RepetitionConfig().action_phrases)
    fan = next(h for h in hits if h.phrase == "风扇")
    assert fan.count == 4  # 3 earlier + 1 in the scene

    r = analyze_scene_repetition(scene, previous_chapter="", chapter_so_far=so_far, config=RepetitionConfig())
    assert r.triggered
    assert any(h.phrase == "风扇" for h in r.action_hits)


def test_action_phrase_list_is_configurable() -> None:
    cfg = RepetitionConfig(action_phrases=("咖啡杯",), action_word_max=2)
    so_far = "她端起咖啡杯。"
    scene = "他放下咖啡杯。"
    r = analyze_scene_repetition(scene, previous_chapter="", chapter_so_far=so_far, config=cfg)
    assert r.triggered and r.action_hits[0].phrase == "咖啡杯"
    # a phrase not in the (custom) list is ignored
    r2 = analyze_scene_repetition("风扇风扇风扇", previous_chapter="", chapter_so_far="风扇风扇", config=cfg)
    assert not r2.action_hits


def test_action_phrase_not_in_scene_does_not_reflag() -> None:
    so_far = "风扇风扇风扇风扇"
    scene = "他起身去倒水。"
    assert count_action_phrases(scene, so_far, ("风扇",)) == []


def test_env_overrides_thresholds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YOUTHINK_REPEAT_ACTION_MAX", "2")
    monkeypatch.setenv("YOUTHINK_REPEAT_ACTION_WORDS", "咖啡杯, 台灯")
    monkeypatch.setenv("YOUTHINK_REPEAT_AUTO_REWRITE", "0")
    cfg = RepetitionConfig.from_env()
    assert cfg.action_word_max == 2
    assert cfg.action_phrases == ("咖啡杯", "台灯")
    assert cfg.auto_rewrite is False
    monkeypatch.setenv("YOUTHINK_REPEAT_ENABLED", "0")
    assert RepetitionConfig.from_env().enabled is False


# ----------------------------------------------------------- (c) must_not_include

def test_must_not_include_overlap_detected() -> None:
    scene = "他看着她的背影，突然明白她就是那个网友软糖，认出了她的真实身份。"
    hits = forbidden_overlap(scene, ["认出她是网友", "表白或暧昧"])
    by_item = {h.item: h.overlap for h in hits}
    assert by_item["表白或暧昧"] < 0.5

    r = analyze_scene_repetition(
        scene, previous_chapter="", chapter_so_far="",
        must_not_include=["认出了她的真实身份"], config=RepetitionConfig(),
    )
    assert r.triggered and r.forbidden_hits and "认出了她的真实身份" == r.forbidden_hits[0].item


def test_split_must_not_include_reads_t3_beat_format() -> None:
    beat = "目标：x\n必须发生：a；b\n终点状态：y\n本场禁止出现：认出网友；表白"
    assert split_must_not_include(beat) == ["认出网友", "表白"]
    assert split_must_not_include("没有该字段") == []


def test_disabled_config_never_triggers() -> None:
    r = analyze_scene_repetition(CH3, previous_chapter=CH2, chapter_so_far="",
                                 config=RepetitionConfig(enabled=False))
    assert not r.triggered


# ----------------------------------------------------------- pipeline (mock rewrite)

def _run(coro):
    return asyncio.run(coro)


def test_pipeline_no_trigger_means_no_model_call() -> None:
    calls = {"n": 0}

    async def rewrite(_t, _r):
        calls["n"] += 1
        return "x"

    out = _run(run_repetition_pipeline(
        "清晨的操场很安静。", previous_chapter=CH2, chapter_so_far="", must_not_include=[],
        config=RepetitionConfig(), rewrite_fn=rewrite,
    ))
    assert out["action"] == "none" and out["triggered"] is False and calls["n"] == 0
    assert out["final_text"] == "清晨的操场很安静。"


def test_pipeline_rewrites_once_and_accepts_clean_rewrite() -> None:
    s1 = _split_scenes(CH3)[0]
    seen: list[str] = []

    async def rewrite(text, report):
        seen.append(report.describe_for_model())
        return "夜里他翻了个身，把和她的聊天记录又看了一遍。\n\n“明天见。”他想了想，只打了这三个字。"

    out = _run(run_repetition_pipeline(
        s1, previous_chapter=CH2, chapter_so_far="", must_not_include=[],
        config=RepetitionConfig(), rewrite_fn=rewrite,
    ))
    assert out["action"] == "rewritten"
    assert out["triggered"] is True  # describes the ORIGINAL text
    assert "明天见" in out["final_text"]
    # the concrete repeated spans were handed to the model
    assert len(seen) == 1 and "那你九月一号路上小心" in seen[0]


def test_pipeline_rewrites_only_once_when_rewrite_still_repeats() -> None:
    s1 = _split_scenes(CH3)[0]
    calls = {"n": 0}

    async def rewrite(text, report):
        calls["n"] += 1
        return text  # model ignored the instruction: same repetition remains

    out = _run(run_repetition_pipeline(
        s1, previous_chapter=CH2, chapter_so_far="", must_not_include=[],
        config=RepetitionConfig(), rewrite_fn=rewrite,
    ))
    assert calls["n"] == 1  # never loops
    assert out["action"] == "kept_with_warning"
    assert out["warnings"] and any("重写一次后仍超阈值" in w for w in out["warnings"])
    assert out["final_text"]  # text is kept, not dropped


def test_pipeline_keeps_original_if_rewrite_is_worse() -> None:
    s1 = _split_scenes(CH3)[0]

    async def rewrite(text, report):
        # worse: repeats even more of chapter 2
        return text + "\n" + "\n".join(f"「吃一口软糖」：{l}" for l in REPEATED_LINES)

    out = _run(run_repetition_pipeline(
        s1, previous_chapter=CH2, chapter_so_far="", must_not_include=[],
        config=RepetitionConfig(), rewrite_fn=rewrite,
    ))
    assert out["action"] == "kept_with_warning"
    assert out["final_text"] == s1  # the less-repetitive original wins


def test_pipeline_rewrite_failure_keeps_original() -> None:
    s1 = _split_scenes(CH3)[0]

    async def rewrite(text, report):
        raise RuntimeError("upstream down")

    out = _run(run_repetition_pipeline(
        s1, previous_chapter=CH2, chapter_so_far="", must_not_include=[],
        config=RepetitionConfig(), rewrite_fn=rewrite,
    ))
    assert out["action"] == "rewrite_failed" and out["final_text"] == s1
    assert out["warnings"]


def test_pipeline_auto_rewrite_off_only_warns() -> None:
    s1 = _split_scenes(CH3)[0]
    calls = {"n": 0}

    async def rewrite(text, report):
        calls["n"] += 1
        return "x"

    out = _run(run_repetition_pipeline(
        s1, previous_chapter=CH2, chapter_so_far="", must_not_include=[],
        config=RepetitionConfig(auto_rewrite=False), rewrite_fn=rewrite,
    ))
    assert calls["n"] == 0 and out["action"] == "kept_with_warning" and out["final_text"] == s1


def test_pipeline_records_every_measurement() -> None:
    s1 = _split_scenes(CH3)[0]
    recorded: list[tuple[str, str]] = []

    def record(stage, action, report, thresholds):
        recorded.append((stage, action))
        assert thresholds["ngram"] == 8 and "action_phrases" in thresholds
        return len(recorded)

    async def rewrite(text, report):
        return "夜里很安静，他合上手机睡了。"

    out = _run(run_repetition_pipeline(
        s1, previous_chapter=CH2, chapter_so_far="", must_not_include=[],
        config=RepetitionConfig(), rewrite_fn=rewrite, record_fn=record,
    ))
    assert recorded == [("initial", "none"), ("after_rewrite", "rewritten")]
    assert out["check_ids"] == [1, 2]


def test_pipeline_survives_a_failing_recorder() -> None:
    def record(*_a, **_k):
        raise RuntimeError("db locked")

    async def rewrite(text, report):
        return "夜里很安静。"

    out = _run(run_repetition_pipeline(
        _split_scenes(CH3)[0], previous_chapter=CH2, chapter_so_far="", must_not_include=[],
        config=RepetitionConfig(), rewrite_fn=rewrite, record_fn=record,
    ))
    assert out["action"] == "rewritten"


# ----------------------------------------------------------- T13 conservative rewrite prompt

def test_rewrite_instruction_only_touches_flagged_spans_and_keeps_time_words() -> None:
    report = RepetitionReport(time_hits=["前一晚"], story_time_gap_days=7)
    report.reasons.append("与上一章相隔 7 天，疑似相对时间错位：前一晚")
    hint = build_time_hint("八月二十五日", "九月一日", 7)
    text = build_rewrite_instruction(report, time_hint=hint)

    assert "只改写下列被标出的重复片段" in text
    assert "必须原样保留" in text and "不得新增、删除或调换任何情节" in text
    assert "那天晚上" in text  # explicitly protected by the instruction
    assert "上一章发生时间：八月二十五日" in text
    assert "本章发生时间：九月一日" in text
    assert "相隔天数：7 天" in text
    assert "禁止使用与实际相隔天数不符的相对时间词" in text
    assert "前一晚" in text and "昨天" in text
    # the old "rewrite the whole scene with completely new wording" instruction is gone
    assert "换用全新的措辞" not in text


def test_time_hint_does_not_ban_qiantian_when_gap_is_two_days() -> None:
    hint = build_time_hint("8月30日", "9月1日", 2)
    banned = next(line for line in hint.splitlines() if line.startswith("禁止使用"))
    body = banned.split("：", 1)[1].split("（", 1)[0].strip("。")
    banned_words = body.split("/")
    assert "前天" not in banned_words  # exactly two days: 前天 is correct
    assert "大前天" in banned_words
    assert "昨晚" in banned_words and "前一晚" in banned_words
    assert "“前天”与相隔天数一致" in hint


def test_time_hint_states_unknown_gap_without_guessing() -> None:
    hint = build_time_hint("", "", None)
    assert "上一章发生时间：未指定" in hint
    assert "本章发生时间：未指定" in hint
    assert "无法确定" in hint and "不得猜补日期" in hint


# ----------------------------------------------------------- HTTP integration

@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    reset_config_for_testing(tmp_path / "test_data_t5")
    ensure_global_db_initialized()
    c = TestClient(create_app())
    c.post(
        "/api/v1/settings/llm-profiles",
        json={"name": "T5", "base_url": "https://api.example.com/v1", "model": "deepseek-chat",
              "api_key": "sk-t5", "is_default": True},
    )
    return c


@pytest.fixture()
def two_chapters(client: TestClient):
    uid = client.post("/api/v1/novels", json={"title": "重复T5"}).json()["novel_uid"]
    v = client.post(f"/api/v1/novels/{uid}/outline/volumes", json={"title": "卷"}).json()["id"]
    a = client.post(f"/api/v1/novels/{uid}/outline/arcs", json={"volume_id": v, "title": "弧"}).json()["id"]
    c2 = client.post(f"/api/v1/novels/{uid}/outline/chapters",
                     json={"arc_id": a, "title": "二", "synopsis": "s"}).json()["id"]
    c3 = client.post(f"/api/v1/novels/{uid}/outline/chapters",
                     json={"arc_id": a, "title": "三", "synopsis": "s"}).json()["id"]
    client.put(f"/api/v1/novels/{uid}/chapters/{c2}/content",
               json={"content": CH2, "source": "manual", "create_new_version": True})
    scene = client.post(
        f"/api/v1/novels/{uid}/chapters/{c3}/scenes",
        json={"beat": "目标：g\n必须发生：x\n本场禁止出现：江澈当场表白", "target_words": 800},
    ).json()["id"]
    return uid, c2, c3, scene


def _chat_body(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}], "usage": {"prompt_tokens": 5, "completion_tokens": 5}}


def test_endpoint_detects_chapter2_repetition_rewrites_once_and_persists(
    client: TestClient, two_chapters, monkeypatch
) -> None:
    uid, _c2, c3, scene = two_chapters
    calls = {"n": 0}

    async def fake_post(self, url, **kw):
        calls["n"] += 1
        return httpx.Response(200, json=_chat_body("夜里他把聊天记录翻到底，什么也没回。"),
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    s1 = _split_scenes(CH3)[0]
    res = client.post(
        f"/api/v1/novels/{uid}/chapters/{c3}/scenes/{scene}/repetition-check",
        json={"scene_text": s1, "chapter_so_far": ""},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["triggered"] is True
    assert body["action"] == "rewritten"
    assert "聊天记录" in body["final_text"]
    assert calls["n"] == 1  # exactly one rewrite call
    assert len(body["check_ids"]) == 2

    from app.db.manager import get_novel_db
    with get_novel_db(uid) as conn:
        rows = conn.execute(
            "SELECT stage, action_taken, triggered, thresholds_json FROM repetition_checks ORDER BY id"
        ).fetchall()
    assert [(r["stage"], r["action_taken"]) for r in rows] == [("initial", "none"), ("after_rewrite", "rewritten")]
    assert rows[0]["triggered"] == 1 and rows[1]["triggered"] == 0
    assert json.loads(rows[0]["thresholds_json"])["ngram"] == 8


def test_rewrite_prompt_carries_dates_gap_and_conservative_rules(
    client: TestClient, two_chapters, monkeypatch
) -> None:
    uid, c2, c3, scene = two_chapters
    from app.db.manager import get_novel_db
    with get_novel_db(uid) as conn:
        conn.execute("UPDATE chapters SET story_time = ? WHERE id = ?", ("八月二十五日", c2))
        conn.execute("UPDATE chapters SET story_time = ? WHERE id = ?", ("九月一日", c3))
        conn.commit()

    prompts: list[list[dict]] = []

    async def fake_post(self, url, **kw):
        prompts.append(kw["json"]["messages"])
        return httpx.Response(200, json=_chat_body("夜里他把聊天记录翻到底，什么也没回。"),
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    res = client.post(
        f"/api/v1/novels/{uid}/chapters/{c3}/scenes/{scene}/repetition-check",
        json={"scene_text": _split_scenes(CH3)[0], "chapter_so_far": ""},
    )
    assert res.status_code == 200 and res.json()["action"] == "rewritten"
    user_msg = next(m["content"] for m in prompts[0] if m["role"] == "user")
    assert "上一章发生时间：八月二十五日" in user_msg
    assert "本章发生时间：九月一日" in user_msg
    assert "相隔天数：7 天" in user_msg
    assert "禁止使用与实际相隔天数不符的相对时间词" in user_msg
    assert "只改写下列被标出的重复片段" in user_msg
    assert "那天晚上" in user_msg and "必须原样保留" in user_msg


def test_endpoint_must_not_include_comes_from_scene_beat(
    client: TestClient, two_chapters, monkeypatch
) -> None:
    uid, _c2, c3, scene = two_chapters

    async def fake_post(self, url, **kw):
        return httpx.Response(200, json=_chat_body("他只是点了点头，什么都没说。"),
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    res = client.post(
        f"/api/v1/novels/{uid}/chapters/{c3}/scenes/{scene}/repetition-check",
        json={"scene_text": "走到楼下，江澈当场表白了，说他一直喜欢她。", "chapter_so_far": ""},
    )
    body = res.json()
    assert res.status_code == 200
    assert body["triggered"] is True
    assert any("禁止出现" in r for r in body["reasons"])


def test_endpoint_clean_scene_makes_no_model_call(client: TestClient, two_chapters, monkeypatch) -> None:
    uid, _c2, c3, scene = two_chapters
    calls = {"n": 0}

    async def fake_post(self, url, **kw):
        calls["n"] += 1
        return httpx.Response(200, json=_chat_body("x"), request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    res = client.post(
        f"/api/v1/novels/{uid}/chapters/{c3}/scenes/{scene}/repetition-check",
        json={"scene_text": "清晨的操场很安静，林鹿拎着早餐等了十分钟。", "chapter_so_far": ""},
    )
    assert res.status_code == 200 and res.json()["action"] == "none" and calls["n"] == 0


def test_endpoint_respects_global_off_switch(client: TestClient, two_chapters, monkeypatch) -> None:
    uid, _c2, c3, scene = two_chapters
    monkeypatch.setenv("YOUTHINK_REPEAT_ENABLED", "0")
    res = client.post(
        f"/api/v1/novels/{uid}/chapters/{c3}/scenes/{scene}/repetition-check",
        json={"scene_text": _split_scenes(CH3)[0], "chapter_so_far": ""},
    )
    body = res.json()
    assert res.status_code == 200 and body["action"] == "none" and body["triggered"] is False
