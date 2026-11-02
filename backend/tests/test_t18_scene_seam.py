"""T18: scene seam detection + planning boundary checks.

Fixed samples are the real scene 1/2/3 finals from the live evaluation
(`docs/loop/live_calls2.json`). No live LLM: planning/rewrite calls are mocked.
"""

from __future__ import annotations

import json
from pathlib import Path

import asyncio

import httpx
import pytest

from app.services.repetition_guard import (
    RepetitionConfig,
    analyze_scene_repetition,
    find_scene_seam,
)
from app.services.repetition_service import build_rewrite_instruction, run_repetition_pipeline
from app.services.scene_planning import (
    describe_boundary_issues,
    find_adjacent_boundary_issues,
)
from test_scene_event_checklist import _scene_body, _setup, client

FIX = Path(__file__).parent / "fixtures"
SCENE1 = (FIX / "t18_scene1_final.txt").read_text(encoding="utf-8")
SCENE2 = (FIX / "t18_scene2_final.txt").read_text(encoding="utf-8")
SCENE3 = (FIX / "t17_scene3_initial.txt").read_text(encoding="utf-8")


# --- Seam detection (pure) ---

def test_scene2_ending_repeated_in_scene3_opening_is_detected() -> None:
    """Live sample: scene 3 opened by re-describing scene 2's final table-on-bag action."""
    spans = find_scene_seam(SCENE3, SCENE2, head_chars=200, tail_chars=300, n=6)
    assert spans, "the live scene 2 -> 3 seam must be detected"
    assert any("表格垫在行李袋上" in sp.text for sp in spans)
    assert all(sp.source == "previous_scene_tail" for sp in spans)

    report = analyze_scene_repetition(
        SCENE3, previous_chapter="", chapter_so_far=SCENE2,
        config=RepetitionConfig(),
    )
    assert report.seam_spans
    assert any("本场景开头与上一场景结尾" in reason for reason in report.reasons)
    assert report.triggered


def test_scene1_scene2_live_repeat_is_semantic_not_six_exact_chars() -> None:
    """The live '队伍停住' repeat is shorter than 6 exact chars, so the seam rule skips it.

    This documents the rule's blind spot: a restated state ("队伍停住了" -> "队伍彻底不动了")
    is not caught by exact-character overlap. The threshold is deliberately exact.
    """
    assert find_scene_seam(SCENE2, SCENE1, n=6) == []
    assert "队伍停住" not in SCENE2
    shorter = find_scene_seam(SCENE2, SCENE1, n=4)
    assert shorter
    assert max(sp.length for sp in shorter) == 5


def test_scene1_tail_repeated_verbatim_at_scene2_start_triggers() -> None:
    """If scene 2 had actually repeated scene 1's last line, the seam check would fire."""
    repeated = SCENE1[-40:] + "\n\n" + SCENE2
    spans = find_scene_seam(repeated, SCENE1, n=6)
    assert any("队伍停住了" in sp.text for sp in spans)

    report = analyze_scene_repetition(
        repeated, previous_chapter="", chapter_so_far=SCENE1,
        config=RepetitionConfig(),
    )
    assert any("本场景开头与上一场景结尾" in reason for reason in report.reasons)


def test_seam_check_is_switchable_and_thresholds_are_configurable() -> None:
    assert find_scene_seam(SCENE3, SCENE2, n=6)
    # 8 shared chars: a stricter 10-gram threshold no longer fires.
    assert find_scene_seam(SCENE3, SCENE2, n=10) == []
    # A 4-character head cannot contain a 6-character run.
    assert find_scene_seam(SCENE3, SCENE2, head_chars=4, n=6) == []
    # The previous-scene tail window is configurable too.
    assert find_scene_seam(SCENE3, SCENE2, tail_chars=4, n=6) == []

    off = analyze_scene_repetition(
        SCENE3, previous_chapter="", chapter_so_far=SCENE2,
        config=RepetitionConfig(seam_check=False),
    )
    assert off.seam_spans == []
    assert not any("上一场景结尾" in reason for reason in off.reasons)

    strict = analyze_scene_repetition(
        SCENE3, previous_chapter="", chapter_so_far=SCENE2,
        config=RepetitionConfig(seam_ngram=10),
    )
    assert strict.seam_spans == []


def test_seam_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YOUTHINK_REPEAT_SEAM_CHECK", "0")
    monkeypatch.setenv("YOUTHINK_REPEAT_SEAM_HEAD", "120")
    monkeypatch.setenv("YOUTHINK_REPEAT_SEAM_TAIL", "240")
    monkeypatch.setenv("YOUTHINK_REPEAT_SEAM_NGRAM", "7")
    cfg = RepetitionConfig.from_env()
    assert cfg.seam_check is False
    assert cfg.seam_head_chars == 120
    assert cfg.seam_tail_chars == 240
    assert cfg.seam_ngram == 7


def test_pipeline_rewrites_once_on_scene_seam() -> None:
    seen = []

    async def rewrite(_text: str, report) -> str:
        seen.append(report)
        return (
            "江澈把笔帽扣回去，抬头问登记台旁的志愿者接下来去哪。"
            "志愿者指了西边，他道谢，拎起行李袋往宿舍区走。"
        )

    out = asyncio.run(run_repetition_pipeline(
        SCENE3,
        previous_chapter="",
        chapter_so_far=SCENE2,
        must_not_include=[],
        config=RepetitionConfig(),
        rewrite_fn=rewrite,
    ))
    assert len(seen) == 1
    assert seen[0].seam_spans
    assert out["action"] == "rewritten"
    assert out["triggered"] is True
    assert any("上一场景结尾" in reason for reason in out["reasons"])
    assert "把笔帽扣回去" in out["final_text"]


