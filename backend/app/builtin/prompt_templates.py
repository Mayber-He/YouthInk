"""Built-in prompt templates for each task type (Design Doc Section 7.2)."""

from __future__ import annotations

from typing import Any

BUILTIN_PROMPT_TEMPLATES: dict[str, dict[str, Any]] = {
    "system_role": {
        "version": "2.0",
        "description": "① 系统角色基础设定（4 条正向写法，压缩自原六条铁律）",
        "content": (
            "你是擅长青春文学与长篇连载的资深小说作家，文笔自然细腻，用具体的感官细节（光线、声音、气味、动作）代替空洞的情绪词。\n"
            "写作时守住四点：\n"
            "1. 先认设定再落笔：人物卡的既有经历与关系是故事事实，称呼、语气与距离要与之及前文一致；"
            "但这些是作者信息，不等于角色已知——角色只说得出自己亲历或被告知的事。初到陌生之地要写出打量、看路牌、问路。\n"
            "2. 守住视角：只从当前视角人物的五感与认知写，写他看到的言行与神情，不替他人读心；只有在场人物开口，已离场者不插话。\n"
            "3. 前后一致：时间、季节、伤病、物品与食物称谓、已完成的动作都要延续；移动要有过渡，道具不凭空出现或消失；言行与消费能力符合年龄身份。\n"
            "4. 收得干脆：场景和章节结尾落在对话、动作或决定上，不升华主题，不替读者总结点题。"
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
        "version": "1.2",
        "description": "生成人物卡设定（JSON，含多维常理硬约束推导）",
        "content": (
            "请根据作品《{{title}}》的立项与世界观，设计核心与重要人物卡。\n"
            "角色定位（role）取值：female_lead / male_lead / major / minor / extra。\n"
            "要求每位角色具备鲜明反差感、具体的说话风格与清晰的人物成长弧光。\n"
            "额外要求：为每位角色从 background / initial_age / 身份处境中反向推导 2~4 条【硬约束】"
            "（constraints，字符串数组）——即该角色在开篇阶段【绝不能】被写出的违反常理内容，需覆盖以下常理维度：\n"
            "1. 环境与空间熟悉度边界（如大一新生/转学生 → 「刚入学报到对校园环境陌生，找路、看指示牌或问路是合理的；绝不能写他对校园道路、建筑布局熟门熟路、了如指掌」）；\n"
            "2. 人际交往与初见边界（如慢热/警戒心强/初入新集体 → 「面对陌生同学保持礼貌疏离，绝不能初见就自来熟、主动掏心掏肺或未听自我介绍便直呼对方姓名」）；\n"
            "3. 年龄、身份与能力/经济边界（如普通高中生/家境普通学生 → 「社会经验、消费水平与技能受限于学生身份，绝不能做出超越年龄的老练应酬或随手挥霍高昂开销」）。\n"
            "硬约束必须是具体、可判定的行为禁令，而不是性格描述的复述。"
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
        "version": "2.0",
        "description": "生成章节场景事件清单（JSON：goal/entry_state/must_happen/exit_state/must_not_include）",
        "content": (
            "请为章节《{{chapter_title}}》（梗概：{{chapter_synopsis}}，目标字数：{{target_words}}）拆解场景。\n"
            "每个场景以【事件清单】形式给出，而不是散文式节拍：写清本场目标、起点状态、必须发生的事件、"
            "终点状态与本场禁止出现的素材；只写事件与状态，不写具体台词、分镜动作细节或结尾意象。\n"
            "按剧情重要性分配场景：冲突、决定、关系变化和结果单独成场；纯过渡、重复动作或没有新结果的日常过程应合并，不要凑场景数。\n"
            "常理要求：场景必须符合人物当前身份阶段与情境常理（如刚报到/初访某地应体现找路、观察或陌生感，严禁熟门熟路；初见人物应有合理相识过程；时间推移与地点转换需自然连贯）。"
        ),
    },
    "write_scene": {
        "version": "1.2",
        "description": "逐场景正文生成（流式文本，含情境与视角常理约束）",
        "content": (
            "现在开始撰写《{{chapter_title}}》的第 {{scene_index}} 个场景。\n"
            "【本场景节拍要求】\n{{scene_beat}}\n"
            "【目标字数】约 {{target_words}} 字。\n"
            "【写作常理自检】动笔时请严格遵守本场景的视角人物（POV）、在场人物与情境常理："
            "若角色初来乍到（如新生报到/初访场所）必须体现对环境的陌生感与摸索，严禁熟门熟路；"
            "若人物初见或尚不熟悉，严禁自来熟或未介绍便知晓对方姓名与底细；"
            "若两个人物此前只通过文字沟通，首次听到声音时只能写声音本身，不得拿语调、音色与文字消息对照。"
            "严格限制在 POV 感官范围内描写，未在场角色不得插话。\n"
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
