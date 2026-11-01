"""T3: scene split as event checklist — parsing, beat serialization, dedup, re-split.

No live LLM; model responses are mocked.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import reset_config_for_testing
from app.db.manager import ensure_global_db_initialized
from app.main import create_app
from app.services.scene_planning import (
    DuplicatePair,
    describe_duplicates,
    find_adjacent_duplicates,
    format_scene_beat,
    ngram_similarity,
)


# --- Pure helpers ---

def test_ngram_similarity_bounds() -> None:
    assert ngram_similarity("江澈找到报到处", "江澈找到报到处") == pytest.approx(1.0)
    assert ngram_similarity("江澈找到报到处", "完全不同的另一句话内容") < 0.2
    assert ngram_similarity("", "任意") == 0.0


def test_format_scene_beat_omits_empty_sections() -> None:
    beat = format_scene_beat(
        goal="两人照面",
        entry_state="报到处前",
        must_happen=["江澈找到报到处", "裴南栀发材料", "两人加联系方式", "多余的第四条"],
        exit_state="拿到材料",
        must_not_include=["认出网友"],
    )
    assert "目标：两人照面" in beat
    assert "起点状态：报到处前" in beat
    # must_happen capped at 3
    assert "多余的第四条" not in beat
    assert "江澈找到报到处" in beat
    assert "终点状态：拿到材料" in beat
    assert "本场禁止出现：认出网友" in beat

    # Empty inputs -> empty string, no stray labels.
    assert format_scene_beat("", "", [], "", []) == ""


def test_find_adjacent_duplicates_flags_overlap() -> None:
    mh = [
        ["江澈找到报到处", "办理入学手续"],
        ["江澈找到报到处", "领到宿舍钥匙"],  # first item duplicates scene 1
        ["去食堂吃饭", "遇到室友"],
    ]
    dups = find_adjacent_duplicates(mh, threshold=0.6)
    assert any(d.index_a == 0 and d.index_b == 1 for d in dups)
    # scene 2 vs 3 are distinct -> no dup there
    assert not any(d.index_a == 1 and d.index_b == 2 for d in dups)
    assert "场景1" in describe_duplicates(dups)


def test_find_adjacent_duplicates_clean() -> None:
    mh = [["开学报到"], ["军训第一天"], ["选社团"]]
    assert find_adjacent_duplicates(mh) == []


# --- Integration via mocked model ---

@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    reset_config_for_testing(tmp_path / "test_data_t3")
    ensure_global_db_initialized()
    app = create_app()
    with TestClient(app) as tc:
        yield tc


def _setup(client: TestClient) -> tuple[str, int]:
    client.post(
        "/api/v1/settings/llm-profiles",
        json={"name": "T3P", "base_url": "https://api.example.com/v1",
              "model": "deepseek-chat", "api_key": "sk-t3", "is_default": True},
    )
    uid = client.post("/api/v1/novels", json={"title": "场景T3"}).json()["novel_uid"]
    client.post(f"/api/v1/novels/{uid}/characters",
                json={"name": "江澈", "role": "male_lead"})
    client.post(f"/api/v1/novels/{uid}/characters",
                json={"name": "裴南栀", "role": "female_lead"})
    client.post(f"/api/v1/novels/{uid}/locations", json={"name": "报到处"})
    v = client.post(f"/api/v1/novels/{uid}/outline/volumes", json={"title": "卷一"}).json()["id"]
    a = client.post(f"/api/v1/novels/{uid}/outline/arcs",
                    json={"volume_id": v, "title": "弧一"}).json()["id"]
    ch = client.post(f"/api/v1/novels/{uid}/outline/chapters",
                     json={"arc_id": a, "title": "报到日", "synopsis": "江澈报到遇到学姐"}).json()["id"]
    return uid, ch


def _scene_body(scenes: list[dict]) -> dict:
    return {
        "choices": [{"message": {"content": json.dumps({"scenes": scenes}, ensure_ascii=False)}}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 80},
    }


def test_generate_scenes_parses_checklist_into_beat(client: TestClient, monkeypatch) -> None:
    uid, ch = _setup(client)
    scenes = [
        {
            "goal": "江澈到达报到处",
            "entry_state": "江澈刚进校门",
            "must_happen": ["江澈找到报到处", "开始排队"],
            "exit_state": "轮到江澈办理",
            "must_not_include": ["认出网友"],
            "pov_character_name": "江澈",
            "location_name": "报到处",
            "character_names": ["江澈"],
            "story_time": "报到日上午",
            "target_words": 700,
        },
        {
            "goal": "裴南栀帮江澈办手续",
            "entry_state": "江澈站到窗口前",
            "must_happen": ["裴南栀发放材料", "两人加联系方式"],
            "exit_state": "江澈记住了这个学姐",
            "must_not_include": ["表白"],
            "pov_character_name": "江澈",
            "location_name": "报到处",
            "character_names": ["江澈", "裴南栀"],
            "story_time": "报到日上午",
            "target_words": 900,
        },
    ]

    async def fake_post(self, url, **kwargs):
        return httpx.Response(200, json=_scene_body(scenes), request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    resp = client.post(f"/api/v1/novels/{uid}/chapters/{ch}/scenes/generate",
                       json={"scene_count": 2})
    assert resp.status_code == 200
    out = resp.json()
    assert len(out) == 2
    # beat column holds the serialized checklist.
    assert "目标：江澈到达报到处" in out[0]["beat"]
    assert "必须发生：江澈找到报到处；开始排队" in out[0]["beat"]
    assert "本场禁止出现：认出网友" in out[0]["beat"]
    assert out[0]["pov_character"] is not None
    assert out[1]["target_words"] == 900


def test_generate_scenes_triggers_one_resplit_on_duplicate(client: TestClient, monkeypatch) -> None:
    uid, ch = _setup(client)
    dup_scenes = [
        {"goal": "报到", "entry_state": "进校门", "must_happen": ["江澈找到报到处并排队办理手续"],
         "exit_state": "办完", "must_not_include": [],
         "pov_character_name": "江澈", "character_names": ["江澈"], "target_words": 700},
        {"goal": "报到2", "entry_state": "窗口前", "must_happen": ["江澈找到报到处并排队办理手续"],
         "exit_state": "拿材料", "must_not_include": [],
         "pov_character_name": "江澈", "character_names": ["江澈"], "target_words": 700},
    ]
    clean_scenes = [
        {"goal": "报到", "entry_state": "进校门", "must_happen": ["江澈找到报到处排队"],
         "exit_state": "办完", "must_not_include": [],
         "pov_character_name": "江澈", "character_names": ["江澈"], "target_words": 700},
        {"goal": "认识学姐", "entry_state": "窗口前", "must_happen": ["裴南栀帮他办手续并加好友"],
         "exit_state": "记住学姐", "must_not_include": [],
         "pov_character_name": "江澈", "character_names": ["江澈"], "target_words": 700},
    ]
    calls = {"n": 0}

    async def fake_post(self, url, **kwargs):
        calls["n"] += 1
        body = _scene_body(dup_scenes if calls["n"] == 1 else clean_scenes)
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    resp = client.post(f"/api/v1/novels/{uid}/chapters/{ch}/scenes/generate",
                       json={"scene_count": 2})
    assert resp.status_code == 200
    # A re-split was requested (2 generate calls), and the clean version was kept.
    assert calls["n"] == 2
    out = resp.json()
    assert "裴南栀帮他办手续并加好友" in out[1]["beat"]


def test_generate_scenes_keeps_result_when_resplit_still_dup(client: TestClient, monkeypatch) -> None:
    """If the re-split is still duplicated, keep the result (no infinite loop)."""
    uid, ch = _setup(client)
    dup_scenes = [
        {"goal": "a", "entry_state": "s", "must_happen": ["完全相同的一条必须发生事件内容"],
         "exit_state": "e", "must_not_include": [],
         "pov_character_name": "江澈", "character_names": ["江澈"], "target_words": 700},
        {"goal": "b", "entry_state": "s", "must_happen": ["完全相同的一条必须发生事件内容"],
         "exit_state": "e", "must_not_include": [],
         "pov_character_name": "江澈", "character_names": ["江澈"], "target_words": 700},
    ]
    calls = {"n": 0}

    async def fake_post(self, url, **kwargs):
        calls["n"] += 1
        return httpx.Response(200, json=_scene_body(dup_scenes),
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    resp = client.post(f"/api/v1/novels/{uid}/chapters/{ch}/scenes/generate",
                       json={"scene_count": 2})
    assert resp.status_code == 200
    # Exactly one re-split attempt, then stop (2 total), result still saved.
    assert calls["n"] == 2
    assert len(resp.json()) == 2
