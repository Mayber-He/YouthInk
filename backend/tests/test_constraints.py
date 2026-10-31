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
    assert "动笔前请先复述" in block["content"]
