"""AI generation and single-item rewrite service for M2 Settings & Outline."""

from __future__ import annotations

import json
from typing import TypeVar
from pydantic import BaseModel

from app.core.exceptions import AppError
from app.db.repositories.entity_repo import EntityRepository
from app.db.repositories.constraint_repo import ConstraintRepository
from app.db.repositories.novel_repo import NovelRepository
from app.db.repositories.outline_repo import OutlineRepository
from app.db.repositories.settings_repo import SettingsRepository
from app.schemas.constraints import ConstraintCreate
from app.schemas.entities import (
    CharacterResponse,
    CharacterUpdate,
    LlmCharacterBatchOutput,
    LlmCharacterItem,
    LlmLocationBatchOutput,
    LlmLocationItem,
    LlmMainPlotOutput,
    LlmWorldviewBatchOutput,
    LlmWorldviewItem,
    LocationResponse,
    LocationUpdate,
    MainPlotResponse,
    WorldviewResponse,
    WorldviewUpdate,
)
from app.schemas.outline import (
    LlmChapterBatchOutput,
    LlmStructureOutput,
    OutlineTreeResponse,
)
from app.db.vector_store import NovelVectorStore
from app.services.llm.client import complete_chat
from app.services.llm.json_parser import parse_and_validate_json
from app.services.prompt.renderer import assemble_six_layer_prompt, render_template
from app.services.prompt.planning_knowledge import PLANNING_KNOWLEDGE_RULES, PLANNING_TASKS

T = TypeVar("T", bound=BaseModel)


