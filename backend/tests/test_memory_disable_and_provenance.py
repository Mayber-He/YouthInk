"""作者侧记忆停用 / 冲突提示 / 注入来源标注。

样本取自 docs/loop/rewrite_export.md 的重写导出：关系 rel 6/7/8 与
对话框状态记忆 23、伏笔 18。这里用等价的固定 SQLite 夹具，不依赖被
gitignore 的 docs/loop 文件，也不调用任何模型。
"""
from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

from app.core.exceptions import AppError
from app.db.init_schema import init_novel_db
from app.db.repositories.memory_repo import MemoryRepository
from app.db.repositories.settings_repo import SettingsRepository
from app.services.context import assembler as assembler_module
from app.services.context.assembler import ContextAssembler

TABLE_BY_TYPE = {
    "fact": "facts",
    "char_state": "character_state_changes",
    "cognitive": "cognitive_records",
    "relationship": "relationship_changes",
    "foreshadowing": "foreshadowing",
}


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    init_novel_db(c)
    c.execute("INSERT INTO novels(id,title) VALUES(1,'测试')")
    c.execute("INSERT INTO volumes(id,novel_id,title,sort_order) VALUES(1,1,'卷',1)")
    c.execute("INSERT INTO arcs(id,volume_id,title,sort_order) VALUES(1,1,'弧',1)")
    chapters = [
        (1, "吃一口软糖", 1.0, "八月二十五日，夜"),
        (2, "锁屏上的江边黄昏", 2.0, "九月一日，上午"),
        (3, "一嗓子喊到楼下", 3.0, "九月一日，下午"),
    ]
    for cid, title, sort_order, story_time in chapters:
        c.execute(
            "INSERT INTO chapters(id,arc_id,title,sort_order,story_time,status,synopsis) "
            "VALUES(?,1,?,?,?,'final','江澈与裴南栀在迎新点相遇')",
            (cid, title, sort_order, story_time),
        )
    c.execute(
        "INSERT INTO characters(id,name,role) VALUES"
        "(1,'江澈','male_lead'),(2,'裴南栀','female_lead'),(3,'林鹿','major')"
    )
    # 事实：一条第 2 章，一条无章节的通用设定。
    c.execute(
        "INSERT INTO facts(id,chapter_id,content,fact_type,status,origin) "
        "VALUES(1,2,'江澈在迎新点办理报到','event','confirmed','manual')"
    )
    c.execute(
        "INSERT INTO facts(id,chapter_id,content,fact_type,status,origin) "
        "VALUES(2,NULL,'两人同小区长大','background','confirmed','manual')"
    )
    # 状态：记忆 23（第 2 章对话框） + 记忆 18（第 1 章情绪）。
    c.execute(
        "INSERT INTO character_state_changes"
        "(id,character_id,chapter_id,field,value,confirm_status,origin) VALUES"
        "(23,1,2,'item','手机置顶对话框仍停留在“晚安晚安晚安”','confirmed','manual'),"
        "(18,2,1,'emotion','被具体夸奖后脸热、心情高涨','confirmed','manual')"
    )
    # 认知：记忆 11/13 都含江澈，触发“同一人物多条认知”提示。
    c.execute(
        "INSERT INTO cognitive_records(id,chapter_id,secret,knower_ids,confirm_status,origin) VALUES"
        "(11,1,'两人聊了一个多月，彼此都不知道对方在哪个学校','[1,2]','confirmed','manual'),"
        "(13,2,'江澈确认裴南栀就是线上聊天对象','[1]','confirmed','manual')"
    )
    # 关系：同一对人物 rel 6（第 1 章）、rel 7/8（第 2 章）。
    c.execute(
        "INSERT INTO relationship_changes"
        "(id,char_a_id,char_b_id,chapter_id,rel_type,intimacy,publicity,confirm_status,origin) VALUES"
        "(6,1,2,1,'线上聊友',5,'one_sided','confirmed','manual'),"
        "(7,1,2,2,'学姐与新生',1,'public','confirmed','manual'),"
        "(8,1,2,2,'线上聊天对象（江澈单方确认）',4,'one_sided','confirmed','manual')"
    )
    # 伏笔 18：第 3 章。
    c.execute(
        "INSERT INTO foreshadowing"
        "(id,planted_chapter_id,description,status,confirm_status,origin) VALUES"
        "(18,3,'江澈手机置顶对话框最后一条是前一晚一名女性发来的晚安','planted','confirmed','manual')"
    )
    c.commit()
    yield c
    c.close()


@pytest.fixture
def repo(conn):
    return MemoryRepository(conn)


def _context(conn, monkeypatch):
    class _NoVectors:
        store_file = SimpleNamespace(exists=lambda: False)

        def incompatible_chapter_ids(self, *args, **kwargs):
            return []

    monkeypatch.setattr(assembler_module, "NovelVectorStore", lambda _uid: _NoVectors())
    settings = SettingsRepository(sqlite3.connect(":memory:"))
    return ContextAssembler(conn, "testnovel", settings).build_context_preview(3)


