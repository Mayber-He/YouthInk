"""Unit and integration tests for the Explicit Constraint System (anti-hallucination)."""

from __future__ import annotations

from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from app.core.config import reset_config_for_testing
from app.db.manager import ensure_global_db_initialized
from app.main import create_app


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    reset_config_for_testing(tmp_path / "test_data_constraints")
    ensure_global_db_initialized()
    app = create_app()
    return TestClient(app)


@pytest.fixture()
def novel_uid(client: TestClient) -> str:
    resp = client.post(
        "/api/v1/novels",
        json={
            "title": "约束测试小说",
            "genre": "校园",
            "tone": "清新治愈",
            "pov": "第三人称限知",
            "protagonist_concept": "大一新生林夏",
            "synopsis": "新生入学故事",
            "romance_ending": "HE",
            "growth_ending": "HE",
        },
    )
    assert resp.status_code == 201
    return str(resp.json()["novel_uid"])


@pytest.fixture()
def character_id(client: TestClient, novel_uid: str) -> int:
    resp = client.post(
        f"/api/v1/novels/{novel_uid}/characters",
        json={"name": "林夏", "role": "female_lead", "background": "大一新生", "locked": True},
    )
    assert resp.status_code == 201
    return int(resp.json()["id"])


def test_constraint_crud(client: TestClient, novel_uid: str, character_id: int) -> None:
    # create
    r = client.post(
        f"/api/v1/novels/{novel_uid}/constraints",
        json={
            "target_type": "character",
            "target_id": character_id,
            "content": "大一新生，对校园不熟悉；绝不能写他对学校了如指掌",
            "severity": "hard",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["target_name"] == "林夏"
    assert body["status"] == "active"
    cid = body["id"]

    # list with filter
    r = client.get(
        f"/api/v1/novels/{novel_uid}/constraints",
        params={"target_type": "character", "target_id": character_id},
    )
    assert r.status_code == 200
    assert len(r.json()) == 1

    # update: resolve
    r = client.put(
        f"/api/v1/novels/{novel_uid}/constraints/{cid}",
        json={"status": "resolved"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "resolved"

    # resolved no longer listed under active filter
    r = client.get(
        f"/api/v1/novels/{novel_uid}/constraints",
        params={"status": "active"},
    )
    assert r.json() == []

    # delete
    r = client.delete(f"/api/v1/novels/{novel_uid}/constraints/{cid}")
    assert r.status_code == 204

    # 404 on missing
    r = client.put(
        f"/api/v1/novels/{novel_uid}/constraints/99999",
        json={"status": "resolved"},
    )
    assert r.status_code == 404


def test_active_constraints_for_chapter(
    client: TestClient, novel_uid: str, character_id: int
) -> None:
    # novel-wide soft constraint
    r = client.post(
        f"/api/v1/novels/{novel_uid}/constraints",
        json={
            "target_type": "novel",
            "content": "全书时间为2024年秋季学期",
            "severity": "soft",
        },
    )
    assert r.status_code == 201

    # character hard constraint
    r = client.post(
        f"/api/v1/novels/{novel_uid}/constraints",
        json={
            "target_type": "character",
            "target_id": character_id,
            "content": "大一新生，对校园不熟悉",
            "severity": "hard",
        },
    )
    assert r.status_code == 201

    # build outline: volume -> arc -> chapter (needed for chapter-scoped query)
    v = client.post(f"/api/v1/novels/{novel_uid}/outline/volumes", json={"title": "第一卷"}).json()
    a = client.post(
        f"/api/v1/novels/{novel_uid}/outline/arcs", json={"volume_id": v["id"], "title": "开学篇"}
    ).json()
    ch = client.post(
        f"/api/v1/novels/{novel_uid}/outline/chapters",
        json={"arc_id": a["id"], "title": "第一章", "synopsis": "报到"},
    ).json()
    chapter_id = ch["id"]

    # scene binds the character to the chapter
    r = client.post(
        f"/api/v1/novels/{novel_uid}/chapters/{chapter_id}/scenes",
        json={
            "beat": "林夏第一天到学校报到",
            "pov_character": character_id,
            "character_ids": [character_id],
            "target_words": 800,
        },
    )
    assert r.status_code in (200, 201)

    r = client.get(
        f"/api/v1/novels/{novel_uid}/chapters/{chapter_id}/active-constraints"
    )
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 2
    # hard constraints first
    assert items[0]["severity"] == "hard"
    assert "大一新生" in items[0]["content"]
    assert items[1]["severity"] == "soft"


def test_context_preview_includes_hard_constraints(
    client: TestClient, novel_uid: str, character_id: int
) -> None:
    client.post(
        f"/api/v1/novels/{novel_uid}/constraints",
        json={
            "target_type": "character",
            "target_id": character_id,
            "content": "大一新生，对校园不熟悉；绝不能写他对学校了如指掌",
            "severity": "hard",
        },
    )
    v = client.post(f"/api/v1/novels/{novel_uid}/outline/volumes", json={"title": "第一卷"}).json()
    a = client.post(
        f"/api/v1/novels/{novel_uid}/outline/arcs", json={"volume_id": v["id"], "title": "开学篇"}
    ).json()
    ch = client.post(
        f"/api/v1/novels/{novel_uid}/outline/chapters",
        json={"arc_id": a["id"], "title": "第一章", "synopsis": "报到"},
    ).json()
    chapter_id = ch["id"]
    client.post(
        f"/api/v1/novels/{novel_uid}/chapters/{chapter_id}/scenes",
        json={
            "beat": "林夏第一天到学校报到",
            "pov_character": character_id,
            "character_ids": [character_id],
            "target_words": 800,
        },
    )

    r = client.get(
        f"/api/v1/novels/{novel_uid}/chapters/{chapter_id}/context-preview"
    )
    assert r.status_code == 200
    blocks = {b["key"]: b for b in r.json()["blocks"]}
    assert "hard_constraints" in blocks
    block = blocks["hard_constraints"]
    assert block["enabled"] is True
    assert "大一新生" in block["content"]
    assert "动笔前请核对" in block["content"]
    assert "正文中不要复述检查过程" in block["content"]


# --- Phase 2: violation / resolution detection through finalize ---

def _setup_llm_profile(client: TestClient) -> None:
    r = client.post(
        "/api/v1/settings/llm-profiles",
        json={
            "name": "ConstraintTestProvider",
            "base_url": "https://api.example.com/v1",
            "model": "deepseek-chat",
            "api_key": "sk-test123456",
            "is_default": True,
        },
    )
    assert r.status_code in (200, 201)


def _make_extraction_response(checks: list) -> dict:
    import json as _json

    extraction = {
        "facts": [],
        "state_changes": [],
        "cognitive_records": [],
        "relationship_changes": [],
        "foreshadowing": [],
        "constraint_checks": checks,
    }
    return {
        "choices": [{"message": {"content": _json.dumps(extraction, ensure_ascii=False)}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 60},
    }


def test_finalize_detects_constraint_violation(
    client: TestClient, novel_uid: str, monkeypatch, character_id: int
) -> None:
    import httpx

    _setup_llm_profile(client)

    con = client.post(
        f"/api/v1/novels/{novel_uid}/constraints",
        json={
            "target_type": "character",
            "target_id": character_id,
            "content": "大一新生，对校园不熟悉；绝不能写他对学校了如指掌",
            "severity": "hard",
        },
    ).json()
    con_id = con["id"]

    v_id = client.post(
        f"/api/v1/novels/{novel_uid}/outline/volumes", json={"title": "第一卷"}
    ).json()["id"]
    a_id = client.post(
        f"/api/v1/novels/{novel_uid}/outline/arcs",
        json={"volume_id": v_id, "title": "开学篇"},
    ).json()["id"]
    ch1 = client.post(
        f"/api/v1/novels/{novel_uid}/outline/chapters",
        json={"arc_id": a_id, "title": "第一章", "synopsis": "报到"},
    ).json()["id"]
    ch2 = client.post(
        f"/api/v1/novels/{novel_uid}/outline/chapters",
        json={"arc_id": a_id, "title": "第二章", "synopsis": "军训"},
    ).json()["id"]
    client.post(
        f"/api/v1/novels/{novel_uid}/chapters/{ch1}/scenes",
        json={
            "beat": "林夏第一天报到",
            "pov_character": character_id,
            "character_ids": [character_id],
            "target_words": 800,
        },
    )
    violating_text = (
        "林夏轻车熟路地穿过校园，直奔实验楼三楼的阶梯教室，"
        "对这所学校了如指掌，仿佛在这里生活了四年。"
    )
    client.put(
        f"/api/v1/novels/{novel_uid}/chapters/{ch1}/content",
        json={"content": violating_text, "source": "manual", "create_new_version": True},
    )

    call_n = {"n": 0}

    async def fake_post(self, url: str, **kwargs):
        import json as _json

        call_n["n"] += 1
        req = httpx.Request("POST", url)
        if call_n["n"] % 2 == 1:
            body = {
                "choices": [{"message": {"content": "林夏第一天报到。"}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 20},
            }
        else:
            body = _make_extraction_response(
                [
                    {
                        "constraint_id": con_id,
                        "verdict": "violated",
                        "evidence_quote": "林夏轻车熟路地穿过校园，对这所学校了如指掌",
                        "description": "正文描写林夏对校园了如指掌，违反硬约束",
                    }
                ]
            )
        return httpx.Response(200, json=body, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    fin = client.post(f"/api/v1/novels/{novel_uid}/chapters/{ch1}/finalize")
    assert fin.status_code == 200
    assert fin.json()["pending_count"] >= 1

    pq = client.get(f"/api/v1/novels/{novel_uid}/memory/pending-queue").json()
    checks = [i for i in pq if i["item_type"] == "constraint_check"]
    assert len(checks) == 1
    assert "违反硬约束" in checks[0]["summary_text"]
    assert "轻车熟路" in checks[0]["source_quote"]

    # Confirm the violation -> constraint flagged as violated
    r = client.put(
        f"/api/v1/novels/{novel_uid}/memory/pending-queue/constraint_check/{checks[0]['id']}",
        json={"action": "confirm"},
    )
    assert r.status_code == 200
    con_after = client.get(
        f"/api/v1/novels/{novel_uid}/constraints",
        params={"target_type": "character", "target_id": character_id},
    ).json()
    assert con_after[0]["status"] == "violated"

    # Violated constraint is still injected for the next chapter, flagged
    ctx = client.get(
        f"/api/v1/novels/{novel_uid}/chapters/{ch2}/context-preview"
    ).json()
    block = next(b for b in ctx["blocks"] if b["key"] == "hard_constraints")
    assert "⚠️已确认违反" in block["content"]
    assert "大一新生" in block["content"]


def test_confirm_resolution_retires_constraint(
    client: TestClient, novel_uid: str, monkeypatch, character_id: int
) -> None:
    import httpx

    _setup_llm_profile(client)

    con = client.post(
        f"/api/v1/novels/{novel_uid}/constraints",
        json={
            "target_type": "character",
            "target_id": character_id,
            "content": "大一新生，对校园不熟悉",
            "severity": "hard",
        },
    ).json()
    con_id = con["id"]

    v_id = client.post(
        f"/api/v1/novels/{novel_uid}/outline/volumes", json={"title": "第一卷"}
    ).json()["id"]
    a_id = client.post(
        f"/api/v1/novels/{novel_uid}/outline/arcs",
        json={"volume_id": v_id, "title": "开学篇"},
    ).json()["id"]
    ch1 = client.post(
        f"/api/v1/novels/{novel_uid}/outline/chapters",
        json={"arc_id": a_id, "title": "第一章", "synopsis": "报到"},
    ).json()["id"]
    client.post(
        f"/api/v1/novels/{novel_uid}/chapters/{ch1}/scenes",
        json={
            "beat": "一个月后",
            "pov_character": character_id,
            "character_ids": [character_id],
            "target_words": 800,
        },
    )
    client.put(
        f"/api/v1/novels/{novel_uid}/chapters/{ch1}/content",
        json={
            "content": "一个月过去，林夏已经能闭着眼睛找到每一栋教学楼。",
            "source": "manual",
            "create_new_version": True,
        },
    )

    call_n = {"n": 0}

    async def fake_post(self, url: str, **kwargs):
        call_n["n"] += 1
        req = httpx.Request("POST", url)
        if call_n["n"] % 2 == 1:
            body = {
                "choices": [{"message": {"content": "一月后林夏熟悉校园。"}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 20},
            }
        else:
            body = _make_extraction_response(
                [
                    {
                        "constraint_id": con_id,
                        "verdict": "resolved",
                        "evidence_quote": "林夏已经能闭着眼睛找到每一栋教学楼",
                        "description": "剧情推进一个月，约束已自然解除",
                    }
                ]
            )
        return httpx.Response(200, json=body, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    fin = client.post(f"/api/v1/novels/{novel_uid}/chapters/{ch1}/finalize")
    assert fin.status_code == 200

    pq = client.get(f"/api/v1/novels/{novel_uid}/memory/pending-queue").json()
    checks = [i for i in pq if i["item_type"] == "constraint_check"]
    assert len(checks) == 1
    assert "约束疑似解除" in checks[0]["summary_text"]
    before = client.get(f"/api/v1/novels/{novel_uid}/constraints").json()
    assert next(c for c in before if c["id"] == con_id)["status"] == "active"
    assert checks[0]["status"] == "pending"

    r = client.put(
        f"/api/v1/novels/{novel_uid}/memory/pending-queue/constraint_check/{checks[0]['id']}",
        json={"action": "confirm"},
    )
    assert r.status_code == 200

    con_after = client.get(
        f"/api/v1/novels/{novel_uid}/constraints",
        params={"target_type": "character", "target_id": character_id},
    ).json()
    assert con_after[0]["status"] == "resolved"
    assert con_after[0]["valid_until_chapter_id"] == ch1
