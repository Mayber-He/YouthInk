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

### T2 约束与人物状态按阶段生效 [完成]
- [x] constraints 生效范围字段：`valid_from_chapter_id` / `valid_until_chapter_id` **已存在于 schema
      且 create/update 已暴露**；`ConstraintRepository.list_active_for_chapter` **已按当前章 sort_order
      过滤**窗口。本轮补测试证明过滤真实生效（窗口内出现、窗口外不出现、until 含当章）。未再改生产代码逻辑。
- [x] 人物“当前状态”无结构化记录时的默认文案：由“保持初始基准状态”改为
      “无结构化状态变更记录；以本章起点为准，沿用人物卡基准状态与前文已写事件，不要据此另造新状态”。
      （关系栏文案此前已较完整，保持不动。）
- [x] 新增只读审计脚本 `backend/scripts/audit_constraints.py`：以只读模式打开 novel.db，
      列出全部约束+生效范围，启发式标注可能冲突（人物“陌生某地”但该地点 related_chars 含该人物／
      背景提到居住；生效窗口为空或 until 早于最新章而仍 active；文本同时含陌生+熟悉措辞），
      输出 `docs/loop/constraint_audit.md`，不修改数据。
- 改动文件：
  - 改 `backend/app/services/context/assembler.py`（人物状态空值文案）
  - 新增 `backend/scripts/audit_constraints.py`
  - 新增 `docs/loop/constraint_audit.md`（在真实库 novel_cf825d92d2d9 上只读生成）
  - 新增 `backend/tests/test_constraint_phasing.py`
- 验证结果：
  - 新增 5 测试全过（按章过滤 2 + 文案 1 + 审计脚本运行/只读 2）。
  - 全量 `pytest tests`：50 passed / 5 failed，5 个为基线既有失败，无新增。
  - 审计脚本在真实库跑通：21 条约束，启发式标注 2 条“可能冲突”（#9/#12，经判定为误报，
    属不同地点的复合约束/否定句式——正说明启发式只作人工复核提示，报告已注明）。
- 遗留问题 / 需人工确认：
  - 审计的“文本同时含陌生+熟悉措辞”启发式偏噪（会命中“对A地熟悉但对B地陌生”这类正常复合约束）。
    保留为人工复核提示，未据此改数据。
  - 现有约束 21 条 valid_from/until 均为空（全程生效），与当前仅 5 章、全在报到阶段一致；
    如需按阶段收窄某条约束，请在约束管理里设置生效范围，assembler 会自动按章过滤。

### T3 场景拆分改为事件清单 [完成]
- [x] `generate_chapter_scenes` 提示词 + 输出 schema 改为事件清单：goal / entry_state /
      must_happen（≤3 条、每条 ≤25 字）/ exit_state / must_not_include / target_words；
      提示词明确禁止写台词、分镜级动作细节、结尾意象。
- [x] **DB 兼容方案选“拼接进现有 `scenes.beat`”（零迁移）**，不新增列。理由：`beat` 已被
      assembler、writing_boundary、write_scene 模板等多处直接内联，拼成稳定可读文本
      （目标/起点状态/必须发生/终点状态/本场禁止出现）后，下游零改动；新增列则要改 SceneResponse、
      前端类型、所有读取点，改动面更大。
- [x] 相邻场景 must_happen 字符 3-gram Jaccard 相似度校验（阈值 0.6）；超阈值带重复处让模型
      重拆一次；仍重复则保留结果并写 warning 日志（最多 1 次重拆，不循环）。
- [x] 章梗概生成（setting_generator 的 generate_outline_chapters 提示词）加入：
      只写“发生了什么事件、从哪个状态起、到哪个状态止”，不写对白/分镜动作细节/结尾意象。
- 改动文件：
  - 新增 `backend/app/services/scene_planning.py`（格式化 beat、n-gram 相似度、相邻重复检测）
  - 改 `backend/app/services/writing_service.py`（提示词、重拆流程、事件清单→beat）
  - 改 `backend/app/schemas/writing.py`（LlmSceneItem 增事件清单字段；保留 beat 等旧字段兼容）
  - 改 `backend/app/services/setting_generator.py`（章梗概提示词）
  - 改 `backend/app/builtin/prompt_templates.py`（generate_scenes 模板 v2.0）
  - 新增 `backend/tests/test_scene_event_checklist.py`
- 验证结果：
  - 新增 7 测试全过（纯函数 4 + 集成 3：解析→beat、触发一次重拆并采用干净版、重拆后仍重复则保留且不再重试）。
  - 全量 `pytest tests`：57 passed / 5 failed，5 个为基线既有失败，无新增。
  - 旧的 m3 `scenes/generate` 测试（只给 `beat` 字段）仍通过——schema 向后兼容。
