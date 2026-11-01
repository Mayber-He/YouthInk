"""T1: per-item tolerant memory extraction parsing + quote validation + fallback.

Uses the real model output from generation_logs id=77 (chapter《江边黄昏》) as a
fixed sample — NO live LLM. See docs/loop/PROGRESS.md for provenance.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.memory.extraction_parse import (
    normalize_for_quote_match,
    parse_extraction_items,
)

FIXTURES = Path(__file__).parent / "fixtures"
LOG77_OUTPUT = (FIXTURES / "memory_extract_log77_output.json").read_text(encoding="utf-8")
LOG77_CHAPTER = (FIXTURES / "memory_extract_log77_chapter.txt").read_text(encoding="utf-8")


def test_log77_real_sample_does_not_fail_batch_and_keeps_valid_items() -> None:
    """The log-77 output drifts field names for 5 of 6 categories.

    Old behaviour: whole-payload validate silently produced empty items.
    New behaviour: facts (schema-correct here) are kept; the field-drifted
    categories are dropped item-by-item. The batch never raises.
    """
    r = parse_extraction_items(LOG77_OUTPUT, LOG77_CHAPTER)

    assert r.raw_items == 30
    # All 10 facts use {content, source_quote} which match the schema -> kept.
    assert len(r.output.facts) == 10
    assert r.kept == 10
    # The other 20 items use wrong field names (entity/change, characters, ...) -> dropped.
    assert r.dropped_invalid == 20
    assert r.dropped_quote == 0
    # Partial, not failed: something survived.
    assert r.status == "partial"
    # Dropped items are logged with a reason.
    assert any("state_changes" in msg for msg in r.drop_log)


def test_quote_must_exist_verbatim_in_chapter() -> None:
    """An item whose source_quote is not in the chapter is dropped as hallucinated."""
    payload = {
        "facts": [
            {
                "content": "真实事实",
                "source_quote": "江澈把王姨那台旧喷墨打印机搬上餐桌",  # present verbatim
            },
            {
                "content": "编造事实",
                "source_quote": "江澈开着跑车冲进了燃烧的大楼",  # not in chapter
            },
        ],
        "state_changes": [],
        "cognitive_records": [],
        "relationship_changes": [],
        "foreshadowing": [],
        "constraint_checks": [],
    }
    r = parse_extraction_items(json.dumps(payload, ensure_ascii=False), LOG77_CHAPTER)
    assert len(r.output.facts) == 1
    assert r.output.facts[0].content == "真实事实"
    assert r.dropped_quote == 1
    assert r.status == "partial"


def test_quote_match_tolerates_punctuation_and_whitespace() -> None:
    """Smart-quote / whitespace drift in the quote should NOT drop a valid item."""
    chapter = '他说：“我只管接起来。”\n然后放下了手机。'
    payload = {
        "facts": [
            {"content": "江澈只管接起来", "source_quote": "我只管接起来"},  # no punctuation
        ],
        "state_changes": [],
        "cognitive_records": [],
        "relationship_changes": [],
        "foreshadowing": [],
        "constraint_checks": [],
    }
    r = parse_extraction_items(json.dumps(payload, ensure_ascii=False), chapter)
    assert len(r.output.facts) == 1
    assert r.dropped_quote == 0


def test_well_formed_payload_all_six_categories_kept() -> None:
    """A schema-correct payload across all six categories is fully retained -> ok."""
    chapter = (
        "林栀在钢琴谱架下捡到一张泛黄的手写乐谱，背面写着缩写 SJ。"
        "沈倦推门而入，左手腕上多了一道擦伤。他其实早就知道林栀每天都在这里练琴。"
    )
    payload = {
        "facts": [
            {
                "content": "林栀捡到乐谱",
                "fact_type": "item",
                "character_names": ["林栀"],
                "location_names": [],
                "source_quote": "林栀在钢琴谱架下捡到一张泛黄的手写乐谱",
            }
        ],
        "state_changes": [
            {
                "character_name": "沈倦",
                "field": "body",
                "value": "左手腕擦伤",
                "source_quote": "左手腕上多了一道擦伤",
            }
        ],
        "cognitive_records": [
            {
                "secret": "沈倦早知道林栀在此练琴",
                "knower_names": ["沈倦"],
                "learned_by": "暗中观察",
                "source_quote": "他其实早就知道林栀每天都在这里练琴",
            }
        ],
        "relationship_changes": [
            {
                "char_a_name": "林栀",
                "char_b_name": "沈倦",
                "rel_type": "同校同学",
                "intimacy": 6,
                "publicity": "mutual",
                "change_reason": "琴房偶遇",
                "source_quote": "沈倦推门而入",
            }
        ],
        "foreshadowing": [
            {
                "description": "缩写SJ的含义",
                "status": "planted",
                "source_quote": "背面写着缩写 SJ",
            }
        ],
        "constraint_checks": [],
    }
    r = parse_extraction_items(json.dumps(payload, ensure_ascii=False), chapter)
    assert r.kept == 5
    assert r.dropped_invalid == 0
    assert r.dropped_quote == 0
    assert r.status == "ok"
    assert len(r.output.state_changes) == 1
    assert len(r.output.cognitive_records) == 1
    assert len(r.output.relationship_changes) == 1
    assert len(r.output.foreshadowing) == 1


def test_bad_outer_json_raises_valueerror() -> None:
    """Un-parseable outer JSON raises ValueError so the caller can retry/fallback."""
    with pytest.raises(ValueError):
        parse_extraction_items("this is not json at all {", LOG77_CHAPTER)


def test_empty_arrays_are_failed_status() -> None:
    """Valid JSON with no items at all is 'failed' (nothing extracted)."""
    payload = {
        "facts": [],
        "state_changes": [],
        "cognitive_records": [],
        "relationship_changes": [],
        "foreshadowing": [],
        "constraint_checks": [],
    }
    r = parse_extraction_items(json.dumps(payload), LOG77_CHAPTER)
    assert r.raw_items == 0
    assert r.kept == 0
    assert r.status == "failed"


def test_normalize_for_quote_match_folds_variants() -> None:
    assert normalize_for_quote_match("他 说 ：“好”") == normalize_for_quote_match('他说:"好"')


# --- Integration: finalize end-to-end with a mocked, field-drifted model output ---

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import reset_config_for_testing  # noqa: E402
from app.db.manager import ensure_global_db_initialized  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture()
def client(tmp_path):
    reset_config_for_testing(tmp_path / "test_data_t1")
    ensure_global_db_initialized()
    app = create_app()
    with TestClient(app) as tc:
        yield tc


def _mk_novel_with_chapter(client: TestClient, chapter_text: str):
    client.post(
        "/api/v1/settings/llm-profiles",
        json={
            "name": "T1Provider",
            "base_url": "https://api.example.com/v1",
            "model": "deepseek-chat",
            "api_key": "sk-t1-secret",
            "is_default": True,
        },
    )
    uid = client.post("/api/v1/novels", json={"title": "江边黄昏测试"}).json()["novel_uid"]
    client.post(
        f"/api/v1/novels/{uid}/characters",
        json={"name": "江澈", "role": "male_lead"},
    )
    v = client.post(f"/api/v1/novels/{uid}/outline/volumes", json={"title": "第一卷"}).json()["id"]
    a = client.post(
        f"/api/v1/novels/{uid}/outline/arcs", json={"volume_id": v, "title": "第一弧"}
    ).json()["id"]
    ch = client.post(
        f"/api/v1/novels/{uid}/outline/chapters",
        json={"arc_id": a, "title": "江边黄昏", "synopsis": "修打印机"},
    ).json()["id"]
    client.put(
        f"/api/v1/novels/{uid}/chapters/{ch}/content",
        json={"content": chapter_text, "source": "manual", "create_new_version": True},
    )
    return uid, ch


def test_finalize_with_field_drifted_output_is_partial_not_crash(
    client: TestClient, monkeypatch
) -> None:
    """The real log-77 output (field names drifted) must finalize as 'partial',
    keep the 10 schema-correct facts, and never raise."""
    chapter_text = LOG77_CHAPTER
    uid, ch = _mk_novel_with_chapter(client, chapter_text)

    calls = {"n": 0}

    async def fake_post(self, url, **kwargs):
        calls["n"] += 1
        req = httpx.Request("POST", url)
        if calls["n"] == 1:
            body = {"choices": [{"message": {"content": "江澈修好了打印机。"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
        else:
            body = {"choices": [{"message": {"content": LOG77_OUTPUT}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 200}}
        return httpx.Response(200, json=body, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    res = client.post(f"/api/v1/novels/{uid}/chapters/{ch}/finalize")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "final"
    assert data["extraction_status"] == "partial"

    # The 10 facts are persisted (auto-confirmed by trust mode default).
    pq = client.get(
        f"/api/v1/novels/{uid}/memory/pending-queue", params={"status": "confirmed"}
    ).json()
    facts = [i for i in pq if i["item_type"] == "fact"]
    assert len(facts) == 10


def test_finalize_unparseable_output_falls_back_pending(
    client: TestClient, monkeypatch
) -> None:
    """Totally unparseable extraction -> 'failed' status + a single pending
    fallback fact that is NOT auto-confirmed."""
    chapter_text = "江澈把打印机搬上餐桌，底下垫了两层报纸。"
    uid, ch = _mk_novel_with_chapter(client, chapter_text)

    calls = {"n": 0}

    async def fake_post(self, url, **kwargs):
        calls["n"] += 1
        req = httpx.Request("POST", url)
        if calls["n"] == 1:
            body = {"choices": [{"message": {"content": "摘要。"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
        else:
            # Both the first extract attempt and the retry return garbage.
            body = {"choices": [{"message": {"content": "对不起我无法完成这个任务。"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 10}}
        return httpx.Response(200, json=body, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    res = client.post(f"/api/v1/novels/{uid}/chapters/{ch}/finalize")
    assert res.status_code == 200
    data = res.json()
    assert data["extraction_status"] == "failed"
    # Fallback fact went to pending (never auto-confirmed), so auto_confirmed==0.
    assert data["auto_confirmed_count"] == 0
    pending = client.get(
        f"/api/v1/novels/{uid}/memory/pending-queue", params={"status": "pending"}
    ).json()
    fallback = [i for i in pending if i["item_type"] == "fact"]
    assert len(fallback) == 1
    assert "待人工确认" in fallback[0]["summary_text"]
    # A retry was attempted (extract called at least twice after the summary call).
    assert calls["n"] >= 3
