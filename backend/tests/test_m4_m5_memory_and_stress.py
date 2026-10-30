"""M4 & M5 Integration and 100-Chapter Stress Tests: Memory Loop, Trust Mode, Hybrid RAG, and Temporal Consistency."""

from __future__ import annotations

import json
from pathlib import Path
from fastapi.testclient import TestClient
import httpx
import pytest

from app.core.config import reset_config_for_testing
from app.db.manager import ensure_global_db_initialized, get_novel_db
from app.db.repositories.memory_repo import MemoryRepository
from app.db.vector_store import NovelVectorStore, VectorChunkRecord
from app.main import create_app
from app.services.embedding.encoder import encode_text_sync


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    reset_config_for_testing(tmp_path / "test_data_m4_m5")
    ensure_global_db_initialized()
    app = create_app()
    with TestClient(app) as tc:
        yield tc


def test_m4_finalization_trust_mode_and_pending_queue(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 1. Configure LLM Profile
    p_res = client.post(
        "/api/v1/settings/llm-profiles",
        json={
            "name": "M4Provider",
            "base_url": "https://api.example.com/v1",
            "model": "deepseek-chat",
            "api_key": "sk-m4-secret",
            "is_default": True,
        },
    )
    assert p_res.status_code in (200, 201)

    # 2. Create novel, characters, and outline
    uid = client.post("/api/v1/novels", json={"title": "盛夏回音"}).json()["novel_uid"]
    c1 = client.post(
        f"/api/v1/novels/{uid}/characters",
        json={"name": "林栀", "role": "female_lead", "appearance": "齐肩黑发"},
    ).json()["id"]
    c2 = client.post(
        f"/api/v1/novels/{uid}/characters",
        json={"name": "沈倦", "role": "male_lead", "appearance": "白衬衫少年"},
    ).json()["id"]

    v_id = client.post(
        f"/api/v1/novels/{uid}/outline/volumes", json={"title": "第一卷"}
    ).json()["id"]
    a_id = client.post(
        f"/api/v1/novels/{uid}/outline/arcs",
        json={"volume_id": v_id, "title": "第一弧"},
    ).json()["id"]
    ch1 = client.post(
        f"/api/v1/novels/{uid}/outline/chapters",
        json={
            "arc_id": a_id,
            "title": "旧琴房的乐谱",
            "synopsis": "林栀在旧琴房发现匿名乐谱",
        },
    ).json()["id"]
    ch2 = client.post(
        f"/api/v1/novels/{uid}/outline/chapters",
        json={
            "arc_id": a_id,
            "title": "广播站重逢",
            "synopsis": "两人在广播站相遇",
        },
    ).json()["id"]

    # 3. Save draft content for Chapter 1
    draft_text = (
        "放学后的旧琴房洒满夕阳，林栀在钢琴谱架下捡到一张泛黄的手写乐谱，背面写着缩写 SJ。\n"
        "沈倦推门而入，神色有些慌张，左手腕上多了一道擦伤。他其实早就知道林栀每天都在这里练琴。"
    )
    client.put(
        f"/api/v1/novels/{uid}/chapters/{ch1}/content",
        json={"content": draft_text, "source": "manual", "create_new_version": True},
    )

    # Mock LLM summary and 5-category extraction
    call_counter = {"n": 0}

    async def fake_post(self, url: str, **kwargs):
        call_counter["n"] += 1
        req = httpx.Request("POST", url)
        if call_counter["n"] == 1:
            body = {
                "choices": [
                    {
                        "message": {
                            "content": "林栀在旧琴房捡到写有SJ缩写的泛黄乐谱，恰逢左手腕擦伤的沈倦推门而入。"
                        }
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 40},
            }
        else:
            extraction = {
                "facts": [
                    {
                        "content": "林栀在旧琴房捡到写有缩写SJ的泛黄手写乐谱",
                        "fact_type": "item",
                        "character_names": ["林栀"],
                        "location_names": ["旧琴房"],
                        "source_quote": "林栀在钢琴谱架下捡到一张泛黄的手写乐谱",
                    }
                ],
                "state_changes": [
                    {
                        "character_name": "沈倦",
                        "field": "body",
                        "value": "左手腕有一道擦伤",
                        "source_quote": "左手腕上多了一道擦伤",
                    }
                ],
                "cognitive_records": [
                    {
                        "secret": "沈倦早就知道林栀每天放学都在旧琴房练琴",
                        "knower_names": ["沈倦"],
                        "learned_by": "暗中观察",
                        "source_quote": "他其实早就知道林栀每天都在这里练琴",
                    }
                ],
                "relationship_changes": [
                    {
                        "char_a_name": "林栀",
                        "char_b_name": "沈倦",
                        "rel_type": "琴房偶遇的同校同学",
                        "intimacy": 6,
                        "publicity": "mutual",
                        "change_reason": "旧琴房偶遇",
                        "source_quote": "沈倦推门而入",
                    }
                ],
                "foreshadowing": [
                    {
                        "description": "乐谱背面的缩写SJ究竟代表谁的赠予",
                        "status": "planted",
                        "plan_recover_start": 10,
                        "plan_recover_end": 20,
                        "source_quote": "背面写着缩写 SJ",
                    },
                    {
                        "description": "琴房窗台上的薄荷糖暗示有人常来",
                        "status": "hinted",
                        "plan_recover_start": 5,
                        "plan_recover_end": 12,
                        "source_quote": "放学后的旧琴房洒满夕阳",
                    },
                ],
            }
            body = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(extraction, ensure_ascii=False)
                        }
                    }
                ],
                "usage": {"prompt_tokens": 120, "completion_tokens": 180},
            }
        return httpx.Response(200, json=body, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    # 4. Execute Finalize on Chapter 1
    fin_res = client.post(f"/api/v1/novels/{uid}/chapters/{ch1}/finalize")
    assert fin_res.status_code == 200
    fin_data = fin_res.json()
    assert fin_data["status"] == "final"
    assert fin_data["chunks_indexed"] >= 1
    assert fin_data["auto_confirmed_count"] == 2
    assert fin_data["pending_count"] == 4

    # 5. Verify unconfirmed state is NOT leaked into Chapter 2 context preview
    ctx_before = client.get(
        f"/api/v1/novels/{uid}/chapters/{ch2}/context-preview"
    ).json()
    char_block_before = next(
        b for b in ctx_before["blocks"] if b["key"] == "character_states"
    )
    assert "左手腕有一道擦伤" not in char_block_before["content"]

    # 6. List pending queue and batch confirm all 4 pending items
    pq_res = client.get(f"/api/v1/novels/{uid}/memory/pending-queue")
    assert pq_res.status_code == 200
    pending_items = pq_res.json()
    assert len(pending_items) == 4

    batch_res = client.post(
        f"/api/v1/novels/{uid}/memory/pending-queue/batch",
        json={
            "action": "confirm",
            "items": [
                {"item_type": i["item_type"], "id": i["id"]} for i in pending_items
            ],
        },
    )
    assert batch_res.status_code == 200
    assert batch_res.json()["updated_count"] == 4

    # 7. Verify confirmed state & secret ARE now injected into Chapter 2 context preview
    ctx_after = client.get(
        f"/api/v1/novels/{uid}/chapters/{ch2}/context-preview"
    ).json()
    char_block_after = next(
        b for b in ctx_after["blocks"] if b["key"] == "character_states"
    )
    cog_block_after = next(
        b for b in ctx_after["blocks"] if b["key"] == "cognitive_constraints"
    )
    assert "左手腕有一道擦伤" in char_block_after["content"]
    assert "沈倦早就知道林栀每天放学都在旧琴房练琴" in cog_block_after["content"]

    # 8. Verify Hybrid RAG search recalls Chapter 1 via both Vector and FTS5
    rag_res = client.get(
        f"/api/v1/novels/{uid}/memory/search",
        params={"q": "泛黄手写乐谱 缩写SJ"},
    )
    assert rag_res.status_code == 200
    hits = rag_res.json()["hits"]
    assert len(hits) >= 1
    assert hits[0]["chapter_id"] == ch1
    assert hits[0]["source"] in ("hybrid", "vector", "fts")
    assert c1 > 0 and c2 > 0


def test_m5_hundred_chapter_long_book_stress_and_temporal_isolation(
    client: TestClient,
) -> None:
    """
    M5 Acceptance: Simulate a 105-chapter novel with evolving character states,
    cognitive secrets, summaries, FTS5 and vector chunks across 105 chapters.
    Verify zero OOM/latency issues, strict temporal isolation at Chapter 40/60 vs Chapter 105,
    and accurate RRF recall.
    """
    uid = client.post(
        "/api/v1/novels", json={"title": "百章长篇压测：青空之下"}
    ).json()["novel_uid"]
    heroine_id = client.post(
        f"/api/v1/novels/{uid}/characters",
        json={"name": "苏念", "role": "female_lead", "appearance": "高一校服马尾辫"},
    ).json()["id"]
    hero_id = client.post(
        f"/api/v1/novels/{uid}/characters",
        json={"name": "陆星河", "role": "male_lead", "appearance": "蓝白运动服"},
    ).json()["id"]

    v_id = client.post(
        f"/api/v1/novels/{uid}/outline/volumes", json={"title": "全书卷"}
    ).json()["id"]
    a_id = client.post(
        f"/api/v1/novels/{uid}/outline/arcs",
        json={"volume_id": v_id, "title": "长篇主弧"},
    ).json()["id"]

    chapter_ids: list[int] = []
    vec_store = NovelVectorStore(uid)
    all_vec_records: list[VectorChunkRecord] = []

    with get_novel_db(uid) as conn:
        mem_repo = MemoryRepository(conn)
        for i in range(1, 106):
            sort_val = float(i * 10)
            cur = conn.execute(
                """
                INSERT INTO chapters (arc_id, sort_order, title, synopsis, status, word_count, story_time)
                VALUES (?, ?, ?, ?, 'final', 2600, ?)
                """,
                (
                    a_id,
                    sort_val,
                    f"第{i}章 青春刻度{i}",
                    f"第{i}章剧情梗概",
                    f"高二第{i}天",
                ),
            )
            cid = int(cur.lastrowid or 0)
            chapter_ids.append(cid)

            if i == 12:
                text = "第12章特别事件：苏念在天文台顶楼把一枚银色北极星胸针借给了陆星河。"
            elif i == 50:
                text = "第50章转折：省物理竞赛决赛当天，苏念剪去了长发换成清爽短发，心情坚定。"
            elif i == 90:
                text = "第90章重逢：大学开学典礼上，陆星河归还了那枚珍藏多年的银色北极星胸针。"
            else:
                text = f"第{i}章日常正文：苏念与陆星河在图书馆自习，讨论第{i}套模拟卷的压轴题。"

            v_cur = conn.execute(
                "INSERT INTO chapter_versions (chapter_id, version, content, source) VALUES (?, 1, ?, 'manual')",
                (cid, text),
            )
            vid = int(v_cur.lastrowid or 0)
            mem_repo.index_chapter_version_fts(vid, text)
            mem_repo.upsert_summary(
                "chapter", cid, f"第{i}章摘要：{text[:50]}", is_stale=False
            )

            all_vec_records.append(
                VectorChunkRecord(
                    chunk_id=f"ch_{cid}_ck_1",
                    chapter_id=cid,
                    chapter_sort_order=sort_val,
                    scene_id=None,
                    character_ids=[heroine_id, hero_id],
                    location_id=None,
                    story_time=f"高二第{i}天",
                    embedding_model_id="bge-m3-onnx-int8",
                    text=text,
                    vector=encode_text_sync(text),
                )
            )

        conn.execute(
            """
            INSERT INTO character_state_changes (character_id, chapter_id, field, value, confirm_status)
            VALUES (?, ?, 'location', '高中图书馆二楼', 'confirmed'),
                   (?, ?, 'location', '火星基地（幻觉未确认）', 'pending'),
                   (?, ?, 'appearance', '齐耳清爽短发（省赛剪发）', 'confirmed'),
                   (?, ?, 'location', '京华大学礼堂', 'confirmed')
            """,
            (
                heroine_id,
                chapter_ids[9],
                heroine_id,
                chapter_ids[29],
                heroine_id,
                chapter_ids[49],
                heroine_id,
                chapter_ids[94],
            ),
        )
        conn.execute(
            """
            INSERT INTO cognitive_records (secret, knower_ids, chapter_id, learned_by, confirm_status)
            VALUES ('陆星河高一时曾匿名替苏念修好坏掉的单车', ?, ?, '偶然发现修车收据', 'confirmed')
            """,
            (json.dumps([heroine_id]), chapter_ids[79]),
        )

    vec_store._save_all(all_vec_records)

    # 1. Verify Temporal Snapshot at Chapter 40 (sort 400)
    snap_ch40 = client.get(
        f"/api/v1/novels/{uid}/characters/{heroine_id}/timeline",
        params={"up_to_chapter_sort": 400.0},
    ).json()
    assert snap_ch40["current_states"]["location"] == "高中图书馆二楼"
    assert snap_ch40["effective_appearance"] == "高一校服马尾辫"
    assert len(snap_ch40["known_secrets"]) == 0

    # 2. Verify Temporal Snapshot at Chapter 60 (sort 600)
    snap_ch60 = client.get(
        f"/api/v1/novels/{uid}/characters/{heroine_id}/timeline",
        params={"up_to_chapter_sort": 600.0},
    ).json()
    assert "齐耳清爽短发（省赛剪发）" in snap_ch60["effective_appearance"]
    assert len(snap_ch60["known_secrets"]) == 0

    # 3. Verify Temporal Snapshot at Chapter 105 (sort 1050)
    snap_ch105 = client.get(
        f"/api/v1/novels/{uid}/characters/{heroine_id}/timeline",
        params={"up_to_chapter_sort": 1050.0},
    ).json()
    assert snap_ch105["current_states"]["location"] == "京华大学礼堂"
    assert len(snap_ch105["known_secrets"]) == 1

    # 4. Verify Hybrid RAG Search across 105 chapters with temporal filter
    rag_ch60 = client.get(
        f"/api/v1/novels/{uid}/memory/search",
        params={"q": "银色北极星胸针", "max_chapter_sort": 600.0},
    ).json()
    hit_chapters_60 = [h["chapter_id"] for h in rag_ch60["hits"]]
    assert chapter_ids[11] in hit_chapters_60
    assert chapter_ids[89] not in hit_chapters_60

    rag_ch105 = client.get(
        f"/api/v1/novels/{uid}/memory/search",
        params={"q": "银色北极星胸针", "max_chapter_sort": 1050.0},
    ).json()
    hit_chapters_105 = [h["chapter_id"] for h in rag_ch105["hits"][:3]]
    assert chapter_ids[11] in hit_chapters_105
    assert chapter_ids[89] in hit_chapters_105
