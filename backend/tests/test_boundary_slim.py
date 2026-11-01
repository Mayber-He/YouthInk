"""T6: slim continuity-check injection + visible failure notice.

Real data: tests/fixtures/boundary_real_outputs.json holds the 16 actual writing_boundary outputs
from this project's generation_logs. No live LLM; model calls are mocked.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import reset_config_for_testing
from app.db.manager import ensure_global_db_initialized, get_global_db, get_novel_db
from app.db.repositories.settings_repo import SettingsRepository
from app.main import create_app
from app.schemas.writing import StreamWriteRequest
from app.services.writing_boundary import (
    BOUNDARY_HEADER,
    MAX_REPEAT_PHRASES,
    WritingBoundary,
    _normalize_for_match,
    boundary_slim_enabled,
    boundary_timeout_sec,
    evidence_in_history,
    format_boundary_for_prompt,
    is_safe_to_phrase,
    is_usable_phrase,
    to_phrase,
    unavailable_notice,
)
from app.services.writing_service import WritingService

REAL = json.loads(
    (Path(__file__).parent / "fixtures" / "boundary_real_outputs.json").read_text(encoding="utf-8")
)
OLD_HEADER = "【生成前章节衔接检查】以下是基于原文证据的写作边界；与梗概重复时从已发生事件之后推进。\n"


def _wb(**kw) -> WritingBoundary:
    kw.setdefault("next_step", "从已写结尾手机亮起处接。")
    return WritingBoundary.model_validate(kw)


# ------------------------------------------------------------------ format

def test_format_has_continue_from_and_avoid_list_only() -> None:
    b = _wb(
        established=[{"statement": "时间是傍晚", "evidence_quote": "八月最后一个周一傍晚六点半"}],
        repeated_events=[{"statement": "计划中修打印机已发生", "evidence_quote": "镊子探进滚轴夹住卡住的半张纸"}],
        next_step="从当前结尾“测试页已经出来”继续。下一段可写她洗完澡回来后发晚安。",
        avoid=["修打印机", "她抱怨冰棍化手"],
    )
    out = format_boundary_for_prompt(b)
    assert out.startswith(BOUNDARY_HEADER)
    assert "本场景从这里接：从当前结尾“测试页已经出来”继续" in out
    assert "已写过、不要再写：修打印机；她抱怨冰棍化手" in out
    # No raw evidence, no established-fact dump, no JSON, no concrete follow-up script.
    assert "镊子探进滚轴" not in out and "八月最后一个周一傍晚六点半" not in out
    assert "evidence_quote" not in out and "established" not in out and "{" not in out
    assert "下一段可写" not in out


def test_continue_from_keeps_first_sentence_and_respects_quotes() -> None:
    # The full stop inside the quotation must not end the sentence.
    b = _wb(next_step="从已写正文结尾“嗯……不太想说话。”之后续写：江澈发表情问她是不是有事。随后她回答。", avoid=["x物"])
    out = format_boundary_for_prompt(b)
    line = next(l for l in out.splitlines() if l.startswith("本场景从这里接："))
    assert "“嗯……不太想说话。”之后续写" in line
    assert "随后她回答" not in line


def test_continue_from_is_capped_and_never_leaves_dangling_quote() -> None:
    long = "从已写结尾接，" + "江澈拿起手机" * 30 + "“未闭合的引号内容" + "很长" * 30
    out = format_boundary_for_prompt(_wb(next_step=long, avoid=["某素材"]))
    line = next(l for l in out.splitlines() if l.startswith("本场景从这里接："))
    body = line.split("：", 1)[1]
    assert len(body) <= 85  # cap 80 (+ ellipsis)
    assert body.count("“") == body.count("”")


def test_avoid_list_deduped_and_capped() -> None:
    avoid = [f"素材{i}号事件" for i in range(20)] + ["素材0号事件", "素材0号事件"]
    out = format_boundary_for_prompt(_wb(avoid=avoid))
    phrases = out.split("已写过、不要再写：", 1)[1].split("；")
    assert len(phrases) == MAX_REPEAT_PHRASES
    assert len(set(phrases)) == len(phrases)


def test_model_avoid_phrases_are_trimmed_and_length_capped() -> None:
    out = format_boundary_for_prompt(_wb(avoid=["  修打印机。 ", "超长" * 30, ""]))
    phrases = out.split("已写过、不要再写：", 1)[1].split("；")
    assert phrases[0] == "修打印机"
    assert all(len(p) <= 25 for p in phrases)  # 24 + possible ellipsis
    assert "" not in phrases


# ------------------------------------------------------------------ fallback (no `avoid`)

def test_fallback_extracts_clean_phrase_from_plan_sentence() -> None:
    assert to_phrase("计划中她发老冰棍照片已发生，不必再发一遍。") == "她发老冰棍照片"
    assert to_phrase("计划中的江澈藏录取通知书已经发生。") == "江澈藏录取通知书"


def test_fallback_does_not_split_inside_a_quotation() -> None:
    p = to_phrase("计划中的聊开学、她不想开学、问“哪所啊？”、江澈答“本地，走读。”、她回“哦。”已经发生。")
    assert p.count("“") == p.count("”")
    assert "问“哪所啊？”" in p  # was previously cut to '聊开学、她不想开学、问'


def test_fallback_rejects_negating_or_conditional_sentences() -> None:
    # Shortening these would drop the negation and could make the model WRITE the very thing.
    bad = "计划要写江澈把录取通知书摊在床上码进文件袋，但前文结尾通知书已推进抽屉旧练习册底下；不能直接写它已在床上。"
    assert not is_safe_to_phrase(bad)
    out = format_boundary_for_prompt(_wb(repeated_events=[{"statement": bad, "evidence_quote": "通知书往里推了推"}]))
    assert "摊在床上" not in out
    assert "已写过、不要再写" not in out  # nothing usable -> no half-baked list


def test_fallback_rejects_commentary_fragments_and_truncations() -> None:
    for junk in ("要写的", "江澈已经问过", "前章已出现过一次", "x…", "ab", ""):
        assert not is_usable_phrase(junk)
    assert is_usable_phrase("傍晚修打印机、手机震个不停")


def test_negation_marker_allows_do_not_rewrite_phrasing() -> None:
    # '不应再…/不必再…' is the "don't write this again" semantic we WANT, not an inversion risk.
    assert is_safe_to_phrase("计划中她发老冰棍照片已发生，不必再发一遍。")


def test_fallback_never_emits_empty_or_dangling_phrases_on_real_data() -> None:
    seen = set()
    for item in REAL:
        for ev in item["output"].get("repeated_events", []):
            s = ev["statement"]
            if s in seen:
                continue
            seen.add(s)
            p = to_phrase(s) if is_safe_to_phrase(s) else ""
            if is_usable_phrase(p):
                assert p.count("“") == p.count("”") and p.count("「") == p.count("」")
                assert not p.endswith("…")
    assert len(seen) >= 50  # real sample is non-trivial


# ------------------------------------------------------------------ real-data regression

def test_real_outputs_shrink_massively_and_never_leak_evidence() -> None:
    old_total = new_total = 0
    for item in REAL:
        d = item["output"]
        old = OLD_HEADER + json.dumps(d, ensure_ascii=False)
        new = format_boundary_for_prompt(WritingBoundary.model_validate(d))
        old_total += len(old)
        new_total += len(new)
        for ev in d.get("established", []) + d.get("repeated_events", []):
            q = ev["evidence_quote"]
            if len(q) >= 12:
                assert q not in new, f"evidence_quote leaked into injection (log {item['log_id']})"
        assert new.startswith(BOUNDARY_HEADER) and "本场景从这里接：" in new
    assert new_total <= old_total * 0.2  # observed ~95% reduction; assert a conservative ≥80%


# ------------------------------------------------------------------ switch

def test_slim_switch_default_on_and_can_restore_full_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("YOUTHINK_BOUNDARY_SLIM", raising=False)
    assert boundary_slim_enabled() is True
    monkeypatch.setenv("YOUTHINK_BOUNDARY_SLIM", "0")
    assert boundary_slim_enabled() is False


# ------------------------------------------------------------------ integration

def _chat(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}], "usage": {"prompt_tokens": 5, "completion_tokens": 5}}


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    reset_config_for_testing(tmp_path / "test_data_t6")
    ensure_global_db_initialized()
    c = TestClient(create_app())
    c.post("/api/v1/settings/llm-profiles", json={
        "name": "T6", "base_url": "https://api.example.com/v1", "model": "deepseek-chat",
        "api_key": "sk-t6", "is_default": True})
    return c


@pytest.fixture()
def two_chapters(client: TestClient):
    uid = client.post("/api/v1/novels", json={"title": "衔接T6"}).json()["novel_uid"]
    v = client.post(f"/api/v1/novels/{uid}/outline/volumes", json={"title": "卷"}).json()["id"]
    a = client.post(f"/api/v1/novels/{uid}/outline/arcs", json={"volume_id": v, "title": "弧"}).json()["id"]
    c1 = client.post(f"/api/v1/novels/{uid}/outline/chapters",
                     json={"arc_id": a, "title": "一", "synopsis": "s"}).json()["id"]
    c2 = client.post(f"/api/v1/novels/{uid}/outline/chapters",
                     json={"arc_id": a, "title": "二", "synopsis": "s"}).json()["id"]
    client.put(f"/api/v1/novels/{uid}/chapters/{c1}/content",
               json={"content": "宿舍在四楼。她把箱子搬上去。", "source": "manual", "create_new_version": True})
    return uid, c1, c2


def _svc(uid: str):
    nconn = get_novel_db(uid)
    gconn = get_global_db()
    return nconn, gconn


def test_ex_returns_ok_with_lean_text(client: TestClient, two_chapters, monkeypatch) -> None:
    uid, _c1, c2 = two_chapters
    payload = {
        "established": [{"statement": "宿舍在四楼", "evidence_quote": "宿舍在四楼。"}],
        "repeated_events": [{"statement": "计划中搬箱子已发生", "evidence_quote": "她把箱子搬上去。"}],
        "next_step": "从搬完箱子之后接。随后写晚饭。",
        "avoid": ["搬箱子上楼"],
    }

    async def fake_post(self, url, **kw):
        return httpx.Response(200, json=_chat(json.dumps(payload, ensure_ascii=False)),
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    with get_novel_db(uid) as n, get_global_db() as g:
        svc = WritingService(uid, n, SettingsRepository(g))
        text, status, note = asyncio.run(svc.check_write_boundary_ex(StreamWriteRequest(chapter_id=c2)))
        assert status == "ok" and note == ""
        assert "本场景从这里接：从搬完箱子之后接" in text
        assert "已写过、不要再写：搬箱子上楼" in text
        assert "宿舍在四楼" not in text and "她把箱子搬上去" not in text
        # back-compat wrapper returns the same text
        assert asyncio.run(svc.check_write_boundary(StreamWriteRequest(chapter_id=c2))) == text


def test_ex_opening_chapter_is_skipped_not_failed(client: TestClient, two_chapters) -> None:
    uid, c1, _c2 = two_chapters
    with get_novel_db(uid) as n, get_global_db() as g:
        svc = WritingService(uid, n, SettingsRepository(g))
        text, status, note = asyncio.run(svc.check_write_boundary_ex(StreamWriteRequest(chapter_id=c1)))
    assert (text, status, note) == ("", "skipped", "")


def test_technical_failure_is_visible_not_silent(client: TestClient, two_chapters, monkeypatch, caplog) -> None:
    uid, _c1, c2 = two_chapters

    async def fake_post(self, url, **kw):
        return httpx.Response(200, json=_chat("对不起，我无法按要求输出 JSON。"),
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    with caplog.at_level(logging.WARNING):
        with get_novel_db(uid) as n, get_global_db() as g:
            svc = WritingService(uid, n, SettingsRepository(g))
            text, status, note = asyncio.run(svc.check_write_boundary_ex(StreamWriteRequest(chapter_id=c2)))
    assert text == "" and status == "failed"
    assert note.startswith("衔接检查未生效")
    assert any("衔接检查未生效" in r.getMessage() for r in caplog.records)  # also in the log


def test_upstream_error_is_also_visible(client: TestClient, two_chapters, monkeypatch) -> None:
    uid, _c1, c2 = two_chapters

    async def fake_post(self, url, **kw):
        return httpx.Response(500, text="boom", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    with get_novel_db(uid) as n, get_global_db() as g:
        svc = WritingService(uid, n, SettingsRepository(g))
        _t, status, note = asyncio.run(svc.check_write_boundary_ex(StreamWriteRequest(chapter_id=c2)))
    assert status == "failed" and "衔接检查未生效" in note


RETRY_SENTENCE = "引用必须是前文中连续的原文片段，不要改动标点，不确定就不引用"


def _mock_model(monkeypatch, *replies: str) -> list[str]:
    """Reply with ``replies`` in order (the last one repeats). Returns the user prompts it received."""
    prompts: list[str] = []

    async def fake_post(self, url, **kw):
        prompts.append(kw["json"]["messages"][-1]["content"])
        body = replies[min(len(prompts), len(replies)) - 1]
        return httpx.Response(200, json=_chat(body), request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return prompts


def _ex(uid: str, chapter_id: int):
    with get_novel_db(uid) as n, get_global_db() as g:
        svc = WritingService(uid, n, SettingsRepository(g))
        return asyncio.run(svc.check_write_boundary_ex(StreamWriteRequest(chapter_id=chapter_id)))


def _payload(**kw) -> str:
    base = {"established": [], "repeated_events": [], "next_step": "从搬完箱子之后接。", "avoid": []}
    return json.dumps({**base, **kw}, ensure_ascii=False)


BAD_REP = [{"statement": "计划中她住五楼已发生", "evidence_quote": "宿舍在五楼。"}]  # invented quote
GOOD_REP = [{"statement": "计划中搬箱子已发生", "evidence_quote": "她把箱子搬上去。"}]  # verbatim


def test_all_injectable_evidence_invented_retries_once_then_degrades(client, two_chapters, monkeypatch) -> None:
    """repeated_events is what the fallback path injects (no `avoid`). All of it invented ->
    retry once with the fix-it prompt -> still invented -> degrade: nothing injected, never an error."""
    uid, _c1, c2 = two_chapters
    prompts = _mock_model(monkeypatch, _payload(repeated_events=BAD_REP))
    text, status, note = _ex(uid, c2)
    assert len(prompts) == 2 and RETRY_SENTENCE not in prompts[0] and RETRY_SENTENCE in prompts[1]
    assert status == "failed" and note.startswith("衔接检查未生效")
    assert text == ""  # degraded means it really did not take effect: no half-trusted injection


def test_one_bad_item_is_dropped_the_good_one_survives_without_retry(client, two_chapters, monkeypatch, caplog) -> None:
    """Per-item handling: a mismatched quote used to abort everything; now only that item goes."""
    uid, _c1, c2 = two_chapters
    prompts = _mock_model(monkeypatch, _payload(repeated_events=GOOD_REP + BAD_REP))
    with caplog.at_level(logging.WARNING):
        text, status, note = _ex(uid, c2)
    assert len(prompts) == 1 and status == "ok" and note == ""  # something survived -> no retry, no failure
    assert "本场景从这里接：从搬完箱子之后接" in text
    assert any("dropped 1/2 evidence" in r.getMessage() for r in caplog.records)  # visible at default level


def test_good_item_is_what_feeds_the_fallback_phrase(client, two_chapters, monkeypatch) -> None:
    """The surviving repeated_event is the one that becomes the '已写过' phrase; the invented one is not."""
    uid, _c1, c2 = two_chapters
    # Both statements reduce to a usable phrase (>= 4 chars): "她把箱子搬上楼" and "她住五楼".
    rep = [{"statement": "计划中她把箱子搬上楼已发生，不必再写。", "evidence_quote": "她把箱子搬上去。"},
           {"statement": "计划中她住五楼已发生，不必再写。", "evidence_quote": "宿舍在五楼。"}]
    # Control: with both evidence items trusted, the invented one WOULD have been injected.
    assert to_phrase(rep[1]["statement"]) == "她住五楼" and is_usable_phrase("她住五楼")
    text, status, _ = _ex_with(monkeypatch, client, two_chapters, _payload(repeated_events=rep))
    assert status == "ok"
    assert "已写过、不要再写：她把箱子搬上楼" in text and "五楼" not in text


def _ex_with(monkeypatch, client, two_chapters, body: str):
    uid, _c1, c2 = two_chapters
    _mock_model(monkeypatch, body)
    return _ex(uid, c2)


def test_model_avoid_means_evidence_fields_are_not_in_use(client, two_chapters, monkeypatch) -> None:
    """With the T6 `avoid` list only next_step + avoid reach the prompt; neither carries a quote.
    So even a fully invented established/repeated_events must neither retry nor mark the check failed."""
    uid, _c1, c2 = two_chapters
    body = _payload(established=[{"statement": "宿舍在五楼", "evidence_quote": "宿舍在五楼。"}],
                    repeated_events=BAD_REP, avoid=["搬箱子上楼"])
    prompts = _mock_model(monkeypatch, body)
    text, status, note = _ex(uid, c2)
    assert len(prompts) == 1 and status == "ok" and note == ""
    assert "已写过、不要再写：搬箱子上楼" in text and "五楼" not in text


def test_established_never_triggers_a_retry_in_slim_mode(client, two_chapters, monkeypatch) -> None:
    """`established` is not injected in slim mode, so a bad one there is irrelevant."""
    uid, _c1, c2 = two_chapters
    body = _payload(established=[{"statement": "宿舍在五楼", "evidence_quote": "宿舍在五楼。"}], repeated_events=GOOD_REP)
    prompts = _mock_model(monkeypatch, body)
    _text, status, _note = _ex(uid, c2)
    assert len(prompts) == 1 and status == "ok"


def test_legacy_mode_validates_both_evidence_fields(client, two_chapters, monkeypatch) -> None:
    """YOUTHINK_BOUNDARY_SLIM=0 injects the whole JSON, so established IS in use and is filtered too."""
    monkeypatch.setenv("YOUTHINK_BOUNDARY_SLIM", "0")
    uid, _c1, c2 = two_chapters
    est = [{"statement": "宿舍在四楼", "evidence_quote": "宿舍在四楼。"},
           {"statement": "宿舍在五楼", "evidence_quote": "宿舍在五楼。"}]
    prompts = _mock_model(monkeypatch, _payload(established=est, repeated_events=GOOD_REP))
    text, status, _ = _ex(uid, c2)
    assert len(prompts) == 1 and status == "ok"
    assert "宿舍在四楼" in text and "宿舍在五楼" not in text  # bad one removed from the injected JSON


def test_retry_that_succeeds_uses_the_second_answer(client, two_chapters, monkeypatch) -> None:
    uid, _c1, c2 = two_chapters
    prompts = _mock_model(monkeypatch, _payload(repeated_events=BAD_REP, next_step="第一次的落点。"),
                          _payload(repeated_events=GOOD_REP, next_step="第二次的落点。"))
    text, status, note = _ex(uid, c2)
    assert len(prompts) == 2 and RETRY_SENTENCE in prompts[1]
    assert status == "ok" and note == "" and "第二次的落点" in text and "第一次" not in text


def test_whole_call_failure_is_retried_once_then_degrades(client, two_chapters, monkeypatch) -> None:
    """Unparseable reply both times: one retry (with the fix-it prompt), then '衔接检查未生效', no raise."""
    uid, _c1, c2 = two_chapters
    prompts = _mock_model(monkeypatch, "对不起，我无法按要求输出 JSON。")
    text, status, note = _ex(uid, c2)
    assert len(prompts) == 2 and RETRY_SENTENCE in prompts[1] and RETRY_SENTENCE not in prompts[0]
    assert (text, status) == ("", "failed") and note.startswith("衔接检查未生效")


def test_whole_call_failure_then_success_on_retry(client, two_chapters, monkeypatch) -> None:
    uid, _c1, c2 = two_chapters
    prompts = _mock_model(monkeypatch, "不是JSON", _payload(repeated_events=GOOD_REP))
    text, status, note = _ex(uid, c2)
    assert len(prompts) == 2 and status == "ok" and note == "" and "本场景从这里接" in text


def _direct(uid: str, chapter_id: int, fn_name: str):
    """Call writing_boundary.<fn_name> directly (below the service layer, which would mask its result)."""
    import app.services.writing_boundary as wb
    with get_global_db() as g:
        return asyncio.run(getattr(wb, fn_name)(
            novel_uid=uid, chapter_id=chapter_id, settings=SettingsRepository(g),
            history="宿舍在四楼。她把箱子搬上去。", plan="本次计划",
        ))


def test_degraded_result_injects_nothing_at_every_layer(client, two_chapters, monkeypatch) -> None:
    """'衔接检查未生效' must be literally true: BoundaryResult.text is '' and so is what the
    back-compat wrapper returns. (The service layer drops `text` on failure, so only a direct call sees it.)"""
    uid, _c1, c2 = two_chapters
    _mock_model(monkeypatch, _payload(repeated_events=BAD_REP, next_step="不该被注入的落点"))
    res = _direct(uid, c2, "check_writing_boundary_result")
    assert res.text == "" and res.note.endswith("已重试一次") and res.dropped == 0
    assert _direct(uid, c2, "check_writing_boundary") == ""  # wrapper returns r.text


def test_boundary_result_reports_how_many_items_were_dropped(client, two_chapters, monkeypatch) -> None:
    uid, _c1, c2 = two_chapters
    _mock_model(monkeypatch, _payload(repeated_events=GOOD_REP + BAD_REP + BAD_REP))
    res = _direct(uid, c2, "check_writing_boundary_result")
    assert res.note == "" and res.dropped == 2 and res.text.startswith(BOUNDARY_HEADER)


def test_retry_never_happens_more_than_once(client, two_chapters, monkeypatch) -> None:
    uid, _c1, c2 = two_chapters
    prompts = _mock_model(monkeypatch, _payload(repeated_events=BAD_REP))
    _ex(uid, c2)
    assert len(prompts) == 2  # exactly one retry, never a third call


def test_nothing_offered_is_not_a_retry_trigger(client, two_chapters, monkeypatch) -> None:
    """The model legitimately returned no evidence at all: that is a valid (empty) answer, not a failure."""
    uid, _c1, c2 = two_chapters
    prompts = _mock_model(monkeypatch, _payload())
    _text, status, _note = _ex(uid, c2)
    assert len(prompts) == 1 and status == "ok"


def test_sse_write_is_not_aborted_when_every_quote_is_invented(client, two_chapters, monkeypatch) -> None:
    """End to end through the real route: no 502, the first SSE frame carries the failure notice,
    and the prose still streams (this is the bug the user hit)."""
    from contextlib import asynccontextmanager
    uid, _c1, c2 = two_chapters
    _mock_model(monkeypatch, _payload(repeated_events=BAD_REP))

    @asynccontextmanager
    async def fake_stream(self, method, url, **kw):
        yield httpx.Response(200, text='data: {"choices":[{"delta":{"content":"正文"}}]}\n\ndata: [DONE]\n\n',
                             request=httpx.Request(method, url))

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)
    r = client.post(f"/api/stream/novels/{uid}/write", json={"chapter_id": c2, "existing_content": "", "mode": "scene"})
    assert r.status_code == 200
    meta = json.loads(r.text.split("\n\n", 1)[0].split("data: ", 1)[1])
    assert meta["boundary_status"] == "failed" and meta["boundary_note"].startswith("衔接检查未生效")
    assert "event: delta" in r.text and "正文" in r.text and "event: error" not in r.text


def test_sse_meta_frame_carries_boundary_failure_notice(client: TestClient, two_chapters, monkeypatch) -> None:
    """End to end: when the check fails the FIRST SSE frame tells the UI so, and writing still proceeds."""
    from contextlib import asynccontextmanager
    uid, _c1, c2 = two_chapters

    async def fake_post(self, url, **kw):
        return httpx.Response(200, json=_chat("不是JSON"), request=httpx.Request("POST", url))

    @asynccontextmanager
    async def fake_stream(self, method, url, **kw):
        yield httpx.Response(200, text='data: {"choices":[{"delta":{"content":"正文"}}]}\n\ndata: [DONE]\n\n',
                             request=httpx.Request(method, url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)
    r = client.post(f"/api/stream/novels/{uid}/write",
                    json={"chapter_id": c2, "existing_content": "", "mode": "scene"})
    assert r.status_code == 200
    first = r.text.split("\n\n", 1)[0]
    assert first.startswith("event: meta")
    meta = json.loads(first.split("data: ", 1)[1])
    assert meta["boundary_status"] == "failed"
    assert meta["boundary_note"].startswith("衔接检查未生效")
    assert meta["model"] == "deepseek-chat" and "generation_id" in meta  # core keys intact
    assert "event: delta" in r.text and "正文" in r.text  # generation was NOT blocked


def test_sse_meta_for_opening_chapter_reports_skipped(client: TestClient, two_chapters, monkeypatch) -> None:
    from contextlib import asynccontextmanager
    uid, c1, _c2 = two_chapters

    @asynccontextmanager
    async def fake_stream(self, method, url, **kw):
        yield httpx.Response(200, text="data: [DONE]\n\n", request=httpx.Request(method, url))

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)
    r = client.post(f"/api/stream/novels/{uid}/write",
                    json={"chapter_id": c1, "existing_content": "", "mode": "scene"})
    meta = json.loads(r.text.split("\n\n", 1)[0].split("data: ", 1)[1])
    assert meta["boundary_status"] == "skipped" and "boundary_note" not in meta


def test_unavailable_notice_text() -> None:
    n = unavailable_notice("timeout")
    assert n.startswith("衔接检查未生效（timeout）")


def test_boundary_timeout_defaults_to_40_and_is_configurable(monkeypatch) -> None:
    monkeypatch.delenv("YOUTHINK_BOUNDARY_TIMEOUT_SEC", raising=False)
    assert boundary_timeout_sec() == 40.0
    monkeypatch.setenv("YOUTHINK_BOUNDARY_TIMEOUT_SEC", "30")
    assert boundary_timeout_sec() == 30.0
    monkeypatch.setenv("YOUTHINK_BOUNDARY_TIMEOUT_SEC", "45")
    assert boundary_timeout_sec() == 45.0
    monkeypatch.setenv("YOUTHINK_BOUNDARY_TIMEOUT_SEC", "not-a-number")
    assert boundary_timeout_sec() == 40.0
    monkeypatch.setenv("YOUTHINK_BOUNDARY_TIMEOUT_SEC", "1")
    assert boundary_timeout_sec() == 5.0  # clamped to the sane lower bound
    monkeypatch.setenv("YOUTHINK_BOUNDARY_TIMEOUT_SEC", "999")
    assert boundary_timeout_sec() == 120.0  # clamped upper bound


def test_boundary_call_passes_the_configured_timeout(client, two_chapters, monkeypatch) -> None:
    """The 30–45 s setting must reach complete_chat; worst case is two attempts."""
    from types import SimpleNamespace
    import app.services.writing_boundary as wb

    uid, _c1, c2 = two_chapters
    monkeypatch.setenv("YOUTHINK_BOUNDARY_TIMEOUT_SEC", "30")
    seen: dict = {}

    async def fake_complete_chat(**kw):
        seen.update(kw)
        return SimpleNamespace(content=_payload(repeated_events=GOOD_REP))

    monkeypatch.setattr(wb, "complete_chat", fake_complete_chat)
    text, status, note = _ex(uid, c2)
    assert status == "ok" and note == "" and "本场景从这里接" in text
    assert seen["timeout_sec"] == 30.0


# ---- normalize & evidence_in_history --------------------------------------------------------

def test_normalize_keeps_only_letters_and_digits() -> None:
    """_normalize_for_match strips ALL punctuation, spaces, and control characters."""
    assert _normalize_for_match("他，好吗？") == "他好吗"
    assert _normalize_for_match("  宿舍在四楼。 \n") == "宿舍在四楼"
    assert _normalize_for_match("走读的。") == "走读的"
    assert _normalize_for_match('"走读的"。') == "走读的"  # smart quotes gone
    # empty / pure punctuation normalizes to empty string
    assert _normalize_for_match("…——，") == ""


def test_evidence_in_history_rejects_empty_normalized_quote() -> None:
    # A quote that normalizes to '' must not match ('' in any_string is always True).
    assert not evidence_in_history("…——", "任何前文都不算")
    assert not evidence_in_history("", "任何前文")


# ---- real failures from generation_logs (tests/fixtures/boundary_evidence_failures.json) -----
# Every quote below was returned by the real model and rejected by the pre-fix check. Categories:
# a = punctuation/quote/line-break only, c = stitched from several places, d = words changed.

FAILS = json.loads(
    (Path(__file__).parent / "fixtures" / "boundary_evidence_failures.json").read_text(encoding="utf-8")
)
FCASES = FAILS["cases"]
FCALLS = FAILS["calls"]
_A = [c for c in FCASES if c["category"] == "a"]
_NOT_A = [c for c in FCASES if c["category"] != "a"]


def _in_history(case: dict) -> bool:
    return evidence_in_history(case["quote"], _normalize_for_match(FCALLS[case["call"]]["history"]))


def test_fixture_is_the_real_data_we_investigated() -> None:
    cats = sorted(c["category"] for c in FCASES)
    assert cats == ["a", "a", "c", "c", "d", "d", "d", "d", "d", "d"]  # 10 rejected quotes in 22 real calls
    assert {"LIVE#83", "LIVE#86", "LIVE#87"} <= set(FCALLS)  # the three failures in the live database
    assert all(c["call"].startswith(("LIVE", "bak")) for c in FCASES)


@pytest.mark.parametrize("case", _A, ids=lambda c: f"{c['call']}-{c['field']}[{c['index']}]")
def test_real_format_only_drift_now_matches(case) -> None:
    """(a) The model moved the full stop across a closing quote / dropped a lead-in word. Same text."""
    assert _in_history(case)


@pytest.mark.parametrize("case", _NOT_A, ids=lambda c: f"{c['call']}-{c['field']}[{c['index']}]-{c['category']}")
def test_real_altered_or_stitched_quotes_are_still_rejected(case) -> None:
    """(c)/(d) The model swapped 他/她/名字, reordered words, or stitched sentences with text it invented.
    Looser normalization must not turn these into matches."""
    assert not _in_history(case)


def test_the_stitched_quote_skips_a_clause_that_sits_between_its_real_pieces() -> None:
    """(c) Every piece of the quote is real text, but the model dropped the clause that separates them in
    the chapter, so the whole is not one continuous passage and must not be accepted."""
    c = next(c for c in FCASES if c["category"] == "c")
    hn = _normalize_for_match(FCALLS[c["call"]]["history"])
    pieces = [p for p in c["quote"].split("\n\n") if p.strip()]
    skipped = "江澈的手指停在屏幕上方，还没落下去"
    assert len(pieces) == 3
    assert all(evidence_in_history(p, hn) for p in pieces)  # each piece exists on its own
    assert not evidence_in_history(c["quote"], hn)  # ...but not as the contiguous passage claimed
    assert evidence_in_history(pieces[0] + skipped + pieces[1], hn)  # the skipped clause is what separates them


def test_normalization_keeps_pronoun_and_word_order_differences() -> None:
    """The looser normalization only ignores punctuation/whitespace/width/case, never words."""
    hn = _normalize_for_match("他用两指把画面撑大。第二天我提前查了轮渡时刻表。")
    assert not evidence_in_history("她用两指把画面撑大", hn)  # 他 -> 她
    assert not evidence_in_history("我第二天提前查了轮渡时刻表", hn)  # word order
    assert evidence_in_history("“他用两指，把画面撑大！”", hn)  # punctuation only -> fine


def test_normalize_is_symmetric_and_width_insensitive() -> None:
    assert _normalize_for_match("ＡＢＣ１２３，Ｄ！") == _normalize_for_match("abc123 d?") == "abc123d"
    assert _normalize_for_match("走读的。”") == _normalize_for_match("“走读的”。") == "走读的"
    assert _normalize_for_match("") == "" and _normalize_for_match("……——「」") == ""
    assert not evidence_in_history("……——", _normalize_for_match("任何前文"))  # '' must never match everything


def test_real_calls_that_used_to_abort_now_keep_their_good_items(client, two_chapters, monkeypatch) -> None:
    """Replay each real model output through check_writing_boundary_result with the real history.
    Before the fix 6 of these 9 calls raised BOUNDARY_EVIDENCE_MISMATCH (the other 3 are controls that
    passed); now none raises and none needs a retry."""
    from app.services.writing_boundary import check_writing_boundary_result
    uid, _c1, _c2 = two_chapters
    results = {}
    for name, call in FCALLS.items():
        prompts = _mock_model(monkeypatch, json.dumps(call["output"], ensure_ascii=False))
        with get_global_db() as g:
            res = asyncio.run(check_writing_boundary_result(
                novel_uid=uid, chapter_id=1, settings=SettingsRepository(g),
                history=call["history"], plan="本次计划",
            ))
        assert len(prompts) == 1, f"{name}: should not need a retry"
        assert res.note == "" and res.text.startswith(BOUNDARY_HEADER), name
        results[name] = res
    # LIVE#86/#87 used to abort on a repeated_event; they have `avoid`, so those quotes are not injected
    assert "已写过、不要再写：" in results["LIVE#87"].text
