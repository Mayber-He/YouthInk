"""T21: key-choice scenes must state an inner judgment/decision.

The fixed sample is scene 3 of the third live evaluation (`live_eval_export3.md`):
its goal/exit signal a key choice (确认/决定/压在心里), its ``must_happen`` only
lists external actions, and the final prose never states the decision. No live
LLM: planning/rewrite calls are mocked.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
import pytest

from app.db.manager import get_global_db, get_novel_db
from app.db.repositories.settings_repo import SettingsRepository
from app.schemas.writing import StreamWriteRequest
from app.services.key_choice import (
    KEY_CHOICE_WRITE_RULE,
    KeyChoiceConfig,
    describe_planning_issues,
    find_planning_issues,
    has_inner_decision,
    is_key_choice_beat,
    lacks_inner_decision,
    must_happen_items,
    parse_beat_sections,
)
from app.services.writing_service import WritingService
from test_scene_event_checklist import _scene_body, _setup, client  # noqa: F401

FIX = Path(__file__).parent / "fixtures"
BEAT = (FIX / "t21_scene3_beat.txt").read_text(encoding="utf-8")
FINAL = (FIX / "t21_scene3_final.txt").read_text(encoding="utf-8")


# ----------------------------------------------------------- pure helpers

def test_sample_scene3_is_key_choice_but_lacks_inner_decision() -> None:
    assert is_key_choice_beat(BEAT)
    sections = parse_beat_sections(BEAT)
    assert "确认" in sections["goal"]
    assert "压在心里" in sections["exit_state"]
    items = must_happen_items(BEAT)
    assert items and not has_inner_decision(items)

    issues = find_planning_issues(
        [sections["goal"]], [sections["exit_state"]], [items or []]
    )
    assert len(issues) == 1
    assert issues[0].index == 0
    assert "内心判断" in issues[0].reason

    # The real prose only has external "确认没有漏填", not a decision.
    assert "确认" in FINAL
    assert lacks_inner_decision(FINAL)


def test_inner_decision_in_must_happen_clears_the_issue() -> None:
    sections = parse_beat_sections(BEAT)
    items = [
        "学姐接电话，锁屏露出江边黄昏照",
        "他判断相认等于替她揭开隐私，决定暂不点破",
    ]
    assert find_planning_issues(
        [sections["goal"]], [sections["exit_state"]], [items]
    ) == []
    assert not lacks_inner_decision(FINAL + "\n他决定不点破。")


def test_describe_planning_issues_names_scene_and_concrete_reason() -> None:
    sections = parse_beat_sections(BEAT)
    issues = find_planning_issues(
        [sections["goal"]], [sections["exit_state"]], [must_happen_items(BEAT) or []]
    )
    text = describe_planning_issues(issues)
    assert "场景1" in text
    assert "must_happen 只有外部事件" in text
    assert "他判断……，决定……" in text


def test_config_defaults_to_warning_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("YOUTHINK_KEY_CHOICE_CHECK", raising=False)
    monkeypatch.delenv("YOUTHINK_KEY_CHOICE_REWRITE", raising=False)
    cfg = KeyChoiceConfig.from_env()
    assert cfg.check is True
    assert cfg.rewrite is False

    monkeypatch.setenv("YOUTHINK_KEY_CHOICE_CHECK", "0")
    monkeypatch.setenv("YOUTHINK_KEY_CHOICE_REWRITE", "1")
    cfg = KeyChoiceConfig.from_env()
    assert cfg.check is False
    assert cfg.rewrite is True


# ----------------------------------------------------------- planning validation

MISSING_SCENE = {
    "goal": "让江澈确认学姐就是网友，并决定暂时不揭穿",
    "entry_state": "江澈在桌前填表",
    "must_happen": ["学姐接电话", "江澈填完表"],
    "exit_state": "江澈把这件事压在心里",
    "must_not_include": [],
    "pov_character_name": "江澈",
    "character_names": ["江澈"],
    "story_time": "报到日上午",
    "target_words": 700,
}
FIXED_SCENE = {
    **MISSING_SCENE,
    "must_happen": ["学姐接电话", "他判断相认会揭开隐私，决定暂不点破"],
}


def test_planning_resplits_once_with_concrete_key_choice_reason(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid, ch = _setup(client)
    prompts: list[str] = []

    async def fake_post(self, url, **kwargs):
        prompts.append(kwargs["json"]["messages"][-1]["content"])
        scenes = [MISSING_SCENE] if len(prompts) == 1 else [FIXED_SCENE]
        return httpx.Response(
            200, json=_scene_body(scenes), request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    resp = client.post(
        f"/api/v1/novels/{uid}/chapters/{ch}/scenes/generate", json={"scene_count": 1}
    )
    assert resp.status_code == 200, resp.text
    assert len(prompts) == 2
    assert "关键选择场景缺少内心判断" in prompts[1]
    assert "must_happen 只有外部事件" in prompts[1]
    assert "决定暂不点破" in resp.json()[0]["beat"]


def test_planning_keeps_result_and_warns_when_still_missing(
    client, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    uid, ch = _setup(client)
    calls = {"n": 0}

    async def fake_post(self, url, **kwargs):
        calls["n"] += 1
        return httpx.Response(
            200, json=_scene_body([MISSING_SCENE]), request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    caplog.set_level(logging.WARNING)
    resp = client.post(
        f"/api/v1/novels/{uid}/chapters/{ch}/scenes/generate", json={"scene_count": 1}
    )
    assert resp.status_code == 200
    assert calls["n"] == 2  # one re-split only, then keep
    assert "key-choice scene still lacks an inner decision" in caplog.text


# ----------------------------------------------------------- writing instruction

def _prompts_for_scene(client, uid: str, ch: int, beat: str) -> str:
    scene = client.post(
        f"/api/v1/novels/{uid}/chapters/{ch}/scenes",
        json={"beat": beat, "target_words": 700},
    ).json()
    with get_novel_db(uid) as nconn, get_global_db() as gconn:
        svc = WritingService(uid, nconn, SettingsRepository(gconn))
        _system, user = svc.prepare_stream_write_prompts(
            StreamWriteRequest(chapter_id=ch, scene_id=scene["id"], mode="scene")
        )
    return user


def test_write_prompt_adds_inner_judgment_rule_for_key_choice_scene(client) -> None:
    uid, ch = _setup(client)
    user = _prompts_for_scene(client, uid, ch, BEAT)
    assert KEY_CHOICE_WRITE_RULE in user
    assert "本场必须以一句明确的内心判断收束，不要只写动作" in user


def test_write_prompt_does_not_add_rule_for_plain_scene(client) -> None:
    uid, ch = _setup(client)
    user = _prompts_for_scene(
        client,
        uid,
        ch,
        "目标：江澈交表\n起点状态：桌前\n必须发生：填表；交表\n终点状态：离开桌前",
    )
    assert KEY_CHOICE_WRITE_RULE not in user


# ----------------------------------------------------------- post-generation advisory

def _scene_with_beat(client, uid: str, ch: int, beat: str) -> int:
    return client.post(
        f"/api/v1/novels/{uid}/chapters/{ch}/scenes",
        json={"beat": beat, "target_words": 700},
    ).json()["id"]


def test_repetition_check_warns_about_missing_inner_judgment(client) -> None:
    uid, ch = _setup(client)
    scene_id = _scene_with_beat(client, uid, ch, BEAT)
    resp = client.post(
        f"/api/v1/novels/{uid}/chapters/{ch}/scenes/{scene_id}/repetition-check",
        json={"scene_text": FINAL, "chapter_so_far": ""},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["action"] == "none"
    assert data["advisories"], data
    assert "关键选择场景缺少明确的内心判断或决定" in data["advisories"][0]
    assert data["advisories"][0] in data["warnings"]


def test_supplement_switch_rewrites_once_and_adopts_result(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid, ch = _setup(client)
    scene_id = _scene_with_beat(client, uid, ch, BEAT)
    prompts: list[str] = []
    supplemented = FINAL + "\n他判断相认等于替她揭开隐私，决定不点破。"

    async def fake_post(self, url, **kwargs):
        prompts.append(json.dumps(kwargs["json"], ensure_ascii=False))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": supplemented}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 20},
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setenv("YOUTHINK_KEY_CHOICE_REWRITE", "1")
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    resp = client.post(
        f"/api/v1/novels/{uid}/chapters/{ch}/scenes/{scene_id}/repetition-check",
        json={"scene_text": FINAL, "chapter_so_far": ""},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(prompts) == 1
    assert "补足人物明确的内心判断" in prompts[0]
    assert data["action"] == "supplemented"
    assert "决定不点破" in data["final_text"]
    assert "已按开关补写一句内心判断。" in data["warnings"]
