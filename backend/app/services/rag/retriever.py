"""Hybrid RAG Retriever: Metadata filter + Vector similarity + jieba FTS5 + RRF fusion."""

from __future__ import annotations

import asyncio
import sqlite3

from app.db.repositories.memory_repo import MemoryRepository
from app.db.repositories.settings_repo import SettingsRepository
from app.db.vector_store import NovelVectorStore
from app.schemas.memory import RagChunkHit, RagSearchResponse
from app.services.embedding.encoder import (
    EMBEDDING_DIM,
    EMBEDDING_MODEL_ID,
    EMBEDDING_VERSION,
    EmbeddingModelUnavailable,
    encode_text_sync,
    get_embedding_runtime_status,
)

RRF_K = 60


class HybridRagRetriever:
    """Executes metadata-filtered Vector + FTS5 hybrid search with RRF fusion."""

    def __init__(
        self,
        novel_uid: str,
        novel_conn: sqlite3.Connection,
        global_conn: sqlite3.Connection,
    ) -> None:
        self.novel_uid = novel_uid
        self.memory_repo = MemoryRepository(novel_conn)
        self.settings_repo = SettingsRepository(global_conn)
        self.vector_store = NovelVectorStore(novel_uid)

    async def search(
        self,
        query: str,
        max_chapter_sort: float | None = None,
        character_ids: list[int] | None = None,
        location_id: int | None = None,
        top_k: int = 5,
    ) -> RagSearchResponse:
        if not query or not query.strip():
            return RagSearchResponse(query=query, hits=[])

        runtime = get_embedding_runtime_status()
        mismatch = self.vector_store.has_incompatible(
            EMBEDDING_DIM, EMBEDDING_VERSION, EMBEDDING_MODEL_ID
        )
        embedding_error: str | None = None
        vec_hits: list[tuple[object, float]] = []

        # 1. Encode query vector in threadpool to avoid blocking event loop.
        # A failure is reported, never replaced by the legacy hash vector space.
        try:
            query_vec = await asyncio.to_thread(encode_text_sync, query)
            # 2. Vector recall with metadata filtering
            vec_hits = self.vector_store.search_vectors(
                query_vec=query_vec,
                max_chapter_sort=max_chapter_sort,
                character_ids=character_ids,
                location_id=location_id,
                top_k=top_k * 2,
                expected_dim=EMBEDDING_DIM,
                expected_version=EMBEDDING_VERSION,
                expected_model_id=EMBEDDING_MODEL_ID,
            )
        except EmbeddingModelUnavailable as exc:
            embedding_error = str(exc)

        # 3. FTS5 keyword recall with jieba pre-tokenization
        fts_rows = self.memory_repo.search_chapters_fts(
            query=query,
            max_chapter_sort=max_chapter_sort,
            top_k=top_k * 2,
        )

        # 4. Reciprocal Rank Fusion (RRF: 1 / (60 + rank))
        fused: dict[str, RagChunkHit] = {}
        chapter_best_chunk: dict[int, str] = {}

        for rank_idx, (rec, _sim) in enumerate(vec_hits, start=1):
            rrf = 1.0 / (RRF_K + rank_idx)
            fused[rec.chunk_id] = RagChunkHit(
                chunk_id=rec.chunk_id,
                chapter_id=rec.chapter_id,
                chapter_sort_order=rec.chapter_sort_order,
                scene_id=rec.scene_id,
                text=rec.text,
                rrf_score=round(rrf, 6),
                source="vector",
            )
            if rec.chapter_id not in chapter_best_chunk:
                chapter_best_chunk[rec.chapter_id] = rec.chunk_id

        for rank_idx, row in enumerate(fts_rows, start=1):
            rrf = 1.0 / (RRF_K + rank_idx)
            ch_id = int(row["chapter_id"])
            ch_sort = float(row["sort_order"])
            content = str(row["content"])

            if ch_id in chapter_best_chunk:
                cid = chapter_best_chunk[ch_id]
                existing = fused[cid]
                existing.rrf_score = round(existing.rrf_score + rrf, 6)
                existing.source = "hybrid"
            else:
                cid = f"fts_ch_{ch_id}"
                snippet = content[:650]
                fused[cid] = RagChunkHit(
                    chunk_id=cid,
                    chapter_id=ch_id,
                    chapter_sort_order=ch_sort,
                    scene_id=None,
                    text=snippet,
                    rrf_score=round(rrf, 6),
                    source="fts",
                )
                chapter_best_chunk[ch_id] = cid

        sorted_hits = sorted(
            fused.values(), key=lambda h: h.rrf_score, reverse=True
        )[:top_k]

        return RagSearchResponse(
            query=query,
            embedding_model_mismatch=mismatch,
            embedding_model_id=runtime.model_id,
            embedding_dimension=runtime.dimension,
            embedding_error=embedding_error,
            hits=sorted_hits,
        )
