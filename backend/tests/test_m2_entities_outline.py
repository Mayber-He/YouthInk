"""Unit and integration tests for M2 Settings & Outline (CRUD, Locking, Timeline, Float Sort, AI Chain)."""

from __future__ import annotations

import json
from pathlib import Path
from fastapi.testclient import TestClient
import httpx
import pytest

from app.core.config import reset_config_for_testing
from app.db.manager import ensure_global_db_initialized, get_novel_db
from app.main import create_app


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    reset_config_for_testing(tmp_path / "test_data_m2")
    ensure_global_db_initialized()
    app = create_app()
    c = TestClient(app)
    c.post(
        "/api/v1/settings/llm-profiles",
        json={
            "name": "Test Planner",
            "base_url": "https://api.example.com/v1",
            "model": "deepseek-chat",
            "api_key": "sk-test123456",
            "is_default": True,
        },
    )
    return c


@pytest.fixture()
def novel_uid(client: TestClient) -> str:
    resp = client.post(
        "/api/v1/novels",
        json={
            "title": "香樟树下的秘密",
            "genre": "校园",
            "tone": "清新治愈",
            "pov": "第三人称限知",
            "protagonist_concept": "转校生林夏与学神陆川",
            "synopsis": "高二分班后两人成为同桌，共同经历竞赛与艺术联考的成长故事。",
            "romance_ending": "HE",
            "growth_ending": "HE",
        },
    )
    assert resp.status_code == 201
    return str(resp.json()["novel_uid"])


