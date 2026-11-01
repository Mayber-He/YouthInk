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
    boundary_slim_enabled,
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


def test_fabricated_evidence_still_aborts(client: TestClient, two_chapters, monkeypatch) -> None:
    """Hallucination guard unchanged: made-up evidence_quote -> hard error, nothing injected."""
    uid, _c1, c2 = two_chapters
    bad = {"established": [{"statement": "宿舍在五楼", "evidence_quote": "宿舍在五楼。"}],
           "repeated_events": [], "next_step": "接着写。", "avoid": []}

    async def fake_post(self, url, **kw):
        return httpx.Response(200, json=_chat(json.dumps(bad, ensure_ascii=False)),
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    from app.core.exceptions import AppError
    with get_novel_db(uid) as n, get_global_db() as g:
        svc = WritingService(uid, n, SettingsRepository(g))
        with pytest.raises(AppError) as ei:
            asyncio.run(svc.check_write_boundary_ex(StreamWriteRequest(chapter_id=c2)))
    assert ei.value.code == "BOUNDARY_EVIDENCE_MISMATCH"


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
