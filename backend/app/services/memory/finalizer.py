"""Chapter Finalization & Memory Loop Pipeline (Design Doc 5.4 & Dev Doc 4.3)."""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3

from app.core.exceptions import AppError
from app.core.text_hash import text_sha256
from app.db.repositories.constraint_repo import ConstraintRepository
from app.db.repositories.entity_repo import EntityRepository
from app.db.repositories.memory_repo import MemoryRepository
from app.db.repositories.outline_repo import OutlineRepository
from app.db.repositories.settings_repo import SettingsRepository
from app.db.repositories.writing_repo import WritingRepository
from app.db.vector_store import NovelVectorStore, VectorChunkRecord
from app.schemas.memory import (
    FinalizeChapterResponse,
    LlmExtractedFact,
    LlmMemoryExtractionOutput,
)
from app.services.backup_service import create_novel_backup
from app.services.embedding.encoder import encode_text_sync
from app.services.llm.client import complete_chat
from app.services.memory.extraction_parse import (
    ExtractionParseResult,
    normalize_for_quote_match,
    parse_extraction_items,
)

logger = logging.getLogger(__name__)


# Field/枚举说明 + 一个示例，与 app/schemas/memory.py 的六类子模型逐字对齐。
# 单独抽成常量以便测试断言提示词覆盖了全部六类与关键字段名。
MEMORY_EXTRACTION_SCHEMA_GUIDE = (
    "必须严格输出下列六个数组字段的 JSON 对象（无多余字段），每个元素字段名必须与下方完全一致：\n"
    "1) facts（最多 8 条，只收对后续剧情有影响的关系变化、承诺、秘密、关键物品和地点状态）：\n"
    "   不收看相册、收藏照片等一次性动作；同义内容只保留一条，不把同一事件拆成多条。\n"
    '   {"content": "事实描述", "fact_type": "event|item|place|state|other", '
    '"character_names": ["涉及角色名"], "location_names": ["涉及地点名"], '
    '"source_quote": "正文原句（逐字）"}\n'
    "2) state_changes（人物状态变更）：\n"
    '   {"character_name": "角色名", '
    '"field": "location|body|emotion|goal|identity|item|appearance", '
    '"value": "新状态值", "source_quote": "正文原句（逐字）"}\n'
    "3) cognitive_records（谁知道了什么秘密/认知）：\n"
    '   {"secret": "秘密或认知内容", "knower_names": ["知情角色名"], '
    '"learned_by": "如何得知", "source_quote": "正文原句（逐字）"}\n'
    "4) relationship_changes（人物关系变化，a≠b）：\n"
    '   {"char_a_name": "角色A", "char_b_name": "角色B", "rel_type": "关系类型", '
    '"intimacy": 0-10 的整数, "publicity": "public|mutual|one_sided", '
    '"change_reason": "变化原因", "source_quote": "正文原句（逐字）"}\n'
    "5) foreshadowing（只收有明确回收可能的伏笔；普通情绪、日常动作和已结束事件不算伏笔）：\n"
    '   {"description": "伏笔描述", "status": "planted|hinted|recovered", '
    '"plan_recover_start": 章号或null, "plan_recover_end": 章号或null, '
    '"source_quote": "正文原句（逐字）"}\n'
    "6) constraint_checks（只输出确有违反或剧情正式解除的约束，violated/resolved）：\n"
    '   {"constraint_id": 约束编号, "verdict": "violated|resolved", '
    '"evidence_quote": "正文原句（逐字）", "description": "判定说明"}\n'
    "resolved 只表示剧情已正式解除该约束，且原文有证据；本章未涉及/未违反一律不要输出。"
    "没有违反也没有解除的约束不用出现在 constraint_checks 里，禁止用 resolved 表示未违反。\n"
    "规则：source_quote / evidence_quote 必须是正文中真实存在的连续原句，不得改写、拼接或省略；"
    "无法给出原句证据的条目一律不要输出；无相应内容的数组请给空数组 []。\n"
    "示例（仅示意字段形态，不要照抄内容）：\n"
    '{"facts": [{"content": "江澈修好了王姨的旧打印机", "fact_type": "event", '
    '"character_names": ["江澈"], "location_names": [], '
    '"source_quote": "吐出来的那张测试页平整干净，字口清楚。"}], '
    '"state_changes": [], "cognitive_records": [], "relationship_changes": [], '
    '"foreshadowing": [], "constraint_checks": []}'
)


