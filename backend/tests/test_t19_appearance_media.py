"""T19: appearance-card label repeats + text-only-to-voice media rule.

The fixed sample is the v4 chapter from the live evaluation (`docs/loop/live_eval_export2.md`):
scene 1/2/3 each mention 裴南栀's "眉心" once, so the card phrase "眉心" reaches 3. No live
LLM: the rewrite/planning calls are mocked or not reached.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.builtin.prompt_templates import BUILTIN_PROMPT_TEMPLATES
from app.core.config import reset_config_for_testing
from app.db.manager import ensure_global_db_initialized, get_global_db, get_novel_db
from app.db.repositories.settings_repo import SettingsRepository
from app.main import create_app
from app.schemas.writing import StreamWriteRequest
from app.services.repetition_guard import (
    RepetitionConfig,
    analyze_scene_repetition,
    extract_appearance_tags,
)
from app.services.repetition_service import build_rewrite_instruction, run_repetition_pipeline
from app.services.writing_service import WritingService

FIX = Path(__file__).parent / "fixtures"
SCENE1 = (FIX / "t18_scene1_final.txt").read_text(encoding="utf-8")
SCENE2 = (FIX / "t18_scene2_final.txt").read_text(encoding="utf-8")
SCENE3 = (FIX / "t17_scene3_initial.txt").read_text(encoding="utf-8")
APPEARANCE = (FIX / "t19_appearance_pei.txt").read_text(encoding="utf-8").strip()
MEDIA_RULE = (
    "若两个人物此前只通过文字沟通，首次听到声音时只能写声音本身，"
    "不得拿语调、音色与文字消息对照。"
)


# --- pure extraction / counting ---

def test_short_appearance_phrases_ignore_clothing_actions_and_other_nouns() -> None:
    tags = extract_appearance_tags(APPEARANCE)
    assert "眉心" in tags
    assert "站姿笔直" in tags
    assert all(2 <= len(tag) <= 8 for tag in tags)
    # A 9-character clause is not itself a tag; "低头" and "手机" are not appearance labels.
    assert "眉心有一点淡淡的褶" not in tags
    assert "低头" not in tags
    assert "手机" not in tags
    # T20-a: clothing/accessories are not appearance tags.
    assert "白衬衫" not in tags
    assert "素色发圈" not in tags
    assert "发圈" not in tags


def test_body_and_demeanor_phrases_survive_but_accessories_do_not() -> None:
    tags = extract_appearance_tags(
        "个子高挑，眼下的青色很淡，站姿笔直，白衬衫，素色发圈，校徽别在胸前。"
    )
    assert "站姿笔直" in tags
    assert "眼下的青色很淡" in tags or "眼下" in tags
    for accessory in ("白衬衫", "素色发圈", "发圈", "校徽"):
        assert accessory not in tags


def test_v4_meixi_repeat_is_detected_in_chapter_so_far_plus_scene() -> None:
    report = analyze_scene_repetition(
        SCENE3,
        previous_chapter="",
        chapter_so_far=SCENE1 + SCENE2,
        config=RepetitionConfig(),
        appearances=[APPEARANCE],
    )
    hit = next(h for h in report.appearance_hits if h.phrase == "眉心")
    assert hit.count == 3
    assert hit.scene_count == 1
    assert any("外貌标签重复" in reason and "眉心×3" in reason for reason in report.reasons)
    # T20-a: the repeated white shirt is clothing, not a body/expression label.
    assert all(h.phrase != "白衬衫" for h in report.appearance_hits)
    assert report.triggered


def test_appearance_tag_is_not_flagged_when_the_new_scene_does_not_use_it() -> None:
    report = analyze_scene_repetition(
        "清晨的操场很安静。",
        previous_chapter="",
        chapter_so_far="眉心" * 3,
        config=RepetitionConfig(),
        appearances=[APPEARANCE],
    )
    assert report.appearance_hits == []


def test_appearance_check_switch_and_threshold_are_configurable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _meixi_hit(cfg: RepetitionConfig):
        report = analyze_scene_repetition(
            SCENE3,
            previous_chapter="",
            chapter_so_far=SCENE1 + SCENE2,
            config=cfg,
            appearances=[APPEARANCE],
        )
        return next((h for h in report.appearance_hits if h.phrase == "眉心"), None)

    assert _meixi_hit(RepetitionConfig(appearance_max_count=5)) is None
    assert _meixi_hit(RepetitionConfig(appearance_check=False)) is None

    monkeypatch.setenv("YOUTHINK_REPEAT_APPEARANCE_CHECK", "0")
    monkeypatch.setenv("YOUTHINK_REPEAT_APPEARANCE_MAX", "4")
    cfg = RepetitionConfig.from_env()
    assert cfg.appearance_check is False
    assert cfg.appearance_max_count == 4


def test_rewrite_prompt_lists_the_appearance_tag_and_keeps_the_earliest() -> None:
    report = analyze_scene_repetition(
        SCENE3,
        previous_chapter="",
        chapter_so_far=SCENE1 + SCENE2,
        config=RepetitionConfig(),
        appearances=[APPEARANCE],
    )
    prompt = build_rewrite_instruction(report)
    line = next(row for row in prompt.splitlines() if "外貌标签" in row and "眉心" in row)
    assert "已出现 3 次" in line
    assert "本场 1 次" in line
    assert "保留最早一处" in line
    assert "其余在本场改写或删除" in line


def test_pipeline_rewrites_once_on_appearance_tag_repeat() -> None:
    scene = "她眉心那道褶没松开。他看见她眉心又动了一下。最后眉心垂下去。"
    seen = []

    async def rewrite(_text: str, report) -> str:
        seen.append(report)
        return "她垂下眼，没有接话。"

    out = asyncio.run(run_repetition_pipeline(
        scene,
        previous_chapter="",
        chapter_so_far="",
        must_not_include=[],
        config=RepetitionConfig(),
        rewrite_fn=rewrite,
        appearances=["眉心有一点淡淡的褶"],
    ))
    assert len(seen) == 1
    assert any(h.phrase == "眉心" and h.count == 3 for h in seen[0].appearance_hits)
    assert out["action"] == "rewritten"
    assert out["triggered"] is True
    assert "眉心" not in out["final_text"]


# --- media rule ---

def test_builtin_write_scene_self_check_contains_media_rule() -> None:
    content = BUILTIN_PROMPT_TEMPLATES["write_scene"]["content"]
    assert "【写作常理自检】" in content
    assert MEDIA_RULE in content
    assert content.index("【写作常理自检】") < content.index(MEDIA_RULE)


# --- integration: present character cards feed the endpoint ---

@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    reset_config_for_testing(tmp_path / "test_data_t19")
    ensure_global_db_initialized()
    c = TestClient(create_app())
    c.post(
        "/api/v1/settings/llm-profiles",
        json={"name": "T19", "base_url": "https://api.example.com/v1",
              "model": "deepseek-chat", "api_key": "sk-t19", "is_default": True},
    )
    return c


def _mk_book(client: TestClient, title: str = "T19书") -> tuple[str, int]:
    uid = client.post("/api/v1/novels", json={"title": title}).json()["novel_uid"]
    v = client.post(f"/api/v1/novels/{uid}/outline/volumes", json={"title": "卷一"}).json()["id"]
    a = client.post(f"/api/v1/novels/{uid}/outline/arcs",
                    json={"volume_id": v, "title": "弧一"}).json()["id"]
    ch = client.post(f"/api/v1/novels/{uid}/outline/chapters",
                     json={"arc_id": a, "title": "第一章", "synopsis": "开学"}).json()["id"]
    return uid, ch


def test_endpoint_uses_only_present_characters_appearance(client: TestClient) -> None:
    uid, ch = _mk_book(client)
    present = client.post(
        f"/api/v1/novels/{uid}/characters",
        json={"name": "裴南栀", "role": "female_lead", "appearance": "眉心有一点淡淡的褶"},
    ).json()
    client.post(
        f"/api/v1/novels/{uid}/characters",
        json={"name": "路人", "role": "extra", "appearance": "袖口扣到最上面一颗"},
    )
    scene = client.post(
        f"/api/v1/novels/{uid}/chapters/{ch}/scenes",
        json={
            "beat": "目标：报到\n必须发生：她抬头",
            "pov_character": present["id"],
            "character_ids": [present["id"]],
            "target_words": 500,
        },
    ).json()["id"]
    text = (
        "她眉心那道褶没有松开。他看了一眼，眉心又动了动。最后她眉心垂下去。"
        "她抬手理了理袖口，又低头看袖口，最后把袖口扣好。"
    )
    resp = client.post(
        f"/api/v1/novels/{uid}/chapters/{ch}/scenes/{scene}/repetition-check",
        json={"scene_text": text, "chapter_so_far": "", "auto_rewrite": False},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["triggered"] is True
    phrases = [h["phrase"] for h in body["report"]["appearance_hits"]]
    assert "眉心" in phrases
    assert "袖口" not in phrases  # 路人 is not present in this scene


def test_stream_write_prompt_actually_carries_media_rule(client: TestClient) -> None:
    uid, ch = _mk_book(client)
    client.post(f"/api/v1/novels/{uid}/characters", json={"name": "江澈", "role": "male_lead"})
    client.post(f"/api/v1/novels/{uid}/characters", json={"name": "裴南栀", "role": "female_lead"})
    scene_id = client.post(
        f"/api/v1/novels/{uid}/chapters/{ch}/scenes",
        json={"beat": "目标：初见\n必须发生：她开口", "target_words": 500},
    ).json()["id"]

    with get_novel_db(uid) as nconn, get_global_db() as gconn:
        svc = WritingService(uid, nconn, SettingsRepository(gconn))
        _sys, user_p = svc.prepare_stream_write_prompts(
            StreamWriteRequest(chapter_id=ch, scene_id=scene_id, mode="scene")
        )
    assert MEDIA_RULE in user_p
