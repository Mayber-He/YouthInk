# T8 约束停用事故只读调查（2026-11-01）

当前库：`backend/data/novel_cf825d92d2d9/novel.db`。使用 SQLite `mode=ro` / `query_only=ON` 查询，未执行修复或迁移，未调用 LLM。

## 结论与证据

江澈（character_id=1）约束 #1–#5，裴南栀（character_id=2）约束 #6–#11，当前全部 status=resolved，valid_until_chapter_id=1。对应检查 #1–#11 全部 verdict=resolved、confirm_status=confirmed；说明却是“本章未涉及/未违反”或表达约束仍然成立的描述，不构成正式解除。

定稿前备份 `backups/novel_20261101_115418_822725_finalize_ch_1.db` 中，以上 11 条约束均为 active，valid_until_chapter_id=NULL。当前库停用时间均为 2026-11-01 11:56:52（字段原值）。后续章节的 list_active_for_chapter 只读取 active/violated，所以这些约束已不再参与生效约束注入。

调用链：ChapterFinalizerService._extract_chapter_memories → parse_extraction_items → _persist_extracted_memories → ConstraintRepository.create_constraint_check：定稿只创建 pending 检查。MemoryRepository.update_pending_item(action=confirm) → _apply_constraint_check_verdict：确认 resolved 后把 constraints.status 改为 resolved 并把有效期截止到该章。batch_update_pending 也会调用该确认路径。现有数据可以证明“已确认并停用”，不能单凭数据库区分当时是逐条还是批量确认，也不能归因成定稿自动确认。

抽取提示词原要求“逐条判定、只输出 violated/resolved”，没有明确“未违反不输出”；解析又豁免了 constraint_checks 的逐字引文校验，因此把未违反误写为 resolved 的记录能进入待确认队列。这是本次修复范围。

## 当前约束快照

```json
[
  {
    "id": 1,
    "target_id": 1,
    "content": "报到当天对临江大学老校区完全陌生：需要在校门口看平面图、跟着志愿者举的牌子走、在岔路口犹豫或问路；绝不能写他知道叙旧楼在哪、桂花巷怎么走、三食堂几点开门。",
    "status": "resolved",
    "valid_until_chapter_id": 1,
    "updated_at": "2026-11-01 11:56:52"
  },
  {
    "id": 2,
    "target_id": 1,
    "content": "与裴南栀现实中是初次见面，开口只能叫“学姐”或“同学”；绝不能脱口叫出“软糖”、网名，也不能表现出任何线上聊天积累的熟稔感。",
    "status": "resolved",
    "valid_until_chapter_id": 1,
    "updated_at": "2026-11-01 11:56:52"
  },
  {
    "id": 3,
    "target_id": 1,
    "content": "大一新生，经济来源是家里给的生活费和刚激活的校园卡，消费集中在食堂、打印店、地铁和便利店；绝不能随手请一大桌人吃饭、买昂贵设备或出入高消费场所。",
    "status": "resolved",
    "valid_until_chapter_id": 1,
    "updated_at": "2026-11-01 11:56:52"
  },
  {
    "id": 4,
    "target_id": 1,
    "content": "计算机水平是自学的新生水平，写代码要查文档、要试错、会卡在环境配置上；绝不能一进机房就独立写出成熟系统，或被老师、学长当成技术大牛捧着。",
    "status": "resolved",
    "valid_until_chapter_id": 1,
    "updated_at": "2026-11-01 11:56:52"
  },
  {
    "id": 5,
    "target_id": 1,
    "content": "他不知道裴南栀的家庭情况、专业课程、社交圈和日常作息，只能通过观察和聊天推测；绝不能凭空说出他不可能知道的女主私事。",
    "status": "resolved",
    "valid_until_chapter_id": 1,
    "updated_at": "2026-11-01 11:56:52"
  },
  {
    "id": 6,
    "target_id": 2,
    "content": "与陌生新生、学弟保持礼貌距离，交流限于指路、流程说明、公事对接；绝不能初见就自来熟、主动聊私事，或对江澈使用任何亲近称呼。",
    "status": "resolved",
    "valid_until_chapter_id": 1,
    "updated_at": "2026-11-01 11:56:52"
  },
  {
    "id": 7,
    "target_id": 2,
    "content": "线上身份是必须守住的秘密：她不知道江澈就是「晚风不加糖」，线下绝不能用聊天时的黏人语气、颜文字口吻说话，也不能主动提起网友、暗示自己有这样一个聊天对象。",
    "status": "resolved",
    "valid_until_chapter_id": 1,
    "updated_at": "2026-11-01 11:56:52"
  },
  {
    "id": 8,
    "target_id": 2,
    "content": "大二学生，收入来自家里给的生活费和零星的稿费、勤工补助；买器材、买书要比价、要犹豫；绝不能随手买昂贵镜头、请客挥霍或轻易许诺垫钱。",
    "status": "resolved",
    "valid_until_chapter_id": 1,
    "updated_at": "2026-11-01 11:56:52"
  },
  {
    "id": 9,
    "target_id": 2,
    "content": "对老校区和叙旧楼、器材借还室熟悉，但对江北新校区、计算机学院、男生宿舍区并不熟；绝不能表现得对全校所有场所了如指掌。",
    "status": "resolved",
    "valid_until_chapter_id": 1,
    "updated_at": "2026-11-01 11:56:52"
  },
  {
    "id": 10,
    "target_id": 2,
    "content": "在陌生人或半熟的人面前不会崩溃、哭诉或主动交代家庭压力；情绪流露只发生在独处、深夜或极少数她完全放心的人面前。",
    "status": "resolved",
    "valid_until_chapter_id": 1,
    "updated_at": "2026-11-01 11:56:52"
  },
  {
    "id": 11,
    "target_id": 2,
    "content": "她不会读心，对江澈的真实想法、室友情况、技术水平处于未知状态；绝不能凭空判断出他认得自己。",
    "status": "resolved",
    "valid_until_chapter_id": 1,
    "updated_at": "2026-11-01 11:56:52"
  }
]
```

