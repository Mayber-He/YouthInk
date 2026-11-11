"""Comprehensive tests for Character Memories (日常认知 / 临时安排 / 秘密认知).

Covers all acceptance criteria:
1. Preference isolation to knowers with text evidence & no premature usage in earlier chapters.
2. Temporary schedule ('今天早八') lifecycle: pending on the day -> completed via follow-up record -> historical experience only in later chapters -> rollback to pending when viewing earlier chapters.
3. Unconfirmed, disabled, and stale extracted memories excluded from generation context.
4. Multiple independent memories on the same character do not trigger false conflict flags; unknown knower names are skipped and reported (never bound to default character).
5. Manual memory CRUD (pre-story & chapter-specific, schedule time_scope validation, disable/restore) and chapter memory re-extraction (replaces extracted, preserves manual without duplicates, preserves old data on failure).
6. Consecutive chapters E2E verification ("早八安排 + 饮食偏好") for extraction, context assembly, and prose generation.
"""

from __future__ import annotations

import json
import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import reset_config_for_testing
from app.db.manager import ensure_global_db_initialized
from app.main import create_app


@pytest.fixture()
def client(tmp_path):
    reset_config_for_testing(tmp_path / "test_data_char_memories")
    ensure_global_db_initialized()
    app = create_app()
    with TestClient(app) as tc:
        yield tc


def _setup_novel(client: TestClient):
    client.post(
        "/api/v1/settings/llm-profiles",
        json={
            "name": "TestProvider",
            "base_url": "https://api.example.com/v1",
            "model": "deepseek-chat",
            "api_key": "sk-test-key",
            "is_default": True,
        },
    )
    uid = client.post(
        "/api/v1/novels", json={"title": "早八与甜食测试"}
    ).json()["novel_uid"]
    c_male = client.post(
        f"/api/v1/novels/{uid}/characters",
        json={"name": "江澈", "role": "male_lead"},
    ).json()["id"]
    c_female = client.post(
        f"/api/v1/novels/{uid}/characters",
        json={"name": "裴南栀", "role": "female_lead"},
    ).json()["id"]
    c_other = client.post(
        f"/api/v1/novels/{uid}/characters",
        json={"name": "陈默", "role": "major"},
    ).json()["id"]

    vol_id = client.post(
        f"/api/v1/novels/{uid}/outline/volumes", json={"title": "第一卷"}
    ).json()["id"]
    arc_id = client.post(
        f"/api/v1/novels/{uid}/outline/arcs",
        json={"volume_id": vol_id, "title": "第一弧"},
    ).json()["id"]

    ch1 = client.post(
        f"/api/v1/novels/{uid}/outline/chapters",
        json={
            "arc_id": arc_id,
            "title": "报到日",
            "synopsis": "江澈与裴南栀各自报到",
            "story_time": "九月一日，上午",
            "sort_order": 1.0,
        },
    ).json()["id"]
    ch2 = client.post(
        f"/api/v1/novels/{uid}/outline/chapters",
        json={
            "arc_id": arc_id,
            "title": "食堂偶遇与课表",
            "synopsis": "江澈和裴南栀在食堂聊起早餐喜好与次日早八课",
            "story_time": "九月一日，傍晚",
            "sort_order": 2.0,
        },
    ).json()["id"]
    ch3 = client.post(
        f"/api/v1/novels/{uid}/outline/chapters",
        json={
            "arc_id": arc_id,
            "title": "开学第二天早晨",
            "synopsis": "江澈买早餐并去上早八高数课，陈默也在场",
            "story_time": "九月二日，早晨",
            "sort_order": 3.0,
        },
    ).json()["id"]
    ch4 = client.post(
        f"/api/v1/novels/{uid}/outline/chapters",
        json={
            "arc_id": arc_id,
            "title": "下课后的午休",
            "synopsis": "江澈、裴南栀与陈默在食堂吃午饭",
            "story_time": "九月二日，中午",
            "sort_order": 4.0,
        },
    ).json()["id"]

    return {
        "uid": uid,
        "male_id": c_male,
        "female_id": c_female,
        "other_id": c_other,
        "ch1": ch1,
        "ch2": ch2,
        "ch3": ch3,
        "ch4": ch4,
    }


def _get_block(preview_json: dict, key: str) -> str:
    return next(b["content"] for b in preview_json["blocks"] if b["key"] == key)


