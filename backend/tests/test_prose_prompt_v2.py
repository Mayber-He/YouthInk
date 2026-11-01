"""T4: leaner / re-ordered prose-writing prompt.

No live LLM. Builds prompts from a throw-away DB only.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.builtin.prompt_templates import BUILTIN_PROMPT_TEMPLATES
from app.core.config import reset_config_for_testing
from app.db.manager import ensure_global_db_initialized, get_global_db, get_novel_db
from app.db.repositories.settings_repo import SettingsRepository
from app.main import create_app
from app.schemas.writing import StreamWriteRequest
from app.services.prompt.prose_prompt import (
    ENDING_MODES,
    core_setting_blurb,
    ending_rule,
    protagonist_brief,
    prose_prompt_v2_enabled,
    style_layer,
)
from app.services.writing_service import _LEGACY_SYSTEM_ROLE, WritingService

LATE_PLOT = "两人最终结婚并共同创办公司"


# --- pure helpers ---

def test_system_role_compressed_at_least_30_percent_and_keeps_key_semantics() -> None:
    new = BUILTIN_PROMPT_TEMPLATES["system_role"]["content"]
    assert len(new) <= len(_LEGACY_SYSTEM_ROLE) * 0.70
    # 3–4 numbered principles remain.
    numbered = [ln for ln in new.splitlines() if ln[:2] in ("1.", "2.", "3.", "4.", "5.", "6.")]
    assert 3 <= len(numbered) <= 4
    # Key semantics survive: author-info != character knowledge, POV limits, continuity,
    # unfamiliar-place behaviour, and no thematic summing-up at the end.
    for must in ("不等于角色已知", "视角", "一致", "陌生", "不升华"):
        assert must in new
    # Positive phrasing: the old "严禁" wall is gone.
    assert "严禁" not in new


def test_core_setting_blurb_is_at_most_two_sentences_and_200_chars() -> None:
    synopsis = (
        "大一开学前的暑假，江澈认识了一个特别的网友。她叫软糖。"
        "后来他们在大学相遇。" + LATE_PLOT + "。"
    )
    blurb = core_setting_blurb(synopsis)
    assert LATE_PLOT not in blurb
    assert len(blurb) <= 200
    assert blurb.count("。") <= 2


def test_core_setting_blurb_falls_back_to_protagonist_when_no_synopsis() -> None:
    assert core_setting_blurb("", "男主江澈，大一新生。") == "男主江澈，大一新生。"
    assert core_setting_blurb("", "") == ""


def test_core_setting_blurb_hard_cuts_one_giant_sentence() -> None:
    giant = "字" * 500 + "。"
    assert len(core_setting_blurb(giant)) <= 200


def test_protagonist_brief_is_capped() -> None:
    long = "。".join(["江澈是大一新生"] * 80) + "。"
    assert len(protagonist_brief(long)) <= 300


def test_style_layer_with_style_note_still_has_forbidden_and_two_examples() -> None:
    out = style_layer(
        style_name="清新校园",
        forbidden_exprs=["不由得", "莫名地"],
        example_paras=["范文一", "范文二", "范文三"],
        has_style_note=True,
    )
    assert "不由得" in out and "莫名地" in out
    assert "范文一" in out and "范文二" in out
    assert "范文三" not in out  # capped at 2
    # Descriptive template fields are skipped when the author has their own note.
    assert "风格模板" not in out


def test_style_layer_without_note_keeps_full_template() -> None:
    out = style_layer(style_name="清新校园", pov="第三人称限知", forbidden_exprs=["不由得"],
                      example_paras=["范文一"], has_style_note=False)
    assert "风格模板：清新校园" in out
    assert "不由得" in out


def test_ending_rule_rotates_between_adjacent_scenes() -> None:
    r1, r2, r3 = ending_rule(1), ending_rule(2), ending_rule(3)
    assert len({r1, r2, r3}) == 3
    assert ending_rule(1) == ending_rule(1 + len(ENDING_MODES))
    for r in (r1, r2, r3):
        assert "最后一句用对话、动作或决定结束" in r
        assert "不要以意象" in r


def test_feature_switch_default_on_and_can_disable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("YOUTHINK_PROSE_PROMPT_V2", raising=False)
    assert prose_prompt_v2_enabled() is True
    monkeypatch.setenv("YOUTHINK_PROSE_PROMPT_V2", "0")
    assert prose_prompt_v2_enabled() is False


# --- integration: real WritingService on a throw-away DB ---

@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    reset_config_for_testing(tmp_path / "test_data_t4")
    ensure_global_db_initialized()
    app = create_app()
    c = TestClient(app)
    c.post(
        "/api/v1/settings/llm-profiles",
        json={"name": "T4", "base_url": "https://api.example.com/v1",
              "model": "deepseek-chat", "api_key": "sk-t4", "is_default": True},
    )
    return c


@pytest.fixture()
def book(client: TestClient):
    synopsis = (
        "大一开学前的暑假，江澈认识了一个特别的网友。" + LATE_PLOT + "。"
        + "后续剧情很长很长。" * 60
    )
    uid = client.post(
        "/api/v1/novels",
        json={"title": "T4书", "genre": "校园", "tone": "清新", "pov": "第三人称限知",
              "protagonist_concept": "江澈，大一新生。", "synopsis": synopsis,
              "style_template_id": 1, "style_note": "作者要求：轻松欢脱。"},
    ).json()["novel_uid"]
    client.post(f"/api/v1/novels/{uid}/characters", json={"name": "江澈", "role": "male_lead"})
    client.post(f"/api/v1/novels/{uid}/locations", json={"name": "报到处"})
    v = client.post(f"/api/v1/novels/{uid}/outline/volumes", json={"title": "卷一"}).json()["id"]
    a = client.post(f"/api/v1/novels/{uid}/outline/arcs",
                    json={"volume_id": v, "title": "弧一"}).json()["id"]
    ch = client.post(f"/api/v1/novels/{uid}/outline/chapters",
                     json={"arc_id": a, "title": "报到日", "synopsis": "江澈报到。"}).json()["id"]
    scene_ids = []
    for i in range(1, 4):
        r = client.post(
            f"/api/v1/novels/{uid}/chapters/{ch}/scenes",
            json={"beat": f"目标：第{i}场景\n必须发生：事件{i}", "target_words": 800},
        ).json()
        scene_ids.append(r["id"])
    return uid, ch, scene_ids


def _prompts(uid: str, req: StreamWriteRequest, **kw):
    with get_novel_db(uid) as nconn, get_global_db() as gconn:
        svc = WritingService(uid, nconn, SettingsRepository(gconn))
        return svc.prepare_stream_write_prompts(req, **kw)


def test_prose_prompt_has_no_late_plot_and_keeps_forbidden_and_examples(book) -> None:
    uid, ch, scenes = book
    sys_p, user_p = _prompts(uid, StreamWriteRequest(chapter_id=ch, scene_id=scenes[0], mode="scene"))
    full = sys_p + user_p
    assert LATE_PLOT not in full  # whole-book synopsis tail no longer injected
    assert "全书梗概" not in sys_p
    assert "核心设定" in sys_p
    # style_note is set, yet forbidden expressions + example paragraphs are present.
    assert "禁用套话表达" in sys_p
    assert "不由得" in sys_p
    assert sys_p.count("示例：") == 2
    assert "作者要求：轻松欢脱。" in sys_p  # author's note still wins / still present


def test_user_prompt_order_constraints_then_history_then_scene_then_instruction(book) -> None:
    uid, ch, scenes = book
    _s, user_p = _prompts(
        uid,
        StreamWriteRequest(chapter_id=ch, scene_id=scenes[1], mode="scene",
                           existing_content="本章已写的一段正文。"),
    )
    i_constraint = user_p.index("硬约束清单")
    i_chars = user_p.index("出场人物卡与当前时序状态")
    i_written = user_p.index("本章已写前文")
    i_scene = user_p.index("本章细纲与场景节拍")
    i_task = user_p.index("【⑤ 当前任务指令】")
    assert i_constraint < i_written < i_scene < i_task
    assert i_chars < i_written < i_scene < i_task
    # The scene list is the LAST '###' block: only the ⑤ task instruction and ⑥ format follow it.
    assert "### " not in user_p[i_scene:]
    assert user_p.rindex("### ") < i_scene


def test_ending_rule_present_and_rotates_across_scenes(book) -> None:
    uid, ch, scenes = book
    endings = []
    for sid in scenes:
        _s, user_p = _prompts(uid, StreamWriteRequest(chapter_id=ch, scene_id=sid, mode="scene"))
        assert "最后一句用对话、动作或决定结束" in user_p
        assert "不要以意象" in user_p
        endings.append(user_p.split("本场景优先以", 1)[1].split("收束", 1)[0])
    assert len(set(endings)) == 3  # adjacent scenes use different closing modes


def test_legacy_flag_and_env_switch_restore_old_layout(book, monkeypatch) -> None:
    uid, ch, scenes = book
    req = StreamWriteRequest(chapter_id=ch, scene_id=scenes[0], mode="scene")
    sys_old, user_old = _prompts(uid, req, legacy=True)
    assert "全书梗概" in sys_old and LATE_PLOT in sys_old
    assert "收尾规则" not in user_old

    monkeypatch.setenv("YOUTHINK_PROSE_PROMPT_V2", "0")
    sys_off, user_off = _prompts(uid, req)
    assert "全书梗概" in sys_off
    assert "收尾规则" not in user_off

    monkeypatch.setenv("YOUTHINK_PROSE_PROMPT_V2", "1")
    sys_new, _ = _prompts(uid, req)
    assert len(sys_new) < len(sys_old)
