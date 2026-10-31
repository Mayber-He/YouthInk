"""Unit and integration tests for M3 Writing Workbench (Scenes, Versions, Context, AI Smell, SSE, Export)."""

from __future__ import annotations

from contextlib import asynccontextmanager
import json
from pathlib import Path
from fastapi.testclient import TestClient
import httpx
import pytest

from app.core.config import reset_config_for_testing
from app.db.manager import ensure_global_db_initialized, get_global_db, get_novel_db
from app.db.repositories.settings_repo import SettingsRepository
from app.main import create_app
from app.schemas.writing import StreamWriteRequest
from app.services.writing_service import WritingService


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    reset_config_for_testing(tmp_path / "test_data_m3")
    ensure_global_db_initialized()
    app = create_app()
    c = TestClient(app)
    c.post(
        "/api/v1/settings/llm-profiles",
        json={
            "name": "Test Writer",
            "base_url": "https://api.example.com/v1",
            "model": "deepseek-chat",
            "api_key": "sk-testwriter123",
            "is_default": True,
        },
    )
    return c


@pytest.fixture()
def setup_chapter(client: TestClient) -> tuple[str, int, int]:
    novel = client.post(
        "/api/v1/novels",
        json={
            "title": "蝉鸣停止之前",
            "genre": "校园",
            "tone": "清新治愈",
            "pov": "第三人称限知",
            "protagonist_concept": "林夏 × 陆川",
            "synopsis": "高二盛夏的广播站故事。",
            "style_template_id": 1,
        },
    ).json()
    uid = str(novel["novel_uid"])

    char = client.post(
        f"/api/v1/novels/{uid}/characters",
        json={
            "name": "林夏",
            "role": "female_lead",
            "personality": "慢热细致",
            "speech_style": "说话轻声但笃定",
        },
    ).json()
    client.post(
        f"/api/v1/novels/{uid}/locations",
        json={
            "name": "广播站播音室",
            "type": "校园场所",
            "description": "隔音棉泛黄的小房间",
            "sensory_details": "老式调音台指示灯闪烁，窗外香樟树叶沙沙响",
        },
    )
    vol = client.post(
        f"/api/v1/novels/{uid}/outline/volumes",
        json={"title": "第一卷：盛夏频率"},
    ).json()
    arc = client.post(
        f"/api/v1/novels/{uid}/outline/arcs",
        json={"volume_id": vol["id"], "title": "第一弧：试音"},
    ).json()
    ch = client.post(
        f"/api/v1/novels/{uid}/outline/chapters",
        json={
            "arc_id": arc["id"],
            "title": "五点半的电流声",
            "synopsis": "林夏第一次在放学后独自值班试音，偶遇走错门的陆川。",
            "story_time": "九月第一个周五傍晚",
        },
    ).json()
    return uid, int(ch["id"]), int(char["id"])