def split_text_chunks(text: str, chunk_size: int = 650, overlap: int = 100) -> list[str]:
    """Split chapter text into 500~800 char chunks respecting paragraph boundaries."""
    cleaned = text.strip()
    if not cleaned:
        return []
    if len(cleaned) <= chunk_size:
        return [cleaned]
    chunks: list[str] = []
    start, n = 0, len(cleaned)
    while start < n:
        end = min(start + chunk_size, n)
        if end < n:
            nl = cleaned.rfind("\n", start + chunk_size // 2, end)
            if nl != -1:
                end = nl + 1
        piece = cleaned[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        start = max(start + 1, end - overlap)
    return chunks


class ChapterFinalizerService:
    """Executes the 6-step post-finalization memory loop and index rebuilds."""

    def __init__(
        self,
        novel_uid: str,
        novel_conn: sqlite3.Connection,
        global_conn: sqlite3.Connection,
    ) -> None:
        self.novel_uid = novel_uid
        self.conn = novel_conn
        self.settings_repo = SettingsRepository(global_conn)
        self.outline_repo = OutlineRepository(novel_conn)
        self.writing_repo = WritingRepository(novel_conn)
        self.entity_repo = EntityRepository(novel_conn)
        self.constraint_repo = ConstraintRepository(novel_conn)
        self.memory_repo = MemoryRepository(novel_conn)
        self.vector_store = NovelVectorStore(novel_uid)

    async def finalize_chapter(self, chapter_id: int) -> FinalizeChapterResponse:
        ch = self.outline_repo.get_chapter(chapter_id)
        versions = self.writing_repo.list_versions(chapter_id)
        latest_ver = versions[0] if versions else None
        raw_content = latest_ver.content if latest_ver else ""
        content = raw_content.strip()
        if not content:
            raise AppError("EMPTY_CHAPTER_CONTENT", "章节正文为空，无法执行定稿入库。", 400)

        source_hash = text_sha256(raw_content)
        backup_info = create_novel_backup(self.novel_uid, reason=f"finalize_ch_{chapter_id}")
        chunks_count = await self._index_chapter_chunks_and_fts(
            chapter_id=chapter_id,
            chapter_sort_order=ch.sort_order,
            story_time=ch.story_time or "",
            version_id=latest_ver.id if latest_ver else chapter_id,
            content=raw_content,
            source_hash=source_hash,
        )
        self.conn.commit()

        summary_text = await self._generate_chapter_summary(chapter_id, ch.title, content)
        self.memory_repo.upsert_summary("chapter", chapter_id, summary_text, is_stale=False, source_hash=source_hash)
        self.conn.execute(
            "UPDATE chapters SET status = 'final', content_hash = ?, continuity_review_required = 0, continuity_dirty_from_chapter_id = NULL WHERE id = ?",
            (source_hash, chapter_id),
        )
        self.conn.commit()

        extraction, extraction_status = await self._extract_chapter_memories(
            chapter_id, ch.title, content
        )
        # 整批失败走兜底事实时，禁止自动确认——必须进待确认队列由人工把关。
        auto_confirmed, pending_cnt = self._persist_extracted_memories(
            chapter_id, extraction, source_hash,
            force_pending=(extraction_status == "failed"),
        )

        self.conn.execute(
            "UPDATE chapters SET status = 'final', content_hash = ?, updated_at = datetime('now') WHERE id = ?",
            (source_hash, chapter_id),
        )
        return FinalizeChapterResponse(
            chapter_id=chapter_id,
            status="final",
            backup_filename=backup_info.filename,
            chunks_indexed=chunks_count,
            chapter_summary=summary_text,
            auto_confirmed_count=auto_confirmed,
            pending_count=pending_cnt,
            extraction_status=extraction_status,
        )

    def _current_embedding_model_id(self) -> str:
        cfg = self.settings_repo.get_setting("embedding", {})
        return str(cfg.get("model_id", "bge-m3-onnx-int8")) if isinstance(cfg, dict) else "bge-m3-onnx-int8"

    async def rebuild_all_indexes(self) -> dict[str, int]:
        """Clear and rebuild all vector chunks and FTS5 indexes for finalized chapters."""
        self.vector_store.clear_all_vectors()
        emb_model = self._current_embedding_model_id()
        rows = self.conn.execute(
            "SELECT id, sort_order, story_time, content_hash FROM chapters WHERE status = 'final' AND continuity_review_required = 0 ORDER BY sort_order ASC"
        ).fetchall()
        total_chunks = 0
        for r in rows:
            cid = int(r["id"])
            versions = self.writing_repo.list_versions(cid)
            ver = versions[0] if versions else None
            if ver and ver.content.strip():
                total_chunks += await self._index_chapter_chunks_and_fts(
                    cid, float(r["sort_order"]), str(r["story_time"] or ""), ver.id, ver.content, emb_model, text_sha256(ver.content)
                )
        return {"chapters_reindexed": len(rows), "chunks_indexed": total_chunks}

    async def _index_chapter_chunks_and_fts(
        self,
        chapter_id: int,
        chapter_sort_order: float,
        story_time: str,
        version_id: int,
        content: str,
        model_id: str | None = None,
        source_hash: str | None = None,
    ) -> int:
        emb_model = model_id or self._current_embedding_model_id()
        source_hash = source_hash or text_sha256(content)
        scenes = self.writing_repo.list_scenes(chapter_id)
        char_ids = sorted(
            {cid for s in scenes for cid in ([s.pov_character] if s.pov_character else []) + s.character_ids}
        )
        loc_id = next((s.location_id for s in scenes if s.location_id), None)

        records: list[VectorChunkRecord] = []
        for idx, piece in enumerate(split_text_chunks(content), start=1):
            vec = await asyncio.to_thread(encode_text_sync, piece)
            records.append(
                VectorChunkRecord(
                    chunk_id=f"ch_{chapter_id}_ck_{idx}",
                    chapter_id=chapter_id,
                    chapter_sort_order=chapter_sort_order,
                    scene_id=scenes[0].id if scenes else None,
                    character_ids=char_ids,
                    location_id=loc_id,
                    story_time=story_time,
                    embedding_model_id=emb_model,
                    text=piece,
                    vector=vec,
                    source_hash=source_hash,
                )
            )
        self.vector_store.upsert_chapter_chunks(chapter_id, records)
        self.memory_repo.index_chapter_version_fts(version_id, content)
        return len(records)

    async def _generate_chapter_summary(self, chapter_id: int, title: str, content: str) -> str:
        prompt = f"请将章节《{title}》浓缩为 180~300 字剧情摘要：\n\n{content[:4500]}"
        try:
            _pid, base_url, model, api_key = self.settings_repo.get_credentials_for_task("extract")
            res = await complete_chat(
                base_url=base_url,
                api_key=api_key,
                model=model,
                system_prompt="直接输出客观剧情摘要正文。",
                user_prompt=prompt,
                novel_uid=self.novel_uid,
                task_type="summary_extract",
                chapter_id=chapter_id,
            )
            if res.content.strip():
                return res.content.strip()
        except Exception:
            pass
        return f"【《{title}》章节摘要】" + content[:240].replace("\n", " ")

    def _build_extraction_prompt(
        self, title: str, content: str, char_names: list[str], constraint_lines: str, story_time: str = ""
    ) -> str:
        constraint_section = (
            f"\n\n本章生效中的硬约束清单（仅报告真实违反或剧情正式解除，其余不输出）：\n{constraint_lines}\n"
            if constraint_lines
            else ""
        )
        return (
            f"请从章节《{title}》正文中抽取结构化设定变更与记忆条目。\n"
            f"已知角色（请只使用这些角色名）：{', '.join(char_names) or '无'}\n\n"
            f"本章发生时间：{story_time or '未指定'}\n"
            "state_changes、facts、foreshadowing 中明天/下周/过几天等相对时间，"
            "必须改写成相对本章时间（story_time）的次日/下一周/数日后，或可确定的具体日期；"
            "不得把相对时间原样写入跨章记忆，无法确定日期时不得猜补年份或日期。\n"
            f"{MEMORY_EXTRACTION_SCHEMA_GUIDE}"
            f"{constraint_section}\n\n"
            f"章节正文：\n{content[:5000]}"
        )

    async def _extract_chapter_memories(
        self, chapter_id: int, title: str, content: str
    ) -> tuple[LlmMemoryExtractionOutput, str]:
        """Extract memories with per-item tolerance; returns (output, status).

        status ∈ {'ok','partial','failed'} drives the frontend badge. 'failed'
        means the batch could not be parsed at all and a non-auto-confirmable
        fallback fact was produced.
        """
        char_names = [c.name for c in self.entity_repo.list_characters()]
        ch = self.outline_repo.get_chapter(chapter_id)
        scenes = self.writing_repo.list_scenes(chapter_id)
        char_ids = sorted(
            {cid for s in scenes for cid in ([s.pov_character] if s.pov_character else []) + s.character_ids}
        )
        loc_ids = sorted({s.location_id for s in scenes if s.location_id})
        active_constraints = self.constraint_repo.list_active_for_chapter(
            chapter_id, ch.sort_order, char_ids, loc_ids
        )
        constraint_lines = "\n".join(
            f"[#{c.id}] 【{'硬约束' if c.severity == 'hard' else '软约束'}"
            f"·{c.target_type}{'「' + c.target_name + '」' if c.target_name else ''}】{c.content}"
            for c in active_constraints
        )
        base_prompt = self._build_extraction_prompt(
            title, content, char_names, constraint_lines, story_time=ch.story_time or ""
        )

        try:
            _pid, base_url, model, api_key = self.settings_repo.get_credentials_for_task("extract")
        except Exception:
            logger.warning("memory extract: no LLM credentials; using fallback (chapter_id=%s)", chapter_id)
            return self._fallback_extraction(title, content, char_names), "failed"

        async def _call(user_prompt: str) -> str:
            res = await complete_chat(
                base_url=base_url,
                api_key=api_key,
                model=model,
                system_prompt="你是小说记忆抽取引擎，严格输出 JSON 对象。",
                user_prompt=user_prompt,
                novel_uid=self.novel_uid,
                task_type="memory_extract",
                chapter_id=chapter_id,
            )
            return res.content

        # Attempt 1: normal call + per-item tolerant parse.
        parse_result: ExtractionParseResult | None = None
        last_error = ""
        try:
            raw = await _call(base_prompt)
            parse_result = parse_extraction_items(raw, content)
        except Exception as exc:  # outer-JSON failure or network error
            last_error = str(exc)
            logger.warning("memory extract attempt 1 failed (chapter_id=%s): %s", chapter_id, last_error)

        # Attempt 2 (only when the whole batch was unusable): feed the error back.
        if parse_result is None or parse_result.kept == 0:
            retry_hint = (
                "\n\n上一次输出无法解析或没有任何合法条目。"
                f"错误信息：{last_error or '所有条目字段不符合要求或引文不在正文中'}。"
                "请严格按上面的字段名与 JSON 结构重新输出，不要加解释文字。"
            )
            try:
                raw2 = await _call(base_prompt + retry_hint)
                retry_result = parse_extraction_items(raw2, content)
                if parse_result is None or retry_result.kept >= parse_result.kept:
                    parse_result = retry_result
            except Exception as exc:
                last_error = str(exc)
                logger.warning("memory extract retry failed (chapter_id=%s): %s", chapter_id, last_error)

        if parse_result is not None and parse_result.kept > 0:
            if parse_result.drop_log:
                logger.info(
                    "memory extract chapter_id=%s kept=%d dropped_invalid=%d dropped_quote=%d; %s",
                    chapter_id, parse_result.kept, parse_result.dropped_invalid,
                    parse_result.dropped_quote, "; ".join(parse_result.drop_log[:10]),
                )
            return parse_result.output, parse_result.status

        # Batch still unusable: non-auto-confirmable fallback fact.
        logger.warning(
            "memory extract fully failed (chapter_id=%s); using fallback fact. last_error=%s",
            chapter_id, last_error,
        )
        return self._fallback_extraction(title, content, char_names), "failed"

    def _fallback_extraction(
        self, title: str, content: str, char_names: list[str]
    ) -> LlmMemoryExtractionOutput:
        """A single placeholder fact so the chapter isn't left with nothing.

        Marked so the caller never auto-confirms it (handled via status='failed').
        The quote is a verbatim slice of the chapter so it survives quote checks.
        """
        first_para = content.split("\n")[0][:80]
        return LlmMemoryExtractionOutput(
            facts=[
                LlmExtractedFact(
                    content=f"《{title}》发生事件（自动抽取失败，待人工确认）：{first_para}",
                    fact_type="event",
                    character_names=char_names[:2],
                    location_names=[],
                    source_quote=first_para,
                )
            ]
        )

    def _persist_extracted_memories(
        self,
        chapter_id: int,
        extraction: LlmMemoryExtractionOutput,
        source_hash: str,
        force_pending: bool = False,
    ) -> tuple[int, int]:
        for table, column in (("facts", "chapter_id"), ("character_state_changes", "chapter_id"), ("cognitive_records", "chapter_id"), ("relationship_changes", "chapter_id"), ("foreshadowing", "planted_chapter_id"), ("constraint_checks", "chapter_id")):
            self.conn.execute(f"UPDATE {table} SET is_stale = 1 WHERE {column} = ? AND origin = 'extracted'", (chapter_id,))
        trust = self.settings_repo.get_trust_mode()
        chars = self.entity_repo.list_characters()
        name_to_id = {c.name: c.id for c in chars}
        default_cid = chars[0].id if chars else None
        auto_cnt, pend_cnt = 0, 0

        fact_st = (
            "pending"
            if force_pending
            else ("confirmed" if (trust.enabled and trust.auto_confirm_facts) else "pending")
        )
        for f in extraction.facts:
            eids = [name_to_id[n] for n in f.character_names if n in name_to_id]
            cur = self.conn.execute(
                "INSERT INTO facts (content, fact_type, entity_ids, chapter_id, source_quote, status, source_hash, origin, is_stale) VALUES (?, ?, ?, ?, ?, ?, ?, 'extracted', 0)",
                (f.content, f.fact_type or "event", json.dumps(eids), chapter_id, f.source_quote, fact_st, source_hash),
            )
            if fact_st == "confirmed":
                self.memory_repo.index_fact_fts(int(cur.lastrowid or 0), f.content)
                auto_cnt += 1
            else:
                pend_cnt += 1

        cs_st = "confirmed" if (trust.enabled and trust.auto_confirm_char_state) else "pending"
        for sc in extraction.state_changes:
            cid = name_to_id.get(sc.character_name, default_cid)
            if cid is not None:
                self.conn.execute(
                    "INSERT INTO character_state_changes (character_id, chapter_id, field, value, source_quote, confirm_status, source_hash, origin, is_stale) VALUES (?, ?, ?, ?, ?, ?, ?, 'extracted', 0)",
                    (cid, chapter_id, sc.field, sc.value, sc.source_quote, cs_st, source_hash),
                )
                auto_cnt += 1 if cs_st == "confirmed" else 0
                pend_cnt += 0 if cs_st == "confirmed" else 1

        cog_st = "confirmed" if (trust.enabled and trust.auto_confirm_cognitive) else "pending"
        for cog in extraction.cognitive_records:
            kids = [name_to_id[n] for n in cog.knower_names if n in name_to_id] or ([default_cid] if default_cid else [])
            self.conn.execute(
                "INSERT INTO cognitive_records (secret, knower_ids, chapter_id, learned_by, source_quote, confirm_status, source_hash, origin, is_stale) VALUES (?, ?, ?, ?, ?, ?, ?, 'extracted', 0)",
                (cog.secret, json.dumps(kids), chapter_id, cog.learned_by, cog.source_quote, cog_st, source_hash),
            )
            auto_cnt += 1 if cog_st == "confirmed" else 0
            pend_cnt += 0 if cog_st == "confirmed" else 1

        rel_st = "confirmed" if (trust.enabled and trust.auto_confirm_relationship) else "pending"
        for rel in extraction.relationship_changes:
            ca, cb = name_to_id.get(rel.char_a_name), name_to_id.get(rel.char_b_name)
            if ca and cb and ca != cb:
                self.conn.execute(
                    "INSERT INTO relationship_changes (char_a_id, char_b_id, chapter_id, rel_type, intimacy, publicity, change_reason, source_quote, confirm_status, source_hash, origin, is_stale) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'extracted', 0)",
                    (ca, cb, chapter_id, rel.rel_type, rel.intimacy, rel.publicity, rel.change_reason, rel.source_quote, rel_st, source_hash),
                )
                auto_cnt += 1 if rel_st == "confirmed" else 0
                pend_cnt += 0 if rel_st == "confirmed" else 1

        for fs in extraction.foreshadowing:
            flag = trust.auto_confirm_foreshadow_hint if fs.status == "hinted" else trust.auto_confirm_foreshadow_plant_recover
            fs_st = "confirmed" if (trust.enabled and flag) else "pending"
            self.conn.execute(
                "INSERT INTO foreshadowing (description, planted_chapter_id, plan_recover_start, plan_recover_end, status, related_chapter_ids, source_quote, confirm_status, source_hash, origin, is_stale) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'extracted', 0)",
                (fs.description, chapter_id, fs.plan_recover_start, fs.plan_recover_end, fs.status, json.dumps([chapter_id]), fs.source_quote, fs_st, source_hash),
            )
            auto_cnt += 1 if fs_st == "confirmed" else 0
            pend_cnt += 0 if fs_st == "confirmed" else 1

        # Constraint violation/resolution verdicts always enter the pending queue:
        # they are judgments about the text, never auto-confirmed.
        for cc in extraction.constraint_checks:
            if cc.verdict not in ("violated", "resolved"):
                continue
            try:
                self.constraint_repo.create_constraint_check(
                    constraint_id=cc.constraint_id,
                    chapter_id=chapter_id,
                    verdict=cc.verdict,
                    evidence_quote=cc.evidence_quote,
                    description=cc.description or f"约束 #{cc.constraint_id} 判定为 {cc.verdict}",
                    source_hash=source_hash,
                )
                pend_cnt += 1
            except AppError:
                # Unknown constraint id (e.g. hallucinated by the model): skip silently.
                continue

        return auto_cnt, pend_cnt
