"""T22: narration aliases — hide the real name while the POV does not know it.

Samples are scenes 2 and 3 of the third live evaluation (`live_eval_export3.md`):
both use “裴南栀” in prose before the POV is ever told the name. No live LLM.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.db.manager import get_global_db, get_novel_db
from app.db.repositories.settings_repo import SettingsRepository
from app.schemas.writing import StreamWriteRequest
from app.services.narration_alias import (
    alias_rule,
    apply_aliases,
    collect_narration_aliases,
    parse_narration_aliases,
    strip_narration_lines,
)
from app.services.repetition_guard import RepetitionConfig, analyze_scene_repetition
from app.services.repetition_service import build_rewrite_instruction
from app.services.scene_planning import format_scene_beat
from app.services.writing_service import WritingService
from test_scene_event_checklist import _scene_body, _setup, client  # noqa: F401

FIX = Path(__file__).parent / "fixtures"
BEAT2 = (FIX / "t22_scene2_beat.txt").read_text(encoding="utf-8")
FINAL2 = (FIX / "t22_scene2_final.txt").read_text(encoding="utf-8")
BEAT3 = (FIX / "t22_scene3_beat.txt").read_text(encoding="utf-8")
FINAL3 = (FIX / "t22_scene3_final.txt").read_text(encoding="utf-8")

ALIAS_LINE = "叙述称呼：裴南栀→白衬衫学姐"


# ----------------------------------------------------------- parsing helpers

def test_parse_strip_and_apply_alias_line() -> None:
    beat = f"{BEAT2.rstrip()}\n{ALIAS_LINE}\n"
    assert parse_narration_aliases(beat) == {"裴南栀": "白衬衫学姐"}
    assert "叙述称呼" not in strip_narration_lines(beat)
    replaced = apply_aliases(FINAL2, {"裴南栀": "白衬衫学姐"})
    assert "白衬衫学姐" in replaced
    assert "裴南栀" not in replaced


def test_collect_aliases_across_scenes_and_rule_text() -> None:
    aliases = collect_narration_aliases([ALIAS_LINE, "叙述称呼：林鹿→马尾女生"])
    assert aliases == {"裴南栀": "白衬衫学姐", "林鹿": "马尾女生"}
    rule = alias_rule(aliases)
    assert "正文叙述不得出现本名" in rule
    assert "「裴南栀」→「白衬衫学姐」" in rule


def test_format_scene_beat_serializes_narration_alias() -> None:
    beat = format_scene_beat(
        "让江澈认出学姐",
        "桌前",
        ["他确认学姐就是网友"],
        "把事压在心里",
        [],
        narration_alias="裴南栀→白衬衫学姐",
    )
    assert "叙述称呼：裴南栀→白衬衫学姐" in beat


# ----------------------------------------------------------- repetition reason

def test_scene2_real_name_is_flagged_and_rewrite_replaces_it() -> None:
    beat = f"{BEAT2.rstrip()}\n{ALIAS_LINE}\n"
    report = analyze_scene_repetition(
        FINAL2, previous_chapter="", chapter_so_far="", beat=beat, config=RepetitionConfig()
    )
    assert report.alias_hits
    assert report.alias_hits[0].real_name == "裴南栀"
    assert report.alias_hits[0].alias == "白衬衫学姐"
    assert report.alias_hits[0].count == FINAL2.count("裴南栀")
    assert any("叙述称呼违规" in reason for reason in report.reasons)

    instruction = build_rewrite_instruction(report)
    assert "「裴南栀」→「白衬衫学姐」" in instruction
    assert "必须全部替换" in instruction


def test_scene3_real_name_is_flagged() -> None:
    beat = f"{BEAT3.rstrip()}\n{ALIAS_LINE}\n"
    report = analyze_scene_repetition(
        FINAL3, previous_chapter="", chapter_so_far="", beat=beat, config=RepetitionConfig()
    )
    assert any(v.real_name == "裴南栀" for v in report.alias_hits)


def test_without_alias_line_real_name_is_not_flagged() -> None:
    report = analyze_scene_repetition(
        FINAL2, previous_chapter="", chapter_so_far="", beat=BEAT2, config=RepetitionConfig()
    )
    assert report.alias_hits == []
    assert not any("叙述称呼违规" in reason for reason in report.reasons)


# ----------------------------------------------------------- prompt assembly

def _prompts_for_beat(client, uid: str, ch: int, beat: str) -> tuple[str, str]:
    scene = client.post(
        f"/api/v1/novels/{uid}/chapters/{ch}/scenes",
        json={"beat": beat, "target_words": 700},
    ).json()
    with get_novel_db(uid) as nconn, get_global_db() as gconn:
        svc = WritingService(uid, nconn, SettingsRepository(gconn))
        return svc.prepare_stream_write_prompts(
            StreamWriteRequest(chapter_id=ch, scene_id=scene["id"], mode="scene")
        )


def test_write_prompt_hides_real_name_and_states_alias_rule(client) -> None:
    uid, ch = _setup(client)
    beat = f"{BEAT2.rstrip()}\n{ALIAS_LINE}\n"
    system, user = _prompts_for_beat(client, uid, ch, beat)

    before_rule = user.split("【叙述称呼】", 1)[0]
    assert "裴南栀" not in before_rule  # beat and context blocks show the alias only
    assert "白衬衫学姐" in before_rule
    assert "叙述称呼：" not in user  # meta line never reaches the prose model
    assert "正文叙述不得出现本名" in user
    assert "裴南栀" not in system


def test_write_prompt_without_alias_line_keeps_real_name(client) -> None:
    uid, ch = _setup(client)
    beat = "目标：裴南栀给江澈指路\n起点状态：校门口\n必须发生：裴南栀指路\n终点状态：江澈道谢"
    _system, user = _prompts_for_beat(client, uid, ch, beat)
    assert "裴南栀" in user
    assert "正文叙述不得出现本名" not in user


# ----------------------------------------------------------- planning prompt

def test_planning_prompt_asks_for_alias_and_serializes_it(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid, ch = _setup(client)
    prompts: list[str] = []
    scenes = [{
        "goal": "江澈在报到处遇到学姐",
        "entry_state": "江澈刚进校门，不知道对方姓名",
        "must_happen": ["江澈问路", "学姐指路"],
        "exit_state": "江澈记住这位学姐",
        "must_not_include": [],
        "narration_alias": "裴南栀→白衬衫学姐",
        "pov_character_name": "江澈",
        "character_names": ["江澈", "裴南栀"],
        "story_time": "报到日上午",
        "target_words": 700,
    }]

    async def fake_post(self, url, **kwargs):
        prompts.append(kwargs["json"]["messages"][-1]["content"])
        return httpx.Response(
            200, json=_scene_body(scenes), request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    resp = client.post(
        f"/api/v1/novels/{uid}/chapters/{ch}/scenes/generate", json={"scene_count": 1}
    )
    assert resp.status_code == 200, resp.text
    assert "【叙述称呼】" in prompts[0]
    assert "narration_alias" in prompts[0]
    assert "看到名牌/被人喊出名字" in prompts[0]
    assert "叙述称呼：裴南栀→白衬衫学姐" in resp.json()[0]["beat"]
