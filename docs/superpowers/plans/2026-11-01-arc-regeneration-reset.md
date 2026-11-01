# 本弧重生成与章节数据重置实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 点击“重新生成本弧章节”时，明确清空本弧全部旧章节及其派生数据，再从初始待写状态建立新目录，避免新旧大纲、正文和上下文混用。

**Architecture:** 保留 AI 生成与复核在删除之前完成；只有拿到并通过时间线/连续性校验的新章节后，才执行单次数据库事务重置本弧。生成上下文排除本弧旧章节，只使用本弧之前仍有效的剧情锚点，防止重置后仍沿用旧梗概。级联数据之外，显式清理无外键摘要、章节 FTS 项和本弧向量块；将排序靠后的其他弧章节标记为上下文待复核。前端在执行前展示本弧将被清空的章节数和含正文/定稿数量，并要求用户确认。

**Tech Stack:** React、TypeScript、FastAPI、SQLite 事务、JSON 向量索引、pytest、Vitest。

---

### Task 1：复现当前只删未定稿章节的行为并定义重置边界

**Files:**
- Modify: `backend/tests/test_m2_entities_outline.py`
- Modify: `backend/tests/test_m4_m5_memory_and_stress.py`

- [ ] 建立包含本弧锁定定稿章、未锁定定稿章、草稿章、待写章，以及后续弧章节的测试数据。
- [ ] 为本弧章节建立版本、场景、章节摘要、事实/人物状态、复核记录和向量块；另建一个不属于章节的手动记忆/事实用于验证不会误删。
- [ ] 断言本弧重生成后只保留新建待写章节，本弧旧章节关联的派生数据消失；其他弧章节、其他弧数据和手动记忆保留。
- [ ] 断言后续弧既有章节被标为待复核，并且待复核标记的起点是重置弧之后的第一章。
- [ ] 运行定向测试确认当前实现失败，确保覆盖旧目录残留和派生数据污染。

### Task 2：实现后端原子重置

**Files:**
- Modify: `backend/app/db/repositories/outline_repo.py`
- Modify: `backend/app/services/setting_generator.py`
- Modify: `backend/app/db/vector_store.py`
- Modify: `backend/app/db/repositories/memory_repo.py`（仅在 FTS 清理需要独立复用接口时）
- Test: `backend/tests/test_m2_entities_outline.py`
- Test: `backend/tests/test_m4_m5_memory_and_stress.py`

- [ ] 把 `replace_unlocked_arc_chapters` 改为语义明确的本弧整体替换操作；AI 响应、时间线校验、审查数量校验必须在删除发生前完成。
- [ ] 修改生成上下文：不再把本弧将被清除的定稿/草稿章节作为“保留章节”锚点；只传入本弧之前最近且仍有效的前文锚点、世界设定和本弧目标。确保复核阶段也不将旧本弧正文/梗概当成将被保留的历史。
- [ ] 在同一 SQLite 事务中删除本弧旧章节。利用章节外键级联清理场景、版本、章节记忆、复核等依附数据；显式删除 `summaries` 中引用旧章节 ID 的 chapter/arc 摘要和对应章节版本的 FTS 记录，避免其 `ref_id` 无外键而残留。
- [ ] 删除时清理以本弧旧章节为来源的向量块；更新 `NovelVectorStore` 提供按章节 ID 批量移除的方法，原子写回 JSON，并保留其他章节的块。
- [ ] 插入新章节为 `pending`、未锁定、无正文/版本/场景的初始状态；为新章节分配连续的全书排序位置，保证仍在前弧之后、后弧之前；必要时只对排序值做确定性重排，不改变其他章节内容或所属情节弧。
- [ ] 标记排序在重置区间之后的章节 `continuity_review_required=1`，并设置 `continuity_dirty_from_chapter_id`；删除或标记过期的本弧/后续弧聚合摘要，防止上下文汇总读取旧剧情。
- [ ] 若数据库事务失败，回滚章节及摘要变更；向量文件采用临时文件原子替换，并将更新时机安排为数据库提交后的可恢复步骤，避免留下半写 JSON。
- [ ] 定向运行后端测试，覆盖新章节写入失败、校验失败时旧数据未被清除，以及成功时相关数据和向量同步清理。
- [ ] 测试生成 prompt 不含本弧旧章节梗概/正文，但包含前一弧最后一个有效章节锚点；清除后无法通过 FTS 或向量检索命中本弧旧内容。

### Task 3：在前端让清除行为可见、明确

**Files:**
- Modify: `frontend/src/features/outline/OutlineSection.tsx`
- Modify: `frontend/src/features/outline/ArcCard.tsx`
- Modify: `frontend/src/features/outline/api.ts`
- Modify: existing outline component test file

- [ ] 将普通“生成章节”与“重新生成本弧章节”区分；有现存章节时，后者先展示确认弹窗，列出将清除的章节数量、已有正文数量及定稿数量。
- [ ] 明确提示本弧旧章节、正文、版本和相关记忆会被清除；其他弧章节不删除，但后续章节会变为待复核。
- [ ] 取消确认时不发请求；确认后才调用重生成接口，并在操作成功后刷新目录、章节详情和记忆/上下文相关查询。
- [ ] 验证空弧初次生成不显示破坏性确认；发生 API 错误时保留界面数据并给出明确错误，不显示“已重置”。

### Task 4：重新生成当前选定情节弧并验收

**Files:**
- No source files; operate on the user-selected arc after Tasks 1–3 pass.

- [ ] 先展示本弧待清除的具体计数，再执行用户已经授权的“重置并重生成本弧”行为；如生成或复核在删除前失败，旧章节保持完整。
- [ ] 确认本弧只剩新目录章节，全部为待写、未锁定、空正文状态；旧正文、历史版本和旧派生记忆不会进入上下文预览或向量检索。
- [ ] 确认其他弧章节仍存在，后续弧显示待复核；重写并定稿上游后，下游上下文只由当前有效章节动态组装。
