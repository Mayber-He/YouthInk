"""Chapter Finalization & Memory Loop Pipeline (Design Doc 5.4 & Dev Doc 4.3)."""

from __future__ import annotations

import asyncio
import json
import sqlite3

from app.core.exceptions import AppError
from app.db.repositories.constraint_repo import ConstraintRepository
from app.db.repositories.entity_repo import EntityRepository
from app.db.repositories.memory_repo import MemoryRepository
from app.db.repositories.outline_repo import OutlineRepository
from app.db.repositories.settings_repo import SettingsRepository
from app.db.repositories.writing_repo import WritingRepository
from app.db.vector_store import NovelVectorStore, VectorChunkRecord
from app.schemas.memory import FinalizeChapterResponse, LlmMemoryExtractionOutput
from app.services.backup_service import create_novel_backup
from app.services.embedding.encoder import encode_text_sync
from app.services.llm.client import complete_chat
from app.services.llm.json_parser import parse_and_validate_json


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
        content = latest_ver.content.strip() if latest_ver else ""
        if not content:
            raise AppError("EMPTY_CHAPTER_CONTENT", "章节正文为空，无法执行定稿入库。", 400)

        backup_info = create_novel_backup(self.novel_uid, reason=f"finalize_ch_{chapter_id}")
        chunks_count = await self._index_chapter_chunks_and_fts(
            chapter_id=chapter_id,
            chapter_sort_order=ch.sort_order,
            story_time=ch.story_time or "",
            version_id=latest_ver.id if latest_ver else chapter_id,
            content=content,
        )
        self.conn.commit()

        summary_text = await self._generate_chapter_summary(chapter_id, ch.title, content)
        self.memory_repo.upsert_summary("chapter", chapter_id, summary_text, is_stale=False)
        self._rollup_arc_summary(ch.arc_id)
        self.conn.commit()

        extraction = await self._extract_chapter_memories(chapter_id, ch.title, content)
        auto_confirmed, pending_cnt = self._persist_extracted_memories(chapter_id, extraction)

        self.conn.execute(
            "UPDATE chapters SET status = 'final', updated_at = datetime('now') WHERE id = ?",
            (chapter_id,),
        )
        return FinalizeChapterResponse(
            chapter_id=chapter_id,
            status="final",
            backup_filename=backup_info.filename,
            chunks_indexed=chunks_count,
            chapter_summary=summary_text,
            auto_confirmed_count=auto_confirmed,
            pending_count=pending_cnt,
        )

    def _current_embedding_model_id(self) -> str:
        cfg = self.settings_repo.get_setting("embedding", {})
        return str(cfg.get("model_id", "bge-m3-onnx-int8")) if isinstance(cfg, dict) else "bge-m3-onnx-int8"

    async def rebuild_all_indexes(self) -> dict[str, int]:
        """Clear and rebuild all vector chunks and FTS5 indexes for finalized chapters."""
        self.vector_store.clear_all_vectors()
        emb_model = self._current_embedding_model_id()
        rows = self.conn.execute(
            "SELECT id, sort_order, story_time FROM chapters WHERE status = 'final' ORDER BY sort_order ASC"
        ).fetchall()
        total_chunks = 0
        for r in rows:
            cid = int(r["id"])
            versions = self.writing_repo.list_versions(cid)
            ver = versions[0] if versions else None
            if ver and ver.content.strip():
                total_chunks += await self._index_chapter_chunks_and_fts(
                    cid, float(r["sort_order"]), str(r["story_time"] or ""), ver.id, ver.content, emb_model
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
    ) -> int:
        emb_model = model_id or self._current_embedding_model_id()
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

    def _rollup_arc_summary(self, arc_id: int) -> None:
        rows = self.conn.execute(
            """
            SELECT s.content, c.title FROM summaries s
            JOIN chapters c ON s.level = 'chapter' AND s.ref_id = c.id
            WHERE c.arc_id = ? ORDER BY c.sort_order ASC
            """,
            (arc_id,),
        ).fetchall()
        if rows:
            merged = "；".join(f"《{r['title']}》：{r['content'][:100]}" for r in rows)
            self.memory_repo.upsert_summary("arc", arc_id, merged[:800], is_stale=False)

    async def _extract_chapter_memories(
        self, chapter_id: int, title: str, content: str
    ) -> LlmMemoryExtractionOutput:
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
        constraint_section = (
            f"\n\n本章生效中的硬约束清单（必须逐条判定）：\n{constraint_lines}\n"
            "对每条约束给出判定：ok（本章遵守或无关，不输出）；"
            "violated（本章正文违反了该约束，必须附原文证据 evidence_quote）；"
            "resolved（本章剧情表明该约束已自然解除，如人物已熟悉校园，必须附证据）。"
            "只输出 violated / resolved 的条目。"
            if constraint_lines
            else ""
        )
        prompt = (
            f"请从章节《{title}》正文中抽取结构化设定变更与记忆条目（每项必须含原文引用 source_quote）。\n"
            f"已知角色：{', '.join(char_names) or '无'}\n"
            "输出 JSON (facts, state_changes, cognitive_records, relationship_changes, foreshadowing, constraint_checks)，"
            "其中 constraint_checks 数组每项为 "
            '{"constraint_id": 约束编号, "verdict": "violated|resolved", '
            '"evidence_quote": "原文证据", "description": "判定说明"}。\n'
            f"{constraint_section}\n\n"
            f"章节正文：\n{content[:5000]}"
        )
        try:
            _pid, base_url, model, api_key = self.settings_repo.get_credentials_for_task("extract")
            res = await complete_chat(
                base_url=base_url,
                api_key=api_key,
                model=model,
                system_prompt="你是小说记忆抽取引擎，严格输出 JSON 对象。",
                user_prompt=prompt,
                novel_uid=self.novel_uid,
                task_type="memory_extract",
                chapter_id=chapter_id,
            )
            return await parse_and_validate_json(res.content, LlmMemoryExtractionOutput)
        except Exception:
            first_para = content.split("\n")[0][:80]
            return LlmMemoryExtractionOutput(
                facts=[
                    {  # type: ignore[list-item]
                        "content": f"《{title}》发生事件：{first_para}",
                        "fact_type": "event",
                        "character_names": char_names[:2],
                        "location_names": [],
                        "source_quote": first_para,
                    }
                ]
            )

    def _persist_extracted_memories(
        self, chapter_id: int, extraction: LlmMemoryExtractionOutput
    ) -> tuple[int, int]:
        trust = self.settings_repo.get_trust_mode()
        chars = self.entity_repo.list_characters()
        name_to_id = {c.name: c.id for c in chars}
        default_cid = chars[0].id if chars else None
        auto_cnt, pend_cnt = 0, 0

        fact_st = "confirmed" if (trust.enabled and trust.auto_confirm_facts) else "pending"
        for f in extraction.facts:
            eids = [name_to_id[n] for n in f.character_names if n in name_to_id]
            cur = self.conn.execute(
                "INSERT INTO facts (content, fact_type, entity_ids, chapter_id, source_quote, status) VALUES (?, ?, ?, ?, ?, ?)",
                (f.content, f.fact_type or "event", json.dumps(eids), chapter_id, f.source_quote, fact_st),
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
                    "INSERT INTO character_state_changes (character_id, chapter_id, field, value, source_quote, confirm_status) VALUES (?, ?, ?, ?, ?, ?)",
                    (cid, chapter_id, sc.field, sc.value, sc.source_quote, cs_st),
                )
                auto_cnt += 1 if cs_st == "confirmed" else 0
                pend_cnt += 0 if cs_st == "confirmed" else 1

        cog_st = "confirmed" if (trust.enabled and trust.auto_confirm_cognitive) else "pending"
        for cog in extraction.cognitive_records:
            kids = [name_to_id[n] for n in cog.knower_names if n in name_to_id] or ([default_cid] if default_cid else [])
            self.conn.execute(
                "INSERT INTO cognitive_records (secret, knower_ids, chapter_id, learned_by, source_quote, confirm_status) VALUES (?, ?, ?, ?, ?, ?)",
                (cog.secret, json.dumps(kids), chapter_id, cog.learned_by, cog.source_quote, cog_st),
            )
            auto_cnt += 1 if cog_st == "confirmed" else 0
            pend_cnt += 0 if cog_st == "confirmed" else 1

        rel_st = "confirmed" if (trust.enabled and trust.auto_confirm_relationship) else "pending"
        for rel in extraction.relationship_changes:
            ca, cb = name_to_id.get(rel.char_a_name), name_to_id.get(rel.char_b_name)
            if ca and cb and ca != cb:
                self.conn.execute(
                    "INSERT INTO relationship_changes (char_a_id, char_b_id, chapter_id, rel_type, intimacy, publicity, change_reason, source_quote, confirm_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (ca, cb, chapter_id, rel.rel_type, rel.intimacy, rel.publicity, rel.change_reason, rel.source_quote, rel_st),
                )
                auto_cnt += 1 if rel_st == "confirmed" else 0
                pend_cnt += 0 if rel_st == "confirmed" else 1

        for fs in extraction.foreshadowing:
            flag = trust.auto_confirm_foreshadow_hint if fs.status == "hinted" else trust.auto_confirm_foreshadow_plant_recover
            fs_st = "confirmed" if (trust.enabled and flag) else "pending"
            self.conn.execute(
                "INSERT INTO foreshadowing (description, planted_chapter_id, plan_recover_start, plan_recover_end, status, related_chapter_ids, source_quote, confirm_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (fs.description, chapter_id, fs.plan_recover_start, fs.plan_recover_end, fs.status, json.dumps([chapter_id]), fs.source_quote, fs_st),
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
                )
                pend_cnt += 1
            except AppError:
                # Unknown constraint id (e.g. hallucinated by the model): skip silently.
                continue

        return auto_cnt, pend_cnt
