"""Context Assembler with token budget & confirmation filtering (Design Doc 5.3 & Dev Doc 4.2)."""

from __future__ import annotations

import re
import sqlite3

from app.core.text_hash import text_sha256
from app.db.repositories.entity_repo import EntityRepository
from app.db.repositories.constraint_repo import ConstraintRepository
from app.db.repositories.novel_repo import NovelRepository
from app.db.repositories.outline_repo import OutlineRepository
from app.db.repositories.settings_repo import SettingsRepository
from app.db.repositories.writing_repo import WritingRepository
from app.db.vector_store import NovelVectorStore
from app.schemas.writing import ContextBlockItem, ContextPreviewResponse
from app.services.embedding.encoder import encode_text_sync
from app.services.llm.client import estimate_tokens
from app.services.story_time import time_anchor

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
        self._constraint_repo = ConstraintRepository(novel_conn)
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
        char_name_by_id = {c.id: c.name for c in all_chars}
        loc_name_by_id = {l.id: l.name for l in all_locs}

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
            meta_parts: list[str] = []
            if s.pov_character and s.pov_character in char_name_by_id:
                meta_parts.append(f"视角(POV)：{char_name_by_id[s.pov_character]}")
            if s.location_id and s.location_id in loc_name_by_id:
                meta_parts.append(f"地点：{loc_name_by_id[s.location_id]}")
            present_names = [
                char_name_by_id[cid] for cid in s.character_ids if cid in char_name_by_id
            ]
            if present_names:
                meta_parts.append(f"在场人物：{'、'.join(present_names)}")
            if s.story_time:
                meta_parts.append(f"时间：{s.story_time}")
            meta_str = f" [{' | '.join(meta_parts)}]" if meta_parts else ""
            beats_lines.append(
                f"场景 {idx} {marker}（目标 {s.target_words} 字）{meta_str}：{s.beat}"
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
                or "无结构化状态变更记录；以本章起点为准，沿用人物卡基准状态与前文已写事件，不要据此另造新状态"
            )
            rel_str = (
                "；".join(
                    f"{r['char_a_name']}↔{r['char_b_name']}({r['rel_type']})"
                    for r in snap.relationships
                )
                or "未记录结构化关系状态；请依据人物卡中的既有经历与前文判断，不得据此推断为初见或不熟"
            )
            age_part = f"{c.initial_age}岁" if c.initial_age else "未填"
            bg_part = c.background or "未填"
            char_lines.append(
                f"• 【{c.name}】({c.role}，年龄：{age_part}) 身份背景：{bg_part} | "
                f"外貌：{snap.effective_appearance} | 性格：{c.personality} | "
                f"说话风格：{c.speech_style} | 当前状态：{state_str} | 关系：{rel_str}"
            )
            if snap.known_secrets:
                sec_list = "；".join(str(s["secret"]) for s in snap.known_secrets)
                known_secrets_lines.append(f"• 【{c.name}】已知秘密：{sec_list}")
            else:
                known_secrets_lines.append(
                    f"• 【{c.name}】未记录已确认的认知信息，不代表角色一无所知；以正文中实际获知的事件为准，不得据此抹去已知信息。"
                )

        if char_lines:
            char_lines.append(
                "⚠️ 人物连续性与认知边界：人物卡中的既有经历和关系历史是故事事实，正文不得与之冲突；但人物卡不代表 POV 自动知晓其他角色的私密背景或内心。关系栏仅记录结构化确认的关系变化，若标为未记录，不等于初见或不熟，须结合人物卡和前文判断；关系栏有明确状态时，按该状态及更晚的前文事件推进。"
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

        # 3.5 硬约束清单（防事实幻觉）：当前章节生效中的显式禁令
        constraint_lines: list[str] = []
        active_constraints = self._constraint_repo.list_active_for_chapter(
            chapter_id,
            ch.sort_order,
            sorted(active_char_ids),
            sorted(active_loc_ids),
        )
        for con in active_constraints:
            sev = "硬约束" if con.severity == "hard" else "软约束"
            violated_mark = "⚠️已确认违反" if con.status == "violated" else ""
            scope = {
                "character": "人物",
                "location": "地点",
                "worldview": "世界观",
                "chapter": "章节",
                "novel": "全书",
            }.get(con.target_type, con.target_type)
            name_part = f"「{con.target_name}」" if con.target_name else ""
            constraint_lines.append(f"• 【{sev}{violated_mark}·{scope}{name_part}】{con.content}")
        if constraint_lines:
            constraint_lines.append(
                "⚠️ 动笔前请核对以上硬约束，正文中不要复述检查过程；"
                "如剧情推进需要打破某条约束，请先到约束管理中将其标记为已解除，不要擅自违反。"
            )
        blocks.append(
            self._make_block(
                "hard_constraints",
                "硬约束清单（防事实幻觉）",
                "\n".join(constraint_lines) or "暂无生效中的硬约束",
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
        if loc_lines:
            loc_lines.append(
                "⚠️ 环境熟悉度与物理常理边界：以上地点设定仅供作者镜头描写参考，绝不等于角色脑中的既有记忆！若角色属于初次到访（如新生刚报到、刚转学、初访某场所），言行必须体现陌生感、四处打量、看路牌或问路，严禁表现得熟门熟路；空间移动需有合理动作过渡，严禁瞬移。"
            )
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
            WHERE c.sort_order < ? AND s.is_stale = 0
              AND s.source_hash = c.content_hash
              AND c.status = 'final' AND c.continuity_review_required = 0
            ORDER BY c.sort_order DESC LIMIT 6
            """,
            (ch.sort_order,),
        ).fetchall()
        sum_lines = [
            f"• 《{r['title']}》摘要：{r['content']}" for r in reversed(sum_rows)
        ]
        prev_row = self._conn.execute(
            """
            SELECT c.id, c.title, c.synopsis, c.story_time, c.continuity_review_required,
                   c.content_hash, cv.content AS latest_content
            FROM chapters c
            LEFT JOIN chapter_versions cv ON cv.id = (
                SELECT v.id FROM chapter_versions v WHERE v.chapter_id = c.id
                ORDER BY v.version DESC, v.id DESC LIMIT 1
            )
            WHERE c.sort_order < ? ORDER BY c.sort_order DESC, c.id DESC LIMIT 1
            """,
            (ch.sort_order,),
        ).fetchone()
        time_note, time_warnings = time_anchor(
            str(prev_row['story_time'] or '') if prev_row else None, ch.story_time or '',
        )
        sum_lines.append(time_note)
        prev_is_fresh = bool(
            prev_row
            and not prev_row["continuity_review_required"]
            and prev_row["content_hash"]
            and str(prev_row["content_hash"])
            == text_sha256(str(prev_row["latest_content"] or ""))
        )
        if prev_is_fresh and prev_row["synopsis"]:
            sum_lines.append(
                f"【上一章《{prev_row['title']}》梗概（事实与剧情连续性依据）】{prev_row['synopsis']}"
            )
        prev_full = str(prev_row["latest_content"] or "").strip() if prev_is_fresh else ""
        if prev_full:
            # 只喂上一章结尾片段用于衔接语气与承接悬念；完整事实依据由上一章梗概提供。
            # 不喂全文，避免模型模仿上一章句式造成文风遗传放大，也控制上下文体量。
            tail_chars = 1500
            if len(prev_full) > tail_chars:
                prev_tail = "……\n" + prev_full[-tail_chars:]
            else:
                prev_tail = prev_full
            sum_lines.append(
                f"【上一章《{prev_row['title']}》结尾片段（仅用于衔接语气与承接悬念，完整事实以上方梗概为准）】\n{prev_tail}"
            )
        next_row = self._conn.execute(
            "SELECT title, synopsis FROM chapters WHERE sort_order > ? ORDER BY sort_order ASC LIMIT 1",
            (ch.sort_order,),
        ).fetchone()
        if next_row and next_row["synopsis"]:
            sum_lines.append(
                f"【下一章《{next_row['title']}》梗概（仅作边界，本章严禁提前写入）】{next_row['synopsis']}"
            )
        if prev_row or prev_full or next_row:
            sum_lines.append(
                "⚠️ 跨章衔接边界：①上一章已交代的信息，仅实际在场、收到消息或被告知的角色知晓；不得将叙述者知识分配给所有角色，也不得让已知情者再次把它当成新消息；"
                "上一章梗概与结尾正文是连续性事实来源；角色首次得知某信息的时间，以其中明确写出的场景为准，"
                "不得把人物卡里的背景设定当作角色过去已听过的内容，也不得补造上下文没有记载的旧聊天或旧告知；"
                "回复涉及未来日期的提醒时，必须先核对当前章日期；时间尚未到，不得写成已经出发、到达或完成；"
                "若‘到了’指回家，必须明确写出‘到家了’，并确保回复动机自然；"
                "若本章梗概与上一章正文内容重复，以已写正文为准，跳过重复部分直接推进；"
                "②开篇须先承接上一章结尾留下的悬念、承诺（如“明天再说”）与人物情绪；故事时间只用于保持连贯，"
                "不要求每章开篇直接报日期或时间，可从动作、对话、物件或人物状态切入，再在需要时自然交代时间；"
                "相邻章节开头应改变切入方式，避免反复使用日期加天气/时段的固定句式；"
                "③不得写入下一章梗概中的事件；④避免与上一章使用相同的结构套路与收尾意象。"
            )
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
            SELECT f.description, f.status FROM foreshadowing f
            LEFT JOIN chapters c ON c.id = f.planted_chapter_id
            WHERE f.confirm_status = 'confirmed' AND f.status IN ('planted', 'hinted')
              AND f.is_stale = 0
              AND (f.origin = 'manual' OR f.planted_chapter_id IS NULL OR
                   (f.origin = 'extracted' AND f.source_hash = c.content_hash
                    AND c.status = 'final' AND c.continuity_review_required = 0))
            ORDER BY f.id DESC LIMIT 8
            """
        ).fetchall()
        fact_rows = self._conn.execute(
            """
            SELECT f.content FROM facts f
            LEFT JOIN chapters c ON c.id = f.chapter_id
            WHERE f.status IN ('confirmed', 'locked')
              AND f.is_stale = 0
              AND (f.chapter_id IS NULL OR f.origin = 'manual' OR
                   (f.origin = 'extracted' AND f.source_hash = c.content_hash
                    AND c.status = 'final' AND c.continuity_review_required = 0))
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
            fresh_chapter_hashes = {
                int(row["id"]): str(row["content_hash"])
                for row in self._conn.execute(
                    "SELECT id, content_hash FROM chapters WHERE sort_order < ? "
                    "AND status = 'final' AND continuity_review_required = 0 "
                    "AND content_hash IS NOT NULL",
                    (ch.sort_order,),
                ).fetchall()
            }
            query_str = combined_beats.strip() or ch.title
            q_vec = encode_text_sync(query_str)
            vec_hits = self._vector_store.search_vectors(
                query_vec=q_vec,
                max_chapter_sort=ch.sort_order - 0.0001,
                allowed_chapter_hashes=fresh_chapter_hashes,
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
            warnings=time_warnings,
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