def test_preference_isolation_and_temporal_boundary(
    client: TestClient, monkeypatch
) -> None:
    """女主表达饮食偏好后，只有有证据获知的人物获得对应记忆；此前章节不可提前使用，其他人物不会自动知道。"""
    ctx = _setup_novel(client)
    uid = ctx["uid"]

    ch2_text = (
        "傍晚食堂人不多，裴南栀指了指窗口说：“我早上一般只吃甜口的，最喜欢草莓奶黄包。”\n"
        "江澈点点头把这句话记在了心里。"
    )
    client.put(
        f"/api/v1/novels/{uid}/chapters/{ctx['ch2']}/content",
        json={"content": ch2_text, "source": "manual", "create_new_version": True},
    )

    extraction_payload = {
        "facts": [],
        "state_changes": [],
        "cognitive_records": [
            {
                "secret": "裴南栀早餐喜欢吃甜食，尤其是草莓奶黄包",
                "memory_type": "daily",
                "time_scope": "日常早餐",
                "schedule_status": "pending",
                "knower_names": ["江澈", "裴南栀"],
                "learned_by": "食堂亲耳听到裴南栀说起",
                "source_quote": "我早上一般只吃甜口的，最喜欢草莓奶黄包。",
            }
        ],
        "relationship_changes": [],
        "foreshadowing": [],
        "constraint_checks": [],
    }

    async def fake_post(self, url, **kwargs):
        req = httpx.Request("POST", url)
        body = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(extraction_payload, ensure_ascii=False)
                    }
                }
            ],
            "usage": {"prompt_tokens": 20, "completion_tokens": 40},
        }
        return httpx.Response(200, json=body, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    fin_res = client.post(f"/api/v1/novels/{uid}/chapters/{ctx['ch2']}/finalize")
    assert fin_res.status_code == 200

    # 默认待确认：未确认前不进入第 3 章生成上下文
    preview_before = client.get(
        f"/api/v1/novels/{uid}/chapters/{ctx['ch3']}/context-preview"
    ).json()
    assert "草莓奶黄包" not in _get_block(preview_before, "cognitive_constraints")

    # 确认该条日常认知
    queue = client.get(
        f"/api/v1/novels/{uid}/memory/pending-queue", params={"status": "pending"}
    ).json()
    cog_items = [i for i in queue if i["item_type"] == "cognitive"]
    assert len(cog_items) == 1
    assert cog_items[0]["raw_payload"]["memory_type"] == "daily"
    client.put(
        f"/api/v1/novels/{uid}/memory/pending-queue/cognitive/{cog_items[0]['id']}",
        json={"action": "confirm"},
    )

    # 1) 此前章节（第 1 章 sort_order=1.0 < 2.0）不可提前使用
    preview_ch1 = client.get(
        f"/api/v1/novels/{uid}/chapters/{ctx['ch1']}/context-preview"
    ).json()
    assert "草莓奶黄包" not in _get_block(preview_ch1, "cognitive_constraints")

    # 2) 后续章节（第 3 章 sort_order=3.0）：江澈获得该日常认知，而未获知的陈默绝不会获得
    preview_ch3 = client.get(
        f"/api/v1/novels/{uid}/chapters/{ctx['ch3']}/context-preview"
    ).json()
    cog_block = _get_block(preview_ch3, "cognitive_constraints")
    lines_by_char = {
        line.split("】")[0].lstrip("• 【"): line
        for line in cog_block.splitlines()
        if line.startswith("• 【")
    }
    assert "草莓奶黄包" in lines_by_char["江澈"]
    assert "类型：日常认知" in lines_by_char["江澈"]
    assert "草莓奶黄包" not in lines_by_char["陈默"]

    # 陈默的时间轴快照中也不包含该记忆
    other_tl = client.get(
        f"/api/v1/novels/{uid}/characters/{ctx['other_id']}/timeline"
    ).json()
    assert other_tl["known_secrets"] == []


def test_schedule_lifecycle_pending_to_completed_and_historical_rollback(
    client: TestClient, monkeypatch
) -> None:
    """‘今天早八’在当天作为待办参与生成；后续有明确完成证据并确认后不再作为待办；回看早期章节仍还原待办状态。"""
    ctx = _setup_novel(client)
    uid = ctx["uid"]

    # 第 2 章：记录临时安排“明天（开学第二天早晨）早八有高数课”与模糊时间约定“找个周末去旧书店”
    ch2_text = (
        "江澈低头看了一眼教务系统课表，开学第二天早晨早八有两节高等数学。"
        "他又对裴南栀说：“等找个周末我们一起去趟旧书店吧。”"
    )
    client.put(
        f"/api/v1/novels/{uid}/chapters/{ctx['ch2']}/content",
        json={"content": ch2_text, "source": "manual", "create_new_version": True},
    )

    ch2_extraction = {
        "facts": [],
        "state_changes": [],
        "cognitive_records": [
            {
                "secret": "江澈在开学第二天早晨早八有高等数学课",
                "memory_type": "schedule",
                "time_scope": "开学第二天早晨（早八）",
                "schedule_status": "pending",
                "knower_names": ["江澈"],
                "learned_by": "查看教务系统课表",
                "source_quote": "江澈低头看了一眼教务系统课表，开学第二天早晨早八有两节高等数学。",
            },
            {
                "secret": "与裴南栀约定找个周末一起去旧书店",
                "memory_type": "schedule",
                "time_scope": "找个周末（时间未定）",
                "schedule_status": "pending",
                "knower_names": ["江澈", "裴南栀"],
                "learned_by": "当面约定",
                "source_quote": "等找个周末我们一起去趟旧书店吧。",
            },
        ],
        "relationship_changes": [],
        "foreshadowing": [],
        "constraint_checks": [],
    }

    async def fake_post_ch2(self, url, **kwargs):
        req = httpx.Request("POST", url)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(ch2_extraction, ensure_ascii=False)
                        }
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 40},
            },
            request=req,
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post_ch2)
    client.post(f"/api/v1/novels/{uid}/chapters/{ctx['ch2']}/finalize")

    # 全部确认第 2 章提取的两条安排
    pq2 = client.get(
        f"/api/v1/novels/{uid}/memory/pending-queue", params={"status": "pending"}
    ).json()
    client.post(
        f"/api/v1/novels/{uid}/memory/pending-queue/batch",
        json={
            "action": "confirm",
            "items": [{"item_type": i["item_type"], "id": i["id"]} for i in pq2],
        },
    )

    # 在第 3 章（开学第二天早晨）生成上下文中，早八课作为“待办安排”注入
    preview_ch3 = client.get(
        f"/api/v1/novels/{uid}/chapters/{ctx['ch3']}/context-preview"
    ).json()
    cog_ch3 = _get_block(preview_ch3, "cognitive_constraints")
    assert "江澈在开学第二天早晨早八有高等数学课" in cog_ch3
    assert "状态：待办安排" in cog_ch3
    assert "适用时间：开学第二天早晨（早八）" in cog_ch3

    # 第 3 章定稿：正文中有明确完成早八高数课的证据
    ch3_text = "上午九点四十，下课铃响起，江澈合上高等数学课本，早八的两节高数课终于顺利上完了。"
    client.put(
        f"/api/v1/novels/{uid}/chapters/{ctx['ch3']}/content",
        json={"content": ch3_text, "source": "manual", "create_new_version": True},
    )

    ch3_extraction = {
        "facts": [],
        "state_changes": [],
        "cognitive_records": [
            {
                "secret": "江澈上完了开学第二天早晨的早八高等数学课",
                "memory_type": "schedule",
                "time_scope": "开学第二天早晨（早八）",
                "schedule_status": "completed",
                "related_record_id": None,  # 测试自动匹配早先待办记录
                "knower_names": ["江澈"],
                "learned_by": "亲身经历上完课",
                "source_quote": "江澈合上高等数学课本，早八的两节高数课终于顺利上完了。",
            }
        ],
        "relationship_changes": [],
        "foreshadowing": [],
        "constraint_checks": [],
    }

    async def fake_post_ch3(self, url, **kwargs):
        req = httpx.Request("POST", url)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(ch3_extraction, ensure_ascii=False)
                        }
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 40},
            },
            request=req,
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post_ch3)
    client.post(f"/api/v1/novels/{uid}/chapters/{ctx['ch3']}/finalize")

    # 完成记录未确认前：第 4 章中该早八安排仍保持待办（沿用确认规则）
    preview_ch4_unconfirmed = client.get(
        f"/api/v1/novels/{uid}/chapters/{ctx['ch4']}/context-preview"
    ).json()
    assert "状态：待办安排" in _get_block(
        preview_ch4_unconfirmed, "cognitive_constraints"
    )

    # 确认第 3 章的完成记录
    pq3 = client.get(
        f"/api/v1/novels/{uid}/memory/pending-queue",
        params={"status": "pending", "chapter_id": ctx["ch3"]},
    ).json()
    assert len(pq3) == 1
    client.put(
        f"/api/v1/novels/{uid}/memory/pending-queue/cognitive/{pq3[0]['id']}",
        json={"action": "confirm"},
    )

    # 确认后：第 4 章（下课后的午休）中，早八安排状态变为“已完成（已结束安排，仅作历史经历，不得继续作为待办）”
    # 而时间不明的“找个周末去旧书店”不自动判定过期，仍保留条件提示与待办状态
    preview_ch4_confirmed = client.get(
        f"/api/v1/novels/{uid}/chapters/{ctx['ch4']}/context-preview"
    ).json()
    cog_ch4 = _get_block(preview_ch4_confirmed, "cognitive_constraints")
    assert (
        "状态：于第3章已完成（已结束安排，仅作历史经历，不得继续作为待办）" in cog_ch4
    )
    assert "与裴南栀约定找个周末一起去旧书店" in cog_ch4
    assert "适用时间：找个周末（时间未定）｜状态：待办安排" in cog_ch4

    # 回看早期章节（第 2 章 sort_order=2.0）的时间轴与上下文：早八安排仍还原为当時の pending 待办状态！
    tl_at_ch2 = client.get(
        f"/api/v1/novels/{uid}/characters/{ctx['male_id']}/timeline",
        params={"up_to_chapter_sort": 2.0},
    ).json()
    early_sched = next(
        m
        for m in tl_at_ch2["character_memories"]
        if "高等数学" in m["content"]
    )
    assert early_sched["effective_schedule_status"] == "pending"

    tl_at_ch4 = client.get(
        f"/api/v1/novels/{uid}/characters/{ctx['male_id']}/timeline",
        params={"up_to_chapter_sort": 4.0},
    ).json()
    later_sched = next(
        m
        for m in tl_at_ch4["character_memories"]
        if "高等数学" in m["content"]
    )
    assert later_sched["effective_schedule_status"] == "completed"
    assert later_sched["resolved_chapter_id"] == ctx["ch3"]


