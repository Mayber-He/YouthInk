"""Checklist-based Consistency Review (Phase 3): an independent reviewer pass over chapter text."""

from __future__ import annotations

import json
import logging
import sqlite3

from app.core.exceptions import AppError
from app.core.text_hash import text_sha256
from app.db.repositories.constraint_repo import ConstraintRepository
from app.db.repositories.entity_repo import EntityRepository
from app.db.repositories.memory_repo import MemoryRepository
from app.db.repositories.novel_repo import NovelRepository
from app.db.repositories.outline_repo import OutlineRepository
from app.db.repositories.settings_repo import SettingsRepository
from app.db.repositories.writing_repo import WritingRepository
from app.db.vector_store import NovelVectorStore, VectorChunkRecord
from app.schemas.consistency import (
    ApplyReviewRequest,
    ConsistencyIssue,
    ConsistencyReviewResponse,
    ConsistencyReviewSummary,
)
from app.services.llm.client import complete_chat
from app.schemas.writing import ChapterWorkspaceResponse
from app.services.llm.timeout_budget import (
    RetryBudget,
    call_with_budget,
    env_timeout_sec,
)
from app.services.memory.consistency_parse import (
    ConsistencyParseResult,
    parse_consistency_issues,
)
from app.services.prompt.author_style import author_style_prompt
from app.services.embedding.encoder import (
    EMBEDDING_DIM,
    EMBEDDING_MODEL_ID,
    EMBEDDING_VERSION,
    encode_text_sync,
)
from app.services.memory.finalizer import split_text_chunks

_HISTORY_TOP_K = 3
_HISTORY_QUERY_TOP_K = 5
_HISTORY_MAX_QUERY_CHUNKS = 12
_HISTORY_SNIPPET_CHARS = 420
_HISTORY_MIN_SIMILARITY = 0.18

logger = logging.getLogger(__name__)