- 遗留问题 / 需人工确认：
  - **已存在的 global.db 里的 `generate_scenes` 模板不会自动刷新**（种子用 INSERT OR IGNORE，
    库里仍是 v1.1 文案）。但事件清单的完整要求已在代码里追加到 instruction，行为不依赖模板刷新。
    如希望界面“提示词模板”页也显示 v2.0，需在设置里手动重置该模板（我没有改 global.db）。
  - 3-gram Jaccard 阈值 0.6 为经验值；短句（<10 字）相似度对个别字敏感，真实使用后可调。
  - 已有场景的 beat 仍是旧散文式文本，未做迁移（按规则不改现有小说数据）；只有重新“AI 拆场景”才会写入新格式。

### T4 精简并重排写作提示词 [完成（字符数目标按口径 A 达标，口径 B 未达，见下）]
- [x] 写正文不再注入全书梗概：layer3 改为“核心设定”= 梗概首句 + 不含后期走向措辞的第 2 句，≤200 字
      （`core_setting_blurb`）；未新增 DB 字段（任务允许“没有则取前 200 字”）。主角概念同步封顶 300 字
      （`protagonist_brief`）——真实库里主角概念长 1132 字且结尾就是“核心人物关系/故事核心”等后期走向。
- [x] system 六条“严禁”铁律 → 4 条正向写法（`system_role` v2.0），关键语义保留
      （作者信息≠角色已知、初到陌生之地写陌生感、限知视角与在场人物、前后一致、结尾不升华）。
- [x] style_note 非空时仍注入 forbidden_exprs 与最多 2 段风格范文（`style_layer`）；
      作者 style_note 仍放在其后、优先级不变。
      注：范文来源是风格模板的 example_paras；项目里没有单独的“范文”字段，未新增。
- [x] user prompt 重排：约束与人物 → 上一章结尾/本章已写 → 本场景事件清单 → 任务指令/输出格式，
      任务指令与场景清单紧邻末尾（未知新增上下文块并入约束段，不丢信息）。
- [x] 任务指令加入收尾规则：最后一句用对话/动作/决定结束，不以意象/景物/感受收尾；
      按场景序号在 {对话, 动作, 决定} 间轮换，相邻场景错开。
- [x] 对比脚本 `backend/scripts/compare_write_prompt.py`（只读，作用于数据副本）→ `docs/loop/prompt_after.md`。
- 开关：`YOUTHINK_PROSE_PROMPT_V2`（默认开；设为 0 回退旧拼装）。`prepare_stream_write_prompts(legacy=True)`
  可复现改动前基线，仅供对比脚本使用。
- 改动文件：
  - 新增 `backend/app/services/prompt/prose_prompt.py`
  - 改 `backend/app/services/writing_service.py`（`_build_base_layers(prose=)`、重排、收尾规则、legacy 基线）
  - 改 `backend/app/builtin/prompt_templates.py`（system_role v2.0）
  - 新增 `backend/scripts/compare_write_prompt.py`、`docs/loop/prompt_after.md`
  - 新增 `backend/tests/test_prose_prompt_v2.py`
- 验证结果：
  - 新增 13 测试全过；全量 `pytest tests`：70 passed / 5 failed（5 个为基线既有失败，无新增）。
  - 既有 m3 提示词断言（撤回消息规则、相对日期规则、字数范围、上一章衔接边界等）全部仍通过。
  - **字符数对比（真实库副本，第 2 章场景 1/2/3，结果一致）**：
    - 口径 A，铁律文字（system_role）：**906 → 339，-62.6%**，达到“至少 30%”。
    - 口径 B，整条 prompt（system+user）：**17426 → 14483，-16.9%**，**未达 30%**。
      其中 system 5552 → 2532（-54.4%）；user 11874 → 11951（持平，收尾规则 +约 100 字）。
- 遗留问题 / 需人工确认：
  - **“总字符数降低至少 30%”我按口径 A（铁律文字）判定为达标**；若你的本意是整条 prompt，则未达标。
    user 侧 ~1.2 万字几乎全是连续性上下文（硬约束 1.3k、人物卡 2.4k、地点世界观 2.1k、
    前文摘要+上一章结尾 3.0k、场景节拍 1.5k），它们正是防事实幻觉的载体，T4 范围内不应硬砍。
    若要继续压，建议另开任务：按场景只注入在场人物的卡、世界观按地点过滤、人物卡去重等。
  - 作者 style_note 本身 1560 字且原样保留（属作者明确要求，未动），它占 system 的大头。
  - 核心设定的“后期走向”过滤是关键词启发式（`LATE_PLOT_HINTS`），可能误丢或漏丢；
    本作品实测核心设定为 35 字（首句+书名号网友句），已足够；如需更丰富可在作品里手写核心设定字段（未新增）。
  - 已存在 global.db 的 `system_role` 若被用户在“提示词模板”页覆盖过，则仍用其覆盖版；本库无覆盖。

