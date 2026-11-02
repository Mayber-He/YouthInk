"""T15: previous-chapter voice excerpts + evidence-backed echo beats.

No live LLM: the planning model is mocked and the prompt it receives is asserted.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import reset_config_for_testing
from app.db.manager import ensure_global_db_initialized, get_global_db, get_novel_db
from app.db.repositories.settings_repo import SettingsRepository
from app.main import create_app
from app.schemas.writing import StreamWriteRequest
from app.services.prompt.character_voice import extract_speech_lines, previous_voice_block
from app.services.writing_service import WritingService

PREV_TEXT = (
    "江澈把照片撑大了两指，在灯下慢慢挪。\n"
    "“嗯。”裴南栀应了一声。\n"
    "“这题我讲最后一遍啊，听不懂就算了。”她把笔帽扣上。\n"
    "“你呀，就是不肯先承认不会。”\n"
    "“别急嘛，慢慢来呗。”\n"
    "“行吧。”\n"
    "“我们明天还来这儿吧？”\n"
)
SPOKEN = [
    "这题我讲最后一遍啊，听不懂就算了。",
    "你呀，就是不肯先承认不会。",
    "别急嘛，慢慢来呗。",
    "我们明天还来这儿吧？",
]
NARRATION = "江澈把照片撑大了两指，在灯下慢慢挪。"


# --- pure helpers ---

def test_extract_speech_lines_only_quoted_speech_and_dedupes() -> None:
    lines = extract_speech_lines(PREV_TEXT)
    assert lines == SPOKEN
    assert NARRATION not in lines
    # generic acknowledgements are not "signature" lines
    assert "嗯" not in lines and "行吧" not in lines
    # duplicate line (punctuation-insensitive) appears once
    dup = PREV_TEXT + "\n“这题我讲最后一遍啊，听不懂就算了！”"
    assert extract_speech_lines(dup).count(SPOKEN[0]) == 1


def test_extract_speech_lines_caps_at_five_and_ignores_long_quotes() -> None:
    text = "\n".join(f"“第{i}句话真的很有个人风格呀。”" for i in range(1, 8))
    text += "\n“" + "这是一段远超四十个字的引用内容，" * 3 + "”"
    lines = extract_speech_lines(text, limit=5)
    assert len(lines) == 5
    assert all(len(line) <= 40 for line in lines)
    assert extract_speech_lines(text, limit=0) == []


def test_previous_voice_block_degrades_without_previous_or_speech() -> None:
    assert "本章为开篇" in previous_voice_block("")
    no_speech = previous_voice_block("江澈把照片撑大了两指，在灯下慢慢挪。")
    assert "未提取到可用发言" in no_speech
    block = previous_voice_block(PREV_TEXT)
    assert "共 4 条" in block and block.count("\n- “") == 4


# --- integration ---

@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    reset_config_for_testing(tmp_path / "test_data_t15")
    ensure_global_db_initialized()
    app = create_app()
    with TestClient(app) as tc:
        tc.post(
            "/api/v1/settings/llm-profiles",
            json={"name": "T15", "base_url": "https://api.example.com/v1",
                  "model": "deepseek-chat", "api_key": "sk-t15", "is_default": True},
        )
        yield tc


def _mk_book(client: TestClient, prev_text: str | None) -> tuple[str, int, int | None]:
    uid = client.post("/api/v1/novels", json={"title": "T15书"}).json()["novel_uid"]
    client.post(f"/api/v1/novels/{uid}/characters", json={"name": "江澈", "role": "male_lead"})
    client.post(f"/api/v1/novels/{uid}/characters", json={"name": "裴南栀", "role": "female_lead"})
    client.post(f"/api/v1/novels/{uid}/locations", json={"name": "自习室"})
    v = client.post(f"/api/v1/novels/{uid}/outline/volumes", json={"title": "卷一"}).json()["id"]
    a = client.post(f"/api/v1/novels/{uid}/outline/arcs",
                    json={"volume_id": v, "title": "弧一"}).json()["id"]
    prev_id = None
    if prev_text is not None:
        prev_id = client.post(
            f"/api/v1/novels/{uid}/outline/chapters",
            json={"arc_id": a, "title": "上一章", "synopsis": "讲题"},
        ).json()["id"]
        client.put(
            f"/api/v1/novels/{uid}/chapters/{prev_id}/content",
            json={"content": prev_text, "source": "manual", "create_new_version": True},
        )
    ch = client.post(
        f"/api/v1/novels/{uid}/outline/chapters",
        json={"arc_id": a, "title": "下一章", "synopsis": "他做出关键选择"},
    ).json()["id"]
    return uid, ch, prev_id


def _scenes_body() -> dict:
    scenes = [
        {"goal": "两人复盘题目", "entry_state": "自习室关灯前",
         "must_happen": ["江澈承认自己没听懂"], "exit_state": "气氛松动",
         "must_not_include": ["表白"], "pov_character_name": "江澈",
         "location_name": "自习室", "character_names": ["江澈", "裴南栀"],
         "story_time": "次日晚上", "target_words": 700},
        {"goal": "江澈做出选择", "entry_state": "回到宿舍",
         "must_happen": ["江澈判断她已看穿，决定先开口"], "exit_state": "决定已下",
         "must_not_include": ["她察觉并回头"], "pov_character_name": "江澈",
         "location_name": "自习室", "character_names": ["江澈"],
         "story_time": "当夜", "target_words": 700},
    ]
    return {
        "choices": [{"message": {"content": json.dumps({"scenes": scenes}, ensure_ascii=False)}}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 80},
    }


def _capture(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    prompts: list[str] = []

    async def fake_post(self, url, **kwargs):
        prompts.append(kwargs["json"]["messages"][-1]["content"])
        return httpx.Response(200, json=_scenes_body(), request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return prompts


def test_planning_prompt_carries_speech_excerpts_and_rules(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid, ch, _ = _mk_book(client, PREV_TEXT)
    prompts = _capture(monkeypatch)

    resp = client.post(f"/api/v1/novels/{uid}/chapters/{ch}/scenes/generate",
                       json={"scene_count": 2})
    assert resp.status_code == 200, resp.text
    prompt = prompts[0]

    # 3–5 excerpts, all from the previous chapter's spoken lines only.
    assert "上一章中人物的标志性口癖或句式（仅摘自上一章原文发言，共 4 条）" in prompt
    assert prompt.count("\n- “") == 4
    for line in SPOKEN:
        assert f"- “{line}”" in prompt
    assert NARRATION not in prompt

    # Echo beats must cite one of those exact lines; prose may not invent old chat.
    assert "【与前文呼应的依据】" in prompt
    assert "指明具体对应" in prompt
    assert "逐字使用列出的上一章发言" in prompt
    assert "不得自造旧聊天、旧台词" in prompt
    # Key-choice scenes: inner judgment + decision, and the other party stays unaware.
    assert "【关键选择场景】" in prompt
    assert "明确的内心判断和决定" in prompt
    assert "must_not_include 必须写明对方不得察觉" in prompt
    assert "不得回头、追问或回应" in prompt


def test_planning_prompt_opening_chapter_degrades_without_previous(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid, ch, _ = _mk_book(client, None)
    prompts = _capture(monkeypatch)

    resp = client.post(f"/api/v1/novels/{uid}/chapters/{ch}/scenes/generate",
                       json={"scene_count": 2})
    assert resp.status_code == 200, resp.text
    prompt = prompts[0]
    assert "上一章无原文（本章为开篇）" in prompt
    assert "上一章中人物的标志性口癖或句式" not in prompt
    assert "【与前文呼应的依据】" in prompt


def test_planning_prompt_degrades_when_previous_has_no_speech(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid, ch, _ = _mk_book(client, "江澈把照片撑大了两指，在灯下慢慢挪。窗外起风了。")
    prompts = _capture(monkeypatch)

    resp = client.post(f"/api/v1/novels/{uid}/chapters/{ch}/scenes/generate",
                       json={"scene_count": 2})
    assert resp.status_code == 200, resp.text
    assert "未提取到可用发言" in prompts[0]
    assert "共 0 条" not in prompts[0]


def test_prose_instruction_forbids_reusing_previous_descriptive_sentences(
    client: TestClient
) -> None:
    uid, ch, _ = _mk_book(client, PREV_TEXT)
    client.post(f"/api/v1/novels/{uid}/chapters/{ch}/scenes",
                json={"beat": "目标：复盘\n必须发生：江澈承认没听懂", "target_words": 700})
    scene_id = client.get(f"/api/v1/novels/{uid}/chapters/{ch}/scenes").json()[0]["id"]

    with get_novel_db(uid) as nconn, get_global_db() as gconn:
        svc = WritingService(uid, nconn, SettingsRepository(gconn))
        _sys, user_p = svc.prepare_stream_write_prompts(
            StreamWriteRequest(chapter_id=ch, scene_id=scene_id, mode="scene")
        )
    assert "不得复用上一章已出现的描写句子" in user_p
    assert "不照抄原句" in user_p
    # T18: scene continuity starts AFTER the last written sentence, not by replaying it.
    assert "开头从已写前文最后一句之后继续，不要重复其最后一段的动作和状态。" in user_p
