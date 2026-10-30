"""Built-in prompt templates for each task type (Design Doc Section 7.2)."""

from __future__ import annotations

from typing import Any

BUILTIN_PROMPT_TEMPLATES: dict[str, dict[str, Any]] = {
    "system_role": {
        "version": "1.0",
        "description": "① 系统角色基础设定",
        "content": (
            "你是一位擅长青春文学与长篇连载创作的资深小说作家与文学统筹编辑。\n"
            "你的文笔自然细腻、充满生活质感与时代气息，善于用具体的感官细节（光线、声音、气味、细微动作）替代空洞的情绪形容词。\n"
            "创作铁律：\n"
            "1. 严格遵守世界观、人物设定、当前人物状态与认知约束（人物绝不能提及或知晓其尚未得知的秘密）。\n"
            "2. 对话必须贴合各自人物的性格内核与说话习惯，杜绝千人一面。\n"
            "3. 严禁在章节末尾强行升华主题、替读者总结点题或使用陈词滥调。"
        ),
    },
    "generate_worldview": {
        "version": "1.0",
        "description": "生成世界观设定（JSON）",
        "content": (
            "请根据作品立项信息，为《{{title}}》构建真实可感的青春故事世界观条目。\n"
            "需涵盖以下分类（category）：\n"
            "- era（时代背景）\n"
            "- city（城市风貌与生活气息）\n"
            "- school（学校或核心活动场所生态）\n"
            "- rules（校规、家庭或社会隐性规则）\n"
            "- culture（同龄人流行文化与日常消遣）\n"
            "- term（故事专有名词或特殊惯例）\n"
            "已锁定的条目请勿重复生成：{{locked_items}}"
        ),
    },
    "generate_characters": {
        "version": "1.0",
        "description": "生成人物卡设定（JSON）",
        "content": (
            "请根据作品《{{title}}》的立项与世界观，设计核心与重要人物卡。\n"
            "角色定位（role）取值：female_lead / male_lead / major / minor / extra。\n"
            "要求每位角色具备鲜明反差感、具体的说话风格与清晰的人物成长弧光。"
        ),
    },
    "generate_locations": {
        "version": "1.0",
        "description": "生成地点设定（JSON）",
        "content": (
            "请根据作品《{{title}}》的世界观与人物活动轨迹，生成核心故事地点。\n"
            "每个地点需包含具体的感官细节（声音、气味、光线与季节变化特征）。"
        ),
    },
    "generate_main_plot": {
        "version": "1.0",
        "description": "生成主线剧情（JSON）",
        "content": (
            "请为《{{title}}》规划主线剧情脉络，包含核心矛盾冲突（core_conflict）、"
            "感情线走向（romance_arc，结局方向：{{romance_ending}}）、"
            "成长线走向（growth_arc，结局方向：{{growth_ending}}）以及关键转折点列表（key_turning_pts）。"
        ),
    },
    "generate_outline": {
        "version": "1.0",
        "description": "生成分卷、情节弧与章节目录（JSON）",
        "content": (
            "请根据《{{title}}》的主线剧情与目标篇幅，生成结构化分卷、情节弧及当前情节弧的章节目录。"
        ),
    },
    "generate_scenes": {
        "version": "1.0",
        "description": "生成章节场景细纲（JSON）",
        "content": (
            "请为章节《{{chapter_title}}》（梗概：{{chapter_synopsis}}，目标字数：{{target_words}}）拆解 2~4 个场景节拍。\n"
            "明确每个场景的节拍推进、视角人物、地点、出场人物及预估字数。"
        ),
    },
    "write_scene": {
        "version": "1.0",
        "description": "逐场景正文生成（流式文本）",
        "content": (
            "现在开始撰写《{{chapter_title}}》的第 {{scene_index}} 个场景。\n"
            "【本场景节拍要求】\n{{scene_beat}}\n"
            "【目标字数】约 {{target_words}} 字。\n"
            "请直接输出小说正文，不要包含任何标题、解释或结语。"
        ),
    },
    "rewrite_selection": {
        "version": "1.0",
        "description": "选中片段改写/扩写/缩写/润色/换语气（流式文本）",
        "content": (
            "请对以下选中小说片段执行【{{action_type}}】操作。\n"
            "附加要求：{{instruction}}\n"
            "【待处理原文片段】\n{{selected_text}}\n\n"
            "请直接输出修改后的正文片段，不要附加任何说明。"
        ),
    },
    "summarize_text": {
        "version": "1.0",
        "description": "生成分层摘要（章/弧/卷/全书）",
        "content": (
            "请为以下{{level_label}}内容生成精炼摘要（约 {{target_length}} 字），"
            "保留核心事件推进、情感转折、新出场人物与关键伏笔细节：\n\n{{source_text}}"
        ),
    },
    "extract_memories": {
        "version": "1.0",
        "description": "定稿后抽取事实、人物状态、认知、关系与伏笔（JSON）",
        "content": (
            "请仔细阅读本章定稿正文，抽取以下五类结构化记忆变更：\n"
            "1. facts（新增客观事实：人物属性、事件、物品、约定、地点细节）\n"
            "2. state_changes（人物状态变更：location/body/emotion/goal/identity/item/appearance）\n"
            "3. cognitive_records（认知记录：谁在本章得知了什么秘密或关键事实）\n"
            "4. relationship_changes（人物关系变更：关系类型、亲密度1-10、公开程度、原因）\n"
            "5. foreshadowing（伏笔埋下、暗示或回收）\n"
            "注意：每一条抽取结果必须附带准确的原文引用片段（source_quote）！"
        ),
    },
}