def test_worldview_locking_and_ai_generation(
    client: TestClient, novel_uid: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 1. Create 1 locked entry and 1 unlocked entry
    r1 = client.post(
        f"/api/v1/novels/{novel_uid}/worldview",
        json={"category": "school", "content": "南城一中实行走班选科制", "locked": True},
    )
    r2 = client.post(
        f"/api/v1/novels/{novel_uid}/worldview",
        json={"category": "era", "content": "旧版时代背景（未锁定）", "locked": False},
    )
    assert r1.status_code == 201 and r2.status_code == 201

    # 2. Mock AI generation returning 2 new worldview entries
    async def fake_post(self, url: str, **kwargs):  # type: ignore[no-untyped-def]
        payload = json.dumps(
            {
                "items": [
                    {"category": "era", "content": "2018年南方沿海城市高中"},
                    {"category": "culture", "content": "晚自习课间流行在广播站匿名点歌"},
                ]
            },
            ensure_ascii=False,
        )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": f"```json\n{payload}\n```"}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 60},
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    gen_resp = client.post(
        f"/api/v1/novels/{novel_uid}/worldview/generate",
        json={"instruction": "突出南方沿海气息", "count": 2},
    )
    assert gen_resp.status_code == 200
    items = gen_resp.json()
    contents = [item["content"] for item in items]

    # Locked entry MUST be preserved, unlocked entry MUST be replaced
    assert "南城一中实行走班选科制" in contents
    assert "旧版时代背景（未锁定）" not in contents
    assert "2018年南方沿海城市高中" in contents


def test_character_timeline_temporal_query(client: TestClient, novel_uid: str) -> None:
    # Create two characters
    c1 = client.post(
        f"/api/v1/novels/{novel_uid}/characters",
        json={
            "name": "林夏",
            "role": "female_lead",
            "appearance": "齐肩长发，穿宽大校服",
        },
    ).json()
    c2 = client.post(
        f"/api/v1/novels/{novel_uid}/characters",
        json={"name": "陆川", "role": "male_lead", "appearance": "白衬衫少年"},
    ).json()

    # Create volume -> arc -> 3 chapters with sort_order 1.0, 2.0, 3.0
    vol = client.post(
        f"/api/v1/novels/{novel_uid}/outline/volumes",
        json={"title": "第一卷"},
    ).json()
    arc = client.post(
        f"/api/v1/novels/{novel_uid}/outline/arcs",
        json={"volume_id": vol["id"], "title": "第一弧"},
    ).json()
    ch1 = client.post(
        f"/api/v1/novels/{novel_uid}/outline/chapters",
        json={"arc_id": arc["id"], "title": "第一章", "sort_order": 1.0},
    ).json()
    ch2 = client.post(
        f"/api/v1/novels/{novel_uid}/outline/chapters",
        json={"arc_id": arc["id"], "title": "第二章", "sort_order": 2.0},
    ).json()
    ch3 = client.post(
        f"/api/v1/novels/{novel_uid}/outline/chapters",
        json={"arc_id": arc["id"], "title": "第三章", "sort_order": 3.0},
    ).json()

    # Seed confirmed & pending state changes in novel.db
    with get_novel_db(novel_uid) as conn:
        conn.execute(
            """
            INSERT INTO character_state_changes (character_id, chapter_id, field, value, confirm_status)
            VALUES
                (?, ?, 'emotion', '初来乍到有些紧张', 'confirmed'),
                (?, ?, 'emotion', '和陆川解开误会后释然', 'confirmed'),
                (?, ?, 'appearance', '剪了利落的短发', 'confirmed'),
                (?, ?, 'emotion', '未确认的幻觉情绪', 'pending')
            """,
            (c1["id"], ch1["id"], c1["id"], ch2["id"], c1["id"], ch3["id"], c1["id"], ch3["id"]),
        )
        conn.execute(
            """
            INSERT INTO relationship_changes (char_a_id, char_b_id, chapter_id, rel_type, intimacy, publicity, confirm_status)
            VALUES (?, ?, ?, '同桌兼好友', 7, 'public', 'confirmed')
            """,
            (c1["id"], c2["id"], ch2["id"]),
        )
        conn.execute(
            """
            INSERT INTO cognitive_records (secret, knower_ids, chapter_id, learned_by, confirm_status)
            VALUES ('陆川放弃了省队保送名额', ?, ?, '无意间看到申请表', 'confirmed')
            """,
            (json.dumps([c1["id"]]), ch2["id"]),
        )

    # Query timeline at chapter 1 (sort_order <= 1.0)
    snap1 = client.get(
        f"/api/v1/novels/{novel_uid}/characters/{c1['id']}/timeline?up_to_chapter_sort=1.0"
    ).json()
    assert snap1["current_states"]["emotion"] == "初来乍到有些紧张"
    assert snap1["relationships"] == []
    assert snap1["known_secrets"] == []

    # Query timeline at chapter 2 (sort_order <= 2.0)
    snap2 = client.get(
        f"/api/v1/novels/{novel_uid}/characters/{c1['id']}/timeline?up_to_chapter_sort=2.0"
    ).json()
    assert snap2["current_states"]["emotion"] == "和陆川解开误会后释然"
    assert len(snap2["relationships"]) == 1
    assert snap2["relationships"][0]["rel_type"] == "同桌兼好友"
    assert len(snap2["known_secrets"]) == 1

    # Query timeline at chapter 3 (sort_order <= 3.0) - pending item must be ignored!
    snap3 = client.get(
        f"/api/v1/novels/{novel_uid}/characters/{c1['id']}/timeline?up_to_chapter_sort=3.0"
    ).json()
    assert snap3["current_states"]["emotion"] == "和陆川解开误会后释然"
    assert "剪了利落的短发" in snap3["effective_appearance"]


def test_float_sort_order_and_rolling_chapter_generation(
    client: TestClient, novel_uid: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    vol = client.post(
        f"/api/v1/novels/{novel_uid}/outline/volumes",
        json={"title": "第一卷：盛夏"},
    ).json()
    arc = client.post(
        f"/api/v1/novels/{novel_uid}/outline/arcs",
        json={"volume_id": vol["id"], "title": "第一弧：初遇"},
    ).json()

    c1 = client.post(
        f"/api/v1/novels/{novel_uid}/outline/chapters",
        json={"arc_id": arc["id"], "title": "原第一章", "sort_order": 1.0, "locked": True},
    ).json()
    c2 = client.post(
        f"/api/v1/novels/{novel_uid}/outline/chapters",
        json={"arc_id": arc["id"], "title": "原第二章", "sort_order": 2.0, "locked": True},
    ).json()

    # Insert a chapter between c1 (1.0) and c2 (2.0) -> sort_order should be 1.5
    c_mid = client.post(
        f"/api/v1/novels/{novel_uid}/outline/chapters",
        json={
            "arc_id": arc["id"],
            "title": "插入的过渡章",
            "after_chapter_id": c1["id"],
            "before_chapter_id": c2["id"],
            "locked": False,
        },
    ).json()
    assert c_mid["sort_order"] == pytest.approx(1.5)

    tree = client.get(f"/api/v1/novels/{novel_uid}/outline").json()
    chapters = tree["volumes"][0]["arcs"][0]["chapters"]
    assert [ch["title"] for ch in chapters] == ["原第一章", "插入的过渡章", "原第二章"]
    assert [ch["display_index"] for ch in chapters] == [1, 2, 3]

    # Rolling AI generation for the arc should preserve locked chapters (c1, c2) and replace unlocked (c_mid)
    async def fake_post(self, url: str, **kwargs):  # type: ignore[no-untyped-def]
        payload = json.dumps(
            {
                "chapters": [
                    {"title": "AI生成第三章", "synopsis": "雨天共撑一把伞", "story_time": "九月中旬"},
                ]
            },
            ensure_ascii=False,
        )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": payload}}],
                "usage": {"prompt_tokens": 80, "completion_tokens": 50},
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    gen_tree = client.post(
        f"/api/v1/novels/{novel_uid}/outline/arcs/{arc['id']}/generate-chapters",
        json={"chapter_count": 1, "instruction": ""},
    ).json()
    final_titles = [ch["title"] for ch in gen_tree["volumes"][0]["arcs"][0]["chapters"]]
    assert "原第一章" in final_titles
    assert "原第二章" in final_titles
    assert "插入的过渡章" not in final_titles
    assert "AI生成第三章" in final_titles