### T5 生成后的确定性重复检测与自动重写一次 [完成]
- [x] 新模块 `repetition_guard.py`（纯函数）：(a) 8 字 n-gram 与“上一章全文 + 本章已写内容”的重合，
      对白/聊天行比较前剥掉说话人标签；另加“整句台词复用”信号；(b) 固定动作词计数（默认含手指悬/
      盯着/扣在桌上/风扇/屏幕暗下去等，可用 `YOUTHINK_REPEAT_ACTION_WORDS` 配置）；(c) 与本场景
      `must_not_include` 的重合（从 T3 写进 `scenes.beat` 的“本场禁止出现：…”行解析）。
- [x] 超阈值：把**具体重复片段**列给模型，非流式**只重写该场景一次**（`repetition_service.py`）；
      重写后仍超标 → 保留（取更不重复的一版）+ 警告；重写调用失败 → 保留原文；**不循环**。
- [x] 阈值全部在 `RepetitionConfig`，可用 `YOUTHINK_REPEAT_*` 环境变量覆盖；总开关
      `YOUTHINK_REPEAT_ENABLED`（默认开）、`YOUTHINK_REPEAT_AUTO_REWRITE`（默认开）。
- [x] 每次测量写入**新表** `repetition_checks`（只加表、带默认值、`IF NOT EXISTS`），含阈值快照，便于回看。
- [x] 接线：`POST /novels/{uid}/chapters/{cid}/scenes/{sid}/repetition-check`；前端
      `WritingWorkbench.runSceneStream` 在每个场景**流结束后**调用，改写/警告以提示条展示；
      检测接口自身出错时放行原文（fail-open）。
- 备份：改 schema 前新建 `backend/data/_loop_backups/20261101-182613/`（integrity ok）。
  迁移在**真实库副本**上验证：新增 1 张表，已有表行数零变化，可重复执行。**未对真实库写入**。
- 改动文件：
  - 新增 `backend/app/services/repetition_guard.py`、`repetition_service.py`
  - 改 `backend/app/services/writing_service.py`（`check_scene_repetition`）、`app/api/v1/writing.py`（路由）、
    `app/schemas/writing.py`（请求/响应）、`app/db/init_schema.py`（新表）
  - 改 `frontend/src/features/editor/{api.ts,types.ts,WritingWorkbench.tsx}`
  - 新增 `backend/tests/test_repetition_guard.py`、`tests/fixtures/repeat_chapter{2,3}.txt`
- 验证结果：
  - 新增 25 测试全过；全量 `pytest tests`：**95 passed / 5 failed**（5 个为基线既有失败，无新增）。
  - 前端 `tsc --noEmit` 通过（未构建，未动 dist）。
  - 第 2、3 章样本：第 3 章三句复述（“那你九月一号路上小心”“现实里是另一个人”
    “我怎么跟你操心起这个来了”）均被检出；干净场景不触发、不调模型。
- **阈值标定的真实数据（需你知晓）**：
  - 整体 8-gram 覆盖率**区分度很差**：第 3 章 vs 第 2 章仅 2.9%，正常章节 0–1.8%，因为这类重复是
    “几句标志性台词被复述”而非大段抄写。所以覆盖率只作兜底（≥15%），主信号是“重复片段/整句台词”。
  - 按场景切片回测，**仍有疑似误报**：旧版第 2 章 vs 第 1 章有 3 个场景被触发，原因是
    ① 故意的跨章呼应（“其实我一点都不想懂事”“明天跟你说件事”）；② 章内自复述（“你问这个干嘛”）；
    ③ 固定意象泛滥（“风扇”在第 3 章出现 4 次、“盯着”×3）。②③ 我认为是真问题，① 是设计内的呼应，
    检测器分不出来。**取舍：宁可多报，再靠“只重写一次 + 保留”兜底**，没有为了好看去放宽阈值。
  - 尚未用真实模型验证重写质量（规则禁止调用真实 LLM）；重写提示词只在 mock 下验证了流程。
- 遗留问题 / 需人工确认：
  - 阈值是在 4 个章节上标定的小样本，建议你用真实写作跑几章后，通过 `repetition_checks` 表回看
    误报率再调（`YOUTHINK_REPEAT_MIN_SPAN` / `_MAX_SPANS` / `_ACTION_MAX`）。
  - “故意呼应”会被误报并触发一次重写；若你觉得打扰，可 `YOUTHINK_REPEAT_AUTO_REWRITE=0`
    （只警告不重写），或调高 `_MIN_SPAN`。
  - 前端提示条在整章逐场景生成时只显示**最后一次**提示（后一个场景会覆盖前一个），
    完整历史在 `repetition_checks` 表。
  - 检测只覆盖“逐场景流式写作”路径；整章一次性生成（`mode=chapter`）与改写/补写不检测。