## 对应判定快照

```json
[
  {
    "id": 1,
    "constraint_id": 1,
    "verdict": "resolved",
    "description": "本章为开学前居家夜晚，未涉及报到或老校区认路，未违反。",
    "confirm_status": "confirmed"
  },
  {
    "id": 2,
    "constraint_id": 2,
    "verdict": "resolved",
    "description": "本章仅线上聊天，无现实初次见面与称呼场景，未违反。",
    "confirm_status": "confirmed"
  },
  {
    "id": 3,
    "constraint_id": 3,
    "verdict": "resolved",
    "description": "本章未写江澈任何消费行为，未违反。",
    "confirm_status": "confirmed"
  },
  {
    "id": 4,
    "constraint_id": 4,
    "verdict": "resolved",
    "description": "本章无写代码或机房场景，未涉及技术水平表现，未违反。",
    "confirm_status": "confirmed"
  },
  {
    "id": 5,
    "constraint_id": 5,
    "verdict": "resolved",
    "description": "江澈明确没有问对方学校与专业，也未提自己的；本章未出现他凭空知道对方私事。",
    "confirm_status": "confirmed"
  },
  {
    "id": 6,
    "constraint_id": 6,
    "verdict": "resolved",
    "description": "本章为裴南栀与线上熟人的私聊，未与陌生新生现实接触，未违反。",
    "confirm_status": "confirmed"
  },
  {
    "id": 7,
    "constraint_id": 7,
    "verdict": "resolved",
    "description": "本章仅展示「吃一口软糖」线上聊天，未在线下暴露身份或对陌生人使用线上语气，未违反。",
    "confirm_status": "confirmed"
  },
  {
    "id": 8,
    "constraint_id": 8,
    "verdict": "resolved",
    "description": "本章未写她购买昂贵器材或挥霍，只写自带水等待拍摄，未违反。",
    "confirm_status": "confirmed"
  },
  {
    "id": 9,
    "constraint_id": 9,
    "verdict": "resolved",
    "description": "本章未涉及校内场所指路或熟悉度表现，未违反。",
    "confirm_status": "confirmed"
  },
  {
    "id": 10,
    "constraint_id": 10,
    "verdict": "resolved",
    "description": "本章情绪流露发生在与线上熟人的私聊中，未对陌生人或半熟人崩溃哭诉，未违反。",
    "confirm_status": "confirmed"
  },
  {
    "id": 11,
    "constraint_id": 11,
    "verdict": "resolved",
    "description": "裴南栀通过询问确认江澈开学后是否还理她，未表现读心或凭空判断江澈想法。",
    "confirm_status": "confirmed"
  }
]
```

## 恢复 SQL 草稿（未执行，必须人工复核）

以下恢复到定稿前 active/NULL 状态，并把 11 条错误的解除判定标记 discarded，避免它们继续作为已确认解除依据。执行前请确认这些约束仍应长期有效；若某条已经在后续剧情正式解除，应将它排除。本草稿仅针对已核实的 ID/状态/时间，预期各更新 11 行，任何不一致都应停止检查。

```sql
BEGIN IMMEDIATE;
SELECT id, status, valid_until_chapter_id, updated_at
FROM constraints WHERE id BETWEEN 1 AND 11 ORDER BY id;
SELECT id, constraint_id, verdict, confirm_status, description
FROM constraint_checks WHERE id BETWEEN 1 AND 11 ORDER BY id;

UPDATE constraints
SET status = 'active', valid_until_chapter_id = NULL,
    updated_at = datetime('now')
WHERE id BETWEEN 1 AND 11
  AND target_type = 'character' AND target_id IN (1, 2)
  AND status = 'resolved' AND valid_until_chapter_id = 1
  AND updated_at = '2026-11-01 11:56:52';
SELECT changes() AS restored_constraints; -- 预期 11

UPDATE constraint_checks SET confirm_status = 'discarded'
WHERE id BETWEEN 1 AND 11 AND constraint_id = id
  AND chapter_id = 1 AND verdict = 'resolved' AND confirm_status = 'confirmed';
SELECT changes() AS discarded_incorrect_checks; -- 预期 11

SELECT id, status, valid_until_chapter_id FROM constraints
WHERE id BETWEEN 1 AND 11 ORDER BY id;
ROLLBACK; -- 草稿默认回滚；只有人工核对并决定恢复时，才改成 COMMIT。
```

本次代码不会自动执行以上 SQL，也不会扫描或改写现有记录。后续抽取的 resolved 必须有正文连续原文证据，明显的“未涉及/未违反”说明会被丢弃，合法解除仍先入 pending。人工明确确认 pending 检查后应用约束状态的既有流程保留。
