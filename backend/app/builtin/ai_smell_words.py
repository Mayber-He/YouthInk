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
        "pattern": "下意识地",
        "category": "高频套话",
        "suggestion": "减少「下意识地」机械修饰，直接写出动作本身",
        "is_regex": False,
    },
    {
        "pattern": "鬼使神差",
        "category": "高频套话",
        "suggestion": "用当时具体的感官诱因代替「鬼使神差」",
        "is_regex": False,
    },
    {
        "pattern": "微不可察",
        "category": "高频套话",
        "suggestion": "既然微不可察，视角人物如何看见？改为具体可见的细微动作",
        "is_regex": False,
    },
    {
        "pattern": "嘴角勾起一抹",
        "category": "网文套路",
        "suggestion": "改为自然具体的神态描写，如「笑了笑」「弯起眼睛」",
        "is_regex": False,
    },
    {
        "pattern": "嘴角微扬",
        "category": "网文套路",
        "suggestion": "结合具体语境写笑意，如「抿嘴忍着笑」「眼尾弯了弯」",
        "is_regex": False,
    },
    {
        "pattern": "骨节分明",
        "category": "网文套路",
        "suggestion": "避免高频手部套话，改写为手上的茧、粉笔灰或具体动作",
        "is_regex": False,
    },
    {
        "pattern": "喉结滚动",
        "category": "网文套路",
        "suggestion": "改为更符合青春校园气质的停顿、别开视线或耳根发热",
        "is_regex": False,
    },
    {
        "pattern": "墨色瞳孔",
        "category": "网文套路",
        "suggestion": "避免套路化五官词，改为眼神聚焦的具体事物",
        "is_regex": False,
    },
    {
        "pattern": "心中五味杂陈",
        "category": "抽象情绪",
        "suggestion": "用具体的动作停顿或感官细节替代抽象成语",
        "is_regex": False,
    },
    {
        "pattern": "复杂的神色",
        "category": "抽象情绪",
        "suggestion": "拆解「复杂」究竟是欲言又止、躲闪还是替对方担心",
        "is_regex": False,
    },
    {
        "pattern": "莫名的情绪",
        "category": "抽象情绪",
        "suggestion": "避免用「莫名」逃避心理刻画，写出具体触动点",
        "is_regex": False,
    },
    {
        "pattern": "苦涩的笑",
        "category": "抽象情绪",
        "suggestion": "通过动作细节（如低头抠书角、声音变轻）表现失落",
        "is_regex": False,
    },
    {
        "pattern": "眼中闪过一丝",
        "category": "高频套话",
        "suggestion": "通过视线变化、眨眼或手部动作体现心理波动",
        "is_regex": False,
    },
    {
        "pattern": "眼底闪过",
        "category": "高频套话",
        "suggestion": "删除「眼底闪过」，改用对话停顿或肢体细节表现情绪",
        "is_regex": False,
    },
    {
        "pattern": "深吸一口气",
        "category": "高频动作",
        "suggestion": "AI 极高频动作词，建议换为更贴合场景的小动作",
        "is_regex": False,
    },
    {
        "pattern": "空气仿佛凝固",
        "category": "陈词滥调",
        "suggestion": "通过具体的环境声响（如吊扇转动、窗外蝉鸣）衬托安静",
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
    {
        "pattern": r"一时间[，,]?谁也没有说话",
        "category": "套路转场",
        "suggestion": "描写沉默时两人各自的具体小动作或环境声",
        "is_regex": True,
    },
    {
        "pattern": r"心中(涌起|泛起)一(股|丝)难以言喻",
        "category": "抽象情绪",
        "suggestion": "删去「难以言喻」，用具体的身体感受或回忆片段落笔",
        "is_regex": True,
    },
]
