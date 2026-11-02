# 重新定稿修复前：记忆状态只读统计

统计日期：2026-11-02。真实库：`backend/data/novel_cf825d92d2d9/novel.db`。以 `mode=ro`、`query_only=ON` 和单次读取事务查询，未修改数据。facts 使用 status 作为确认状态；其余表使用 confirm_status。字段值不重分类，NULL 单列。

## facts

总数：15；manual：0。

| origin | confirm_status | is_stale | 条数 |
|---|---|---:|---:|
| extracted | confirmed | 0 | 15 |

manual 记录与来源章节：

无 manual 记录。

## character_state_changes

总数：7；manual：0。

| origin | confirm_status | is_stale | 条数 |
|---|---|---:|---:|
| extracted | confirmed | 0 | 7 |

manual 记录与来源章节：

无 manual 记录。

## cognitive_records

总数：5；manual：0。

| origin | confirm_status | is_stale | 条数 |
|---|---|---:|---:|
| extracted | confirmed | 0 | 5 |

manual 记录与来源章节：

无 manual 记录。

## relationship_changes

总数：1；manual：0。

| origin | confirm_status | is_stale | 条数 |
|---|---|---:|---:|
| extracted | confirmed | 0 | 1 |

manual 记录与来源章节：

无 manual 记录。

## foreshadowing

总数：4；manual：0。

| origin | confirm_status | is_stale | 条数 |
|---|---|---:|---:|
| extracted | confirmed | 0 | 4 |

manual 记录与来源章节：

无 manual 记录。

## constraint_checks

总数：11；manual：0。

| origin | confirm_status | is_stale | 条数 |
|---|---|---:|---:|
| extracted | confirmed | 0 | 11 |

manual 记录与来源章节：

无 manual 记录。

## 结论

六表合计 43 条，manual 合计 0 条。

origin/source_hash 是现存来源字段，不足以证明历史操作者或确认路径；本次不修正、迁移或重分类已有 manual 记录。没有 manual 记录时也不代表历史上从未有过确认操作。

读取前后 57 个既有数据库/密钥/SQLite侧文件 SHA-256 一致。

## 全部记录来源章节补充

manual 记录为 0，因此没有 manual 来源章节可列。下面列出六表全部记录的来源，供核对：

| 表 | 来源章节 ID | 章节名 | 条数 |
|---|---:|---|---:|
| facts | 1 | 吃一口软糖 | 15 |
| character_state_changes | 1 | 吃一口软糖 | 7 |
| cognitive_records | 1 | 吃一口软糖 | 5 |
| relationship_changes | 1 | 吃一口软糖 | 1 |
| foreshadowing | 1 | 吃一口软糖 | 4 |
| constraint_checks | 1 | 吃一口软糖 | 11 |
