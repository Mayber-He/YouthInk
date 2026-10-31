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
    StreamWriteRequest,
    SelectionCritiqueResponse,
)
from app.services.context.assembler import ContextAssembler
from app.services.llm.client import complete_chat
from app.services.llm.json_parser import parse_and_validate_json
from app.services.prompt.renderer import assemble_six_layer_prompt, render_template


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
        if style:
            examples = "\n".join(f"示例：{ex}" for ex in style.example_paras[:2])
            layer2 = (
                f"风格模板：{style.name}\n"
                f"叙事视角：{novel.pov or style.pov} | 语感：{style.tense_feel}\n"
                f"基调：{novel.tone or style.tone} | 句式：{style.sentence_pref} | 对话比例：{style.dialogue_ratio}\n"
                f"描写侧重：{style.desc_focus} | 节奏：{style.pacing}\n"
                f"禁用套话表达：{', '.join(style.forbidden_exprs)}\n"
                f"{examples}"
            )

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
            f"可用人物列表：{json.dumps([c.name for c in chars], ensure_ascii=False)}\n"
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

    def prepare_stream_write_prompts(self, req: StreamWriteRequest) -> tuple[str, str]:
        """Build (system_prompt, user_prompt) for scene-by-scene or full-chapter SSE generation."""
        layer1, layer2, layer3 = self._build_base_layers()
        preview = self._assembler.build_context_preview(
            req.chapter_id, req.scene_id, req.disabled_context_keys
        )
        enabled_parts = [
            f"### {b.label}\n{b.content}" for b in preview.blocks if b.enabled
        ]
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
                    "target_words": target_scene.target_words if target_scene else 800,
                },
            )
        else:
            novel = self._novel_repo.get_novel_detail()
            inst = (
                f"请完整撰写第 {ch.display_index} 章《{ch.title}》的正文。\n"
                f"本章梗概：{ch.synopsis}\n目标字数：约 {novel.words_per_chapter} 字。"
            )

        if req.instruction.strip():
            inst += f"\n作者额外写作要求：{req.instruction.strip()}"

        fmt = "直接输出小说正文段落，不要输出章节标题、序号或任何解释性话语。用具体细节代替抽象情绪。"
        return assemble_six_layer_prompt(
            layer1_system_role=layer1,
            layer2_style_template=layer2,
            layer3_core_setting=layer3,
            layer4_dynamic_context=layer4,
            layer5_task_instruction=inst,
            layer6_output_format=fmt,
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
        return assemble_six_layer_prompt(
            layer1_system_role=layer1,
            layer2_style_template=layer2,
            layer3_core_setting=layer3,
            layer4_dynamic_context="\n".join(context_lines),
            layer5_task_instruction=inst,
            layer6_output_format="只输出修改后的正文片段本身，不要包含引号或任何前后说明。",
        )

    async def critique_selection(self, chapter_id: int, selected_text: str) -> SelectionCritiqueResponse:
        """Analyze selected text for logic, common-sense, timeline, or physical contradictions."""
        ch = self._outline_repo.get_chapter(chapter_id)
        _pid, base_url, model, api_key = self._settings_repo.get_credentials_for_task("extract")
        time_info = ch.story_time or "未明确指定"
        synopsis_info = ch.synopsis or "无"

        sys_prompt = (
            "你是严谨但深刻理解小说创作肌理的文学常理质检员。请对选中文本进行真实常理挑刺，并严守【防教条化过度挑刺】原则。\n\n"
            "【防教条化过度挑刺（重中之重，严禁鸡蛋里挑骨头）】：\n"
            "1. 一章情节往往伴随时间自然推移（如傍晚拖箱收拾、入夜煮面、深夜聊天）。不能因章节末尾有深夜，就机械否定傍晚时‘斜进窗户的光’（夕阳落日、暮光或路灯光影）！正常的环境光影描写绝不能判定为时间冲突！\n"
            "2. 物品陈旧度（如积半年的灰、层叠褪色的托运条）与来源（老爸早年出差用的旧款，比主角小不了几岁）完全自洽，属于生活质感极佳的优秀细节，绝不能判为错误！\n"
            "3. 只有真正不可调和的逻辑硬伤才判定 has_issue: true；对于合情合理、文笔扎实自洽的段落，必须判定 has_issue: false。\n\n"
            "【四大真实逻辑硬伤审查维度】：\n"
            "1. 【叙事时态与时间锚点脱节】：身处当前时间点（如开学前夕），绝不能用远距离总结口吻说‘开学前求来的’；更严禁‘后来过年’这种未来时态倒错。\n"
            "2. 【物理陈旧度与购买时长矛盾（新物旧写悖论）】：严禁把‘压扁的絮状积灰’‘红绳脏得洗都没洗’等陈年特征，硬安在刚买两个月的新箱子或刚求的红绳上。若写积灰，箱子必须是早年旧物；若写新箱子，则不应有陈年厚灰。\n"
            "3. 【物理动作与状态矛盾】：食物吃完又继续吃；物品扔了又在手里；同一事物名称中途随意漂移（如挂面变泡面）等。\n"
            "4. 【限知视角与情境常理】：未被告知却凭空读心/未卜先知；初见自来熟；新生报到对环境轻车熟路等。\n\n"
            "【修改建议(suggestion)要求】：若有漏洞，必须在消除漏洞的同时保持文学质感，绝不能粗暴胡乱改动，输出可完整替换的自洽文本。\n\n"
            "输出严格 JSON：\n"
            '若存在真实硬伤：{"has_issue": true, "issue_type": "time_conflict|action_paradox|omniscience|item_drift|other", "issue_label": "时间常识冲突|物理动作逆转|超知读心|道具漂移|其他常理矛盾", "description": "一针见血指出真实硬伤所在", "suggestion": "修改后的合理自然完整片段"}\n'
            '若细节扎实无硬伤：{"has_issue": false, "issue_type": null, "issue_label": null, "description": "细节扎实自洽，时间、物品陈旧度与物理动作完全合理。", "suggestion": ""}\n'
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

