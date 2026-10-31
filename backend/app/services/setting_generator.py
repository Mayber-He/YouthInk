"""AI generation and single-item rewrite service for M2 Settings & Outline."""

from __future__ import annotations

import json
from typing import TypeVar
from pydantic import BaseModel

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
from app.services.llm.client import complete_chat
from app.services.llm.json_parser import parse_and_validate_json
from app.services.prompt.renderer import assemble_six_layer_prompt, render_template

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
    ) -> T:
        layer1, layer2, layer3 = self._build_base_layers()
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
        return self._entity_repo.apply_generated_main_plot(parsed)

    # --- 5. Outline (Volumes + Arcs + Rolling Chapters per Arc) ---

    async def generate_outline_structure(
        self, volume_count: int = 3, arcs_per_volume: int = 2, instruction: str = ""
    ) -> OutlineTreeResponse:
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
            f"请为《{novel.title}》规划 {volume_count} 个分卷（Volume），每个分卷包含 {arcs_per_volume} 个情节弧（Arc）。"
        )
        if instruction:
            inst += f"\n作者附加要求：{instruction}"

        fmt = (
            '请输出纯 JSON 对象，格式示例：\n'
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
        )
        return self._outline_repo.apply_generated_structure(parsed.volumes)

    async def generate_arc_chapters(
        self, arc_id: int, chapter_count: int = 5, instruction: str = ""
    ) -> OutlineTreeResponse:
        arc = self._outline_repo.get_arc(arc_id)
        vol = self._outline_repo.get_volume(arc.volume_id)
        main_plot = self._entity_repo.get_main_plot()
        tree = self._outline_repo.get_outline_tree()
        existing_locked = [
            ch
            for v in tree.volumes
            for a in v.arcs
            if a.id == arc_id
            for ch in a.chapters
            if ch.locked
        ]

        context = (
            f"所属分卷：{vol.title}（{vol.synopsis}）\n"
            f"当前情节弧：{arc.title} | 目标：{arc.goal} | 核心冲突：{arc.core_conflict}\n"
            f"全书主线冲突：{main_plot.core_conflict}\n"
            f"本弧已锁定章节：{json.dumps([{'title': c.title, 'synopsis': c.synopsis} for c in existing_locked], ensure_ascii=False)}"
        )
        inst = f"请为情节弧「{arc.title}」滚动生成 {chapter_count} 章的章节目录（含章节标题、单章详细梗概、故事内时间）。"
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
        )
        return self._outline_repo.replace_unlocked_arc_chapters(arc_id, parsed.chapters)