def test_unconfirmed_disabled_and_stale_memories_excluded_from_context(
    client: TestClient, monkeypatch
) -> None:
    """未确认、停用及来源正文已失效的自动记忆不进入生成上下文。"""
    ctx = _setup_novel(client)
    uid = ctx["uid"]

    ch2_text = "裴南栀小声说：“其实我有一把琴房的备用钥匙。”"
    client.put(
        f"/api/v1/novels/{uid}/chapters/{ctx['ch2']}/content",
        json={"content": ch2_text, "source": "manual", "create_new_version": True},
    )

    extraction = {
        "facts": [],
        "state_changes": [],
        "cognitive_records": [
            {
                "secret": "裴南栀有一把琴房的备用钥匙",
                "memory_type": "secret",
                "knower_names": ["江澈"],
                "learned_by": "裴南栀告知",
                "source_quote": "其实我有一把琴房的备用钥匙。",
            }
        ],
        "relationship_changes": [],
        "foreshadowing": [],
        "constraint_checks": [],
    }

    async def fake_post(self, url, **kwargs):
        req = httpx.Request("POST", url)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(extraction, ensure_ascii=False)}}
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            },
            request=req,
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    client.post(f"/api/v1/novels/{uid}/chapters/{ctx['ch2']}/finalize")

    pq = client.get(
        f"/api/v1/novels/{uid}/memory/pending-queue", params={"status": "pending"}
    ).json()
    cog_id = pq[0]["id"]

    # 1. 未确认时不进入生成上下文
    p1 = client.get(
        f"/api/v1/novels/{uid}/chapters/{ctx['ch3']}/context-preview"
    ).json()
    assert "琴房的备用钥匙" not in _get_block(p1, "cognitive_constraints")

    # 确认后进入生成上下文
    client.put(
        f"/api/v1/novels/{uid}/memory/pending-queue/cognitive/{cog_id}",
        json={"action": "confirm"},
    )
    p2 = client.get(
        f"/api/v1/novels/{uid}/chapters/{ctx['ch3']}/context-preview"
    ).json()
    assert "琴房的备用钥匙" in _get_block(p2, "cognitive_constraints")

    # 2. 停用后不进入生成上下文
    client.put(
        f"/api/v1/novels/{uid}/memory/character-memories/{cog_id}",
        json={"is_disabled": True},
    )
    p3 = client.get(
        f"/api/v1/novels/{uid}/chapters/{ctx['ch3']}/context-preview"
    ).json()
    assert "琴房的备用钥匙" not in _get_block(p3, "cognitive_constraints")

    # 恢复后重新进入生成上下文
    client.put(
        f"/api/v1/novels/{uid}/memory/character-memories/{cog_id}",
        json={"is_disabled": False},
    )
    p4 = client.get(
        f"/api/v1/novels/{uid}/chapters/{ctx['ch3']}/context-preview"
    ).json()
    assert "琴房的备用钥匙" in _get_block(p4, "cognitive_constraints")

    # 3. 修改第 2 章正文导致已定稿来源哈希失效后，自动提取的记忆不再进入第 3 章上下文
    client.put(
        f"/api/v1/novels/{uid}/chapters/{ctx['ch2']}/content",
        json={
            "content": "裴南栀什么也没说，只是安静地喝完了汤。",
            "source": "manual",
            "create_new_version": True,
        },
    )
    p5 = client.get(
        f"/api/v1/novels/{uid}/chapters/{ctx['ch3']}/context-preview"
    ).json()
    assert "琴房的备用钥匙" not in _get_block(p5, "cognitive_constraints")


