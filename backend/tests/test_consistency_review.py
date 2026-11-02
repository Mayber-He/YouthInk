"""Phase 3 tests: checklist-based Consistency Review (flags only, never auto-edits)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import reset_config_for_testing
from app.db.manager import ensure_global_db_initialized
from app.main import create_app

FIX = Path(__file__).parent / "fixtures"
FAILED_REVIEW_SAMPLE = json.loads(
    (FIX / "consistency_failed_review.json").read_text(encoding="utf-8")
)


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


def test_consistency_review_detects_common_sense_without_explicit_constraint(
    client: TestClient, novel_uid: str, monkeypatch: pytest.MonkeyPatch, character_id: int
) -> None:
    """Even without a manually added constraint, Checklist D checks situational & common-sense rules."""
    _setup_llm_profile(client)
    ch = _make_chapter_with_content(
        client,
        novel_uid,
        character_id,
        "刚来大学报到的林夏熟门熟路地穿过三条近道，还一眼叫出了迎面走来的陌生学长陆川的名字。",
    )

    # Verify ContextPreview includes identity background & common-sense boundary warnings
    preview = client.get(f"/api/v1/novels/{novel_uid}/chapters/{ch}/context-preview").json()
    blocks_by_key = {b["key"]: b["content"] for b in preview["blocks"]}
    assert "大一新生" in blocks_by_key["character_states"]
    assert "人物连续性与认知边界" in blocks_by_key["character_states"]
    assert "不等于初见或不熟" in blocks_by_key["character_states"]
    assert "视角(POV)：林夏" in blocks_by_key["chapter_beats"]

    captured_prompts: list[str] = []

    async def fake_post(self, url: str, **kwargs):
        req = httpx.Request("POST", url)
        payload = kwargs.get("json", {})
        user_msg = payload["messages"][-1]["content"]
        captured_prompts.append(user_msg)
        issues = [
            {
                "check_type": "common_sense",
                "ref_id": 901,
                "ref_label": "常理#901",
                "verdict": "violation",
                "evidence_quote": "刚来大学报到的林夏熟门熟路地穿过三条近道",
                "description": "违反环境熟悉度常理：大一新生刚报到不应熟知校园近道",
                "suggestion": "改为林夏看着校园指示牌摸索前行",
            },
            {
                "check_type": "common_sense",
                "ref_id": 902,
                "ref_label": "常理#902",
                "verdict": "violation",
                "evidence_quote": "一眼叫出了迎面走来的陌生学长陆川的名字",
                "description": "违反人际初见边界：初次见面未经自我介绍便知晓陌生学长姓名",
                "suggestion": "改为先看到对方工作牌或经人介绍后再得知姓名",
            },
        ]
        body = {
            "choices": [
                {"message": {"content": json.dumps({"issues": issues}, ensure_ascii=False)}}
            ],
            "usage": {"prompt_tokens": 220, "completion_tokens": 140},
        }
        return httpx.Response(200, json=body, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    r = client.post(f"/api/v1/novels/{novel_uid}/chapters/{ch}/consistency-review")
    assert r.status_code == 201
    assert len(captured_prompts) == 1
    assert "【检查表D：本章情境与六大常理逻辑自洽】" in captured_prompts[0]
    assert "[#901]【环境与空间熟悉度常理】" in captured_prompts[0]
    assert "[#902]【人际关系与初见边界】" in captured_prompts[0]

    data = r.json()
    assert data["issue_count"] == 2
    assert data["violation_count"] == 2
    assert data["issues"][0]["check_type"] == "common_sense"
    assert data["issues"][0]["ref_id"] == 901


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


def test_vector_index_unavailable_is_visible_in_review(
    client: TestClient, novel_uid: str, monkeypatch: pytest.MonkeyPatch, character_id: int
) -> None:
    _setup_llm_profile(client)
    ch = _make_chapter_with_content(
        client, novel_uid, character_id, "林夏拿着新生手册在校园里找宿舍。"
    )
    _mock_review_response(monkeypatch, [])
    monkeypatch.setattr(
        "app.services.memory.consistency.NovelVectorStore.read_index_status",
        lambda self: {
            "pending_rebuild": True,
            "reason": "向量编码失败：模型文件缺失",
            "chapters": [1],
        },
    )

    r = client.post(f"/api/v1/novels/{novel_uid}/chapters/{ch}/consistency-review")
    assert r.status_code == 201
    data = r.json()
    assert data["issue_count"] == 1
    assert data["violation_count"] == 0
    issue = data["issues"][0]
    assert issue["check_type"] == "continuity"
    assert issue["ref_label"] == "向量检索不可用"
    assert "模型文件缺失" in issue["description"]
    assert issue["verdict"] == "suspicious"


def test_vector_search_exception_is_visible_not_silent(
    client: TestClient, novel_uid: str, monkeypatch: pytest.MonkeyPatch, character_id: int
) -> None:
    _setup_llm_profile(client)
    ch = _make_chapter_with_content(
        client, novel_uid, character_id, "林夏抱着书从图书馆出来。"
    )
    _mock_review_response(monkeypatch, [])
    def fail(self):
        raise OSError("index unreadable")
    monkeypatch.setattr(
        "app.services.memory.consistency.NovelVectorStore.read_index_status", fail
    )

    r = client.post(f"/api/v1/novels/{novel_uid}/chapters/{ch}/consistency-review")
    assert r.status_code == 201
    issue = r.json()["issues"][0]
    assert issue["ref_label"] == "向量检索不可用"
    assert "index unreadable" in issue["description"]


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


def test_cross_chapter_continuity_guards(
    client: TestClient, novel_uid: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Context injects prev tail + next synopsis boundary; review adds Checklist E (continuity)."""
    _setup_llm_profile(client)
    base = f"/api/v1/novels/{novel_uid}"
    v_id = client.post(f"{base}/outline/volumes", json={"title": "第一卷"}).json()["id"]
    a_id = client.post(
        f"{base}/outline/arcs", json={"volume_id": v_id, "title": "开学篇"}
    ).json()["id"]
    ch1 = client.post(
        f"{base}/outline/chapters",
        json={"arc_id": a_id, "title": "深夜聊天", "synopsis": "她说明天再说学校的事"},
    ).json()["id"]
    ch2 = client.post(
        f"{base}/outline/chapters",
        json={"arc_id": a_id, "title": "她说她要去迎新", "synopsis": "她透露自己是临江大学的学姐"},
    ).json()["id"]
    for cid, text in ((ch1, "她说下周要去迎新，学校的事明天再说。"), (ch2, "她说：我下周要去迎新！")):
        r = client.put(
            f"{base}/chapters/{cid}/content",
            json={"content": text, "source": "manual", "create_new_version": True},
        )
        assert r.status_code == 200

    prev1 = client.get(f"{base}/chapters/{ch1}/context-preview").json()
    block1 = {b["key"]: b["content"] for b in prev1["blocks"]}["summaries_and_prev"]
    assert "下一章《她说她要去迎新》梗概" in block1
    assert "跨章衔接边界" in block1

    prev2 = client.get(f"{base}/chapters/{ch2}/context-preview").json()
    block2 = {b["key"]: b["content"] for b in prev2["blocks"]}["summaries_and_prev"]
    assert "学校的事明天再说" in block2
    assert "不得将叙述者知识分配给所有角色" in block2
    assert "不得让已知情者再次把它当成新消息" in block2

    captured: list[str] = []

    async def fake_post(self, url: str, **kwargs):
        captured.append(kwargs["json"]["messages"][-1]["content"])
        issues = [
            {
                "check_type": "continuity",
                "ref_id": 951,
                "ref_label": "连贯#951",
                "verdict": "violation",
                "evidence_quote": "我下周要去迎新！",
                "description": "上一章已交代迎新，本章重复揭示",
                "suggestion": "直接承接上一章的“明天再说”",
            }
        ]
        body = {
            "choices": [{"message": {"content": json.dumps({"issues": issues}, ensure_ascii=False)}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    r = client.post(f"{base}/chapters/{ch2}/consistency-review")
    assert r.status_code == 201
    assert "【检查表E：跨章连贯】" in captured[0]
    assert "学校的事明天再说" in captured[0]
    assert r.json()["issues"][0]["check_type"] == "continuity"


# ---------------------------------------------------------------- T14 tolerance

def test_failed_review_sample_keeps_all_four_issues(
    client: TestClient, novel_uid: str, monkeypatch: pytest.MonkeyPatch, character_id: int
) -> None:
    """Real 422 sample: issues[3].ref_label is null; every issue must survive."""
    _setup_llm_profile(client)
    ch = _make_chapter_with_content(
        client, novel_uid, character_id, "江澈把侧袋里那瓶水抽出来放在脚边，半蹲下身。"
    )
    _mock_review_response(monkeypatch, FAILED_REVIEW_SAMPLE["issues"])

    r = client.post(f"/api/v1/novels/{novel_uid}/chapters/{ch}/consistency-review")
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["issue_count"] == 4
    assert [i["check_type"] for i in data["issues"]] == [
        "common_sense", "common_sense", "common_sense", "prose",
    ]
    # None is normalized to "" so the issue is kept and the frontend type still holds.
    assert data["issues"][3]["ref_label"] == ""
    assert data["issues"][3]["evidence_quote"].startswith("江澈把侧袋里那瓶水")


def test_invalid_issues_are_dropped_individually_with_log(
    client: TestClient, novel_uid: str, monkeypatch: pytest.MonkeyPatch,
    character_id: int, caplog: pytest.LogCaptureFixture
) -> None:
    _setup_llm_profile(client)
    ch = _make_chapter_with_content(
        client, novel_uid, character_id, "林夏拿着新生手册，在校园里转了三圈才找到宿舍楼。"
    )
    valid = {
        "check_type": "common_sense", "ref_id": 901, "ref_label": "常理#901",
        "verdict": "suspicious", "evidence_quote": "林夏拿着新生手册",
        "description": "d", "suggestion": "s",
    }
    invalid_type = {**valid, "check_type": "not_a_type"}
    missing_required = {"ref_label": "缺字段"}
    _mock_review_response(monkeypatch, [valid, invalid_type, missing_required, {**valid, "ref_id": 902}])

    with caplog.at_level(logging.WARNING, logger="app.services.memory.consistency"):
        r = client.post(f"/api/v1/novels/{novel_uid}/chapters/{ch}/consistency-review")
    assert r.status_code == 201, r.text
    assert r.json()["issue_count"] == 2
    assert "dropped 2 invalid issue(s)" in caplog.text


def test_consistency_timeout_env_and_retry_share_budget(
    client: TestClient, novel_uid: str, monkeypatch: pytest.MonkeyPatch, character_id: int
) -> None:
    _setup_llm_profile(client)
    ch = _make_chapter_with_content(
        client, novel_uid, character_id, "林夏拿着新生手册，在校园里转了三圈才找到宿舍楼。"
    )
    monkeypatch.setenv("YOUTHINK_CONSISTENCY_TIMEOUT_SEC", "120")
    clock = {"t": 1000.0}
    monkeypatch.setattr("app.services.llm.timeout_budget.time.monotonic", lambda: clock["t"])

    calls: list[dict] = []

    async def fake_complete_chat(**kwargs):
        calls.append(kwargs)
        clock["t"] += 200  # the first attempt consumed 200 of the 240 s shared budget
        if len(calls) == 1:
            return SimpleNamespace(content="这不是 JSON")
        return SimpleNamespace(content=json.dumps({"issues": []}))

    monkeypatch.setattr("app.services.memory.consistency.complete_chat", fake_complete_chat)
    r = client.post(f"/api/v1/novels/{novel_uid}/chapters/{ch}/consistency-review")
    assert r.status_code == 201, r.text
    assert len(calls) == 2
    assert calls[0]["timeout_sec"] == 120
    assert calls[1]["timeout_sec"] == 40  # 2*120 - 200 consumed
    assert "重新输出" in calls[1]["user_prompt"]


def test_timeout_env_default_range_and_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.llm.timeout_budget import RetryBudget, env_timeout_sec

    monkeypatch.delenv("YOUTHINK_TEST_TIMEOUT", raising=False)
    assert env_timeout_sec("YOUTHINK_TEST_TIMEOUT") == 150
    monkeypatch.setenv("YOUTHINK_TEST_TIMEOUT", "45")
    assert env_timeout_sec("YOUTHINK_TEST_TIMEOUT") == 45
    monkeypatch.setenv("YOUTHINK_TEST_TIMEOUT", "10")
    assert env_timeout_sec("YOUTHINK_TEST_TIMEOUT") == 30
    monkeypatch.setenv("YOUTHINK_TEST_TIMEOUT", "999")
    assert env_timeout_sec("YOUTHINK_TEST_TIMEOUT") == 300
    monkeypatch.setenv("YOUTHINK_TEST_TIMEOUT", "abc")
    assert env_timeout_sec("YOUTHINK_TEST_TIMEOUT") == 150

    clock = {"t": 0.0}
    monkeypatch.setattr("app.services.llm.timeout_budget.time.monotonic", lambda: clock["t"])
    budget = RetryBudget(150)
    assert budget.total_sec == 300 and budget.next_timeout() == 150
    clock["t"] = 200
    assert budget.next_timeout() == 100
    clock["t"] = 300
    assert budget.exhausted() and budget.next_timeout() == 0
