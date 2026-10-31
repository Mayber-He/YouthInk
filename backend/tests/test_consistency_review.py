"""Phase 3 tests: checklist-based Consistency Review (flags only, never auto-edits)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import reset_config_for_testing
from app.db.manager import ensure_global_db_initialized
from app.main import create_app


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    reset_config_for_testing(tmp_path / "test_data_review")
    ensure_global_db_initialized()
    app = create_app()
    return TestClient(app)


@pytest.fixture()
def novel_uid(client: TestClient) -> str:
    resp = client.post(
        "/api/v1/novels",
        json={
            "title": "审查测试小说",
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


def _setup_llm_profile(client: TestClient) -> None:
    r = client.post(
        "/api/v1/settings/llm-profiles",
        json={
            "name": "ReviewTestProvider",
            "base_url": "https://api.example.com/v1",
            "model": "deepseek-chat",
            "api_key": "sk-test123456",
            "is_default": True,
        },
    )
    assert r.status_code in (200, 201)


def _make_chapter_with_content(client: TestClient, uid: str, char_id: int, text: str) -> int:
    v_id = client.post(
        f"/api/v1/novels/{uid}/outline/volumes", json={"title": "第一卷"}
    ).json()["id"]
    a_id = client.post(
        f"/api/v1/novels/{uid}/outline/arcs",
        json={"volume_id": v_id, "title": "开学篇"},
    ).json()["id"]
    ch = client.post(
        f"/api/v1/novels/{uid}/outline/chapters",
        json={"arc_id": a_id, "title": "第一章", "synopsis": "报到"},
    ).json()["id"]
    client.post(
        f"/api/v1/novels/{uid}/chapters/{ch}/scenes",
        json={
            "beat": "林夏报到",
            "pov_character": char_id,
            "character_ids": [char_id],
            "target_words": 800,
        },
    )
    r = client.put(
        f"/api/v1/novels/{uid}/chapters/{ch}/content",
        json={"content": text, "source": "manual", "create_new_version": True},
    )
    assert r.status_code == 200
    return ch


def _mock_review_response(monkeypatch: pytest.MonkeyPatch, issues: list) -> None:
    async def fake_post(self, url: str, **kwargs):
        req = httpx.Request("POST", url)
        body = {
            "choices": [
                {"message": {"content": json.dumps({"issues": issues}, ensure_ascii=False)}}
            ],
            "usage": {"prompt_tokens": 200, "completion_tokens": 120},
        }
        return httpx.Response(200, json=body, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)


def test_consistency_review_detects_violation(
    client: TestClient, novel_uid: str, monkeypatch: pytest.MonkeyPatch, character_id: int
) -> None:
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
    ch = _make_chapter_with_content(
        client,
        novel_uid,
        character_id,
        "林夏轻车熟路地穿过校园，对这所学校了如指掌。",
    )
    _mock_review_response(
        monkeypatch,
        [
            {
                "check_type": "constraint",
                "ref_id": con["id"],
                "ref_label": f"硬约束#{con['id']}",
                "verdict": "violation",
                "evidence_quote": "林夏轻车熟路地穿过校园，对这所学校了如指掌",
                "description": "违反硬约束：大一新生不应熟知校园",
                "suggestion": "改为林夏拿着地图四处张望",
            }
        ],
    )

    r = client.post(f"/api/v1/novels/{novel_uid}/chapters/{ch}/consistency-review")
    assert r.status_code == 201
    data = r.json()
    assert data["issue_count"] == 1
    assert data["violation_count"] == 1
    assert "1 项违反" in data["summary"]
    issue = data["issues"][0]
    assert issue["verdict"] == "violation"
    assert issue["evidence_quote"].startswith("林夏轻车熟路")
    assert issue["suggestion"] != ""

    # Report is persisted and listable
    lst = client.get(f"/api/v1/novels/{novel_uid}/chapters/{ch}/consistency-reviews").json()
    assert len(lst) == 1
    assert lst[0]["id"] == data["id"]
    detail = client.get(
        f"/api/v1/novels/{novel_uid}/consistency-reviews/{data['id']}"
    ).json()
    assert detail["issue_count"] == 1
    assert detail["issues"][0]["description"].startswith("违反硬约束")


def test_consistency_review_clean(
    client: TestClient, novel_uid: str, monkeypatch: pytest.MonkeyPatch, character_id: int
) -> None:
    _setup_llm_profile(client)
    ch = _make_chapter_with_content(
        client,
        novel_uid,
        character_id,
        "林夏拿着新生手册，在校园里转了三圈才找到宿舍楼。",
    )
    _mock_review_response(monkeypatch, [])

    r = client.post(f"/api/v1/novels/{novel_uid}/chapters/{ch}/consistency-review")
    assert r.status_code == 201
    data = r.json()
    assert data["issue_count"] == 0
    assert data["violation_count"] == 0
    assert "未发现问题" in data["summary"]


def test_consistency_review_empty_content_rejected(
    client: TestClient, novel_uid: str, character_id: int
) -> None:
    _setup_llm_profile(client)
    v_id = client.post(
        f"/api/v1/novels/{novel_uid}/outline/volumes", json={"title": "第一卷"}
    ).json()["id"]
    a_id = client.post(
        f"/api/v1/novels/{novel_uid}/outline/arcs",
        json={"volume_id": v_id, "title": "开学篇"},
    ).json()["id"]
    ch = client.post(
        f"/api/v1/novels/{novel_uid}/outline/chapters",
        json={"arc_id": a_id, "title": "空章", "synopsis": "无内容"},
    ).json()["id"]

    r = client.post(f"/api/v1/novels/{novel_uid}/chapters/{ch}/consistency-review")
    assert r.status_code == 400
