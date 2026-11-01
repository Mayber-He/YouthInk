# 小说生成链路修复 · 循环进度

> 工作约定：每轮只做一个任务；mock/固定样本，不调真实 LLM；不动现有小说数据；
> schema 改动必须向后兼容（只加列/加表、带默认值），改前已备份。

## 环境与基线

- 后端：FastAPI + SQLite 双库（global.db + 每部作品 novel.db），Python 3.12。
- 数据备份（改动前，SQLite backup API，已过 integrity_check）：
  `backend/data/_loop_backups/20261101-173017/`（global.db.bak + novel_cf825d92d2d9.db.bak）。
  同目录另存了 T1 测试样本原始件：`log77_prompt.txt` / `log77_output.txt` / `chapter1_latest.txt`。
- 基线测试（改动前，`cd backend && python -m pytest tests -q`）：**36 passed, 5 failed**。
  5 个既有失败均与本任务无关，属历史问题，不计入各任务验收：
  - test_m2_entities_outline.py::test_character_timeline_temporal_query
  - test_m2_entities_outline.py::test_float_sort_order_and_rolling_chapter_generation
  - test_m2_entities_outline.py::test_rolling_generation_uses_retained_chapter_and_rejects_reversed_batch
  - test_m3_writing_stream.py::test_ai_smell_scanner_and_sse_streaming
  - test_m4_m5_memory_and_stress.py::test_m5_hundred_chapter_long_book_stress_and_temporal_isolation
  验收标准：本任务新增/相关测试通过，且不新增上述之外的失败。

## 关于“附件 03 / 日志 77”

真实库 `generation_logs` 中唯一一条 `memory_extract` 日志即 id=77（章节《江边黄昏》，
模型 deepseek-flash）。其原始输出见备份目录 `log77_output.txt`。

该输出的问题已核实：模型给的是**与 schemas/memory.py 不一致的字段**——
facts 用了 `id`/`content`/`source_quote`（缺 fact_type、character_names、location_names），
state_changes 用 `entity`/`change` 而非 `character_name`/`field`/`value`，
cognitive 用 `character`/`content` 而非 `secret`/`knower_names`，
relationship 用 `characters`/`change` 而非 `char_a_name`/`char_b_name`/`rel_type`，
foreshadowing 用 `content` 而非 `description`。
→ 整批 `LlmMemoryExtractionOutput.model_validate` 不会抛错（字段都有默认值），
  但**每个条目的关键字段都会丢空**，等于整章记忆几乎全丢。这正是 T1 要修的核心。
所有 30 条的 source_quote 都逐字存在于正文中（已核验），所以引文校验不应误杀合法条目。

---

## 任务清单

### T1 修复记忆抽取（finalizer._extract_chapter_memories） [完成]
- [x] 提示词补齐六类完整字段/枚举/示例（MEMORY_EXTRACTION_SCHEMA_GUIDE），与 schemas 对齐
- [x] 逐条容错校验（单条 model_validate，合格保留、不合格丢弃并记日志，不整批失败）
- [x] source_quote 必须在正文逐字存在（归一化标点+空白后比对），否则丢弃
- [x] 整批失败：带校验错误重试一次；仍失败用兜底事实（强制 pending，不自动确认）+ 前端标记
- [x] fixture = 日志 77 真实输出；单测覆盖保留/丢弃/不整批失败/引文校验/兜底
- 改动文件：
  - 新增 `backend/app/services/memory/extraction_parse.py`（纯函数：逐条解析+引文校验+状态）
  - 改 `backend/app/services/memory/finalizer.py`（新提示词常量、重试、兜底、返回 status）
  - 改 `backend/app/schemas/memory.py`（FinalizeChapterResponse 增 `extraction_status`，默认 'ok'）
  - 改 `frontend/src/features/memory/types.ts` + `MemoryChapterPanel.tsx`（失败/部分失败标记）
  - 新增 `backend/tests/test_memory_extraction.py` + `backend/tests/fixtures/`（日志 77 固定样本）
- 验证结果：
  - 新增 9 个测试全过（7 纯函数 + 2 finalize 集成，含日志 77 真实样本）。
  - 全量 `pytest tests`：45 passed / 5 failed，5 个失败与基线一致（M2/M3/M5 历史问题），无新增失败。
  - 对日志 77 样本：raw=30 → kept=10（facts 合法保留）/ dropped_invalid=20（五类字段漂移逐条丢弃），
    status=partial，**不再整批失败**。
- 遗留问题 / 需人工确认：
  - 设计取舍：constraint_checks 的 evidence_quote **豁免**逐字校验（仅要求非空），
    因其是跨句判定证据、常为概括；facts/state/cognitive/relationship/foreshadowing 仍要求逐字。
    这与旧行为（旧代码对 constraint_checks 本就不做引文校验）兼容。
  - 兜底“失败”状态下 facts 走 pending、**不自动确认**；前端面板已显示红/黄标记，
    但“标记”目前只在定稿后的即时结果区展示，未落库为持久字段（如需在列表历史回看，可后续加列）。

### T2 约束与人物状态按阶段生效 [待做]
注：schema 里 constraints 已有 valid_from_chapter_id / valid_until_chapter_id 列，
assembler 过滤逻辑待核实是否已按章过滤。

### T3 场景拆分改为事件清单 [待做]

### T4 精简并重排写作提示词 [待做]

### T5 生成后的确定性重复检测与自动重写一次 [待做]

### T6 衔接检查结果瘦身 [待做]

### T7 日志与流式结束判定 [待做]
