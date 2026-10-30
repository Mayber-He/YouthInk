"""Local AI smell vocabulary and regex rules for detection (Design Doc Section 7.4)."""

from __future__ import annotations

from typing import TypedDict


class AiSmellRule(TypedDict):
    pattern: str
    category: str
    suggestion: str
    is_regex: bool


BUILTIN_AI_SMELL_RULES: list[AiSmellRule] = [
    {
        "pattern": "不由得",
        "category": "高频套话",
        "suggestion": "删除「不由得」，直接描写具体动作或生理反应",
        "is_regex": False,
    },
    {
        "pattern": "嘴角勾起一抹",
        "category": "网文套路",
        "suggestion": "改为自然具体的神态描写，如「笑了笑」「弯起眼睛」",
        "is_regex": False,
    },
    {
        "pattern": "心中五味杂陈",
        "category": "抽象情绪",
        "suggestion": "用具体的动作停顿或感官细节替代抽象成语",
        "is_regex": False,
    },
    {
        "pattern": "眼中闪过一丝",
        "category": "高频套话",
        "suggestion": "通过视线变化、眨眼或手部动作体现心理波动",
        "is_regex": False,
    },
    {
        "pattern": "命运的齿轮",
        "category": "陈词滥调",
        "suggestion": "避免宏大旁白点题，回到当下场景细节",
        "is_regex": False,
    },
    {
        "pattern": r"不知为何[，,]?她?他?总觉得",
        "category": "模糊过渡",
        "suggestion": "明确触发直觉的细节线索，或直接略去模糊铺垫",
        "is_regex": True,
    },
    {
        "pattern": r"在(这|那)一刻[，,]?仿佛整个世界都",
        "category": "过度抒情",
        "suggestion": "用周围环境声音的远去或某个具体定格画面表现专注感",
        "is_regex": True,
    },
]
