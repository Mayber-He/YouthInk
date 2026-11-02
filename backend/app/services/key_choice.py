"""T21: deterministic checks for "key choice" scenes.

A scene is a key-choice scene when its ``goal`` or ``exit_state`` says the POV
character confirms/decides/chooses something (or deliberately keeps it hidden).
For those scenes the beat must spell out the inner judgment/decision, and the
prose should end the choice with one explicit inner judgment instead of only
external action. Everything here is word-level heuristics: no LLM, no DB.

The live sample behind this module is scene 3 of the third evaluation
(``docs/loop/live_eval_export3.md``): its goal/exit mention 确认/决定/压在心里,
its ``must_happen`` only lists external actions, and the final prose never states
the decision.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Words in goal/exit_state that mark a scene as a key-choice scene.
KEY_CHOICE_MARKERS: tuple[str, ...] = (
    "确认",
    "决定",
    "选择",
    "不揭穿",
    "不点破",
    "压在心里",
    "暂不",
)

# Words in one ``must_happen`` item (or in the prose) that show an inner
# judgment/decision. "确认" is intentionally absent here: it is often used for
# external checks ("确认没有漏填"), which is exactly the false pass we must avoid.
DECISION_MARKERS: tuple[str, ...] = (
    "判断",
    "决定",
    "选择",
    "不揭穿",
    "不点破",
    "压在心里",
    "暂不",
    "打定主意",
    "拿定主意",
    "心想",
    "暗想",
    "暗下决心",
    "没说出口",
    "没有说出口",
    "压了下去",
    "咽了回去",
)

_SECTION_LABELS: tuple[tuple[str, str], ...] = (
    ("目标：", "goal"),
    ("起点状态：", "entry_state"),
    ("必须发生：", "must_happen"),
    ("终点状态：", "exit_state"),
    ("本场禁止出现：", "must_not_include"),
)

KEY_CHOICE_WRITE_RULE = "【关键选择收束】本场必须以一句明确的内心判断收束，不要只写动作。"


@dataclass
class KeyChoiceConfig:
    """Switch for the post-generation heuristic (warning-only by default)."""

    check: bool = True
    rewrite: bool = False

    @classmethod
    def from_env(cls) -> "KeyChoiceConfig":
        """``YOUTHINK_KEY_CHOICE_CHECK`` (default on) and
        ``YOUTHINK_KEY_CHOICE_REWRITE`` (default off: warn only)."""
        cfg = cls()

        def _flag(name: str, default: bool) -> bool:
            value = os.environ.get(name)
            return default if value is None else value.strip().lower() not in ("0", "false", "no", "")

        cfg.check = _flag("YOUTHINK_KEY_CHOICE_CHECK", cfg.check)
        cfg.rewrite = _flag("YOUTHINK_KEY_CHOICE_REWRITE", cfg.rewrite)
        return cfg


def parse_beat_sections(beat: str) -> dict[str, str]:
    """Split an event-checklist beat into its labelled sections.

    Legacy prose beats have no labels and return ``{}``; callers then avoid the
    deterministic checks instead of guessing.
    """
    sections: dict[str, str] = {}
    for raw in (beat or "").splitlines():
        line = raw.strip()
        for label, key in _SECTION_LABELS:
            if line.startswith(label):
                sections[key] = line[len(label):].strip()
                break
    return sections


def is_key_choice_text(goal: str, exit_state: str) -> bool:
    text = f"{goal or ''} {exit_state or ''}"
    return any(marker in text for marker in KEY_CHOICE_MARKERS)


def is_key_choice_beat(beat: str) -> bool:
    sections = parse_beat_sections(beat)
    goal = sections.get("goal", "")
    exit_state = sections.get("exit_state", "")
    if goal or exit_state:
        return is_key_choice_text(goal, exit_state)
    # Legacy prose beat: fall back to the whole text rather than skipping the check.
    return any(marker in (beat or "") for marker in KEY_CHOICE_MARKERS)


def must_happen_items(beat: str) -> list[str] | None:
    """Items of the ``必须发生`` line, or ``None`` for legacy prose beats."""
    raw = parse_beat_sections(beat).get("must_happen")
    if raw is None:
        return None
    return [item.strip() for item in raw.split("；") if item.strip()]


def has_inner_decision(items: list[str]) -> bool:
    return any(marker in item for item in items for marker in DECISION_MARKERS)


def lacks_inner_decision(scene_text: str) -> bool:
    """True when the prose never states an inner judgment/decision."""
    return not any(marker in (scene_text or "") for marker in DECISION_MARKERS)


@dataclass
class KeyChoiceIssue:
    index: int  # 0-based scene index
    goal: str
    exit_state: str

    @property
    def reason(self) -> str:
        return "must_happen 只有外部事件，缺少人物明确的内心判断和决定"


def find_planning_issues(
    goals: list[str],
    exit_states: list[str],
    must_happen_per_scene: list[list[str]],
) -> list[KeyChoiceIssue]:
    """Scenes that signal a key choice but never put the judgment in ``must_happen``."""
    issues: list[KeyChoiceIssue] = []
    count = min(len(goals), len(exit_states), len(must_happen_per_scene))
    for i in range(count):
        if not is_key_choice_text(goals[i], exit_states[i]):
            continue
        if has_inner_decision(list(must_happen_per_scene[i])):
            continue
        issues.append(KeyChoiceIssue(i, goals[i], exit_states[i]))
    return issues


def describe_planning_issues(issues: list[KeyChoiceIssue]) -> str:
    if not issues:
        return ""
    lines = [
        "以下场景是关键选择场景，但必须发生的事件没有写出人物的内心判断和决定，请重新拆分："
    ]
    for issue in issues:
        lines.append(
            f"- 场景{issue.index + 1} 的目标「{issue.goal}」/ 终点「{issue.exit_state}」"
            f"表明人物要做关键选择，但 {issue.reason}；"
            "请在 must_happen 中增加一条同时写出“他判断……，决定……”的事件。"
        )
    return "\n".join(lines)
