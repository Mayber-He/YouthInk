"""Context Assembler with token budget & confirmation filtering (Design Doc 5.3 & Dev Doc 4.2)."""

from __future__ import annotations

import re
import sqlite3

from app.db.repositories.entity_repo import EntityRepository
from app.db.repositories.novel_repo import NovelRepository
from app.db.repositories.outline_repo import OutlineRepository
from app.db.repositories.settings_repo import SettingsRepository
from app.db.repositories.writing_repo import WritingRepository
from app.db.vector_store import NovelVectorStore
from app.schemas.writing import ContextBlockItem, ContextPreviewResponse
from app.services.embedding.encoder import encode_text_sync
from app.services.llm.client import estimate_tokens

_MENTION_RE = re.compile(r"@([^\s，,。；;！!？?\n]+)")


class ContextAssembler:
    """Builds transparent, toggleable context blocks for chapter/scene generation."""

    def __init__(
        self,
        novel_conn: sqlite3.Connection,
        novel_uid: str,
        settings_repo: SettingsRepository,
    ) -> None:
        self._conn = novel_conn
        self._novel_uid = novel_uid
        self._novel_repo = NovelRepository(novel_conn, novel_uid)
        self._entity_repo = EntityRepository(novel_conn)
        self._outline_repo = OutlineRepository(novel_conn)
        self._writing_repo = WritingRepository(novel_conn)
        self._settings_repo = settings_repo
        self._vector_store = NovelVectorStore(novel_uid)

    def build_context_preview(
        self,
        chapter_id: int,
        scene_id: int | None = None,
        disabled_keys: list[str] | None = None,
    ) -> ContextPreviewResponse:
        disabled = set(disabled_keys or [])
        ch = self._outline_repo.get_chapter(chapter_id)
        scenes = self._writing_repo.list_scenes(chapter_id)
        all_chars = self._entity_repo.list_characters()
        all_locs = self._entity_repo.list_locations()

        active_char_ids: set[int] = set()
        active_loc_ids: set[int] = set()
        beat_texts = [ch.synopsis] + [s.beat for s in scenes]
        combined_beats = "\n".join(beat_texts)

        for s in scenes:
            if scene_id is None or s.id == scene_id:
                if s.pov_character:
                    active_char_ids.add(s.pov_character)
                if s.location_id:
                    active_loc_ids.add(s.location_id)
                active_char_ids.update(s.character_ids)

        mentions = set(_MENTION_RE.findall(combined_beats))
        for c in all_chars:
            names = {c.name, *c.aliases}
            if names & mentions or any(n in combined_beats for n in names if n):
                active_char_ids.add(c.id)
        for loc in all_locs:
            names = {loc.name, *loc.aliases}
            if names & mentions or any(n in combined_beats for n in names if n):
                active_loc_ids.add(loc.id)

        if not active_char_ids:
            active_char_ids.update(
                c.id for c in all_chars if c.role in ("female_lead", "male_lead", "major")
            )

        blocks: list[ContextBlockItem] = []

        # 1. 本章细纲与场景节拍
        beats_lines = [
            f"章节：第 {ch.display_index} 章《{ch.title}》",
            f"本章梗概：{ch.synopsis or '无'}",
            f"故事内时间：{ch.story_time or '未指定'}",
        ]
        for idx, s in enumerate(scenes, start=1):
            marker = "👉 [当前生成场景]" if s.id == scene_id else ""
            beats_lines.append(
                f"场景 {idx} {marker}（目标 {s.target_words} 字）：{s.beat}"
            )
        blocks.append(
            self._make_block("chapter_beats", "本章细纲与场景节拍", "\n".join(beats_lines), disabled)
        )

        # 2. 出场人物当前状态 + 人物卡 (only confirmed state changes up to ch.sort_order)
        char_lines: list[str] = []
        known_secrets_lines: list[str] = []
        for cid in sorted(active_char_ids):
            c = next((item for item in all_chars if item.id == cid), None)
            if not c:
                continue
            snap = self._entity_repo.get_character_timeline_snapshot(cid, ch.sort_order)
            state_str = (
                "；".join(f"{k}:{v}" for k, v in snap.current_states.items())
                or "保持初始基准状态"
            )
            rel_str = (
                "；".join(
                    f"{r['char_a_name']}↔{r['char_b_name']}({r['rel_type']})"
                    for r in snap.relationships
                )
                or "无变更"
            )
            char_lines.append(
                f"• 【{c.name}】({c.role}) 外貌：{snap.effective_appearance} | "
                f"性格：{c.personality} | 说话风格：{c.speech_style} | "
                f"当前状态：{state_str} | 关系：{rel_str}"
            )
            if snap.known_secrets:
                sec_list = "；".join(str(s["secret"]) for s in snap.known_secrets)
                known_secrets_lines.append(f"• 【{c.name}】已知秘密：{sec_list}")
            else:
                known_secrets_lines.append(
                    f"• 【{c.name}】目前尚不知晓任何隐藏秘密（严禁在言行中提前剧透）"
                )

        blocks.append(
            self._make_block(
                "character_states",
                "出场人物卡与当前时序状态",
                "\n".join(char_lines) or "暂无指定出场人物",
                disabled,
            )
        )

        # 3. 出场人物认知约束
        blocks.append(
            self._make_block(
                "cognitive_constraints",
                "出场人物认知边界（防超知幻觉）",
                "\n".join(known_secrets_lines) or "无特殊认知约束",
                disabled,
            )
        )

        # 4. 本章地点与世界观硬约束
        loc_lines: list[str] = []
        for lid in sorted(active_loc_ids):
            loc = next((l for l in all_locs if l.id == lid), None)
            if loc:
                loc_lines.append(
                    f"• 地点【{loc.name}】：{loc.description}（感官细节：{loc.sensory_details}）"
                )
        for wv in self._entity_repo.list_worldview()[:6]:
            loc_lines.append(f"• 世界观[{wv.category}]：{wv.content}")
        blocks.append(
            self._make_block(
                "location_and_worldview",
                "本章地点感官与世界观约束",
                "\n".join(loc_lines) or "无特定地点描述",
                disabled,
            )
        )

        # 5. 分层摘要与上一章结尾
        sum_rows = self._conn.execute(
            """
            SELECT s.content, c.title, c.sort_order
            FROM summaries s
            JOIN chapters c ON s.level = 'chapter' AND s.ref_id = c.id
            WHERE c.sort_order < ?
            ORDER BY c.sort_order DESC LIMIT 6
            """,
            (ch.sort_order,),
        ).fetchall()
        sum_lines = [
            f"• 《{r['title']}》摘要：{r['content']}" for r in reversed(sum_rows)
        ]
        prev_tail = self._writing_repo.get_previous_chapter_text(ch.sort_order)
        if prev_tail:
            sum_lines.append(prev_tail)
        blocks.append(
            self._make_block(
                "summaries_and_prev",
                "前文摘要与上一章衔接片段",
                "\n".join(sum_lines) or "本章为开篇章节，无前文摘要",
                disabled,
            )
        )

        # 6. 计划伏笔与已确认事实
        fs_rows = self._conn.execute(
            """
            SELECT description, status FROM foreshadowing
            WHERE confirm_status = 'confirmed' AND status IN ('planted', 'hinted')
            ORDER BY id DESC LIMIT 8
            """
        ).fetchall()
        fact_rows = self._conn.execute(
            """
            SELECT f.content FROM facts f
            LEFT JOIN chapters c ON c.id = f.chapter_id
            WHERE f.status IN ('confirmed', 'locked')
              AND (c.sort_order IS NULL OR c.sort_order <= ?)
            ORDER BY f.id DESC LIMIT 10
            """,
            (ch.sort_order,),
        ).fetchall()
        fs_lines = [f"• [伏笔-{r['status']}] {r['description']}" for r in fs_rows] + [
            f"• [已确认事实] {r['content']}" for r in fact_rows
        ]
        blocks.append(
            self._make_block(
                "foreshadowing_and_facts",
                "伏笔台账与已确认事实库",
                "\n".join(fs_lines) or "暂无待回收伏笔或历史事实",
                disabled,
                priority="optional",
            )
        )

        # 7. RAG 历史高相关场景片段
        rag_lines: list[str] = []
        if self._vector_store.store_file.exists():
            query_str = combined_beats.strip() or ch.title
            q_vec = encode_text_sync(query_str)
            vec_hits = self._vector_store.search_vectors(
                query_vec=q_vec,
                max_chapter_sort=ch.sort_order - 0.0001,
                top_k=3,
            )
            rag_lines = [
                f"• [历史章节 #{rec.chapter_id} 片段] {rec.text[:260]}"
                for rec, _score in vec_hits
            ]
        blocks.append(
            self._make_block(
                "rag_history",
                "RAG 检索相关历史场景片段",
                "\n".join(rag_lines) or "暂无已定稿历史向量片段",
                disabled,
                priority="optional",
            )
        )

        total_tokens = sum(b.tokens for b in blocks if b.enabled)
        return ContextPreviewResponse(
            chapter_id=chapter_id,
            scene_id=scene_id,
            total_tokens=total_tokens,
            budget_tokens=24000,
            blocks=blocks,
        )

    @staticmethod
    def _make_block(
        key: str,
        label: str,
        content: str,
        disabled: set[str],
        priority: str = "required",
    ) -> ContextBlockItem:
        return ContextBlockItem(
            key=key,
            label=label,
            priority=priority,  # type: ignore[arg-type]
            enabled=key not in disabled,
            tokens=estimate_tokens(content),
            content=content,
        )