def test_multiple_memories_no_conflict_and_unknown_knower_skipped(
    client: TestClient, monkeypatch
) -> None:
    """同一人物拥有多条独立记忆不会误报冲突；未知姓名不会错误绑定到默认人物并会报告警告。"""
    ctx = _setup_novel(client)
    uid = ctx["uid"]

    ch2_text = (
        "江澈记住了裴南栀喜欢喝热牛奶，也记住了明天早八要交报名表。"
        "旁边一个叫张伟的陌生男生说自己周日要去兼职。"
    )
    client.put(
        f"/api/v1/novels/{uid}/chapters/{ctx['ch2']}/content",
        json={"content": ch2_text, "source": "manual", "create_new_version": True},
    )

    extraction = {
        "facts": [],
        "state_changes": [],
        "cognitive_records": [
            {
                "secret": "裴南栀喜欢喝热牛奶",
                "memory_type": "daily",
                "knower_names": ["江澈"],
                "learned_by": "交谈得知",
                "source_quote": "江澈记住了裴南栀喜欢喝热牛奶",
            },
            {
                "secret": "明天早八要交报名表",
                "memory_type": "schedule",
                "time_scope": "明天早八",
                "schedule_status": "pending",
                "knower_names": ["江澈"],
                "learned_by": "自己记下",
                "source_quote": "也记住了明天早八要交报名表。",
            },
            {
                "secret": "张伟周日要去兼职",
                "memory_type": "schedule",
                "time_scope": "周日",
                "schedule_status": "pending",
                "knower_names": ["张伟"],  # 未知角色名！绝不能绑定到默认人物江澈
                "learned_by": "本人提起",
                "source_quote": "旁边一个叫张伟的陌生男生说自己周日要去兼职。",
            },
        ],
        "relationship_changes": [],
        "foreshadowing": [],
        "constraint_checks": [],
    }

    async def fake_post(self, url, **kwargs):
        req = httpx.Request("POST", url)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(extraction, ensure_ascii=False)}}
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 40},
            },
            request=req,
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    res = client.post(f"/api/v1/novels/{uid}/chapters/{ctx['ch2']}/finalize")
    assert res.status_code == 200
    data = res.json()
    # 报告了未知角色警告
    assert any("张伟" in w for w in data["extraction_warnings"])

    # 待确认队列中只有江澈的 2 条，没有张伟的那条（未错误绑定给江澈）
    pq = client.get(
        f"/api/v1/novels/{uid}/memory/pending-queue", params={"status": "pending"}
    ).json()
    secrets = [i["raw_payload"]["secret"] for i in pq if i["item_type"] == "cognitive"]
    assert "裴南栀喜欢喝热牛奶" in secrets
    assert "明天早八要交报名表" in secrets
    assert "张伟周日要去兼职" not in secrets

    # 确认这两条记忆后，检查章节记忆面板：同一人物江澈拥有多条记忆不会误报冲突
    client.post(
        f"/api/v1/novels/{uid}/memory/pending-queue/batch",
        json={
            "action": "confirm",
            "items": [{"item_type": i["item_type"], "id": i["id"]} for i in pq],
        },
    )
    items = client.get(
        f"/api/v1/novels/{uid}/memory/items", params={"chapter_id": ctx["ch2"]}
    ).json()
    cog_items = [i for i in items if i["item_type"] == "cognitive"]
    assert len(cog_items) == 2
    assert all(i["conflict"] is False for i in cog_items)