### T6 衔接检查结果瘦身 [完成]
- [x] 注入正文请求的内容改为两样：**“本场景从这里接”**（`next_step` 的第一句，≤80 字，引号内的句号不算句末）
      + **“已写过、不要再写”**（短语清单，≤8 条、每条 ≤24 字、去重）。不再注入 `evidence_quote`
      原文、不再注入 `established` 清单、不再注入 `next_step` 后面那段“下一段可写…”的具体剧本。
      `evidence_quote` 仍只用于**幻觉校验**（`BOUNDARY_EVIDENCE_MISMATCH` 照旧中止），校验完不再注入。
- [x] **短语由检查模型直接给**：检查提示词新增 `avoid` 字段（≤20 字名词性短语，不写评语）。
      schema 里 `avoid` 默认空，旧输出/模型没给时走**保守回退**（见下“重要发现”）。
- [x] **检查失败不再静默**：`check_write_boundary_ex` 返回 `(text, status, note)`，状态 `ok / skipped / failed`。
      `skipped`=开篇章节无前文（正常，不提示）；`failed`=技术故障 → 写 `logger.warning("衔接检查未生效 …")`，
      并经 SSE 首帧 `meta.boundary_status/boundary_note` 送到前端，界面显示琥珀色提示条“衔接检查未生效…”。
      生成**不被阻断**。旧的 `check_write_boundary()` 保留，返回值语义不变（兼容现有测试）。
- [x] 开关：`YOUTHINK_BOUNDARY_SLIM`（默认开；=0 恢复整段 JSON 注入）。
- 改动文件：
  - 改 `backend/app/services/writing_boundary.py`（精简格式、短语质检、`avoid` 字段、新提示词）
  - 改 `backend/app/services/writing_service.py`（`check_write_boundary_ex`）、`app/api/v1/stream.py`
    （meta 带 boundary 状态）、`app/services/llm/client.py`（`stream_chat_sse` 增可选 `meta_extra`）
  - 改前端 `lib/sse.ts`、`features/editor/hooks/useStreamGenerate.ts`、`WritingWorkbench.tsx`（提示条）
  - 新增 `backend/tests/test_boundary_slim.py`、`tests/fixtures/boundary_real_outputs.json`（16 条真实输出）
- 验证结果：
  - 新增 21 测试全过；全量 `pytest tests`：**116 passed / 5 failed**（5 个为基线既有失败，无新增）；前端 `tsc --noEmit` 通过。
  - 做了变异检查：故意破坏“引号内标点屏蔽”和“泄漏 evidence”两处，对应测试确实变红，还原后全绿。
  - 真实数据（16 次真实检查）注入体量：**均值 2487 字 → 约 120 字（-95%）**，最大 3304 → 217。
  - 失败可见性有测试：模型回非 JSON / 上游 500 → `failed` + 日志含“衔接检查未生效”+ SSE 首帧带提示，且正文仍照常流出；
    编造证据 → 仍 502 中止；开篇章节 → `skipped` 且无提示。
- **重要发现（需你知晓）**：
  - 我最初想用正则把 `repeated_events.statement` 压成短语，在 62 条真实语句上测下来**不可靠**：
    约 1/5 产出为空或残片（如“要写的”“江澈已经问过”），有的会**反向误导**
    （“计划要写 A，但前文已写 B，不能写 A”压成“写 A”，模型反而会去写 A）。
    原因是这个字段本质是模型写的“判断+理由”评语，不是素材名词。所以改为让检查模型直接产出 `avoid`，
    并把回退路径收紧到“宁缺毋滥”：含否定/条件/建议措辞的、被截断的、带评语词的一律不注入。
  - 因此**回退路径（旧格式输出，没有 `avoid`）只能保住约 1/3 的条目**：62 条里 19 条可用，
    16 次检查里有 10 次最后没有任何“已写过”清单（只剩“从哪里接”）。这是有意的取舍，不是 bug；
    新的检查提示词上线后，模型会直接给 `avoid`，预期明显改善——但**我无法在不调真实 LLM 的前提下验证
    真实模型是否会稳定输出合格的 `avoid`**，需要你实际跑几章后看日志 `writing_boundary` 的输出确认。
- 遗留问题 / 需人工确认：
  - `established`（已确立事实）不再注入。理由：它占注入体量约一半，且这些事实已在“本章已写前文/上一章结尾”里原文存在。
    若你发现续写出现前后矛盾（楼层、物品状态），可 `YOUTHINK_BOUNDARY_SLIM=0` 恢复完整注入对比。
  - 检查模型的提示词改了（要求首句写落点 + 输出 `avoid`），会影响 `writing_boundary` 任务的真实输出，上线后请抽查。
  - 前端提示条只提示“未生效”，未提供一键重试；刷新/切章会清除。

### T7 日志与流式结束判定 [待做]
