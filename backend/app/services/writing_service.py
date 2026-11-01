"""AI Scene Outline Generation and Streaming Prompt Preparation Service (M3)."""

from __future__ import annotations

import json
import sqlite3

from app.db.repositories.entity_repo import EntityRepository
from app.db.repositories.novel_repo import NovelRepository
from app.db.repositories.outline_repo import OutlineRepository
from app.db.repositories.settings_repo import SettingsRepository
from app.db.repositories.writing_repo import WritingRepository
from app.schemas.writing import (
    LlmSceneBatchOutput,
    SceneCreate,
    SceneResponse,
    StreamRewriteRequest,
    StreamSupplementRequest,
    StreamWriteRequest,
    SelectionCritiqueResponse,
)
from app.services.context.assembler import ContextAssembler
from app.services.llm.client import complete_chat
from app.services.llm.json_parser import parse_and_validate_json
from app.services.prompt.renderer import assemble_six_layer_prompt, render_template


def _word_count_range(target: int) -> str:
    lower = round(target * 0.8)
    upper = round(target * 1.12)
    return f"{lower:,}–{upper:,}"


class WritingService:
    """Handles AI scene beat generation and prepares 6-layer prompts for SSE streaming."""

    def __init__(
        self,
        novel_uid: str,
        novel_conn: sqlite3.Connection,
        settings_repo: SettingsRepository,
    ) -> None:
        self._novel_uid = novel_uid
        self._conn = novel_conn
        self._novel_repo = NovelRepository(novel_conn, novel_uid)
        self._entity_repo = EntityRepository(novel_conn)
        self._outline_repo = OutlineRepository(novel_conn)
        self._writing_repo = WritingRepository(novel_conn)
        self._settings_repo = settings_repo
        self._assembler = ContextAssembler(novel_conn, novel_uid, settings_repo)

    def _build_base_layers(self) -> tuple[str, str, str]:
        prompts = {p.task_type: p for p in self._settings_repo.list_prompt_templates()}
        layer1 = prompts["system_role"].content
        novel = self._novel_repo.get_novel_detail()
        styles = self._settings_repo.list_style_templates()
        style = next((s for s in styles if s.id == novel.style_template_id), None)

        layer2 = ""
        if style and not (novel.style_note or '').strip():
            examples = "\n".join(f"示例：{ex}" for ex in style.example_paras[:2])
            layer2 = (
                f"风格模板：{style.name}\n"
                f"叙事视角：{novel.pov or style.pov} | 语感：{style.tense_feel}\n"
                f"基调：{novel.tone or style.tone} | 句式：{style.sentence_pref} | 对话比例：{style.dialogue_ratio}\n"
                f"描写侧重：{style.desc_focus} | 节奏：{style.pacing}\n"
                f"禁用套话表达：{', '.join(style.forbidden_exprs)}\n"
                f"{examples}"
            )

        from app.services.prompt.author_style import author_style_prompt
        layer2 += "\n" + author_style_prompt(novel)

        layer3 = (
            f"书名：《{novel.title}》\n"
            f"题材：{novel.genre or '校园'} | 基调：{novel.tone or '清新治愈'} | 视角：{novel.pov or '第三人称限知'}\n"
            f"主角概念：{novel.protagonist_concept or ''}\n"
            f"全书梗概：{novel.synopsis or ''}\n"
            f"结局方向：感情线({novel.romance_ending or 'HE'}) / 成长线({novel.growth_ending or 'HE'})"
        )
        return layer1, layer2, layer3

    async def generate_chapter_scenes(
        self, chapter_id: int, scene_count: int = 3, instruction: str = ""
    ) -> list[SceneResponse]:
        """Generate structured scene beats for chapter_id and map character/location names to IDs."""
        novel = self._novel_repo.get_novel_detail()
        ch = self._outline_repo.get_chapter(chapter_id)
        chars = self._entity_repo.list_characters()
        locs = self._entity_repo.list_locations()

        layer1, layer2, layer3 = self._build_base_layers()
        context = (
            f"当前章节：第 {ch.display_index} 章《{ch.title}》\n"
            f"章节梗概：{ch.synopsis}\n"
            "人物卡中的既有经历与人物弧线（章节事实约束）："
            f"{json.dumps([{'name': c.name, 'role': c.role, 'background': c.background, 'arc_design': c.arc_design} for c in chars], ensure_ascii=False)}\n"
            f"可用地点列表：{json.dumps([l.name for l in locs], ensure_ascii=False)}"
        )

        tpl = next(
            p for p in self._settings_repo.list_prompt_templates() if p.task_type == "generate_scenes"
        )
        inst = render_template(
            tpl.content,
            {
                "chapter_title": ch.title,
                "chapter_synopsis": ch.synopsis,
                "target_words": novel.words_per_chapter,
            },
        )
        inst += f"\n请拆解为 {scene_count} 个场景节拍。节拍描述中可用 @人物名 和 @地点名 标注关联实体。"
        inst += (
            "人物卡中的既有经历和关系是必须遵守的故事事实；不得把已经认识或持续联系的人物安排成初次相识、首次加好友。"
            "人物卡不代表 POV 自动知晓他人的私密信息，但不能因此改写人物既有经历。若章节梗概与人物卡冲突，调整场景节拍以遵守人物卡与前文事实。"
        )
        if instruction:
            inst += f"\n作者附加要求：{instruction}"

        fmt = (
            '请输出纯 JSON 对象，格式示例：\n'
            '{"scenes": [{"beat": "场景节拍具体推进（含@林夏 @实验楼天台）", '
            '"pov_character_name": "林夏", "location_name": "实验楼天台", '
            '"character_names": ["林夏", "陆川"], "story_time": "午休时分", "target_words": 850}]}'
        )
        sys_msg, user_msg = assemble_six_layer_prompt(
            layer1_system_role=layer1,
            layer2_style_template=layer2,
            layer3_core_setting=layer3,
            layer4_dynamic_context=context,
            layer5_task_instruction=inst,
            layer6_output_format=fmt,
        )

        _, base_url, model, api_key = self._settings_repo.get_credentials_for_task("planning")
        res = await complete_chat(
            base_url=base_url,
            api_key=api_key,
            model=model,
            system_prompt=sys_msg,
            user_prompt=user_msg,
            temperature=0.7,
            novel_uid=self._novel_uid,
            task_type="generate_scenes",
            chapter_id=chapter_id,
        )

        parsed = await parse_and_validate_json(res.content, LlmSceneBatchOutput)
        char_by_name = {c.name: c.id for c in chars}
        loc_by_name = {l.name: l.id for l in locs}

        scenes_to_create: list[SceneCreate] = []
        for idx, item in enumerate(parsed.scenes, start=1):
            pov_id = char_by_name.get(item.pov_character_name)
            loc_id = loc_by_name.get(item.location_name)
            c_ids = [char_by_name[n] for n in item.character_names if n in char_by_name]
            scenes_to_create.append(
                SceneCreate(
                    beat=item.beat,
                    pov_character=pov_id,
                    location_id=loc_id,
                    character_ids=c_ids,
                    story_time=item.story_time or ch.story_time,
                    target_words=max(200, item.target_words),
                    sort_order=float(idx),
                )
            )
        return self._writing_repo.replace_chapter_scenes(chapter_id, scenes_to_create)

    def prepare_stream_write_prompts(self, req: StreamWriteRequest, boundary: str = "") -> tuple[str, str]:
        """Build (system_prompt, user_prompt) for scene-by-scene or full-chapter SSE generation."""
        layer1, layer2, layer3 = self._build_base_layers()
        preview = self._assembler.build_context_preview(
            req.chapter_id, req.scene_id, req.disabled_context_keys
        )
        enabled_parts = [
            f"### {b.label}\n{b.content}" for b in preview.blocks if b.enabled
        ]
        if boundary:
            enabled_parts.append(boundary)
        if req.custom_context.strip():
            enabled_parts.append(f"### 作者手动补充参考\n{req.custom_context.strip()}")
        if req.existing_content.strip():
            tail = req.existing_content.strip()[-1800:]
            enabled_parts.append(f"### 本章已写前文（请自然衔接续写，切勿重复）\n{tail}")

        layer4 = "\n\n".join(enabled_parts)
        ch = self._outline_repo.get_chapter(req.chapter_id)
        scenes = self._writing_repo.list_scenes(req.chapter_id)

        if req.mode == "scene" and req.scene_id is not None:
            target_scene = next((s for s in scenes if s.id == req.scene_id), None)
            scene_idx = next(
                (i for i, s in enumerate(scenes, start=1) if s.id == req.scene_id), 1
            )
            tpl = next(
                p for p in self._settings_repo.list_prompt_templates() if p.task_type == "write_scene"
            )
            inst = render_template(
                tpl.content,
                {
                    "chapter_title": ch.title,
                    "scene_index": scene_idx,
                    "scene_beat": target_scene.beat if target_scene else ch.synopsis,
                    "target_words": _word_count_range(
                        target_scene.target_words if target_scene else 800
                    ),
                },
            )
            inst += "\n字数范围仅供参考，叙事完整、表达紧凑优先，不得为达到下限补写流水账。"
        else:
            novel = self._novel_repo.get_novel_detail()
            inst = (
                f"请完整撰写第 {ch.display_index} 章《{ch.title}》的正文，建议范围 "
                f"{_word_count_range(novel.words_per_chapter)} 字。"
            )
            inst += "字数范围仅供参考，叙事完整、表达紧凑优先，不得为达到下限补写流水账。"

        if req.instruction.strip():
            inst += f"\n作者额外写作要求：{req.instruction.strip()}"

        inst += (
            "\n【写作执行与成稿校对】按本章梗概推进剧情，但人物卡中明确的既有经历、关系历史、关系快照与前文已发生事实属于连续性约束；"
            "梗概与这些事实冲突时必须调整冲突情节，不能把已认识或持续联系的人物重写成初次见面、首次加好友或首次得知。"
            "人物背景不代表 POV 自动知晓他人私密信息，只限制角色认知，不得据此忽略或改写人物卡里的故事事实。不要重复输入的梗概；"
            "目标字数是参考，不得用重复心理、同义解释或无结果动作补足篇幅；"
            "按剧情重要性分配细节：冲突变化、关键选择、关系转折和决定后果要写清来龙去脉；"
            "普通过场和重复日常动作快速带过，不要把同一目的的动作拆成多个段落或反复解释。"
            "日常动作只保留能推动情节或改变人物状态的部分，不要把收拾、做饭、等待等过程拆成连续的微动作清单，"
            "若动作只是过渡，可用一句话带过或直接跳到有意义的结果。每段至少推进动作、对话、决定或关系中的一项，"
            "普通动作用清楚直白的中文写，不为显得文学化而叠加比喻。正文完成后逐句默读，检查主谓搭配、指代对象、"
            "人物当下已知信息、对话归属和动作时间顺序；聊天界面提示必须按当前视角区分发起者和接收者，"
            "自己收到对方撤回的消息时，应写“对方撤回了一条消息”，不可误写成“你撤回了一条消息”；"
            "只有当前视角人物自己撤回消息时，才写“你撤回了一条消息”。不得虚构上下文中没有发生过的旧对话或旧事件，"
            "严格区分交流媒介：文字消息只能提供文字、措辞、标点和表情信息，不能据此写出对方的声线、音色、语调或尾音，也不能把文字消息称为听过的声音；"
            "只有前文明确出现过的语音、电话、视频或线下发声，才能作为听觉记忆依据。若要对照线上文字与线下说话，只能比较明确写出的措辞/口头禅与实际听到的表达；"
            "避免把“想起一条文字消息”紧接着写成“同一个声音/声调/尾音”，造成文字消息提供了声音的误读；确需对照时，明确指出声音来自哪次已发生的语音或线下交谈。"
            "相对日期必须按当前场景的具体故事日期换算，不得把“明天”跨越未写出的日期直接当成既定事件日；"
            "跨日章节须先标明关键事件实际发生日期。"
            "若本章梗概要求重写前文已发生的事件或复用前文标志性原句，以前文为准，跳过重复内容并从事件之后继续推进；"
            "前文已出现的完整台词不得原样再次安排，不能因梗概里再次提及就重演。也不得与前文已写明的事实冲突；"
            "有歧义就重写整句。人物提问必须对应真实的信息缺口或关系推进，"
            "不要让人物确认所有人都知道的常识；若剧情需要确认具体日期、届别或安排，要写清确认的理由。"
            "例如“这张纸，家里只有爸妈知道”对象错位，应明确为“家里只有爸妈知道他考上了临江大学”"
            "或“这件事，他还没告诉其他人”；“一张合影，是他高中班拍的那种”指代悬空，应写成“一张高中班级合影”。"
            "不改动既定人物关系和剧情方向，不输出校对过程。"
        )

        fmt = "直接输出小说正文段落，不要输出章节标题、序号或任何解释性话语。用具体细节代替抽象情绪。"
        return assemble_six_layer_prompt(
            layer1_system_role=layer1,
            layer2_style_template=layer2,
            layer3_core_setting=layer3,
            layer4_dynamic_context=layer4,
            layer5_task_instruction=inst,
            layer6_output_format=fmt,
        )

    async def check_write_boundary(self, req: StreamWriteRequest) -> str:
        from app.services.writing_boundary import check_writing_boundary
        from app.services.prompt.author_style import author_style_prompt

        ch = self._outline_repo.get_chapter(req.chapter_id)
        history = self._writing_repo.get_previous_chapter_text(ch.sort_order, tail_chars=None)
        if req.existing_content.strip():
            history += "\n【本章已写正文】\n" + req.existing_content
        scenes = self._writing_repo.list_scenes(req.chapter_id)
        beats = "\n".join(
            s.beat for s in scenes if req.scene_id is None or s.id == req.scene_id
        )
        plan = (
            f"章节：{ch.title}；时间：{ch.story_time}\n梗概：{ch.synopsis}\n本次场景：{beats}\n"
            f"作者补充：{req.instruction}\n{req.custom_context}\n"
            + author_style_prompt(self._novel_repo.get_novel_detail())
        )
        return await check_writing_boundary(
            novel_uid=self._novel_uid, chapter_id=req.chapter_id, settings=self._settings_repo,
            history=history, plan=plan,
        )

    def prepare_stream_rewrite_prompts(self, req: StreamRewriteRequest) -> tuple[str, str]:
        """Build (system_prompt, user_prompt) for selection rewrite/expand/shorten/polish/tone_shift."""
        layer1, layer2, layer3 = self._build_base_layers()
        action_labels = {
            "rewrite": "改写（换一种更自然生动的表达方式）",
            "expand": "扩写（补充环境光影、微表情或细腻心理活动）",
            "shorten": "缩写（精简冗余修饰，使节奏更利落）",
            "polish": "文学润色（消除 AI 套话，增强青春小说质感）",
            "tone_shift": "换语气（贴合指定人物的性格内核与说话习惯）",
        }
        context_lines: list[str] = []
        if req.target_character_id is not None:
            char = self._entity_repo.get_character(req.target_character_id)
            context_lines.append(
                f"目标人物【{char.name}】：性格（{char.personality}），说话风格与口头禅（{char.speech_style}）"
            )

        tpl = next(
            p
            for p in self._settings_repo.list_prompt_templates()
            if p.task_type == "rewrite_selection"
        )
        inst = render_template(
            tpl.content,
            {
                "action_type": action_labels.get(req.action_type, req.action_type),
                "instruction": req.instruction or "保持上下文连贯，杜绝陈词滥调",
                "selected_text": req.selected_text,
            },
        )
        inst += (
            "\n【中文表达校对】修改后逐句默读，检查语义完整、指代明确、主谓搭配和修饰关系自然；"
            "发现问题时重写整句并保留原意。比喻须意思明确、搭配自然；不为追求文学感硬接无关意象，宁可删掉多余修饰。"
        )
        return assemble_six_layer_prompt(
            layer1_system_role=layer1,
            layer2_style_template=layer2,
            layer3_core_setting=layer3,
            layer4_dynamic_context="\n".join(context_lines),
            layer5_task_instruction=inst,
            layer6_output_format="只输出修改后的正文片段本身，不要包含引号或任何前后说明。",
        )

    def prepare_stream_supplement_prompts(
        self, req: StreamSupplementRequest
    ) -> tuple[str, str]:
        """Build prompts for an additive passage at a precise point in a chapter."""
        layer1, layer2, layer3 = self._build_base_layers()
        chapter = self._outline_repo.get_chapter(req.chapter_id)
        preview = self._assembler.build_context_preview(
            req.chapter_id, disabled_keys=req.disabled_context_keys
        )
        context_parts = [
            f"### {block.label}\n{block.content}"
            for block in preview.blocks
            if block.enabled
        ]
        utf16_prefix = req.content.encode("utf-16-le")[: req.insertion_index * 2]
        prefix = utf16_prefix.decode("utf-16-le", errors="ignore")
        char_index = len(prefix)
        marked_content = (
            req.content[:char_index]
            + "\n\n【作者指定的补充插入位置】\n\n"
            + req.content[char_index:]
        )
        context_parts.append(
            f"### 第{chapter.display_index}章《{chapter.title}》现有正文（含精确插入标记）\n{marked_content}"
        )
        instruction = (
            f"请为第{chapter.display_index}章《{chapter.title}》在标记位置补写内容。\n"
            f"作者要求：{req.instruction.strip()}\n"
            "只生成新增段落，不得改写、复述或输出标记两侧已有正文；开头和结尾要能直接接入标记两侧。"
            "严格遵守章节梗概、时间线、人物已知信息与已发生事件；补充内容不得与已有正文冲突或重复。"
            "篇幅以完整交代作者要求为准，避免流水账和无关铺陈。"
        )
        return assemble_six_layer_prompt(
            layer1_system_role=layer1,
            layer2_style_template=layer2,
            layer3_core_setting=layer3,
            layer4_dynamic_context="\n\n".join(context_parts),
            layer5_task_instruction=instruction,
            layer6_output_format="只输出可以直接插入正文的新增小说段落，不要输出标题、说明、引用标记或写作分析。",
        )

    async def critique_selection(self, chapter_id: int, selected_text: str) -> SelectionCritiqueResponse:
        """Analyze selected text for logic, common-sense, timeline, or physical contradictions."""
        ch = self._outline_repo.get_chapter(chapter_id)
        _pid, base_url, model, api_key = self._settings_repo.get_credentials_for_task("extract")
        time_info = ch.story_time or "未明确指定"
        synopsis_info = ch.synopsis or "无"

        sys_prompt = (
            "你是一位目光极其敏锐、重视“生活真实感”、极度反感“悬浮矫饰与情节描写过度夸张”的小说质检员。\n"
            "请对作者选中的小说片段进行严格深入的逻辑与真实常理挑刺：\n\n"
            "【七大核心审查维度（必须严密审视）】：\n"
            "1. 【情节与描写过于夸张造作（脱离生活常情与用力过猛）】：\n"
            "   - 器物或情节设定严重脱离生活常理（例如：准大一新生收拾行李，翻出一个‘比自己小不了几岁’、快跟人同龄的近20年老古董箱子去大学报到，属于严重脱离现实生活常情的用力过猛与刻意煽情）；\n"
            "   - 刻意堆砌文艺慢镜头特写（如刚好两张褪色托运条交叠翘起、灰尘在斜光中慢速定格悬浮、轮子长鸣刮响），人工雕琢痕迹过重，显得做作、浮夸且失真。\n"
            "2. 【叙事时态与时间锚点脱节】：身处当前时间点（如开学前夕），绝不能用远距离总结口吻说‘开学前求来的’；更严禁‘后来过年’这种未来时态倒错。\n"
            "3. 【物理陈旧度与购买时长矛盾（新物旧写悖论）】：严禁把‘压扁的絮状积灰’‘红绳脏得洗都没洗’等陈年特征，硬安在刚买两个月的新箱子或刚求的红绳上。若写积灰，箱子必须是早年旧物；若写新箱子，则不应有陈年厚灰。\n"
            "4. 【语义前后矛盾、对话动机与话题连续性】：逐句核对明确断言是否被后文推翻，人物是否知道对方未告知的信息，以及话题结束后是否无转场地继续同一话题。事实矛盾与对话不自然要分开分类。特别检查‘她问过一次“你今年开学吗”，他说“嗯”，就翻篇了。她也没追问，只说“我也是”’：两句不构成事实矛盾，但若人物均处于通常的开学季，文本又没有提出不同学校/届别/安排等具体信息差或情感动机，就应标记为‘对话动机牵强’，说明这个问题为什么显得多余，并给出更自然的改法；不能因为它不是硬性矛盾就判无问题。学校报到日期可能不同，只有文本给出相应背景时才能用日期差异解释提问。若人物被写成‘从没告诉对方某事’，随后对方却准确询问该事，且选段或已提供背景没有信息来源，再指出信息来源缺失。只报告文本明确支持的问题，不把合理推断或单纯措辞不精确判成硬伤。\n"
            "5. 【衣物与物品状态连续性】：逐句核对衣物、配饰及随身物品当前处于穿着/佩戴、拿着、放置、脱下、收起还是寄到等状态；同一片段内状态变化必须有明确动作或时间过渡。若前文写衣服穿在身上，后文却直接写它仍在包裹/衣柜/他人手中，或衣服尚未穿上却已出现穿着后的效果，必须指出状态断裂；仅凭季节不合适不能判错，须结合故事时间与场景。\n"
            "6. 【其他物理动作与状态矛盾】：食物吃完又继续吃；物品扔了又在手里；同一事物名称中途随意漂移（如挂面变泡面）等。\n"
            "7. 【限知视角与情境常理】：未被告知却凭空读心/未卜先知；初见自来熟；新生报到对环境轻车熟路等。\n\n"
            "【修改建议(suggestion)要求】：\n"
            "- 若存在上述问题，给出改写建议：仅使用选段和已提供背景中的事实，不得擅自补写具体开学日期、学校或人物经历；信息不足以合理补足动机时，删去多余问答或改为不添加新事实的自然表达。建议保持简短、平实。\n"
            "- 输出严格 JSON：\n"
            '若存在问题：{"has_issue": true, "issue_type": "contradiction|omniscience|exaggeration|time_conflict|action_paradox|other", "issue_label": "语义前后矛盾|信息来源缺失|对话动机牵强|情节描写过于夸张|时间常识冲突|物理动作逆转|常理失真", "description": "指出原文中具体问题及对应语句；不得只给泛泛结论", "suggestion": "修改后的平实质朴生活化自然片段"}\n'
            '若细节平实扎实无硬伤无夸张：{"has_issue": false, "issue_type": null, "issue_label": null, "description": "细节平实自洽，无夸张做作，生活逻辑合理。", "suggestion": ""}\n'
            "只输出严格 JSON，不要包含任何额外说明。"
        )
        user_prompt = (
            f"【所属章节】《{ch.title}》\n"
            f"【本章故事时间】{time_info}\n"
            f"【本章梗概背景】{synopsis_info}\n\n"
            f"【待挑刺片段】\n{selected_text}"
        )

        res = await complete_chat(
            base_url=base_url,
            api_key=api_key,
            model=model,
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            temperature=0.2,
            novel_uid=self._novel_uid,
            task_type="consistency_review",
            chapter_id=chapter_id,
        )
        return await parse_and_validate_json(res.content, SelectionCritiqueResponse)