def _block(preview, key):
    return next(b.content for b in preview.blocks if b.key == key)


def test_newest_relationship_only_in_context_while_older_rows_remain(repo, conn, monkeypatch):
    chars = _block(_context(conn, monkeypatch), "character_states")
    assert "线上聊天对象（江澈单方确认）" in chars
    assert "线上聊友" not in chars
    assert "学姐与新生" not in chars
    # 旧关系仍保留在库中，面板列表可见。
    items = repo.list_chapter_memory_items(1)
    assert [i.id for i in items if i.item_type == "relationship"] == [6]


def test_provenance_prefixes_use_chapter_and_story_time(conn, monkeypatch):
    preview = _context(conn, monkeypatch)
    chars = _block(preview, "character_states")
    secrets = _block(preview, "cognitive_constraints")
    ledger = _block(preview, "foreshadowing_and_facts")

    assert "（第2章·九月一日，上午） item:手机置顶对话框仍停留在“晚安晚安晚安”" in chars
    assert "（第1章·八月二十五日，夜） emotion:被具体夸奖后脸热、心情高涨" in chars
    assert "（第1章·八月二十五日，夜） 两人聊了一个多月" in secrets
    assert "（第2章·九月一日，上午） 江澈确认裴南栀就是线上聊天对象" in secrets
    assert "（第3章·九月一日，下午） [伏笔-planted] 江澈手机置顶对话框" in ledger
    assert "（第2章·九月一日，上午） [已确认事实] 江澈在迎新点办理报到" in ledger
    assert "（通用设定） [已确认事实] 两人同小区长大" in ledger


def test_conflict_flags_use_simple_pair_and_knower_rules(repo):
    items = {(i.item_type, i.id): i for i in repo.list_chapter_memory_items(2)}
    # rel 7/8 与第 1 章 rel 6 同属一对人物，全部提示可能冲突。
    assert items[("relationship", 7)].conflict is True
    assert items[("relationship", 8)].conflict is True
    assert "同一对人物" in items[("relationship", 8)].conflict_reason
    # 认知 13 与第 1 章认知 11 都含江澈，但同一人物有多条认知不再误判为冲突。
    assert items[("cognitive", 13)].conflict is False
    assert items[("cognitive", 13)].conflict_reason == ""
    # 事实/状态/伏笔不参与这两条简单规则。
    assert items[("fact", 1)].conflict is False


@pytest.mark.parametrize("item_type,item_id", [
    ("fact", 1), ("char_state", 23), ("cognitive", 13), ("relationship", 8), ("foreshadowing", 18),
])
def test_disable_hides_from_injection_but_keeps_row(repo, conn, monkeypatch, item_type, item_id):
    table = TABLE_BY_TYPE[item_type]
    repo.set_memory_item_disabled(item_type, item_id, True)
    row = repo.conn.execute(f"SELECT * FROM {table} WHERE id = ?", (item_id,)).fetchone()
    assert row["is_disabled"] == 1
    assert row["is_stale"] == 0
    assert row["confirm_status" if item_type != "fact" else "status"] == "confirmed"

    text = "\n".join(b.content for b in _context(conn, monkeypatch).blocks)
    needles = {
        "fact": "江澈在迎新点办理报到",
        "char_state": "手机置顶对话框仍停留在",
        "cognitive": "江澈确认裴南栀就是线上聊天对象",
        "relationship": "线上聊天对象（江澈单方确认）",
        "foreshadowing": "江澈手机置顶对话框最后一条是前一晚",
    }
    assert needles[item_type] not in text

    # 列表仍返回该条，便于恢复。
    chapter_id = 3 if item_type == "foreshadowing" else 2
    listed = {(i.item_type, i.id): i for i in repo.list_chapter_memory_items(chapter_id)}
    assert listed[(item_type, item_id)].is_disabled is True
    assert listed[(item_type, item_id)].is_effective is False

    repo.set_memory_item_disabled(item_type, item_id, False)
    restored = repo.conn.execute(
        f"SELECT is_disabled FROM {table} WHERE id = ?", (item_id,)
    ).fetchone()[0]
    assert restored == 0


def test_disabled_newest_relationship_does_not_fall_back_to_older(repo, conn, monkeypatch):
    repo.set_memory_item_disabled("relationship", 8, True)
    chars = _block(_context(conn, monkeypatch), "character_states")
    assert "线上聊天对象（江澈单方确认）" not in chars
    assert "线上聊友" not in chars
    assert "学姐与新生" not in chars


def test_stale_item_cannot_be_disabled(repo):
    repo.conn.execute("UPDATE facts SET is_stale = 1 WHERE id = 1")
    with pytest.raises(AppError) as exc:
        repo.set_memory_item_disabled("fact", 1, True)
    assert exc.value.status_code == 409