def test_manual_crud_and_reextract_chapter_memories(
    client: TestClient, monkeypatch
) -> None:
    """手动记忆可增改、停用、恢复；按章重新提取替换自动提取记录、保留手动记录不重复，失败不丢旧数据。"""
    ctx = _setup_novel(client)
    uid = ctx["uid"]

    # 1. 手动新增“临时安排”未填 time_scope 时报错 400
    bad_res = client.post(
        f"/api/v1/novels/{uid}/memory/character-memories",
        json={
            "content": "下午三点去图书馆",
            "memory_type": "schedule",
            "time_scope": "",
            "knower_ids": [ctx["male_id"]],
        },
    )
    assert bad_res.status_code == 400

    # 2. 手动新增“故事开始前已知”的日常认知（直接生效，连第 1 章都能使用）
    pre_mem = client.post(
        f"/api/v1/novels/{uid}/memory/character-memories",
        json={
            "content": "江澈从小对花生过敏",
            "memory_type": "daily",
            "time_scope": "长期",
            "knower_ids": [ctx["male_id"]],
            "learned_by": "自身体质",
            "chapter_id": None,
        },
    ).json()
    assert pre_mem["confirm_status"] == "confirmed"
    assert pre_mem["chapter_id"] is None

    p_ch1 = client.get(
        f"/api/v1/novels/{uid}/chapters/{ctx['ch1']}/context-preview"
    ).json()
    assert "（故事开始前已知） 江澈从小对花生过敏" in _get_block(
        p_ch1, "cognitive_constraints"
    )

    # 3. 手动在第 2 章新增一条记忆，随后定稿第 2 章并测试“重新提取记忆”
    manual_ch2 = client.post(
        f"/api/v1/novels/{uid}/memory/character-memories",
        json={
            "content": "裴南栀喜欢草莓味甜食",
            "memory_type": "daily",
            "time_scope": "日常",
            "knower_ids": [ctx["male_id"]],
            "learned_by": "手动录入",
            "chapter_id": ctx["ch2"],
        },
    ).json()

    ch2_text = (
        "裴南栀笑着说自己喜欢草莓味甜食。"
        "江澈看了一眼手机，记住今晚八点要给家里打个电话。"
    )
    client.put(
        f"/api/v1/novels/{uid}/chapters/{ctx['ch2']}/content",
        json={"content": ch2_text, "source": "manual", "create_new_version": True},
    )

    first_extraction = {
        "facts": [],
        "state_changes": [],
        "cognitive_records": [
            {
                "secret": "旧自动提取：江澈看到裴南栀笑了",
                "memory_type": "daily",
                "knower_names": ["江澈"],
                "learned_by": "看到",
                "source_quote": "裴南栀笑着说自己喜欢草莓味甜食。",
            }
        ],
        "relationship_changes": [],
        "foreshadowing": [],
        "constraint_checks": [],
    }
    second_extraction = {
        "facts": [],
        "state_changes": [],
        "cognitive_records": [
            # 与手动记录同义同章同类型：应自动去重，不产生重复记录
            {
                "secret": "裴南栀喜欢草莓味甜食",
                "memory_type": "daily",
                "knower_names": ["江澈"],
                "learned_by": "亲耳听到",
                "source_quote": "裴南栀笑着说自己喜欢草莓味甜食。",
            },
            # 新的自动提取记录：应替换旧自动提取记录
            {
                "secret": "今晚八点要给家里打个电话",
                "memory_type": "schedule",
                "time_scope": "今晚八点",
                "schedule_status": "pending",
                "knower_names": ["江澈"],
                "learned_by": "看手机提醒",
                "source_quote": "江澈看了一眼手机，记住今晚八点要给家里打个电话。",
            },
        ],
        "relationship_changes": [],
        "foreshadowing": [],
        "constraint_checks": [],
    }

    mode = {"step": "first"}

    async def fake_post(self, url, **kwargs):
        req = httpx.Request("POST", url)
        if mode["step"] == "first":
            payload = first_extraction
        elif mode["step"] == "second":
            payload = second_extraction
        else:
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "非JSON错误返回"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                },
                request=req,
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(payload, ensure_ascii=False)}}
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 40},
            },
            request=req,
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    # 未定稿章节调用 reextract-memories 会被拒绝
    not_final_res = client.post(
        f"/api/v1/novels/{uid}/chapters/{ctx['ch2']}/reextract-memories"
    )
    assert not_final_res.status_code == 400

    # 定稿第 2 章
    client.post(f"/api/v1/novels/{uid}/chapters/{ctx['ch2']}/finalize")

    # 执行重新提取记忆（step="second"）
    mode["step"] = "second"
    re_res = client.post(
        f"/api/v1/novels/{uid}/chapters/{ctx['ch2']}/reextract-memories"
    )
    assert re_res.status_code == 200
    re_data = re_res.json()
    assert re_data["extraction_status"] == "ok"
    assert re_data["preserved_previous"] is False

    # 验证：旧自动提取记录已被替换，手动记录完好保留且未产生重复，新自动提取记录已生成
    ch2_items = client.get(
        f"/api/v1/novels/{uid}/memory/items", params={"chapter_id": ctx["ch2"]}
    ).json()
    cog_contents = [i["content"] for i in ch2_items if i["item_type"] == "cognitive"]
    assert "旧自动提取：江澈看到裴南栀笑了" not in cog_contents
    assert cog_contents.count("裴南栀喜欢草莓味甜食") == 1
    assert "今晚八点要给家里打个电话" in cog_contents

    # 执行一次失败的重新提取（step="fail"）：必须保留上次有效结果，不丢失旧数据
    mode["step"] = "fail"
    fail_res = client.post(
        f"/api/v1/novels/{uid}/chapters/{ctx['ch2']}/reextract-memories"
    )
    assert fail_res.status_code == 200
    fail_data = fail_res.json()
    assert fail_data["extraction_status"] == "failed"
    assert fail_data["preserved_previous"] is True

    ch2_items_after_fail = client.get(
        f"/api/v1/novels/{uid}/memory/items", params={"chapter_id": ctx["ch2"]}
    ).json()
    cog_contents_after = [
        i["content"] for i in ch2_items_after_fail if i["item_type"] == "cognitive"
    ]
    assert "裴南栀喜欢草莓味甜食" in cog_contents_after
    assert "今晚八点要给家里打个电话" in cog_contents_after

    # 4. 手动编辑、停用、恢复
    upd = client.put(
        f"/api/v1/novels/{uid}/memory/character-memories/{manual_ch2['id']}",
        json={
            "content": "裴南栀喜欢草莓味甜食与热可可",
            "is_disabled": True,
        },
    ).json()
    assert upd["content"] == "裴南栀喜欢草莓味甜食与热可可"
    assert upd["is_disabled"] is True

    restored = client.put(
        f"/api/v1/novels/{uid}/memory/character-memories/{manual_ch2['id']}",
        json={"is_disabled": False},
    ).json()
    assert restored["is_disabled"] is False


