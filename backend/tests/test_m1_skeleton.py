"""Unit and integration tests for M1 Skeleton (Dual DB, Security, Settings, Novels, LLM)."""

from __future__ import annotations

from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from app.core.config import reset_config_for_testing
from app.core.security import decrypt_api_key, encrypt_api_key, mask_api_key
from app.db.manager import ensure_global_db_initialized
from app.main import create_app
from app.services.llm.json_parser import try_parse_json


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    reset_config_for_testing(tmp_path / "test_data")
    ensure_global_db_initialized()
    app = create_app()
    return TestClient(app)


def test_api_key_encryption_and_masking(tmp_path: Path) -> None:
    secret_file = tmp_path / ".secret.key"
    raw = "sk-proj-1234567890abcdef"
    enc = encrypt_api_key(raw, secret_file)
    assert enc != raw
    dec = decrypt_api_key(enc, secret_file)
    assert dec == raw
    masked = mask_api_key(raw)
    assert masked == "sk-****cdef"


def test_json_parser_stages() -> None:
    # Markdown code block with trailing comma
    raw = 'Here is the output:\n```json\n{"name": "林夏", "role": "female_lead",}\n```'
    parsed = try_parse_json(raw)
    assert parsed["name"] == "林夏"
    assert parsed["role"] == "female_lead"


def test_global_settings_and_llm_profiles(client: TestClient) -> None:
    # 1. Health check
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # 2. Built-in style templates seeded
    styles_resp = client.get("/api/v1/settings/style-templates")
    assert styles_resp.status_code == 200
    styles = styles_resp.json()
    assert len(styles) >= 4
    assert any(s["name"] == "清新校园" for s in styles)

    # 3. Create LLM profile & verify masking
    create_resp = client.post(
        "/api/v1/settings/llm-profiles",
        json={
            "name": "DeepSeek V3",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "api_key": "sk-test9876543210",
            "is_default": True,
        },
    )
    assert create_resp.status_code == 201
    profile = create_resp.json()
    assert profile["name"] == "DeepSeek V3"
    assert profile["api_key_masked"] == "sk-****3210"
    assert "sk-test9876543210" not in str(profile)

    # 4. Task assignments
    assign_resp = client.put(
        "/api/v1/settings/task-assignments",
        json={
            "writing": profile["id"],
            "planning": profile["id"],
            "extract": profile["id"],
        },
    )
    assert assign_resp.status_code == 200
    assert assign_resp.json()["writing"] == profile["id"]

    # 5. Prompt template override and reset
    prompts_resp = client.get("/api/v1/settings/prompt-templates")
    assert prompts_resp.status_code == 200
    assert len(prompts_resp.json()) >= 8

    override_resp = client.put(
        "/api/v1/settings/prompt-templates/system_role",
        json={"content": "自定义系统角色：{{title}}", "version": "1.1"},
    )
    assert override_resp.status_code == 200
    assert override_resp.json()["is_overridden"] is True

    reset_resp = client.delete("/api/v1/settings/prompt-templates/system_role")
    assert reset_resp.status_code == 200
    assert reset_resp.json()["is_overridden"] is False


def test_novel_lifecycle_and_backup(client: TestClient) -> None:
    # 1. Create novel
    create_resp = client.post(
        "/api/v1/novels",
        json={
            "title": "盛夏的柠檬汽水",
            "genre": "校园",
            "tone": "清新治愈",
            "pov": "第三人称限知",
            "protagonist_concept": "转学生林夏与校篮球队长陆川",
            "synopsis": "一场关于香樟树与蝉鸣的双向暗恋。",
            "target_words": 800000,
            "estimated_chapters": 320,
            "words_per_chapter": 2500,
            "romance_ending": "HE",
            "growth_ending": "HE",
        },
    )
    assert create_resp.status_code == 201
    novel = create_resp.json()
    novel_uid = novel["novel_uid"]
    assert novel["title"] == "盛夏的柠檬汽水"

    # 2. List novels
    list_resp = client.get("/api/v1/novels")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    # 3. Update novel
    upd_resp = client.put(
        f"/api/v1/novels/{novel_uid}",
        json={"title": "盛夏的柠檬汽水（修订版）", "romance_ending": "开放式"},
    )
    assert upd_resp.status_code == 200
    assert upd_resp.json()["title"] == "盛夏的柠檬汽水（修订版）"
    assert upd_resp.json()["romance_ending"] == "开放式"

    # 4. Create snapshot backup & restore
    bak_resp = client.post(f"/api/v1/novels/{novel_uid}/backups?reason=init")
    assert bak_resp.status_code == 201
    bak_filename = bak_resp.json()["filename"]

    # Modify title then restore backup
    client.put(f"/api/v1/novels/{novel_uid}", json={"title": "临时错误书名"})
    restore_resp = client.post(
        f"/api/v1/novels/{novel_uid}/backups/{bak_filename}/restore"
    )
    assert restore_resp.status_code == 200

    restored_novel = client.get(f"/api/v1/novels/{novel_uid}").json()
    assert restored_novel["title"] == "盛夏的柠檬汽水（修订版）"

    # 5. Delete novel
    del_resp = client.delete(f"/api/v1/novels/{novel_uid}")
    assert del_resp.status_code == 204
    assert client.get("/api/v1/novels").json() == []


def test_llm_connection_mocked(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    async def fake_post(self, url: str, **kwargs):  # type: ignore[no-untyped-def]
        assert url == "https://api.example.com/v1/chat/completions"
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-123",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "蝉鸣穿过香樟树叶，黑板报上的粉笔字在午后阳光里微微发亮。",
                        },
                    }
                ],
                "usage": {"prompt_tokens": 28, "completion_tokens": 26},
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    test_resp = client.post(
        "/api/v1/settings/llm-profiles/test",
        json={
            "base_url": "https://api.example.com/v1",
            "model": "gpt-4o-mini",
            "api_key": "sk-mock123456",
        },
    )
    assert test_resp.status_code == 200
    data = test_resp.json()
    assert data["ok"] is True
    assert "香樟树" in data["reply"]
    assert data["input_tokens"] == 28
    assert data["output_tokens"] == 26

    # Verify static SPA index.html is served at GET /
    spa_resp = client.get("/")
    assert spa_resp.status_code == 200
    assert "YouthInk" in spa_resp.text