def test_rewrite_prompt_lists_seam_repeat() -> None:
    report = analyze_scene_repetition(
        SCENE3, previous_chapter="", chapter_so_far=SCENE2,
        config=RepetitionConfig(),
    )
    prompt = build_rewrite_instruction(report)
    assert "本场景开头与上一场景结尾重复" in prompt
    assert "表格垫在行李袋上" in prompt
    assert "请从上场结束之后的新动作或新状态写起" in prompt


# --- Planning boundary (pure) ---

def test_exit_state_containing_next_trigger_is_flagged() -> None:
    issues = find_adjacent_boundary_issues(
        entry_states=["江澈刚进校门", "江澈在窗口前排队"],
        exit_states=["江澈刚办完入学手续并领到宿舍钥匙", "他拿着钥匙离开"],
        must_happen_per_scene=[["江澈找到报到处"], ["领到宿舍钥匙"]],
    )
    assert any(i.kind == "exit_contains_next_event" for i in issues)
    issue = next(i for i in issues if i.kind == "exit_contains_next_event")
    assert issue.index_a == 0 and issue.index_b == 1
    assert "领到宿舍钥匙" in issue.text_b
    assert "提前包含了" in describe_boundary_issues([issue])
    assert "终点状态必须停在触发事件之前" in describe_boundary_issues([issue])


def test_identical_exit_and_next_entry_is_flagged() -> None:
    issues = find_adjacent_boundary_issues(
        entry_states=["进校门", "江澈刚办完入学手续"],
        exit_states=["江澈刚办完入学手续", "拿材料"],
        must_happen_per_scene=[["找到报到处"], ["领宿舍钥匙"]],
    )
    assert any(i.kind == "exit_entry_similar" for i in issues)
    assert "过于相似" in describe_boundary_issues(issues)
    assert "下一场应从新的状态开始" in describe_boundary_issues(issues)


def test_clean_boundaries_have_no_issues() -> None:
    issues = find_adjacent_boundary_issues(
        entry_states=["江澈刚进校门", "江澈走到窗口前"],
        exit_states=["江澈排到队尾", "江澈拿到钥匙"],
        must_happen_per_scene=[["江澈找到报到处"], ["江澈领到宿舍钥匙"]],
    )
    assert issues == []
    assert describe_boundary_issues([]) == ""


# --- Integration: planning prompt + one re-split ---

def test_planning_prompt_states_boundary_rules_and_resplits_once(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid, ch = _setup(client)
    first_scenes = [
        {"goal": "报到", "entry_state": "江澈刚进校门",
         "must_happen": ["江澈找到报到处排队"],
         "exit_state": "江澈刚办完入学手续并领到宿舍钥匙",
         "must_not_include": [],
         "pov_character_name": "江澈", "character_names": ["江澈"], "target_words": 700},
        {"goal": "领钥匙", "entry_state": "江澈在窗口前排队",
         "must_happen": ["领到宿舍钥匙"],
         "exit_state": "他拿着钥匙离开", "must_not_include": [],
         "pov_character_name": "江澈", "character_names": ["江澈"], "target_words": 700},
    ]
    clean_scenes = [
        {"goal": "报到", "entry_state": "江澈刚进校门",
         "must_happen": ["江澈找到报到处排队"],
         "exit_state": "手续办到一半，轮到江澈", "must_not_include": [],
         "pov_character_name": "江澈", "character_names": ["江澈"], "target_words": 700},
        {"goal": "领钥匙", "entry_state": "江澈走到窗口前",
         "must_happen": ["领到宿舍钥匙"],
         "exit_state": "他拿着钥匙离开", "must_not_include": [],
         "pov_character_name": "江澈", "character_names": ["江澈"], "target_words": 700},
    ]
    calls = {"n": 0}
    prompts: list[str] = []

    async def fake_post(self, url, **kwargs):
        calls["n"] += 1
        prompts.append(kwargs["json"]["messages"][-1]["content"])
        body = _scene_body(first_scenes if calls["n"] == 1 else clean_scenes)
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    resp = client.post(f"/api/v1/novels/{uid}/chapters/{ch}/scenes/generate",
                       json={"scene_count": 2})
    assert resp.status_code == 200, resp.text
    assert calls["n"] == 2
    assert "exit_state 不得包含下一场景 must_happen 的触发事件" in prompts[0]
    assert "entry_state 必须从上一场 exit_state 之后开始" in prompts[0]
    assert "不得复述上场的动作或状态" in prompts[0]
    assert "终点状态越过场景边界" in prompts[1]
    assert "提前包含了" in prompts[1]
    assert "领到宿舍钥匙" in prompts[1]
    out = resp.json()
    assert "手续办到一半" in out[0]["beat"]
    assert "领到宿舍钥匙" in out[1]["beat"]


def test_boundary_issue_dataclass_is_json_serializable() -> None:
    issue = find_adjacent_boundary_issues(
        ["进校门", "窗口前"],
        ["江澈刚办完入学手续并领到宿舍钥匙", "离开"],
        [["找到报到处"], ["领到宿舍钥匙"]],
    )[0]
    assert json.loads(json.dumps(issue.__dict__, ensure_ascii=False))