class ConsistencyReviewService:
    """Runs an LLM reviewer against an explicit checklist; flags only, never auto-edits."""

    def __init__(
        self,
        novel_uid: str,
        novel_conn: sqlite3.Connection,
        settings_repo: SettingsRepository,
    ) -> None:
        self._novel_uid = novel_uid
        self._conn = novel_conn
        self._outline_repo = OutlineRepository(novel_conn)
        self._writing_repo = WritingRepository(novel_conn)
        self._entity_repo = EntityRepository(novel_conn)
        self._constraint_repo = ConstraintRepository(novel_conn)
        self._settings_repo = settings_repo

    async def run_review(self, chapter_id: int) -> ConsistencyReviewResponse:
        ch = self._outline_repo.get_chapter(chapter_id)
        versions = self._writing_repo.list_versions(chapter_id)
        latest = versions[0] if versions else None
        raw_content = latest.content if latest else ""
        content = raw_content.strip()
        if not content:
            raise AppError("EMPTY_CHAPTER_CONTENT", "章节正文为空，无法执行一致性审查。", 400)

        upstream_rows = self._conn.execute(
            "SELECT id, content_hash, continuity_review_required FROM chapters WHERE sort_order < ? ORDER BY sort_order, id",
            (ch.sort_order,),
        ).fetchall()
        upstream_hash = text_sha256("|".join(f"{r['id']}:{r['content_hash'] or ''}:{r['continuity_review_required']}" for r in upstream_rows))
        checklist = self._build_checklist(chapter_id, ch.sort_order)
        history_context = self._retrieve_historical_context(chapter_id, content)
        if history_context:
            checklist += "\n\n" + history_context
        prompt = self._build_prompt(ch, content, checklist)

        _pid, base_url, model, api_key = self._settings_repo.get_credentials_for_task("extract")
        budget = RetryBudget(env_timeout_sec("YOUTHINK_CONSISTENCY_TIMEOUT_SEC"))
        last_raw = ""
        last_exc: Exception | None = None

        async def _call_and_parse(
            extra: str, attempt_timeout: float
        ) -> ConsistencyParseResult:
            nonlocal last_raw
            res = await complete_chat(
                base_url=base_url,
                api_key=api_key,
                model=model,
                system_prompt="你是小说一致性与常理逻辑审查员，只输出严格 JSON，不做任何解释。",
                user_prompt=prompt + extra,
                novel_uid=self._novel_uid,
                task_type="consistency_review",
                chapter_id=chapter_id,
                timeout_sec=attempt_timeout,
            )
            last_raw = res.content
            return parse_consistency_issues(res.content)

        async def _attempt(extra: str = "") -> ConsistencyParseResult:
            return await call_with_budget(
                lambda attempt_timeout: _call_and_parse(extra, attempt_timeout),
                budget,
            )

        # Attempt 1: per-issue tolerant parsing; one bad issue never fails the review.
        result: ConsistencyParseResult | None = None
        try:
            result = await _attempt()
        except Exception as exc:  # outer JSON failure, timeout, upstream error
            last_exc = exc
            logger.warning(
                "consistency review attempt 1 failed (chapter_id=%s): %s", chapter_id, exc
            )

        # One retry when nothing usable came back; both attempts share ``budget``.
        if result is None or (result.raw_items > 0 and not result.issues):
            retry_hint = (
                "\n\n上一次输出无法解析或没有任何合法条目。"
                f"错误信息：{last_exc or '所有 issues 字段不符合要求'}。"
                "请严格按上面的字段名与 JSON 结构重新输出，不要加解释文字。"
            )
            try:
                retry_result = await _attempt(retry_hint)
                if result is None or len(retry_result.issues) >= len(result.issues):
                    result = retry_result
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "consistency review retry failed (chapter_id=%s): %s", chapter_id, exc
                )

        if result is None:
            if isinstance(last_exc, ValueError):
                raise AppError(
                    code="LLM_JSON_PARSE_FAILED",
                    message="模型返回格式解析失败，请重试或手动修改",
                    detail={"error": str(last_exc), "raw_output": last_raw},
                    status_code=422,
                )
            assert last_exc is not None
            raise last_exc

        if result.dropped_invalid:
            logger.warning(
                "consistency review dropped %d invalid issue(s) (chapter_id=%s): %s",
                result.dropped_invalid, chapter_id, "; ".join(result.drop_log[:10]),
            )

        content_hash = text_sha256(raw_content)
        issues = [i for i in result.issues if i.verdict in ("violation", "suspicious")]
        for issue in issues:
            if issue.check_type == "prose":
                issue.verdict = "suspicious"
        violation_count = sum(1 for i in issues if i.verdict == "violation")
        suspicious_count = len(issues) - violation_count
        if not issues:
            summary = "未发现问题：正文与检查表及常理逻辑一致"
        else:
            parts = []
            if violation_count:
                parts.append(f"{violation_count} 项违反")
            if suspicious_count:
                parts.append(f"{suspicious_count} 项可疑")
            summary = "发现" + "、".join(parts)

        cur = self._conn.execute(
            """
            INSERT INTO consistency_reviews (
                chapter_id, version_id, content_hash, upstream_hash, summary, issue_count, violation_count, issues_json, model
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chapter_id,
                latest.id if latest else None,
                content_hash,
                upstream_hash,
                summary,
                len(issues),
                violation_count,
                json.dumps([i.model_dump() for i in issues], ensure_ascii=False),
                model,
            ),
        )
        if not any(i.check_type != "prose" for i in issues) and not self.get_review(int(cur.lastrowid)).is_stale:
            prior_dirty = self._conn.execute(
                "SELECT 1 FROM chapters WHERE sort_order < ? AND continuity_review_required = 1 LIMIT 1",
                (ch.sort_order,),
            ).fetchone()
            current = self._conn.execute("SELECT continuity_review_required FROM chapters WHERE id = ?", (chapter_id,)).fetchone()
            if current and current[0] and not prior_dirty:
                self._conn.execute(
                    "UPDATE chapters SET continuity_review_required = 0, continuity_dirty_from_chapter_id = NULL WHERE id = ? AND content_hash = ?",
                    (chapter_id, content_hash),
                )
                self._refresh_arc_summary(chapter_id)
        self._conn.commit()
        return self.get_review(int(cur.lastrowid or 0))

    def _refresh_arc_summary(self, chapter_id: int) -> None:
        arc = self._conn.execute("SELECT arc_id FROM chapters WHERE id = ?", (chapter_id,)).fetchone()
        if arc is None:
            return
        arc_id = int(arc[0])
        pending = self._conn.execute(
            "SELECT 1 FROM chapters WHERE arc_id = ? AND continuity_review_required = 1 LIMIT 1",
            (arc_id,),
        ).fetchone()
        if pending:
            return
        rows = self._conn.execute(
            "SELECT s.content, c.title FROM summaries s JOIN chapters c ON c.id = s.ref_id "
            "WHERE s.level = 'chapter' AND c.arc_id = ? AND s.is_stale = 0 "
            "AND s.source_hash = c.content_hash AND c.status = 'final' ORDER BY c.sort_order",
            (arc_id,),
        ).fetchall()
        if rows:
            merged = "；".join(f"《{r['title']}》：{r['content'][:100]}" for r in rows)
            self._conn.execute(
                "UPDATE summaries SET is_stale = 0 WHERE level = 'arc' AND ref_id = ?",
                (arc_id,),
            )
            MemoryRepository(self._conn).upsert_summary(
                "arc", arc_id, merged[:800], is_stale=False
            )

    def get_review(self, review_id: int) -> ConsistencyReviewResponse:
        row = self._conn.execute(
            "SELECT * FROM consistency_reviews WHERE id = ?", (review_id,)
        ).fetchone()
        if row is None:
            raise AppError("REVIEW_NOT_FOUND", f"未找到审查记录 #{review_id}", status_code=404)
        return ConsistencyReviewResponse(
            id=int(row["id"]),
            chapter_id=int(row["chapter_id"]),
            version_id=row["version_id"],
            summary=str(row["summary"]),
            issue_count=int(row["issue_count"]),
            violation_count=int(row["violation_count"]),
            issues=[ConsistencyIssue(**d) for d in json.loads(row["issues_json"] or "[]")],
            model=str(row["model"] or ""),
            created_at=str(row["created_at"]),
            is_stale=self._review_is_stale(row),
        )

    def apply_revision(self, review_id: int, payload: ApplyReviewRequest) -> ChapterWorkspaceResponse:
        from app.services.review_revision import apply_review_revision
        # Acquire the write lock before checking freshness and modifying a version.
        self._conn.execute("BEGIN IMMEDIATE")
        return apply_review_revision(self.get_review(review_id), payload, self._writing_repo)

    def list_reviews(self, chapter_id: int) -> list[ConsistencyReviewSummary]:
        rows = self._conn.execute(
            "SELECT * FROM consistency_reviews WHERE chapter_id = ? ORDER BY id DESC",
            (chapter_id,),
        ).fetchall()
        return [
            ConsistencyReviewSummary(
                id=int(r["id"]),
                chapter_id=int(r["chapter_id"]),
                summary=str(r["summary"]),
                issue_count=int(r["issue_count"]),
                violation_count=int(r["violation_count"]),
                created_at=str(r["created_at"]),
                is_stale=self._review_is_stale(r),
            )
            for r in rows
        ]

    def _review_is_stale(self, review_row: sqlite3.Row) -> bool:
        chapter = self._conn.execute(
            "SELECT sort_order, content_hash FROM chapters WHERE id = ?",
            (int(review_row["chapter_id"]),),
        ).fetchone()
        if chapter is None or not review_row["content_hash"] or not review_row["upstream_hash"]:
            return True
        upstream_rows = self._conn.execute(
            "SELECT id, content_hash, continuity_review_required FROM chapters WHERE sort_order < ? ORDER BY sort_order, id",
            (float(chapter["sort_order"]),),
        ).fetchall()
        upstream_hash = text_sha256("|".join(f"{r['id']}:{r['content_hash'] or ''}:{r['continuity_review_required']}" for r in upstream_rows))
        return (
            str(review_row["content_hash"]) != str(chapter["content_hash"] or "")
            or str(review_row["upstream_hash"]) != upstream_hash
        )

    def _retrieve_historical_context(self, chapter_id: int, content: str) -> str:
        """Return a few fresh finalized vector matches; retrieval is best-effort only."""
        try:
            vector_store = NovelVectorStore(self._novel_uid)
            if not vector_store.store_file.exists():
                return ""

            ordered_rows = self._conn.execute(
                """
                SELECT c.id, c.title, c.story_time, c.content_hash,
                       c.status, c.continuity_review_required
                FROM chapters c
                JOIN arcs a ON a.id = c.arc_id
                JOIN volumes v ON v.id = a.volume_id
                ORDER BY v.sort_order, a.sort_order, c.sort_order, c.id
                """
            ).fetchall()
            allowed_hashes: dict[int, str] = {}
            chapter_info: dict[int, dict[str, object]] = {}
            for display_index, row in enumerate(ordered_rows, start=1):
                cid = int(row["id"])
                if (
                    cid == chapter_id
                    or row["status"] != "final"
                    or bool(row["continuity_review_required"])
                    or not row["content_hash"]
                ):
                    continue
                allowed_hashes[cid] = str(row["content_hash"])
                chapter_info[cid] = {
                    "display_index": display_index,
                    "title": str(row["title"] or "未命名章节"),
                    "story_time": str(row["story_time"] or ""),
                }
            if not allowed_hashes:
                return ""

            best_by_chunk: dict[str, tuple[VectorChunkRecord, float]] = {}
            query_chunks = split_text_chunks(content)
            if len(query_chunks) > _HISTORY_MAX_QUERY_CHUNKS:
                last_index = len(query_chunks) - 1
                query_chunks = [
                    query_chunks[round(i * last_index / (_HISTORY_MAX_QUERY_CHUNKS - 1))]
                    for i in range(_HISTORY_MAX_QUERY_CHUNKS)
                ]
            for query_text in query_chunks:
                query_vec = encode_text_sync(query_text)
                hits = vector_store.search_vectors(
                    query_vec=query_vec,
                    allowed_chapter_hashes=allowed_hashes,
                    top_k=_HISTORY_QUERY_TOP_K,
                    expected_dim=EMBEDDING_DIM,
                    expected_version=EMBEDDING_VERSION,
                    expected_model_id=EMBEDDING_MODEL_ID,
                )
                for record, score in hits:
                    if score < _HISTORY_MIN_SIMILARITY:
                        continue
                    previous = best_by_chunk.get(record.chunk_id)
                    if previous is None or score > previous[1]:
                        best_by_chunk[record.chunk_id] = (record, score)

            ranked = sorted(best_by_chunk.values(), key=lambda hit: hit[1], reverse=True)
            lines: list[str] = []
            for record, _score in ranked:
                info = chapter_info.get(int(record.chapter_id))
                if info is None:
                    continue
                time_label = f"；故事时间：{info['story_time']}" if info["story_time"] else ""
                snippet = record.text.strip()[:_HISTORY_SNIPPET_CHARS]
                if not snippet:
                    continue
                lines.append(
                    f"[历史片段{len(lines) + 1}｜第{info['display_index']}章《{info['title']}》{time_label}] "
                    f"{snippet}"
                )
                if len(lines) >= _HISTORY_TOP_K:
                    break
            if not lines:
                return ""
            return (
                "【检查表F：向量检索到的定稿章节参考片段】\n"
                + "\n".join(lines)
                + "\n注意：检索片段是少量、不完整的参考证据；未检索到不代表历史中没有发生。"
                "历史章节片段只提供作者层面的剧情参照；若片段来自待查章节之后，不能据此认定人物在待查时点已知晓后续信息。"
            )
        except Exception as exc:
            # Search is supplemental; a missing or unhealthy index must not block review,
            # but the reason is logged instead of silently pretending there were no hits.
            logger.warning("consistency vector search unavailable: %s", exc)
            return ""

    def _build_checklist(self, chapter_id: int, sort_order: float) -> str:
        ch = self._outline_repo.get_chapter(chapter_id)
        scenes = self._writing_repo.list_scenes(chapter_id)
        all_chars = self._entity_repo.list_characters()
        char_name_by_id = {c.id: c.name for c in all_chars}

        char_ids = sorted(
            {
                cid
                for s in scenes
                for cid in ([s.pov_character] if s.pov_character else []) + s.character_ids
            }
        )
        loc_ids = sorted({s.location_id for s in scenes if s.location_id})
        if not char_ids:
            char_ids = [
                c.id
                for c in all_chars
                if c.role in ("female_lead", "male_lead", "major")
            ]

        novel = NovelRepository(self._conn, self._novel_uid).get_novel_detail()
        sections: list[str] = [author_style_prompt(novel)]

        constraints = self._constraint_repo.list_active_for_chapter(
            chapter_id, sort_order, char_ids, loc_ids
        )
        if constraints:
            lines = [
                f"[#{c.id}]【{'硬约束' if c.severity == 'hard' else '软约束'}"
                f"·{c.target_type}{'「' + c.target_name + '」' if c.target_name else ''}】{c.content}"
                for c in constraints
            ]
            sections.append("【检查表A：硬约束/软约束】（违反=事故）\n" + "\n".join(lines))

        fact_rows = self._conn.execute(
            """
            SELECT f.id, f.content FROM facts f
            LEFT JOIN chapters c ON c.id = f.chapter_id
            WHERE f.status IN ('confirmed', 'locked')
              AND f.is_stale = 0
              AND (c.sort_order IS NULL OR c.sort_order <= ?)
              AND (c.id IS NULL OR (f.origin = 'manual' OR (f.source_hash = c.content_hash AND c.status = 'final' AND c.continuity_review_required = 0)))
            ORDER BY f.id DESC LIMIT 15
            """,
            (sort_order,),
        ).fetchall()
        if fact_rows:
            lines = [f"[#{r['id']}] {r['content']}" for r in fact_rows]
            sections.append("【检查表B：已确认事实】\n" + "\n".join(lines))

        char_lines: list[str] = []
        for cid in char_ids:
            try:
                c = self._entity_repo.get_character(cid)
            except AppError:
                continue
            snap = self._entity_repo.get_character_timeline_snapshot(cid, sort_order)
            states = "；".join(f"{k}:{v}" for k, v in snap.current_states.items())
            rels = (
                "；".join(
                    f"{r['char_a_name']}↔{r['char_b_name']}({r['rel_type']})"
                    for r in snap.relationships
                )
                or "未记录已确认关系，不代表初见；以人物背景和前文实际交往为准"
            )
            char_lines.append(
                f"[人物#{c.id}「{c.name}」] {c.role}；身份背景：{c.background or '未填'}"
                f"{'；当前状态：' + states if states else ''}；当前关系：{rels}"
            )
        if char_lines:
            sections.append("【检查表C：出场人物核心属性与时序状态】\n" + "\n".join(char_lines))

        scene_summary_lines = [
            f"本章梗概：{ch.synopsis or '无'}（故事时间：{ch.story_time or '未指定'}）"
        ]
        for idx, s in enumerate(scenes, start=1):
            pov_name = char_name_by_id.get(s.pov_character, "未指定") if s.pov_character else "未指定"
            present = [char_name_by_id[cid] for cid in s.character_ids if cid in char_name_by_id]
            scene_summary_lines.append(
                f"场景{idx}（POV：{pov_name}；在场：{'、'.join(present) or '未指定'}）：{s.beat}"
            )

        common_sense_lines = [
            *scene_summary_lines,
            "[#901]【环境与空间熟悉度常理】若角色属于初次到访（如新生刚报到、刚转学、首次踏足某场所），绝不能表现得对校园/建筑/路线熟门熟路、轻车熟路；空间移动需有合理过渡，不能瞬移。",
            "[#902]【人际关系与初见边界】初次见面或尚未熟稔的角色之间，绝不能无铺垫自来熟、绝不能未经自我介绍或他人提及便直呼对方姓名/绰号/知晓对方过往隐私。",
            "[#903]【限知视角与超知边界】按作品指定视角审查：限知叙述不得直接读取他人内心，全知叙述可以描写不同人物内心与场外事件；两者都不能让角色凭空获知未曾得知的秘密。不得把全知叙述误判为角色超知。",
            "[#904]【时间、季节与物理状态连续性】食物、道具称谓严禁前后自相矛盾或中途漂移（如前文挂面后文变泡面）；已完成的物理动作与状态（如食物吃完、物品放下）严禁在后文凭空逆转或重复进行（如吃完了又继续吃）；昼夜时间流速、季节气候与衣着不得违背常识。",
            "[#905]【在场状态与身份常识】未到场或已离场的角色绝不能凭空插话或参与互动；人物言行、消费与技能不得违背其年龄、学生身份或时代背景常识。",
            "[#906]【交流媒介与感官信息】文字消息只能证明其中的文字、措辞、标点和表情，不能作为声线、音色、语调或尾音的听觉依据；只有前文明确出现的语音、电话、视频或线下发声，才可作为声音记忆。若正文把文字消息直接写成角色曾听过的声音，或据此做音色/语调对照，判为明确逻辑问题；若虽有独立的线下声音来源，但写法把它与文字消息混在一起、容易让读者误以为收到过语音，判为可疑并建议明确来源。",
        ]
        sections.append("【检查表D：本章情境与六大常理逻辑自洽】\n" + "\n".join(common_sense_lines))

        prev_content = self._writing_repo.get_previous_chapter_text(
            sort_order, tail_chars=None
        )
        if prev_content:
            sections.append(
                "【检查表E：跨章连贯】\n"
                f"【完整上一章正文，用于核对已发生事件、动作与物品状态】\n{prev_content}\n"
                "[#951]【重复揭示】已实际获知信息的角色，不得再次把它当作新发现；叙述者或其他角色已知，不代表所有角色已知。带来新后果或新视角的回顾不算重复。\n"
                "[#952]【悬念承接】上一章结尾留下的悬念、承诺或人物情绪，本章须有承接或交代，不能凭空断档。\n"
                "[#953]【时间日期衔接】本章故事时间、日期与上一章及已交代的计划（如报到日、“下周”“明天”）须一致。\n"
                "[#954]【重复动作】上一章已完成的具体动作（如清洁、收拾、打包、放置物品）不得在本章再次描写一遍；"
                "应承接动作后的物品状态；不同日期合理再次发生的日常动作不属于事实矛盾，无叙事作用的重复可列为可疑的删冗建议。"
            )

        return "\n\n".join(sections)

    @staticmethod
    def _build_prompt(ch, content: str, checklist: str) -> str:
        return (
            "你是小说一致性与常理逻辑审查员。请逐项检查【待审正文】是否违反以下检查表（含A硬软约束、B已确认事实、C人物属性、D情境常理逻辑、E跨章连贯及F向量检索参考片段），"
            "只输出存在问题的项（遵守的项不要输出）。\n\n"
            f"{checklist}\n\n"
            f"待审正文（第 {ch.display_index} 章《{ch.title}》）：\n{content}\n\n"
            "输出严格 JSON：{\"issues\": [{\"check_type\": \"constraint|fact|character|common_sense|continuity\", "
            "\"ref_id\": 检查表编号或 null, \"ref_label\": \"如 硬约束#1、常理#901、连贯#951 或 历史片段1·第X章\", "
            "\"verdict\": \"violation|suspicious\", "
            "\"evidence_quote\": \"待审正文原句证据\", \"historical_evidence\": \"若依据F指出问题，填写对应历史片段原文；否则留空\", "
            "\"description\": \"违反说明（指出为何违背设定或常理）\", \"suggestion\": \"一句话修改思路\", \"suggested_rewrite\": \"修改后的正文片段（必须可无缝直接替换evidence_quote，保留叙事口吻并修正逻辑漏洞）\"}]}。\n"
            "判定标准：violation=明确违反检查表或违反情境常理（例如新生刚报到却对学校熟门熟路、初见未介绍却直呼姓名、上帝视角读心等）；suspicious=疑似但证据不足。"
            "若依据F报告冲突或剧情重复，check_type使用continuity，ref_id填null，ref_label必须写清历史片段编号和章节，historical_evidence必须引用检索结果中的原句，evidence_quote仍引用待审正文原句；检索内容不足以支撑明确结论时标为suspicious或不报告。"
            "另外检查正文内部楼层、称谓、物品位置和动作状态是否自相矛盾。"
            "可以最多提出3项有具体原句的删冗或语句不顺建议，check_type用prose、verdict只能为suspicious；"
            "只局部压缩无推进的微动作、重复心理或重复解释，不新增事件，不统一改成华丽文风，不把个人文学偏好判为事实错误。"
            "evidence_quote必须是待审正文中连续、完整的原文片段，不能拼接句子或使用省略号；suggested_rewrite必须只替换这个片段。"
            "不要输出任何解释文字。"
        )