def test_scenes_versions_context_and_export(
    client: TestClient, setup_chapter: tuple[str, int, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    uid, ch_id, _ = setup_chapter

    # 1. AI generate scenes
    async def fake_post(self, url: str, **kwargs):  # type: ignore[no-untyped-def]
        payload = json.dumps(
            {
                "scenes": [
                    {
                        "beat": "@林夏 在 @广播站播音室 调试麦克风，耳机里传来细微电流声。",
                        "pov_character_name": "林夏",
                        "location_name": "广播站播音室",
                        "character_names": ["林夏"],
                        "story_time": "17:30",
                        "target_words": 800,
                    },
                    {
                        "beat": "暮色降临，走廊外传来篮球拍击声。",
                        "pov_character_name": "林夏",
                        "location_name": "广播站播音室",
                        "character_names": ["林夏"],
                        "story_time": "17:50",
                        "target_words": 900,
                    },
                ]
            },
            ensure_ascii=False,
        )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": payload}}],
                "usage": {"prompt_tokens": 120, "completion_tokens": 90},
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    scenes_resp = client.post(
        f"/api/v1/novels/{uid}/chapters/{ch_id}/scenes/generate",
        json={"scene_count": 2, "instruction": ""},
    )
    assert scenes_resp.status_code == 200
    scenes = scenes_resp.json()
    assert len(scenes) == 2
    assert scenes[0]["pov_character"] is not None
    assert scenes[0]["location_id"] is not None

    # Chapter status should now be 'outline'
    ws = client.get(f"/api/v1/novels/{uid}/chapters/{ch_id}/workspace").json()
    assert ws["chapter"]["status"] == "outline"

    # 2. Context preview & block toggle
    ctx = client.get(
        f"/api/v1/novels/{uid}/chapters/{ch_id}/context-preview?scene_id={scenes[0]['id']}"
    ).json()
    assert ctx["total_tokens"] > 0
    assert any(b["key"] == "character_states" and "林夏" in b["content"] for b in ctx["blocks"])

    ctx_disabled = client.get(
        f"/api/v1/novels/{uid}/chapters/{ch_id}/context-preview?disabled_keys=character_states"
    ).json()
    assert ctx_disabled["total_tokens"] < ctx["total_tokens"]

    # 3. Save versions & restore
    v1_ws = client.put(
        f"/api/v1/novels/{uid}/chapters/{ch_id}/content",
        json={
            "content": "第一版草稿：调音台的红灯亮起。",
            "source": "manual",
            "create_new_version": True,
        },
    ).json()
    assert v1_ws["latest_version"] == 1
    assert v1_ws["chapter"]["status"] == "draft"
    assert v1_ws["chapter"]["word_count"] == 15

    v2_ws = client.put(
        f"/api/v1/novels/{uid}/chapters/{ch_id}/content",
        json={
            "content": "第二版AI生成：推开隔音门时，夕阳正好落在麦克风防风罩上。",
            "source": "ai",
            "create_new_version": True,
        },
    ).json()
    assert v2_ws["latest_version"] == 2
    assert len(v2_ws["versions"]) == 2

    restored_ws = client.post(
        f"/api/v1/novels/{uid}/chapters/{ch_id}/versions/1/restore"
    ).json()
    assert restored_ws["latest_version"] == 3
    assert restored_ws["latest_content"] == "第一版草稿：调音台的红灯亮起。"

    # 4. Export Markdown & TXT (Full novel & single chapter)
    md_resp = client.get(f"/api/v1/novels/{uid}/export?format=md")
    assert md_resp.status_code == 200
    assert "五点半的电流声" in md_resp.text
    assert "第一版草稿：调音台的红灯亮起。" in md_resp.text

    # Single chapter export
    ch_md_resp = client.get(f"/api/v1/novels/{uid}/export?format=md&chapter_id={ch_id}")
    assert ch_md_resp.status_code == 200
    assert "Content-Disposition" in ch_md_resp.headers
    assert "filename*=" in ch_md_resp.headers["Content-Disposition"]
    assert "五点半的电流声" in ch_md_resp.text
    assert "第一版草稿：调音台的红灯亮起。" in ch_md_resp.text


def test_chapter_prompt_uses_outline_once_and_requires_clear_chinese(
    client: TestClient, setup_chapter: tuple[str, int, int]
) -> None:
    uid, ch_id, _ = setup_chapter
    synopsis = "林夏第一次在放学后独自值班试音，偶遇走错门的陆川。"
    with get_novel_db(uid) as novel_conn, get_global_db() as global_conn:
        service = WritingService(uid, novel_conn, SettingsRepository(global_conn))
        _system_prompt, user_prompt = service.prepare_stream_write_prompts(
            StreamWriteRequest(chapter_id=ch_id, mode="chapter")
        )
        _scene_system_prompt, scene_user_prompt = service.prepare_stream_write_prompts(
            StreamWriteRequest(chapter_id=ch_id, mode="scene", scene_id=1)
        )

    assert user_prompt.count(synopsis) == 1
    assert "这张纸，家里只有爸妈知道”对象错位" in user_prompt
    assert "普通动作用清楚直白的中文写" in user_prompt
    assert "聊天界面提示必须按当前视角区分发起者和接收者" in user_prompt
    assert "自己收到对方撤回的消息时，应写“对方撤回了一条消息”" in user_prompt
    assert "若本章梗概要求重写前文已发生的事件或复用前文标志性原句，以前文为准" in user_prompt
    assert "前文已出现的完整台词不得原样再次安排" in user_prompt
    assert "故事时间只用于保持连贯，不要求每章开篇直接报日期或时间" in user_prompt
    assert "相邻章节开头应改变切入方式" in user_prompt
    assert "相对日期必须按当前场景的具体故事日期换算" in user_prompt
    assert "日常动作只保留能推动情节或改变人物状态的部分" in user_prompt
    assert "不要把收拾、做饭、等待等过程拆成连续的微动作清单" in user_prompt
    assert "目标字数是参考，不得用重复心理、同义解释或无结果动作补足篇幅" in user_prompt
    assert "建议范围 2,000–2,800 字" in user_prompt
    assert "字数范围仅供参考，叙事完整、表达紧凑优先" in user_prompt
    assert "640–896 字" in scene_user_prompt
    assert "不得为达到下限补写流水账" in scene_user_prompt
    assert "不得虚构上下文中没有发生过的旧对话或旧事件" in user_prompt
    assert "不要让人物确认所有人都知道的常识" in user_prompt


def test_next_chapter_prompt_includes_previous_chapter_synopsis(
    client: TestClient, setup_chapter: tuple[str, int, int]
) -> None:
    uid, _previous_chapter_id, _ = setup_chapter
    previous_synopsis = "林夏第一次在放学后独自值班试音，偶遇走错门的陆川。"
    outline = client.get(f"/api/v1/novels/{uid}/outline").json()
    arc_id = outline["volumes"][0]["arcs"][0]["id"]
    previous_opening = "【前章开头事实】"
    previous_ending = "【前章最后一句】"
    previous_content = previous_opening + "中间情节。" * 500 + previous_ending
    client.put(
        f"/api/v1/novels/{uid}/chapters/{previous_chapter_id}/content",
        json={"content": previous_content, "source": "manual", "create_new_version": True},
    )
    next_chapter = client.post(
        f"/api/v1/novels/{uid}/outline/chapters",
        json={"arc_id": arc_id, "title": "碰上了也别认我", "synopsis": "承接上一章。"},
    ).json()

    with get_novel_db(uid) as novel_conn, get_global_db() as global_conn:
        service = WritingService(uid, novel_conn, SettingsRepository(global_conn))
        _system_prompt, user_prompt = service.prepare_stream_write_prompts(
            StreamWriteRequest(chapter_id=next_chapter["id"], mode="chapter")
        )

    assert "上一章梗概" in user_prompt
    assert previous_synopsis in user_prompt
    assert previous_opening in user_prompt
    assert previous_ending in user_prompt
    assert "不得把人物卡里的背景设定当作角色过去已听过的内容" in user_prompt
    assert "回复涉及未来日期的提醒时，必须先核对当前章日期" in user_prompt
    assert "时间尚未到，不得写成已经出发、到达或完成" in user_prompt


def test_ai_smell_scanner_and_sse_streaming(
    client: TestClient, setup_chapter: tuple[str, int, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    uid, ch_id, char_id = setup_chapter

    # 1. Local AI smell detection
    smell_resp = client.post(
        f"/api/v1/novels/{uid}/ai-smell-scan",
        json={
            "text": "听到这句话，林夏不由得怔住了，陆川嘴角勾起一抹弧度。在那一刻，仿佛整个世界都安静了下来。"
        },
    )
    assert smell_resp.status_code == 200
    smell_data = smell_resp.json()
    assert smell_data["total_hits"] >= 3
    matched_words = [h["matched_text"] for h in smell_data["hits"]]
    assert "不由得" in matched_words

    # 2. Mock SSE stream for /api/stream/novels/{uid}/write and /rewrite
    class FakeStreamResponse:
        status_code = 200

        async def aiter_lines(self):
            yield 'data: {"choices": [{"delta": {"content": "夕阳把走廊拉得很长，"}}]}'
            yield 'data: {"choices": [{"delta": {"content": "广播里传来试音的钢琴曲。"}}]}'
            yield "data: [DONE]"

        async def aread(self) -> bytes:
            return b""

    stream_temperatures: list[float] = []

    @asynccontextmanager
    async def fake_stream(self, method: str, url: str, **kwargs):  # type: ignore[no-untyped-def]
        stream_temperatures.append(kwargs["json"]["temperature"])
        yield FakeStreamResponse()

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)

    write_sse = client.post(
        f"/api/stream/novels/{uid}/write",
        json={"chapter_id": ch_id, "mode": "chapter"},
    )
    assert write_sse.status_code == 200
    assert "event: meta" in write_sse.text
    assert "夕阳把走廊拉得很长，" in write_sse.text
    assert "event: done" in write_sse.text
    assert stream_temperatures == [0.7]

    rewrite_sse = client.post(
        f"/api/stream/novels/{uid}/rewrite",
        json={
            "chapter_id": ch_id,
            "selected_text": "林夏不由得心里一紧。",
            "action_type": "tone_shift",
            "target_character_id": char_id,
        },
    )
    assert rewrite_sse.status_code == 200
    assert "event: delta" in rewrite_sse.text

    # Verify generation_logs recorded both calls
    with get_novel_db(uid) as conn:
        cnt = conn.execute("SELECT COUNT(*) FROM generation_logs").fetchone()[0]
        assert cnt >= 2



def test_critique_selection_detects_contradiction(
    client: TestClient, setup_chapter: tuple[str, int, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    uid, ch_id, _ = setup_chapter
    captured_system_prompt = ""

    async def fake_post(self, url: str, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal captured_system_prompt
        captured_system_prompt = kwargs["json"]["messages"][0]["content"]
        payload = json.dumps(
            {
                "has_issue": True,
                "issue_type": "time_conflict",
                "issue_label": "时间常识冲突",
                "description": "箱子是6月高考完新买的，无法在年三十绑红绳",
                "suggestion": "箱子是高考完买的打折款，拉链上系着开学前求来的红绳",
            }
        )
        body = {
            "choices": [{"message": {"content": payload}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 60},
        }
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    resp = client.post(
        f"/api/v1/novels/{uid}/chapters/{ch_id}/critique-selection",
        json={
            "selected_text": "箱子是高考完他妈在超市买的打折款，拉链头上还系着年三十晚上绑上去的红绳"
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_issue"] is True
    assert data["issue_type"] == "time_conflict"
    assert "高考完" in data["description"]
    assert "开学前" in data["suggestion"]
    assert "对话动机与话题连续性" in captured_system_prompt
    assert "对话动机牵强" in captured_system_prompt
    assert "她问过一次“你今年开学吗”" in captured_system_prompt