def test_consecutive_chapters_early_eight_and_sweet_preference_e2e(
    client: TestClient, monkeypatch
) -> None:
    """用包含‘早八安排＋饮食偏好’的连续章节验证提取和实际生成效果。"""
    ctx = _setup_novel(client)
    uid = ctx["uid"]

    # 第 2 章（九月一日，傍晚）：女主表达喜欢甜食（红豆软欧包），男主记下明天早八有课
    ch2_prose = (
        "晚饭后走出食堂时，裴南栀指着面包房橱窗说：“我早餐最爱吃甜食，尤其是红豆软欧包。”\n"
        "江澈暗暗记在心里，又看了一眼课表，明天（开学第二天早晨）早八有一节必修高数课，得提前去占座。"
    )
    client.put(
        f"/api/v1/novels/{uid}/chapters/{ctx['ch2']}/content",
        json={"content": ch2_prose, "source": "manual", "create_new_version": True},
    )

    ch2_extract = {
        "facts": [],
        "state_changes": [],
        "cognitive_records": [
            {
                "secret": "裴南栀早餐喜欢吃甜食，尤其是红豆软欧包",
                "memory_type": "daily",
                "time_scope": "早餐时段",
                "schedule_status": "pending",
                "knower_names": ["江澈", "裴南栀"],
                "learned_by": "面包房外亲耳听裴南栀说起",
                "source_quote": "我早餐最爱吃甜食，尤其是红豆软欧包。",
            },
            {
                "secret": "开学第二天早晨早八有一节必修高数课",
                "memory_type": "schedule",
                "time_scope": "开学第二天早晨（早八）",
                "schedule_status": "pending",
                "knower_names": ["江澈"],
                "learned_by": "查看课表",
                "source_quote": "明天（开学第二天早晨）早八有一节必修高数课，得提前去占座。",
            },
        ],
        "relationship_changes": [],
        "foreshadowing": [],
        "constraint_checks": [],
    }

    captured_prompts: list[str] = []

    async def fake_post(self, url, **kwargs):
        req = httpx.Request("POST", url)
        req_json = kwargs.get("json") or {}
        messages = req_json.get("messages") or []
        user_msg = "\n".join(m.get("content", "") for m in messages)
        captured_prompts.append(user_msg)

        if "抽取结构化设定变更与记忆条目" in user_msg:
            if "食堂偶遇与课表" in user_msg:
                content_str = json.dumps(ch2_extract, ensure_ascii=False)
            else:
                ch3_extract = {
                    "facts": [],
                    "state_changes": [],
                    "cognitive_records": [
                        {
                            "secret": "江澈已上完开学第二天早晨的早八必修高数课",
                            "memory_type": "schedule",
                            "time_scope": "开学第二天早晨（早八）",
                            "schedule_status": "completed",
                            "knower_names": ["江澈"],
                            "learned_by": "亲身完成早八课程",
                            "source_quote": "早八的高数课一结束，江澈便收拾好笔记本走出阶梯教室。",
                        }
                    ],
                    "relationship_changes": [],
                    "foreshadowing": [],
                    "constraint_checks": [],
                }
                content_str = json.dumps(ch3_extract, ensure_ascii=False)
        elif "剧情摘要" in user_msg:
            content_str = "章节剧情摘要。"
        else:
            content_str = "{}"

        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content_str}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 60},
            },
            request=req,
        )

    async def fake_stream_chat_sse(**kwargs):
        user_prompt = kwargs.get("user_prompt", "")
        assert "裴南栀早餐喜欢吃甜食，尤其是红豆软欧包" in user_prompt
        assert "开学第二天早晨早八有一节必修高数课" in user_prompt
        assert "状态：待办安排" in user_prompt
        prose = (
            "清晨七点半，江澈惦记着早八的高数课，路过面包房时自然地挑了一只红豆软欧包带给裴南栀。\n"
            "早八的高数课一结束，江澈便收拾好笔记本走出阶梯教室。"
        )
        yield f"data: {json.dumps({'type': 'delta', 'content': prose}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'content': prose}, ensure_ascii=False)}\n\n"

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr("app.api.v1.stream.stream_chat_sse", fake_stream_chat_sse)

    # 1. 定稿第 2 章并确认提取到的“饮食偏好 + 早八安排”
    client.post(f"/api/v1/novels/{uid}/chapters/{ctx['ch2']}/finalize")
    pq2 = client.get(
        f"/api/v1/novels/{uid}/memory/pending-queue", params={"status": "pending"}
    ).json()
    client.post(
        f"/api/v1/novels/{uid}/memory/pending-queue/batch",
        json={
            "action": "confirm",
            "items": [{"item_type": i["item_type"], "id": i["id"]} for i in pq2],
        },
    )

    # 2. 为第 3 章（开学第二天早晨）创建场景并调用写作流式生成接口，验证记忆注入与生成正文效果
    sc3 = client.post(
        f"/api/v1/novels/{uid}/chapters/{ctx['ch3']}/scenes",
        json={
            "beat": "江澈早起去上早八高数课，顺路给裴南栀带早餐，室友陈默同行",
            "pov_character": ctx["male_id"],
            "character_ids": [ctx["male_id"], ctx["female_id"], ctx["other_id"]],
            "target_words": 600,
        },
    ).json()["id"]

    gen_res = client.post(
        f"/api/stream/novels/{uid}/write",
        json={"chapter_id": ctx["ch3"], "scene_id": sc3, "mode": "scene"},
    )
    assert gen_res.status_code == 200
    generated_text = (
        "清晨七点半，江澈惦记着早八的高数课，路过面包房时自然地挑了一只红豆软欧包带给裴南栀。\n"
        "早八的高数课一结束，江澈便收拾好笔记本走出阶梯教室。"
    )
    assert "红豆软欧包" in gen_res.text
    assert "早八的高数课一结束" in gen_res.text

    # 将生成正文保存并定稿第 3 章，提取并确认“早八完成”后续记录
    client.put(
        f"/api/v1/novels/{uid}/chapters/{ctx['ch3']}/content",
        json={
            "content": generated_text,
            "source": "ai",
            "create_new_version": True,
        },
    )
    client.post(f"/api/v1/novels/{uid}/chapters/{ctx['ch3']}/finalize")
    pq3 = client.get(
        f"/api/v1/novels/{uid}/memory/pending-queue",
        params={"status": "pending", "chapter_id": ctx["ch3"]},
    ).json()
    assert len(pq3) == 1
    client.put(
        f"/api/v1/novels/{uid}/memory/pending-queue/cognitive/{pq3[0]['id']}",
        json={"action": "confirm"},
    )

    # 3. 检查第 4 章（下课后的午休）上下文：早八已变为“已完成（已结束安排，仅作历史经历，不得继续作为待办）”，
    # 日常认知“红豆软欧包”继续对江澈有效，而陈默仍然不知晓女主的饮食偏好
    preview_ch4 = client.get(
        f"/api/v1/novels/{uid}/chapters/{ctx['ch4']}/context-preview"
    ).json()
    cog_ch4 = _get_block(preview_ch4, "cognitive_constraints")
    lines_by_char = {
        line.split("】")[0].lstrip("• 【"): line
        for line in cog_ch4.splitlines()
        if line.startswith("• 【")
    }
    assert "红豆软欧包" in lines_by_char["江澈"]
    assert (
        "状态：于第3章已完成（已结束安排，仅作历史经历，不得继续作为待办）"
        in lines_by_char["江澈"]
    )
    assert "红豆软欧包" not in lines_by_char["陈默"]