class SettingGeneratorService:
    """Orchestrates 6-layer prompt assembly, LLM calls, and JSON validation for M2."""

    def __init__(
        self,
        novel_uid: str,
        novel_repo: NovelRepository,
        entity_repo: EntityRepository,
        outline_repo: OutlineRepository,
        settings_repo: SettingsRepository,
        constraint_repo: ConstraintRepository,
    ) -> None:
        self._novel_uid = novel_uid
        self._novel_repo = novel_repo
        self._entity_repo = entity_repo
        self._outline_repo = outline_repo
        self._settings_repo = settings_repo
        self._constraint_repo = constraint_repo

    def _build_base_layers(self) -> tuple[str, str, str]:
        """Return (layer1_system_role, layer2_style_template, layer3_core_setting)."""
        prompts = {p.task_type: p for p in self._settings_repo.list_prompt_templates()}
        layer1 = prompts["system_role"].content

        novel = self._novel_repo.get_novel_detail()
        styles = self._settings_repo.list_style_templates()
        matched_style = next((s for s in styles if s.id == novel.style_template_id), None)
        layer2 = ""
        if matched_style:
            layer2 = (
                f"风格模板：{matched_style.name}\n"
                f"叙事视角：{novel.pov or matched_style.pov} | 语感：{matched_style.tense_feel}\n"
                f"基调：{novel.tone or matched_style.tone} | 句式：{matched_style.sentence_pref}\n"
                f"描写侧重：{matched_style.desc_focus} | 节奏：{matched_style.pacing}\n"
                f"禁用表达：{', '.join(matched_style.forbidden_exprs[:10])}"
            )

        layer3 = (
            f"书名：《{novel.title}》\n"
            f"题材：{novel.genre or '校园'} | 基调：{novel.tone or '清新治愈'} | 视角：{novel.pov or '第三人称限知'}\n"
            f"主角概念：{novel.protagonist_concept or '待定'}\n"
            f"故事梗概：{novel.synopsis or '待定'}\n"
            f"结局方向：感情线({novel.romance_ending or 'HE'}) / 成长线({novel.growth_ending or 'HE'})\n"
            f"补充说明：{novel.ending_note or ''} {novel.style_note or ''}"
        )
        return layer1, layer2, layer3

    async def _call_and_parse_json(
        self,
        *,
        task_type: str,
        layer4_context: str,
        layer5_instruction: str,
        layer6_format: str,
        schema_cls: type[T],
        timeout_sec: float = 60.0,
    ) -> T:
        layer1, layer2, layer3 = self._build_base_layers()
        if task_type in PLANNING_TASKS:
            characters = self._entity_repo.list_characters()
            sources = [{
                "name": c.name, "background": c.background,
                "arc_design": c.arc_design, "speech_style": c.speech_style,
            } for c in characters]
            layer4_context += (
                "\n【人物经历与交流渠道依据；未写明的渠道不得自行补设】\n"
                + json.dumps(sources, ensure_ascii=False)
            )
            layer5_instruction += "\n" + PLANNING_KNOWLEDGE_RULES
        sys_msg, user_msg = assemble_six_layer_prompt(
            layer1_system_role=layer1,
            layer2_style_template=layer2,
            layer3_core_setting=layer3,
            layer4_dynamic_context=layer4_context,
            layer5_task_instruction=layer5_instruction,
            layer6_output_format=layer6_format,
        )

        _, base_url, model, api_key = self._settings_repo.get_credentials_for_task("planning")
        res = await complete_chat(
            base_url=base_url,
            api_key=api_key,
            model=model,
            system_prompt=sys_msg,
            user_prompt=user_msg,
            temperature=0.7,
            timeout_sec=timeout_sec,
            novel_uid=self._novel_uid,
            task_type=task_type,
        )

        async def _repair_with_cheap_model(broken_text: str, err_msg: str) -> str:
            _, ex_url, ex_model, ex_key = self._settings_repo.get_credentials_for_task("extract")
            rep = await complete_chat(
                base_url=ex_url,
                api_key=ex_key,
                model=ex_model,
                system_prompt="你是 JSON 语法修复器。只输出合法的 JSON，不要包含任何解释。",
                user_prompt=(
                    f"以下 JSON 解析失败（错误：{err_msg}）。请按要求格式修复并仅返回合法 JSON：\n"
                    f"格式要求：{layer6_format}\n\n待修复文本：\n{broken_text}"
                ),
                temperature=0.1,
                timeout_sec=timeout_sec,
                novel_uid=self._novel_uid,
                task_type=f"{task_type}_json_repair",
            )
            return rep.content

        return await parse_and_validate_json(
            res.content, schema_cls, repair_fn=_repair_with_cheap_model, max_retries=2
        )

    # --- 1. Worldview ---

    async def generate_worldview(self, instruction: str = "", count: int = 6) -> list[WorldviewResponse]:
        novel = self._novel_repo.get_novel_detail()
        locked = [w for w in self._entity_repo.list_worldview() if w.locked]
        locked_str = json.dumps([w.model_dump() for w in locked], ensure_ascii=False) if locked else "无"

        tpl = next(p for p in self._settings_repo.list_prompt_templates() if p.task_type == "generate_worldview")
        inst = render_template(tpl.content, {"title": novel.title, "locked_items": locked_str})
        if instruction:
            inst += f"\n作者附加要求：{instruction}"

        fmt = (
            f"请输出纯 JSON 对象，包含 items 数组（共 {count} 条），格式示例：\n"
            '{"items": [{"category": "era|city|school|rules|culture|term", "content": "具体世界观设定内容"}]}'
        )
        parsed = await self._call_and_parse_json(
            task_type="generate_worldview",
            layer4_context=f"已锁定世界观条目（请保持兼容且不重复）：{locked_str}",
            layer5_instruction=inst,
            layer6_format=fmt,
            schema_cls=LlmWorldviewBatchOutput,
        )
        return self._entity_repo.replace_unlocked_worldview(parsed.items)

    async def rewrite_worldview_item(self, entry_id: int, instruction: str) -> WorldviewResponse:
        entry = self._entity_repo.get_worldview(entry_id)
        fmt = '{"category": "era|city|school|rules|culture|term", "content": "重写后的设定内容"}'
        parsed = await self._call_and_parse_json(
            task_type="rewrite_worldview",
            layer4_context=f"原条目分类：{entry.category}\n原条目内容：{entry.content}",
            layer5_instruction=f"请根据以下修改意见重写该世界观条目：{instruction}",
            layer6_format=fmt,
            schema_cls=LlmWorldviewItem,
        )
        return self._entity_repo.update_worldview(
            entry_id, WorldviewUpdate(category=parsed.category, content=parsed.content)
        )

    # --- 2. Characters ---

    async def generate_characters(self, instruction: str = "", count: int = 4) -> list[CharacterResponse]:
        novel = self._novel_repo.get_novel_detail()
        worldview = self._entity_repo.list_worldview()
        locked_chars = [c for c in self._entity_repo.list_characters() if c.locked]
        context = (
            f"世界观设定：{json.dumps([w.content for w in worldview], ensure_ascii=False)}\n"
            f"已锁定人物卡（请勿重复生成，新角色需与之形成良好化学反应）："
            f"{json.dumps([c.name for c in locked_chars], ensure_ascii=False)}"
        )
        tpl = next(p for p in self._settings_repo.list_prompt_templates() if p.task_type == "generate_characters")
        inst = render_template(tpl.content, {"title": novel.title}) + f"\n请生成 {count} 位角色。"
        if instruction:
            inst += f"\n作者附加要求：{instruction}"

        fmt = (
            '请输出纯 JSON 对象，格式示例：\n'
            '{"characters": [{"name": "林夏", "aliases": ["夏夏"], "role": "female_lead|male_lead|major|minor|extra", '
            '"gender": "女", "initial_age": "高一(16岁)", "appearance": "...", "personality": "...", '
            '"speech_style": "...", "background": "...", "arc_design": "...", '
            '"constraints": ["对大学校园不熟悉，问路、走错教学楼是合理的；绝不能写他对学校了如指掌", "..."]}]}'
        )
        parsed = await self._call_and_parse_json(
            task_type="generate_characters",
            layer4_context=context,
            layer5_instruction=inst,
            layer6_format=fmt,
            schema_cls=LlmCharacterBatchOutput,
        )
        unlocked_ids = [
            c.id for c in self._entity_repo.list_characters() if not c.locked
        ]
        created = self._entity_repo.replace_unlocked_characters(parsed.characters)
        for cid in unlocked_ids:
            self._constraint_repo.delete_for_target("character", cid)
        self._persist_derived_character_constraints(parsed.characters, created)
        return created

    def _persist_derived_character_constraints(
        self,
        items: list[LlmCharacterItem],
        created: list[CharacterResponse],
    ) -> None:
        """Persist LLM-derived hard constraints for newly generated characters.

        Only creates constraints for characters that were actually (re)created in
        this batch, matched by name. User-locked characters are untouched.
        """
        created_by_name = {c.name: c for c in created}
        for item in items:
            char = created_by_name.get(item.name)
            if char is None:
                continue
            for text in item.constraints or []:
                text = text.strip()
                if not text:
                    continue
                self._constraint_repo.create_constraint(
                    ConstraintCreate(
                        target_type="character",
                        target_id=char.id,
                        content=text,
                        severity="hard",
                    )
                )

    async def rewrite_character(self, char_id: int, instruction: str) -> CharacterResponse:
        char = self._entity_repo.get_character(char_id)
        fmt = (
            '{"name": "...", "aliases": ["..."], "role": "female_lead|male_lead|major|minor|extra", '
            '"gender": "...", "initial_age": "...", "appearance": "...", "personality": "...", '
            '"speech_style": "...", "background": "...", "arc_design": "..."}'
        )
        parsed = await self._call_and_parse_json(
            task_type="rewrite_character",
            layer4_context=f"当前人物卡：{json.dumps(char.model_dump(), ensure_ascii=False)}",
            layer5_instruction=f"请根据以下修改意见重写或完善该人物卡：{instruction}",
            layer6_format=fmt,
            schema_cls=LlmCharacterItem,
        )
        return self._entity_repo.update_character(char_id, CharacterUpdate(**parsed.model_dump()))

    # --- 3. Locations ---

    async def generate_locations(self, instruction: str = "", count: int = 4) -> list[LocationResponse]:
        novel = self._novel_repo.get_novel_detail()
        worldview = self._entity_repo.list_worldview()
        chars = self._entity_repo.list_characters()
        locked_locs = [loc for loc in self._entity_repo.list_locations() if loc.locked]
        context = (
            f"世界观：{json.dumps([w.content for w in worldview], ensure_ascii=False)}\n"
            f"人物列表：{json.dumps([c.name for c in chars], ensure_ascii=False)}\n"
            f"已锁定地点：{json.dumps([l.name for l in locked_locs], ensure_ascii=False)}"
        )
        tpl = next(p for p in self._settings_repo.list_prompt_templates() if p.task_type == "generate_locations")
        inst = render_template(tpl.content, {"title": novel.title}) + f"\n请生成 {count} 个核心地点。"
        if instruction:
            inst += f"\n作者附加要求：{instruction}"

        fmt = (
            '请输出纯 JSON 对象，格式示例：\n'
            '{"locations": [{"name": "实验楼天台", "aliases": ["旧天台"], "type": "校园场所", '
            '"description": "空间结构与特征", "sensory_details": "声音、气味、光线细节"}]}'
        )
        parsed = await self._call_and_parse_json(
            task_type="generate_locations",
            layer4_context=context,
            layer5_instruction=inst,
            layer6_format=fmt,
            schema_cls=LlmLocationBatchOutput,
        )
        return self._entity_repo.replace_unlocked_locations(parsed.locations)

    async def rewrite_location(self, loc_id: int, instruction: str) -> LocationResponse:
        loc = self._entity_repo.get_location(loc_id)
        fmt = '{"name": "...", "aliases": ["..."], "type": "...", "description": "...", "sensory_details": "..."}'
        parsed = await self._call_and_parse_json(
            task_type="rewrite_location",
            layer4_context=f"当前地点设定：{json.dumps(loc.model_dump(), ensure_ascii=False)}",
            layer5_instruction=f"请根据以下修改意见重写该地点：{instruction}",
            layer6_format=fmt,
            schema_cls=LlmLocationItem,
        )
        return self._entity_repo.update_location(loc_id, LocationUpdate(**parsed.model_dump()))

    # --- 4. Main Plot ---

    async def generate_main_plot(self, instruction: str = "") -> MainPlotResponse:
        novel = self._novel_repo.get_novel_detail()
        worldview = self._entity_repo.list_worldview()
        chars = self._entity_repo.list_characters()
        context = (
            f"世界观：{json.dumps([w.content for w in worldview], ensure_ascii=False)}\n"
            f"核心人物：{json.dumps([{'name': c.name, 'role': c.role, 'arc': c.arc_design} for c in chars], ensure_ascii=False)}"
        )
        tpl = next(p for p in self._settings_repo.list_prompt_templates() if p.task_type == "generate_main_plot")
        inst = render_template(
            tpl.content,
            {
                "title": novel.title,
                "romance_ending": novel.romance_ending or "HE",
                "growth_ending": novel.growth_ending or "HE",
            },
        )
        if instruction:
            inst += f"\n作者附加要求：{instruction}"

        fmt = (
            '请输出纯 JSON 对象，格式示例：\n'
            '{"core_conflict": "...", "romance_arc": "...", "growth_arc": "...", '
            '"key_turning_pts": [{"desc": "转折事件描述", "chapter_sort": 15}]}'
        )
        parsed = await self._call_and_parse_json(
            task_type="generate_main_plot",
            layer4_context=context,
            layer5_instruction=inst,
            layer6_format=fmt,
            schema_cls=LlmMainPlotOutput,
        )
        audited = await self._call_and_parse_json(
            task_type="review_main_plot",
            layer4_context=context + "\n【待复核主线初稿】\n" + parsed.model_dump_json(),
            layer5_instruction=(
                "在保存前核对主线各转折的因果与角色信息获取顺序，尤其身份识别的证据是否真的可被该角色获得。"
                "逐项检查从网友到现实初见的渠道边界；修正缺少依据的识别线索及关联转折描述。"
                "保持主线方向和无问题内容，输出修正后的完整主线。\n作者附加要求：" + instruction
            ),
            layer6_format=fmt,
            schema_cls=LlmMainPlotOutput,
        )
        return self._entity_repo.apply_generated_main_plot(audited)

    # --- 5. Outline (Volumes + Arcs + Rolling Chapters per Arc) ---

    async def generate_outline_structure(self, instruction: str = "") -> OutlineTreeResponse:
        self._outline_repo.clear_generated_structure()
        NovelVectorStore(self._novel_uid).clear_all_vectors()

        novel = self._novel_repo.get_novel_detail()
        main_plot = self._entity_repo.get_main_plot()
        chars = self._entity_repo.list_characters()
        context = (
            f"主线核心冲突：{main_plot.core_conflict}\n"
            f"感情线：{main_plot.romance_arc}\n成长线：{main_plot.growth_arc}\n"
            f"关键转折：{json.dumps([pt.model_dump() for pt in main_plot.key_turning_pts], ensure_ascii=False)}\n"
            f"主要人物：{json.dumps([c.name for c in chars], ensure_ascii=False)}"
        )
        inst = (
            f"请为《{novel.title}》规划完整的分卷（Volume）与情节弧（Arc），根据故事阶段、主线转折和因果推进自行决定数量。"
            "全书规划 1 至 10 卷，每卷规划 1 至 6 条情节弧；不同卷的情节弧数量可以不同，不要平均分配或为了达到某个数量拆分剧情。"
            "每卷应代表清楚可辨的故事阶段、目标变化或主要局势转折；每条情节弧必须有自己的目标、核心冲突和阶段性结果，"
            "并推动人物、关系或主线至少一项发生实质变化。相邻情节弧不能只是同一事件的不同步骤、重复铺陈或改写标题；"
            "准备、等待、重复确认等没有独立结果的过场应合并到相关情节弧。卷与弧按故事因果顺序排列，避免重复、遗漏关键转折或凭空添加支线。"
        )
        if instruction:
            inst += (
                f"\n作者结构偏好（供参考；最终卷数和各卷弧数仍须按故事实际推进决定，不得为满足固定数量拆分剧情）：{instruction}"
            )

        fmt = (
            '请输出纯 JSON 对象，卷数为 1 至 10，每卷包含 1 至 6 条情节弧，各卷弧数可不同。\n'
            '{"volumes": [{"title": "第一卷：盛夏入场券", "synopsis": "卷梗概", "goal": "卷目标", '
            '"arcs": [{"title": "第一弧：开学风波", "goal": "弧目标", "core_conflict": "弧冲突", '
            '"start_chapter": 1, "end_chapter": 10}]}]}'
        )
        parsed = await self._call_and_parse_json(
            task_type="generate_outline",
            layer4_context=context,
            layer5_instruction=inst,
            layer6_format=fmt,
            schema_cls=LlmStructureOutput,
            timeout_sec=180.0,
        )
        audit = await self._call_and_parse_json(
            task_type="review_outline_structure",
            layer4_context=(
                f"{context}\n\n【待复核的分卷与情节弧初稿】\n"
                f"{json.dumps([volume.model_dump() for volume in parsed.volumes], ensure_ascii=False)}"
            ),
            layer5_instruction=(
                "复核这份全书结构是否忠于给定主线和关键转折。逐卷检查它是否代表清晰且不同的故事阶段或局势变化；"
                "逐弧检查目标、冲突、阶段性结果及其因果顺序。找出只重复同一事件、只改写标题、把一件事拆成多个步骤、"
                "或没有独立剧情结果的相邻卷/弧，并合并或调整；同时避免合并掉有独立冲突、选择或关系变化的重要内容。"
                "允许按故事需要改变卷数和各卷弧数，不要求平均拆分；不得为了凑数新增无关剧情，不得改变核心人物关系和主线方向。"
                "如果初稿已经合理，则原样返回。只输出复核后的完整结构。"
            ),
            layer6_format=(
                '只输出纯 JSON：{"volumes": [{"title": "卷标题", "synopsis": "卷梗概", "goal": "卷目标", '
                '"arcs": [{"title": "弧标题", "goal": "弧目标", "core_conflict": "弧冲突", '
                '"start_chapter": 1, "end_chapter": 10}]}]}。最终须为 1 至 10 卷，每卷 1 至 6 条情节弧；'
                "各卷弧数可不同，并按故事因果顺序排列。"
            ),
            schema_cls=LlmStructureOutput,
            timeout_sec=180.0,
        )
        tree = self._outline_repo.insert_generated_structure(audit.volumes)
        return tree

    async def generate_arc_chapters(
        self, arc_id: int, chapter_count: int | None = None, instruction: str = ""
    ) -> OutlineTreeResponse:
        arc = self._outline_repo.get_arc(arc_id)
        vol = self._outline_repo.get_volume(arc.volume_id)
        main_plot = self._entity_repo.get_main_plot()
        characters = self._entity_repo.list_characters()
        tree = self._outline_repo.get_outline_tree()
        earlier_chapters = []
        found_arc = False
        for volume in tree.volumes:
            for candidate_arc in volume.arcs:
                if candidate_arc.id == arc_id:
                    found_arc = True
                    break
                earlier_chapters.extend(candidate_arc.chapters)
            if found_arc:
                break
        prior_valid_chapters = sorted(
            (
                ch
                for ch in earlier_chapters
                if ch.status == "final" and not ch.continuity_review_required
            ),
            key=lambda chapter: (chapter.sort_order, chapter.id),
        )
        anchor_chapters = prior_valid_chapters[-3:]

        context = (
            f"所属分卷：{vol.title}（{vol.synopsis}）\n"
            f"当前情节弧：{arc.title} | 目标：{arc.goal} | 核心冲突：{arc.core_conflict}\n"
            f"全书主线冲突：{main_plot.core_conflict}\n"
            "人物卡中的既有经历与人物弧线（章节事实约束）："
            f"{json.dumps([{'name': c.name, 'role': c.role, 'background': c.background, 'arc_design': c.arc_design} for c in characters], ensure_ascii=False)}\n"
            "本弧之前最近且当前有效的已定稿章节（最多三章，仅作为新大纲的前文锚点）："
            f"{json.dumps([{'title': c.title, 'story_time': c.story_time, 'synopsis': c.synopsis} for c in anchor_chapters], ensure_ascii=False)}"
        )
        count_instruction = (
            f"请生成恰好 {chapter_count} 章。"
            if chapter_count is not None
            else "请根据本弧的独立事件、重要转折和因果结果自然决定章节数量，最多 20 章；不要为了凑固定章数拆分过场。"
        )
        inst = (
            f"请为情节弧「{arc.title}」生成章节目录（含章节标题、单章梗概、故事内时间）。{count_instruction}\n"
            "【章节拆分与节奏】每章围绕一个有实质结果的核心事件，说明角色选择/状态变化及其后果；冲突升级、关键决定、关系转折应留出充分展开空间。"
            "准备、等待、重复确认等没有独立事件结果的过场应合并进相邻章节，不单独拆章。相邻章节必须各自带来新信息、选择、冲突或状态变化，"
            "不能只把同一件事拆成连续步骤。梗概只写【发生了什么事件、从哪个状态起、到哪个状态止】，"
            "不写具体对白台词，不写分镜级动作细节，不写结尾意象或景物升华；这些留给正文生成。"
            "【人物经历与关系连续性】人物卡中的既有经历、关系历史与人物弧线是已经确定的故事事实，必须遵守；不能把已经认识、交谈或建立联系的人物重新写成初次见面、首次加好友或首次得知对方。人物背景仅不代表其他角色自动知晓这些信息，不代表作者可以忽略这些事实。前文锚点中更晚发生的明确事件可更新人物卡所述的较早状态；没有更新记录时，必须遵守人物卡。若某个情节目标与人物既有经历冲突，调整情节安排，不得改写人物历史。"
            "例如，若前文已写明江澈得知对方就读临江大学，人物卡里“从没问过学校”只代表更早阶段，后续不得再安排他询问学校或校区，除非剧情明确出现需要确认的新校区。\n"
            "【跨章连贯要求】①每章必须有区别于相邻章节的新核心事件或关系推进，不得把同一段对话、建议、情绪反应拆写到两章；"
            "标志性台词、具体建议和已发生动作只能在首次发生的章节完整呈现，后续章节不得换个说法再次演一遍。"
            "生成前逐章核对前文已经完成的具体动作及其结果；物品已收拾、清洁、放置或处理后，后续章节只能沿用其当前状态，"
            "不得因日期变化或新章节开头而再次安排同一动作，也不得把前章已经完成的准备过程重新当作本章开场。"
            "相邻章节的核心事件与信息揭示严禁重叠：某条信息（如身份、学校、计划）只能在一章中首次揭示，"
            "后续章节只能引用或推进，不得让角色重新得知或再次询问；"
            "②上一章结尾留下的悬念/承诺（如“明天再说”）必须在下一章开头得到回应，故事内时间须与之吻合；"
            "新生成章节必须接在上述前文锚点之后，不得重写或重复其事件；"
            "③首次明确的固定事件日期（如报到日、考试日、迎新日）是全书时间锚点，后续所有章节提及同一事件时必须沿用该日期，"
            "不得为了按日推进章节而把事件提前或延后；‘明天/后天/下周’必须按当前章节日期换算，跨多日章节须给关键事件标明具体日期。"
            "新生成章节的故事时间必须按章节顺序递进，不得从深夜倒回同日早晨；如确需倒叙，须在故事时间中明确标注‘回忆/倒叙/插叙’；"
            "各章日期须与前文锚点一致，人物之间的已知程度（是否见过面、通过视频/语音还是仅文字）须保持一致。"
        )
        if instruction:
            inst += f"\n作者附加要求：{instruction}"

        fmt = (
            '请输出纯 JSON 对象，格式示例：\n'
            '{"chapters": [{"title": "高一（3）班的新同桌", "synopsis": "本章核心事件与情感推进梗概", "story_time": "九月一日上午"}]}'
        )
        parsed = await self._call_and_parse_json(
            task_type="generate_outline_chapters",
            layer4_context=context,
            layer5_instruction=inst,
            layer6_format=fmt,
            schema_cls=LlmChapterBatchOutput,
            timeout_sec=180.0,
        )
        if not parsed.chapters or len(parsed.chapters) > 20:
            raise AppError(
                "OUTLINE_CHAPTER_COUNT_INVALID",
                "章节规划必须生成 1 至 20 章，请重试。",
                status_code=502,
            )
        if chapter_count is not None and len(parsed.chapters) != chapter_count:
            raise AppError(
                "OUTLINE_CHAPTER_COUNT_INVALID",
                f"章节规划应返回 {chapter_count} 章，实际返回 {len(parsed.chapters)} 章，请重试。",
                status_code=502,
            )
        audit = await self._call_and_parse_json(
            task_type="review_outline_chapters",
            layer4_context=(
                f"{context}\n\n【待核对的新生成章节】\n"
                f"{json.dumps([chapter.model_dump() for chapter in parsed.chapters], ensure_ascii=False)}"
            ),
            layer5_instruction=(
                "在保存前核对待生成章节与给出的前文锚点、人物卡既有经历/关系，以及待生成章节彼此之间的剧情连续性和拆章节奏。"
                "重点检查人物已经知道的信息是否被重新询问或重新揭示、同一事件/动作是否重复、日期和相对时间是否冲突。"
                "人物卡里的既有关系不得被写成首次认识或首次加好友；人物卡的作者信息不代表POV已知，但其明确经历仍是故事事实。更晚的前文锚点可以更新较早人物状态。检查是否把纯过场拆成独立章节；"
                "若是自适应章数规划，可合并没有独立推进的相邻章节；若用户指定了章数，必须保持章节数量不变。"
                "若发现问题，只修改有问题章节的必要部分；保持顺序和无问题章节原文。"
                "若没有问题，原样返回全部章节。"
            ),
            layer6_format=(
                '只输出纯 JSON：{"chapters": [{"title": "章节标题", '
                '"synopsis": "章节梗概", "story_time": "故事内时间"}]}。'
                + (
                    f"必须返回恰好 {chapter_count} 章并保持原顺序。"
                    if chapter_count is not None
                    else "可合并无独立剧情推进的相邻章节，但保持故事事件顺序；最终返回 1 至 20 章。"
                )
            ),
            schema_cls=LlmChapterBatchOutput,
            timeout_sec=180.0,
        )
        if (
            not audit.chapters
            or len(audit.chapters) > 20
            or (chapter_count is not None and len(audit.chapters) != chapter_count)
        ):
            raise AppError(
                "OUTLINE_REVIEW_INVALID",
                "大纲连贯性复核返回的章节数量不符合要求，请重试生成。",
                status_code=502,
            )
        tree, deleted_chapter_ids = self._outline_repo.replace_arc_chapters(
            arc_id, audit.chapters, prior_valid_chapters
        )
        if deleted_chapter_ids:
            NovelVectorStore(self._novel_uid).remove_chapter_chunks(deleted_chapter_ids)
        return tree
