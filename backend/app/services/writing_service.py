"""AI Scene Outline Generation and Streaming Prompt Preparation Service (M3)."""

from __future__ import annotations

import json
import logging
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

_scene_logger = logging.getLogger(__name__)

# T4 之前的 system_role 全文（六条“严禁”铁律）。仅用于 scripts/compare_write_prompt.py
# 复现“改动前”基线以量化瘦身效果；生产路径不再使用。
_LEGACY_SYSTEM_ROLE = (
    "你是一位擅长青春文学与长篇连载创作的资深小说作家与文学统筹编辑。\n"
    "你的文笔自然细腻、充满生活质感与时代气息，善于用具体的感官细节（光线、声音、气味、细微动作）替代空洞的情绪形容词。\n"
    "创作铁律（六大常理与视角边界准则，全程严禁违反）：\n"
    "1. 【设定事实与角色认知隔离（防上帝视角渗透）】：人物卡中的既有经历、关系历史和全书设定属于必须遵守的故事事实，不得因角色本人尚不知情而改写；但这些作者信息不等于 POV 已经知道，严禁让角色知晓其尚未得知的秘密或未亲历的事实。\n"
    "2. 【空间与环境熟悉度常理】：严格依据角色身份与当前剧情阶段展现环境熟悉度。凡属初次到访（如新生刚报到、刚转学、首次去某场所），必须通过观察路牌、四处打量、看地图、问路或走错路等细节体现陌生感，严禁表现得熟门熟路、轻车熟路。\n"
    "3. 【人际关系与初见边界】：对话称呼、语气与肢体距离必须严格匹配人物卡既有关系、已确认关系变化和前文事实。没有结构化关系记录不代表初见或不熟；只有设定与前文确认为初次见面或尚不熟稔时，才按初见边界处理，严禁无铺垫自来熟、严禁未经自我介绍或他人提及便直呼对方姓名/绰号/过往隐私。\n"
    "4. 【限知视角与感官边界】：采用限知视角写作时，严格从当前场景视角人物（POV）的五感与认知出发描写；POV 角色只能观察他人外在言行与微表情，严禁直接读取他人内心独白或描写 POV 视线/听觉范围之外的死角。\n"
    "5. 【时间、季节与物理状态连续性】：严格遵守故事内时间流速、昼夜光线、季节气候与服装搭配、人物身体伤病/体力限制及随身物品状态；物品、食物与道具称谓严禁前后自相矛盾或中途随意漂移（如前文挂面后文绝不能擅自写成泡面）；已完成的物理动作与状态（如食物吃完、物品放下、已消耗或已离开）在后续必须保持一致，严禁出现吃完又继续吃等动作前后矛盾；空间移动必须有合理的动作与路径过渡，严禁空间瞬移或前后道具凭空出现/消失。\n"
    "6. 【场景在场与年龄身份边界】：仅限当前场景在场人物参与对话与互动，未到场或已离场角色严禁凭空插话；人物言行、消费能力、社会阅历与技能水平必须符合其年龄与身份常理。严禁在章节末尾强行升华主题或替读者总结点题。"
)


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

    def _build_base_layers(self, prose: bool = False) -> tuple[str, str, str]:
        """Return (system_role, style, core_setting).

        ``prose=True`` is used only by the prose-writing path (T4): the style layer
        always carries forbidden expressions + up to 2 example paragraphs (even when the
        author wrote a style_note), and the core setting uses a 1–2 sentence blurb instead
        of the whole-book synopsis (which holds late-plot spoilers). All other callers keep
        the previous behaviour.
        """
        from app.services.prompt.prose_prompt import (
            core_setting_blurb,
            prose_prompt_v2_enabled,
            protagonist_brief,
            style_layer,
        )

        prompts = {p.task_type: p for p in self._settings_repo.list_prompt_templates()}
        layer1 = prompts["system_role"].content
        novel = self._novel_repo.get_novel_detail()
        styles = self._settings_repo.list_style_templates()
        style = next((s for s in styles if s.id == novel.style_template_id), None)
        has_note = bool((novel.style_note or "").strip())

        use_v2 = prose and prose_prompt_v2_enabled()

        if use_v2 and style:
            layer2 = style_layer(
                style_name=style.name,
                pov=novel.pov or style.pov,
                tense_feel=style.tense_feel,
                tone=novel.tone or style.tone,
                sentence_pref=style.sentence_pref,
                dialogue_ratio=style.dialogue_ratio,
                desc_focus=style.desc_focus,
                pacing=style.pacing,
                forbidden_exprs=list(style.forbidden_exprs),
                example_paras=list(style.example_paras),
                has_style_note=has_note,
            )
        else:
            layer2 = ""
            if style and not has_note:
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

        if use_v2:
            blurb = core_setting_blurb(novel.synopsis or "", novel.protagonist_concept or "")
            layer3 = (
                f"书名：《{novel.title}》\n"
                f"题材：{novel.genre or '校园'} | 基调：{novel.tone or '清新治愈'} | 视角：{novel.pov or '第三人称限知'}\n"
                f"主角概念：{protagonist_brief(novel.protagonist_concept or '')}\n"
                f"核心设定：{blurb}"
            )
        else:
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
        inst += (
            f"\n请拆解为 {scene_count} 个场景，每个场景以【事件清单】形式给出，"
            "不要写成散文式节拍。节拍里可用 @人物名 和 @地点名 标注关联实体。\n"
            "每个场景必须输出以下字段：\n"
            "- goal：本场景要达成的叙事目的（一句话）\n"
            "- entry_state：进入本场景时的起点状态（人物位置/关系/情绪的简短快照）\n"
            "- must_happen：本场必须发生的事件，最多 3 条，每条不超过 25 字，只写事件不写细节\n"
            "- exit_state：本场结束时的终点状态（为下一场留下的钩子）\n"
            "- must_not_include：本场禁止出现的素材（留给后续场景的事件、不该提前的信息）\n"
            "- target_words：预估字数\n"
            "【严禁】不要写具体台词或对白、不要写分镜级的具体动作细节、不要写结尾意象或景物升华；"
            "这些留给正文生成阶段。must_happen 用“谁做了什么、发生了什么结果”的事件句，不要展开过程。\n"
            "相邻场景的 must_happen 不得重复同一事件；每个场景都要带来新的事件或状态推进。"
        )
        inst += (
            "人物卡中的既有经历和关系是必须遵守的故事事实；不得把已经认识或持续联系的人物安排成初次相识、首次加好友。"
            "人物卡不代表 POV 自动知晓他人的私密信息，但不能因此改写人物既有经历。若章节梗概与人物卡冲突，调整场景以遵守人物卡与前文事实。"
        )
        if instruction:
            inst += f"\n作者附加要求：{instruction}"

        fmt = (
            '请输出纯 JSON 对象，格式示例：\n'
            '{"scenes": [{"goal": "两人第一次正式照面并交换联系方式", '
            '"entry_state": "江澈刚到报到处，裴南栀在发放材料", '
            '"must_happen": ["江澈找到报到处", "裴南栀帮他办手续", "两人加了联系方式"], '
            '"exit_state": "江澈拿到材料，心里记住了这个学姐", '
            '"must_not_include": ["江澈认出她是网友", "表白或暧昧"], '
            '"pov_character_name": "江澈", "location_name": "报到处", '
            '"character_names": ["江澈", "裴南栀"], "story_time": "报到日上午", "target_words": 850}]}'
        )

        _, base_url, model, api_key = self._settings_repo.get_credentials_for_task("planning")

        async def _request_scenes(extra_hint: str = "") -> LlmSceneBatchOutput:
            sys_msg, user_msg = assemble_six_layer_prompt(
                layer1_system_role=layer1,
                layer2_style_template=layer2,
                layer3_core_setting=layer3,
                layer4_dynamic_context=context,
                layer5_task_instruction=inst + extra_hint,
                layer6_output_format=fmt,
            )
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
            return await parse_and_validate_json(res.content, LlmSceneBatchOutput)

        parsed = await _request_scenes()

        # 相邻场景 must_happen 重复校验：超阈值则带着重复处让模型重拆一次；
        # 仍重复则保留结果并写警告日志（不无限循环）。
        from app.services.scene_planning import (
            describe_duplicates,
            find_adjacent_duplicates,
            format_scene_beat,
        )

        def _mh(batch: LlmSceneBatchOutput) -> list[list[str]]:
            return [list(s.must_happen) for s in batch.scenes]

        dups = find_adjacent_duplicates(_mh(parsed))
        if dups:
            retry = await _request_scenes(
                "\n\n上一次拆分存在相邻场景事件重复，请重新拆分。"
                + describe_duplicates(dups)
            )
            if len(find_adjacent_duplicates(_mh(retry))) <= len(dups):
                parsed = retry
            remaining = find_adjacent_duplicates(_mh(parsed))
            if remaining:
                _scene_logger.warning(
                    "generate_chapter_scenes: adjacent must_happen still overlaps after one re-split "
                    "(chapter_id=%s, pairs=%d)",
                    chapter_id, len(remaining),
                )

        char_by_name = {c.name: c.id for c in chars}
        loc_by_name = {l.name: l.id for l in locs}

        scenes_to_create: list[SceneCreate] = []
        for idx, item in enumerate(parsed.scenes, start=1):
            pov_id = char_by_name.get(item.pov_character_name)
            loc_id = loc_by_name.get(item.location_name)
            c_ids = [char_by_name[n] for n in item.character_names if n in char_by_name]
            # 事件清单序列化进现有 beat 列（零迁移）；老模型只给 beat 时原样沿用。
            if item.has_event_checklist():
                beat_text = format_scene_beat(
                    item.goal, item.entry_state, item.must_happen,
                    item.exit_state, item.must_not_include,
                )
            else:
                beat_text = item.beat
            scenes_to_create.append(
                SceneCreate(
                    beat=beat_text or item.beat or item.goal or "（场景待细化）",
                    pov_character=pov_id,
                    location_id=loc_id,
                    character_ids=c_ids,
                    story_time=item.story_time or ch.story_time,
                    target_words=max(200, item.target_words),
                    sort_order=float(idx),
                )
            )
        return self._writing_repo.replace_chapter_scenes(chapter_id, scenes_to_create)

    # 约束与人物类 → 上一章/前文类 → 本章细纲(含本场景事件清单)；任务指令永远在最后。
    _CONSTRAINT_BLOCK_KEYS = (
        "hard_constraints",
        "character_states",
        "cognitive_constraints",
        "location_and_worldview",
    )
    _HISTORY_BLOCK_KEYS = ("summaries_and_prev", "foreshadowing_and_facts", "rag_history")
    _SCENE_BLOCK_KEYS = ("chapter_beats",)

    def prepare_stream_write_prompts(
        self, req: StreamWriteRequest, boundary: str = "", legacy: bool = False
    ) -> tuple[str, str]:
        """Build (system_prompt, user_prompt) for scene-by-scene or full-chapter SSE generation.

        ``legacy=True`` reproduces the pre-T4 assembly (used only by the before/after
        comparison script). Default is the T4 layout, switchable off globally with
        ``YOUTHINK_PROSE_PROMPT_V2=0``.
        """
        from app.services.prompt.prose_prompt import ending_rule, prose_prompt_v2_enabled

        v2 = (not legacy) and prose_prompt_v2_enabled()
        layer1, layer2, layer3 = self._build_base_layers(prose=v2)
        if legacy:
            layer1 = _LEGACY_SYSTEM_ROLE
        preview = self._assembler.build_context_preview(
            req.chapter_id, req.scene_id, req.disabled_context_keys
        )
        enabled_blocks = [b for b in preview.blocks if b.enabled]

        def _fmt(b) -> str:
            return f"### {b.label}\n{b.content}"

        if v2:
            by_key = {b.key: b for b in enabled_blocks}
            known = set(self._CONSTRAINT_BLOCK_KEYS + self._HISTORY_BLOCK_KEYS + self._SCENE_BLOCK_KEYS)
            constraint_parts = [_fmt(by_key[k]) for k in self._CONSTRAINT_BLOCK_KEYS if k in by_key]
            # 未知 key（日后新增的块）并入约束段，保证不丢信息。
            constraint_parts += [_fmt(b) for b in enabled_blocks if b.key not in known]
            if req.custom_context.strip():
                constraint_parts.append(f"### 作者手动补充参考\n{req.custom_context.strip()}")

            history_parts = [_fmt(by_key[k]) for k in self._HISTORY_BLOCK_KEYS if k in by_key]
            if boundary:
                history_parts.append(boundary)
            if req.existing_content.strip():
                tail = req.existing_content.strip()[-1800:]
                history_parts.append(f"### 本章已写前文（请自然衔接续写，切勿重复）\n{tail}")

            scene_parts = [_fmt(by_key[k]) for k in self._SCENE_BLOCK_KEYS if k in by_key]
            layer4 = "\n\n".join(constraint_parts + history_parts + scene_parts)
        else:
            enabled_parts = [_fmt(b) for b in enabled_blocks]
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
            "\n【怎么写好这一段】按本章梗概推进剧情，不重复输入的梗概。"
            "按剧情重要性分配笔墨：冲突、关键选择、关系转折和决定的后果写清来龙去脉；"
            "普通过场和重复日常动作一句话带过，不要把收拾、做饭、等待拆成连续的微动作清单，只是过渡就直接跳到有意义的结果。"
            "每一段至少推进动作、对话、决定或关系中的一项，用具体的动作、对话和感官细节代替抽象情绪词，"
            "普通动作用清楚直白的中文写，不为显得文学化而硬叠比喻；目标字数只是参考，宁可紧凑，不用重复心理或同义解释凑篇幅。"
            "\n【两条必须守住的硬规则】①聊天界面按当前视角区分发起者和接收者：自己收到对方撤回的消息写“对方撤回了一条消息”，"
            "只有当前视角人物自己撤回才写“你撤回了一条消息”。②相对日期按当前场景的具体故事日期换算，"
            "不得把“明天”跨越未写出的日期直接当成既定事件日；跨日章节先标明关键事件的实际发生日期。"
            "不改动既定人物关系和剧情方向，不输出校对过程。"
        )

        if v2:
            # 场景模式按场景序号轮换收尾方式；整章模式用 1（章末同样落在对话/动作/决定）。
            inst += ending_rule(scene_idx if (req.mode == "scene" and req.scene_id is not None) else 1)

        fmt = "直接输出小说正文段落，不要输出章节标题、序号或任何解释性话语。用具体细节代替抽象情绪。"
        return assemble_six_layer_prompt(
            layer1_system_role=layer1,
            layer2_style_template=layer2,
            layer3_core_setting=layer3,
            layer4_dynamic_context=layer4,
            layer5_task_instruction=inst,
            layer6_output_format=fmt,
        )

    async def check_scene_repetition(
        self,
        chapter_id: int,
        scene_id: int,
        scene_text: str,
        chapter_so_far: str = "",
        auto_rewrite: bool | None = None,
    ) -> dict:
        """T5: deterministic repetition check on a freshly generated scene, with ONE rewrite.

        Compares against the previous chapter's full text and the already-written part of this
        chapter; counts stock action phrases chapter-wide; checks the scene's own
        ``must_not_include``. Over threshold -> the model rewrites this scene once with the
        concrete repeated spans listed; still over -> keep + warn (never loops). Every
        measurement is stored in ``repetition_checks`` for later review.
        """
        from app.services.repetition_guard import RepetitionConfig, split_must_not_include
        from app.services.repetition_service import (
            build_rewrite_instruction,
            run_repetition_pipeline,
        )

        cfg = RepetitionConfig.from_env()
        ch = self._outline_repo.get_chapter(chapter_id)
        scene = next((s for s in self._writing_repo.list_scenes(chapter_id) if s.id == scene_id), None)
        if cfg.enabled is False:
            return {
                "triggered": False, "action": "none", "final_text": scene_text,
                "reasons": [], "warnings": [], "report": {}, "check_ids": [],
            }

        raw_prev = self._writing_repo.get_previous_chapter_text(ch.sort_order, tail_chars=None)
        # strip the "【上一章《…》完整正文】" header line so it is not treated as prose
        previous_chapter = raw_prev.split("\n", 1)[1] if raw_prev.startswith("【") and "\n" in raw_prev else raw_prev
        must_not = split_must_not_include(scene.beat) if scene else []

        _, base_url, model, api_key = self._settings_repo.get_credentials_for_task("writing")

        async def _rewrite(text: str, report) -> str:
            sys_msg = (
                "你是青春小说的资深编辑。按要求重写给定的一个场景，保持剧情事件不变，"
                "只输出重写后的场景正文，不加标题、说明或前后缀。"
            )
            user_msg = (
                f"{build_rewrite_instruction(report)}\n\n【待重写的场景正文】\n{text}"
            )
            res = await complete_chat(
                base_url=base_url, api_key=api_key, model=model,
                system_prompt=sys_msg, user_prompt=user_msg,
                temperature=0.8, timeout_sec=120.0,
                novel_uid=self._novel_uid, task_type="rewrite_repetition",
                chapter_id=chapter_id, scene_id=scene_id,
            )
            return res.content

        def _record(stage: str, action: str, report, thresholds: dict) -> int:
            cur = self._conn.execute(
                "INSERT INTO repetition_checks (chapter_id, scene_id, stage, triggered, action_taken, "
                "coverage, reasons_json, report_json, thresholds_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    chapter_id, scene_id, stage, 1 if report.triggered else 0, action,
                    report.coverage,
                    json.dumps(report.reasons, ensure_ascii=False),
                    json.dumps(report.to_dict(), ensure_ascii=False),
                    json.dumps(thresholds, ensure_ascii=False),
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid or 0)

        return await run_repetition_pipeline(
            scene_text,
            previous_chapter=previous_chapter,
            chapter_so_far=chapter_so_far,
            must_not_include=must_not,
            config=cfg,
            rewrite_fn=_rewrite,
            record_fn=_record,
            auto_rewrite=auto_rewrite,
        )

    async def check_write_boundary(self, req: StreamWriteRequest) -> str:
        """Back-compat wrapper: returns only the text to inject (``''`` when nothing to inject)."""
        text, _status, _note = await self.check_write_boundary_ex(req)
        return text

    async def check_write_boundary_ex(self, req: StreamWriteRequest) -> tuple[str, str, str]:
        """Run the continuity check; return ``(text, status, note)``.

        status:
          * ``ok``      – check ran; ``text`` is the lean injection (possibly after dropping some
                          non-verbatim evidence items — that is not a failure).
          * ``skipped`` – nothing to check against (opening chapter / no prior prose). Not an error.
          * ``failed``  – the check could NOT produce anything usable (timeout, unparseable reply, no
                          credentials …, or every injectable evidence item was non-verbatim), still
                          failing after one retry. ``text`` is ``''`` and ``note`` is the
                          user-visible "衔接检查未生效" message.

        Mismatched evidence no longer aborts: bad items are dropped per-item (see
        ``check_writing_boundary_result``). Writing is never blocked by the continuity check.
        """
        from app.services.writing_boundary import check_writing_boundary_result, unavailable_notice
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
        # 衔接检查只是生成前的参考，任何情况都不阻断正文生成：
        #  - 个别证据对不上前文 → 逐条丢弃，保留其余（仍算 ok，只记日志）；
        #  - 整体失败（解析失败/超时/上游错误）或“会被注入的证据全被丢弃” → 带纠错提示重试一次；
        #  - 重试后仍不行 → failed：不注入任何衔接内容，界面提示“衔接检查未生效”，正文照常生成。
        from app.core.exceptions import AppError

        if not history.strip():
            return "", "skipped", ""  # 开篇章节，没有前文可衔接：正常，不是故障
        try:
            res = await check_writing_boundary_result(
                novel_uid=self._novel_uid, chapter_id=req.chapter_id, settings=self._settings_repo,
                history=history, plan=plan,
            )
        except AppError as e:
            reason = f"{e.code}: {e.message}"
        except Exception as e:  # noqa: BLE001 - any technical failure degrades, never blocks writing
            reason = f"{type(e).__name__}: {e}"
        else:
            # 个别证据被丢弃时 writing_boundary 已按条记了 WARNING（含引文样例），这里不重复记。
            if res.note:  # 重试后仍不可用：降级为可见提示，不注入任何衔接内容，正文照常生成
                reason = res.note
            else:
                return res.text, "ok", ""
        _scene_logger.warning(
            "衔接检查未生效 (chapter_id=%s scene_id=%s): %s", req.chapter_id, req.scene_id, reason
        )
        return "", "failed", unavailable_notice(reason[:120])

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

