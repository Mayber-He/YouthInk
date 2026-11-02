# 小说生成链路修复 · 循环进度

> 工作约定：每轮只做一个任务；mock/固定样本，不调真实 LLM；不动现有小说数据；
> schema 改动必须向后兼容（只加列/加表、带默认值），改前已备份。

## 总览（T1–T7 全部完成）

| 任务 | 状态 | 提交 | 要点 |
|---|---|---|---|
| T1 记忆抽取 | 完成 | 3861d38 | 逐条容错 + 引文逐字校验 + 重试 + 兜底(待确认) + 前端失败标记 |
| T2 约束/人物状态 | 完成 | 2fc5227 | 按章过滤补测（字段与逻辑原本就有）+ 起点快照文案 + 只读审计脚本 |
| T3 场景事件清单 | 完成 | 129664d | 事件清单拼进 `scenes.beat`（零迁移）+ 相邻重复校验/重拆 + 章梗概改写 |
| T4 提示词精简重排 | 完成* | 25d7d5f | 铁律 -62.6%；**整条 prompt 仅 -16.9%（未达 30%）** |
| T5 重复检测+重写 | 完成 | 2f69a69 | 新表 `repetition_checks`；阈值是小样本标定，有已知误报 |
| T6 衔接检查瘦身 | 完成 | f264fd7 | 注入体量 -95%；检查失败可见；回退路径只保住约 1/3 条目 |
| T7 日志与结束判定 | 完成 | 53dfcc7 | 新增 2 列；`length` 截断前端不当成功；前端无自动化测试 |
| 修复 衔接证据不匹配中止 | 完成 | 9d4b8bf + 后续 2 次 | 归一化放宽 + 只校验在用字段 + 逐条丢弃 + 重试一次 + 降级不注入；**不再 502 中止**（真实回放 6→0）；检查超时 90→40 秒可配 |

**全量测试**：基线 36 passed / 5 failed → T1–T7 完成时 **146 passed** → 修复初版（9d4b8bf）**155 passed** → 本次修复最终版 **178 passed / 5 failed**（那 5 个是改动前就存在的失败，无新增）。
**真实库**：始终只读；已逐表比对，内容与改动前快照一致。三次备份在 `backend/data/_loop_backups/`（已被 .gitignore 忽略）。

### 需要你人工确认 / 处理的事项（按重要性）
1. **T4 的“降低至少 30%”**：我按“铁律文字”口径判定达标（-62.6%）；按整条 prompt 口径只有 -16.9%，**未达标**。你的本意若是后者，需另开任务压缩上下文块。
2. **所有真实模型行为都没验证过**（规则禁止调真实 LLM）：T1 新提示词能否让真实模型输出合规字段、T3 事件清单质量、T5 重写质量、T6 的 `avoid` 字段是否稳定输出——请实际跑几章后抽查对应 `generation_logs`。
3. **T5 阈值是在 4 个章节上标定的**，存在已知误报（故意的跨章呼应会被判重复）。看 `repetition_checks` 表再调；嫌打扰设 `YOUTHINK_REPEAT_AUTO_REWRITE=0`。
4. **前端改动没有自动化测试，也没在浏览器里实跑**（只过了 `tsc`）：T1 的失败标记、T5 的重复提示条、T6 的“衔接检查未生效”提示条、T7 的截断处理。请手动走一遍。
5. **提示词模板无需手动重置**：复核确认 global.db 的 `prompt_templates` 表当前是 0 行，`SettingsRepository.list_prompt_templates()` 读取时会把代码内置模板合并进来，因此界面“提示词模板”页显示的就是 T3/T4 的最新文案。
6. **新 schema 会在你下次启动后端时自动应用到真实库**：`repetition_checks` 新表、`generation_logs` 新增两列（均为只加、可空/带默认、幂等）。我没有在真实库上执行过迁移，只在副本上验证。
7. **超出任务字面的几处决定**，请确认是否接受：T4 把“主角概念”也封顶 300 字；T6 不再注入 `established`；T7 把 `content_filter` 也当截断；T1 里 `constraint_checks` 的证据豁免逐字校验。
8. 仍存在的 5 个基线失败（M2 时间线/滚动大纲、M3 AI 腔扫描、M5 百章压测）不是本轮引入，也没有修。

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
  - 曾担心 global.db 里的 `generate_scenes` 模板停留在 v1.1；复核后确认该表当前 0 行，
    `list_prompt_templates()` 读取时合并代码内置模板（v2.0），界面显示的就是最新文案，无需手动重置。
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
      `evidence_quote` 仍只用于**幻觉校验**，校验完不再注入。
      （注：T6 当时仍沿用“一条对不上就 `BOUNDARY_EVIDENCE_MISMATCH` 中止”的旧行为；该行为已在后续
      “衔接检查 BOUNDARY_EVIDENCE_MISMATCH 频繁中止生成”修复中改为逐条丢弃 + 重试 + 降级，不再中止，见文末。）
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

### T7 日志与流式结束判定 [完成]
- [x] `generation_logs` 新增 `temperature REAL`、`finish_reason TEXT`（**可空，不回填**）。新库建表即带列；
      旧库启动时由幂等的 `ALTER TABLE ADD COLUMN` 补上。旧行保持 NULL = “当时没有记录”，
      没有编造成 `stop`。流式和非流式（`complete_chat`）都记录。
- [x] 流式区分结束原因：解析 `choices[0].finish_reason` 并归一化（`max_tokens` 等别名 → `length`）。
      `done` 帧新增 `finish_reason` 和 `truncated`（`length`/`content_filter` 为 true）。
      `truncated` 时服务端仍正常发 `done`（不是 error），由前端据此决定不当成功。
- [x] 前端不再把截断当成功：`useStreamGenerate` 的写正文 / 改写 / 补充三条路径遇到 `truncated`
      **都不走成功回调**——写正文走“中断”分支（还原原稿、不保存、不自动审查、整章循环停下，
      不让半截文本当上文喂给下一个场景）；改写不替换选区；补充不当候选。并显示明确原因
      （长度上限 / 内容过滤）。
- 改动文件：
  - 改 `backend/app/services/llm/client.py`（`normalize_finish_reason` / `is_truncated`，流式+非流式解析与落库）
  - 改 `backend/app/db/init_schema.py`（建表列 + 迁移）、`app/db/repositories/novel_repo.py`（落库参数）
  - 改前端 `lib/sse.ts`、`features/editor/hooks/useStreamGenerate.ts`
  - 新增 `backend/tests/test_finish_reason.py`
- 备份：迁移前新建 `backend/data/_loop_backups/20261101-191746/`（integrity ok）。迁移在**真实库副本**上验证：
  新增 2 列、64 条既有日志逐字节不变、旧行新列全 NULL、已有表行数零变化、幂等。**未对真实库写入**。
- 验证结果：
  - 新增 30 测试全过，含你要求的两种结束情况（`stop` 正常、`length` 截断）；全量 `pytest tests`：
    **146 passed / 5 failed**（5 个为基线既有失败，无新增）；前端 `tsc --noEmit` 通过。
  - 变异检查：故意改坏 3 处（未知值当 stop、同帧 finish_reason 读不到、从不判截断），11 个测试变红，还原后全绿。
  - 覆盖的真实世界边角：finish_reason 与正文在同一帧；末尾单独的 usage 帧（choices 为空）；
    上游从不发 finish_reason（按未知处理、不误报截断）；畸形帧；上游连接中断（记为 `error`）。
- 遗留问题 / 需人工确认：
  - **前端没有单元测试框架**（无 vitest/jest），`useStreamGenerate` 的截断分支只过了 `tsc` 类型检查，
    **没有自动化测试，也没在浏览器里实跑过**。建议你手动验证一次：把某场景目标字数/模型最大输出调到很小
    触发 `length`，确认出现“因达到长度上限被截断…已保留原稿”提示且正文没有被保存。
  - 上游若**从不发** finish_reason，截断无法被发现（只能当成功）——这是协议限制，不是 bug。
  - 非流式调用（记忆抽取、大纲、场景拆分等）只**记录** finish_reason 并在被截断时打 warning，
    **没有改变行为**（不抛错、不重试）。被 length 截断的 JSON 仍会在解析层失败，但现在日志里能直接看到原因。
  - 暂无读取 `generation_logs` 的接口/界面，`temperature`/`finish_reason` 目前只能查库看到。
  - 内容过滤（`content_filter`）我也按“截断”处理了，任务只要求 `length`，这是顺手加的，需要你确认是否接受。

---

### 修复 · 衔接检查 BOUNDARY_EVIDENCE_MISMATCH 频繁中止生成 [完成]

**结论先说**：T6 之后，这道会中止生成的校验拦的是**根本没有注入提示词的字段**。它拦下的 10 条引用里，
2 条只是标点位置不同，2 条是把两处真实原文拼在一起，6 条是模型改了字（换人称/人名、调语序）。
现在改为：逐条丢弃；只校验真正注入的字段；必要时带纠错提示重试一次；仍不行就降级提示。**任何情况下都不再中止生成。**

#### 一、调查（只读；脚本放在临时目录，没有写入项目，也没有改小说数据）

**1. 修复前的校验逻辑**（`writing_boundary.check_writing_boundary`）
- 对 `established` 与 `repeated_events` 的**每一条** `evidence_quote`，判断 `归一化(引用) in 归一化(前文全文)`（子串包含）。
- 归一化只做两件事：把常见标点样式折叠成统一形式（“”→"、，→,、。→. …），并去掉全部空白。
  **不去标点**，所以标点出现的“位置”不同仍然判不匹配。
- 只校验这两个字段的 `evidence_quote`；`statement`、`next_step`、`avoid` 不校验。
- **任意一条**不匹配就 `raise BOUNDARY_EVIDENCE_MISMATCH`（HTTP 502），整次生成中止。

**2. 日志里能不能找到失败的调用？** 能找到调用，但没有“被中止”的标记。
- `complete_chat` 在模型返回后、校验之前就写入 `generation_logs`（`task_type=writing_boundary`），
  所以每次失败调用的**原始输出**和**完整 prompt（含传给模型的前文）**都在库里。
- “被中止”这件事本身没有落库（只有一条控制台 WARNING），所以我是把每条日志的输出用旧逻辑**回放**来判断的。
- 数据范围：真实库 6 条 + 三份备份里的 16 条，按 (prompt, 输出) 去重后共 **22 次调用、361 条证据**。

**3. 每条不匹配引用的分类**（共 10 条）：
- **(a) 纯格式漂移 2 条**：句末标点在引号内外位置不同（`走读的。"` vs `"走读的"。`）、
  开引号前省了“对了，”。旧归一化只折叠标点样式、去空白，仍判不匹配。
- **(b) 引用来自前文以外 0 条**：没有一条是凭空编造的前文外内容。
- **(c) 拼接多处原文 2 条**：把前文两处真实原句中间省略一段后接在一起（每一段单独都能找到，整条找不到）。
- **(d) 其他（语义改写）6 条**：人称替换（他→她）、人名/代词互换（他→江澈）、语序调换（第二天我→我第二天）等。
  (c)(d) 是模型**真的改了原文**，归一化解决不了，只能逐条丢弃。

**4. 失败分布**：不集中在第 2 章，也不集中在第一个场景。
- 按调用：第 1 章 1/6 次会中止，第 2 章 5/16 次，两章都会中招（样本小，比例仅供参考）。
  真实库“最近 4 次写作 3 次中止”只是窗口太小造成的表象——那 4 次恰好都在第 2 章。
- 按场景：首场景 3/10、非首场景 3/12，没有明显偏向。
- 同一份 prompt（temperature 0.2）在不同次回放里会一次通过、一次不通过，说明主要来源是模型输出的随机性，
  不是某章/某场景特有的问题。

#### 二、修复

**1. 归一化（对应第 1 条）**
- 引用与前文先做**同一套**归一化：`NFKC`（全角/半角、省略号等兼容形式统一）→ `casefold` →
  **只保留 Unicode 类别 L（字母，含汉字）和 N（数字）**，即去掉全部空白、标点、引号、破折号、省略号。
- 没有采用“只统一标点样式”：真实失败里有标点**位置**漂移（句号在引号内外不同、开引号落在被省掉的“对了，”之后），
  只统一样式仍会误杀。
- 归一化后为空的引用一律不认（避免 `'' in s` 恒真）。
- 语义改写仍会被拒绝：人称、人名、语序差异在归一化后依然存在。

**2. 逐条处理（第 2 条）**
- `_partition()` 逐条判断，`_filter_verbatim()` 把对不上的条目从结果里剔除、合格条目保留；
  **一条不匹配不再影响其他条目，也不再中止生成**。
- 被丢弃的“确实会被注入的字段”证据按条记 `logger.warning`（含最多 3 条引文样例，默认日志级别可见）；
  未使用字段的丢弃只记 INFO，避免噪声。

**3. 字段使用审计（第 4 条）**
T6 之后哪些 evidence 字段真正进提示词，随开关/模型输出而变：
- **默认瘦身 + 模型给了 `avoid`**：注入只有 `next_step` + `avoid`，**没有任何 evidence 字段被使用**；
  `established` / `repeated_events` 的引用对不上既不会重试也不会降级（只记 INFO）。
- **默认瘦身 + 模型没给 `avoid`**：只有 `repeated_events.statement` 被压缩成“已写过”短语，校验它的 `evidence_quote`。
- **`YOUTHINK_BOUNDARY_SLIM=0`（旧整段 JSON）**：`established` 与 `repeated_events` 都注入，两者都校验。
- 未被使用的字段直接从过滤结果里清空，不参与任何判定。

**4. 重试与降级（第 3 条）**
- `MAX_ATTEMPTS = 2`（首次 + 最多重试一次），两种触发共用同一份额度：
  (i) **整体失败**（调用异常/超时/JSON 解析失败）；(ii) **会被注入的证据全部被丢弃**（且模型本来给了证据）。
- 每轮超时**不再是硬编码 90 秒**：默认 **40 秒**（最坏 2×40=80 秒），
  可用 `YOUTHINK_BOUNDARY_TIMEOUT_SEC` 覆盖（限制在 5–120 秒，越界夹紧并记 warning）。
- 两种重试提示都带固定句：**“引用必须是前文中连续的原文片段，不要改动标点，不确定就不引用。”**
  证据类重试另加“请直接从【已写正文】整段复制，不要替换人称或人名，不要跨句拼接”。
- 重试后仍失败 → `BoundaryResult(text="", note="…已重试一次")`：**不注入任何衔接内容**
  （`next_step`/`avoid` 也不注入，保证“未生效”字面为真）。`check_write_boundary_ex` 返回
  `("", "failed", "衔接检查未生效（…）")`，界面琥珀色提示条 + `logger.warning`，**正文照常生成**。
- 兼容：`check_writing_boundary()` 仍返回字符串；新增 `check_writing_boundary_result()` 返回
  `BoundaryResult(text, dropped, note)`；`BOUNDARY_EVIDENCE_MISMATCH` 错误码与 `raise` 已彻底移除。

**改动文件**：
- `backend/app/services/writing_boundary.py`（归一化、字段使用审计、逐条过滤、重试、`BoundaryResult`、移除硬中止）
- `backend/app/services/writing_service.py`（`check_write_boundary_ex` 用新结果；降级不注入、不 re-raise）
- `backend/tests/test_boundary_slim.py`（归一化/逐条丢弃/字段使用/重试/降级/真实样本回放/SSE 端到端）
- `backend/tests/test_writing_quality.py`（原 `test_prewrite_boundary_evidence` 断言 502，改为两种输入都 200、正文照常生成）
- 新增 `backend/tests/fixtures/boundary_evidence_failures.json`（调查中 9 次真实失败调用的 prompt/输出 + 10 条不匹配引用及分类）
- `docs/loop/PROGRESS.md`

**验证**：
- **真实数据回放**（22 次调用、361 条证据）：**0 次中止**（原先 6 次）、**0 次重试**、**0 次降级**；
  全字段校验下按条丢弃 8/361（2.2%）。默认瘦身模式下，真实库现有 6 次调用都带 `avoid`，
  证据字段不参与判定；备份里的老调用有 2 次没有 `avoid`，各有 1 条在用证据被丢，不影响其余内容。
- **真实失败样本测试**：fixture 里 2 条 (a) 现在能匹配；2 条 (c) 与 6 条 (d) 仍被拒绝；
  另有测试确认拼接引文的中间确实跳过了一段真实原文。9 次真实调用各重放一次，全部通过（无重试、`note == ""`）。
- **变异检查**：12 个变异体，11 个被测试杀死（含“恢复一条不匹配就中止”“归一化退回只去空白”
  “未使用字段也校验”等）；唯一存活的是 `degraded-still-injects`——服务层本来就会丢弃降级文本，端到端看不到差异。
  已补两个直接调用 `check_writing_boundary_result()` 的测试锁定该契约，且已执行通过。
- **全量测试**：`pytest tests` **178 passed / 5 failed**（5 个为基线既有失败，无新增）；
  边界相关两个模块 **63 passed**（含前面提到的两个 direct-call 测试）；
  新增超时测试 2 个通过（默认 40、可配 30/45、非法值回退、越界夹紧、配置值传入 `complete_chat`）。
- 真实库全程只读，size/mtime 未变；未调用真实 LLM。

**需你知晓 / 确认**：
- **硬中止不存在了**：证据对不上只会丢该条/重试/降级提示，绝不阻断生成。若你希望某些情况仍然中止，请给判定标准。
- **降级时什么都不注入**：这是刻意选择——既然界面说“未生效”，就不能偷偷用同一份结果里的 `next_step`/`avoid`。
  代价是这次生成完全没有衔接提示。
- **默认模式（瘦身 + `avoid`）下，证据校验实际不拦截任何东西**：T6 设计的幻觉护栏在默认路径上不再起作用。
  这是“只校验真正注入的字段”的直接结果（按你的第 4 条）。若你仍想保留护栏，需要让 `avoid` 依赖证据，
  或把 `established` 重新纳入注入——请确认取舍。
- **重试的等待已缩短**：每轮超时默认 40 秒（原硬编码 90 秒），两次尝试最坏 **80 秒**；
  `YOUTHINK_BOUNDARY_TIMEOUT_SEC` 可配（5–120 秒）。
- **真实模型行为未验证**（规则禁止调真实 LLM）：重试提示能否让真模型给出可逐字复制的证据、降级实际频率，
  需你跑几章后看 `writing_boundary` 日志（`dropped … evidence` / `had no verbatim evidence` / `衔接检查未生效`）。
- **归一化比“统一标点”更宽**：去掉全部标点后，不同标点的句子可能被视为同一句。`evidence_quote` 只做存在性判断、
  不参与语义推理，此放宽可接受；若未来把它用于语义判定需重新评估。

#### 三、按你的反馈收尾（本次提交）

- **默认模式不校验 evidence：接受**。`avoid` 目前不参与校验，而模型在整理“已发生事件”时可能把主语写错
  （真实样本里出现过“他→她”）。实测时重点看 `writing_boundary` 日志里 `avoid` 的内容是否与前文一致；
  若经常出错，再加一个**宽松的存在性检查**（例如 `avoid` 短语归一化后须出现在前文/上一章结尾中），
  本次先不做。
- **降级不注入：接受**。上一章结尾与本章已写正文本来就在请求里，衔接提示只是辅助。
- **超时已缩短并做成配置项**：每轮 `timeout_sec` 从硬编码 90 改为 `boundary_timeout_sec()`，
  默认 **40 秒**；环境变量 `YOUTHINK_BOUNDARY_TIMEOUT_SEC`（5–120 秒，非法值回退默认、越界夹紧）。
  两次尝试最坏 **80 秒**（原 180 秒）。新增测试覆盖默认值/30/45/非法值/越界夹紧，
  以及“配置值确实传给 `complete_chat`”（2 个测试均通过）。
- **归一化去全部标点：接受**（只做存在性判断）。
- **真实模型实测是下一步**：本任务仍只用 mock/固定样本，没有调用真实 LLM。
- **本次验证**：全量 `pytest tests` **178 passed / 5 failed**（无新增失败）；边界两个模块 63 passed。


## 2026-11-01：第 2 章衔接检查 ReadTimeout 调查与修复

用户约束：先只读调查，不调用真实 LLM，不修改小说数据；修复后补测试并提交。

调查明细见 [BOUNDARY_TIMEOUT_INVESTIGATION.md](BOUNDARY_TIMEOUT_INVESTIGATION.md)，包含活动库全部 7 次检查的输入/输出字符数、elapsed_ms、失败场景还原、不确定性、HTTPX 超时定义和流式利弊。

- 当前成功检查输出 1525–3235 字符，耗时 24.765–71.991 秒，3/7 超过 40 秒；40 秒偏短。吞吐折算中位数约 44.9 字符/秒，只能粗估，包含输入处理、等待及可能的推理。
- 本轮第 2 章场景 4/5 的正文日志 #88/#89 无衔接提示；场景 6 的 #91 有提示。2 个场景缺少提示。失败调用没落库，不能声称精确拿到了失败请求；根据 #90 同轮计划与 #88/#89 前文还原，上一章全文 2779 字，本章已写 0/1463 字，prompt 5585/7044 字符（含日志标签；重试再加 78 字符）。
- 默认首次超时恢复 90 秒；环境变量 `YOUTHINK_BOUNDARY_TIMEOUT_SEC` 保留（5–120 秒）。重试 HTTP 空闲超时 = min(120, 首次 × 1.5)，新增单调时钟 150 秒共享墙钟预算，并通过 `asyncio.wait_for` 取消超时请求。默认首次耗满 90 秒时，重试剩 60 秒；首次快速失败时重试可获更长等待。
- HTTPX 的非流式读取也是按相邻网络块空闲超时，并非整次请求总时限。流式仅可能改善上游发包节奏，仍需处理首块等待、缓冲、半截 JSON、usage/finish_reason 与总预算。本次不迁移流式，不改公共 HTTP 客户端或正文 SSE。
- 提示词限制 established/repeated_events/avoid 各最多 5 条，statement/evidence_quote/avoid 每条最多 30 字、next_step 最多 80 字。解析合法冗长 JSON 时不报长度错误，输出前截短；完整引用先校验，瘦身模式完整判断句先通过否定安全检查，再抽短语。兼容完整模式省略不宜截短的长否定/条件判断，防止把“不是已发生事件”剪成肯定事实。
- 降级信息补充总耗时、每次原因/耗时，应用 warning 含 chapter_id、scene_id、HTTP 空闲超时和实际等待额度；服务层保留完整诊断。成功检查日志传入 scene_id，便于关联场景。降级仍不注入衔接内容、不阻断正文。
- 独立审查发现并修复了截短后丢失否定的风险，默认瘦身与兼容完整模式均补回归测试。

**最终验证**：
- 后端全量 `python -m pytest tests -q -p deny_network --basetemp=.pytest-boundary-complete`：**186 passed / 5 failed**（261.29 秒）。独立 HEAD 基线 **178 passed / 5 failed**（298.25 秒），5 个失败项和断言完全一致，无新增失败。
- 最终衔接专项 **61 passed**；前端 `node --test tests/useStreamGenerate.test.mjs` **4 passed**，`npm run typecheck` 通过，`git diff --check` 通过。
- 新增主要回归在旧实现上 5 failed / 1 passed；截断否定语义的两种回归分别先验证失败，再修复通过。独立代码审查最终无剩余问题。
- 全量的 5 个既有失败：`test_character_timeline_temporal_query`、`test_float_sort_order_and_rolling_chapter_generation`、`test_rolling_generation_uses_retained_chapter_and_rejects_reversed_batch`、`test_ai_smell_scanner_and_sse_streaming`、`test_m5_hundred_chapter_long_book_stress_and_temporal_isolation`。本次不改动这些路径。

所有模型响应使用 mock/已有固定样本，运行时额外阻断外部 socket 连接；测试数据库使用临时目录。调查前记录的 13 个现有数据库/密钥文件 SHA-256 核对未变化。


## 2026-11-01：登记后续任务 T8–T12（仅计划）

- 当前分支没有 `docs/loop/PLAN.md`；按本次要求及本文已有工作约定新建该文件，未重建或改写 T1–T7 历史。
- T8–T12 均为 **待执行**：T8 约束解除判定与待确认保护；T9 时间锚点与相对时间检测；T10 活跃人物判定；T11 RAG 去重；T12 记忆精简。各项已列明改动范围、回归验证及人工确认事项。
- 保留每轮一个任务、验证、更新进度、一个 commit、禁止真实 LLM 和禁止修改小说数据的总规则；T8 恢复 SQL 只出草稿，必须由用户决定是否手动执行。
- 本轮验证：逐项核对 T8–T12 要求及任务编号/待执行状态；确认原有 PROGRESS 内容逐字节保留，已有 `eval_export.md` 未变；`git diff --check` 通过。本轮仅改文档，未运行应用测试、未访问小说数据库、未调用 LLM。
- 本轮没有代码实现或功能验收结果。执行结果与需人工确认的具体数据，留待每项任务完成后分别记录；下一轮从 T8 的只读调查开始。


## T8 完成：约束误解除保护（2026-11-01）

- 只读确认江澈/裴南栀约束 #1–#11 已 resolved 且有效期止于第1章，判定记录却描述“未涉及/未违反”；定稿前备份均 active/NULL。定稿只入 pending，人工确认队列项才停用约束，无法判定当时逐条或批量确认。证据与未执行、默认 ROLLBACK 的恢复 SQL 见 `constraint_incident.md`。
- 抽取提示词统一为仅报告真实违反/剧情正式解除；解析 resolved 要求正文逐字连续引文（支持 source_quote 别名），丢弃明显未涉及/未违反说明；仓库写入再校验一次引用，仍只入待确认队列。保留用户明确确认后应用判定的流程，未自动恢复旧数据。
- 验证：新增10项专项通过，含真实解除/引文漂移/不涉及/提示词实际拼装/仓库 pending；既有定稿测试补了确认前约束仍 active 断言。独立 HEAD+T8 源码快照全量 **196 passed / 5 failed**（225.18秒），失败项与既有基线一致；避免后续任务文件并行变更混入此结果。`git diff --check` 通过。
- 人工事项：审阅11条约束及恢复草稿，决定是否手动执行。逐字引文仅证明引用真实，正式解除的语义仍由用户确认；已有错误记录本次未修改。


## T9 完成：时间锚点与跨章相对时间（2026-11-01）

- 上一章衔接块标明前后章 story_time 与可确定天数；支持中文/数字日期及中文逐位年份。无年份只计算在平/闰年都相同且不倒退的间隔；跨年、未知纪年、多日期或缺失不猜补，在提示和上下文面板 role=alert 中提醒补 story_time。写明不可用昨晚/昨天/今早指称上一章。
- 记忆抽取请求注入本章 story_time，要求 state_changes/facts/foreshadowing 的明天/下周/过几天改成相对本章时间或确定日期。
- 间隔>1天且正文有昨晚/昨天/昨夜，确定性检测通过 T5 的一次重写/仅警告开关；关闭总检测时不触发。新增 time_hits 与间隔信息进入检测记录和重写提示，不新增模型调用次数。
- 验证：T9阶段全量 **218 passed / 5 failed**（284.96秒），仍为既有5项；审查补了中文年份/未知纪年回归与实际抽取提示，T9+T10专项合计 **40 passed**。前端现有及新增提醒测试5项通过，typecheck通过。原错把中文年份忽略为月日的问题已先复现再修复。
- 人工事项：补充无法解析的故事日期/年份；当前真实小说的模糊 story_time 本次不写回。相对时间规则按用户要求词面触发，可能把与上一章无关的“昨天”也列为疑似问题，需要抽查警告。


## T10 完成：在场名单决定活跃人物（2026-11-01）

- 节拍中的“本场禁止出现”行从人物名字匹配中剔除；只处理当前选中的场景，避免其他场景带入人物卡、认知或约束。
- 非空 character_ids 优先，其次节拍显式“在场人物”名单（含别名）；显式名单不再被梗概、其他节拍甚至矛盾的 POV 扩充。无名单时保留原有 POV/梗概/有效节拍推断；主角兜底也不会带回仅在禁止行出现的名字，显式空/未识别名单不触发兜底。
- 验证：初始6项缺陷复现；13项临时数据库集成测试通过，覆盖人物卡、认知和硬约束，连同T9专项共40项通过。HEAD+T10独立快照全量 **236 passed / 5 failed**（298.04秒），仍为同5个基线失败；代码审查无剩余问题。
- 人工事项：若显式名单与 POV 矛盾，当前以名单为准，需要用户校正场景信息；本次未改已有场景数据。


## T11 完成：RAG 历史片段去重（2026-11-01）

- 写作上下文的向量检索排除当前章和上一章，检索后再次防御过滤；候选完整片段与上一章末1500字符或本章已写正文存在连续≥20字符重叠（忽略空白）即丢弃，19字符不丢弃。
- 正文生成/补写传入当前未保存编辑内容；上下文预览没有编辑内容参数时用当前最新保存版本。检索不存在、为空或全被过滤时不输出 rag_history 区域及标题；不修改向量数据。
- 验证：缺陷先复现，纯过滤与上下文/真实请求拼接测试9项通过（包含生成和补写传递未保存前文的正反例）；活跃人物+RAG阶段21项通过。独立快照全量 **244 passed / 5 failed**（310.48秒），仍是同5个既有失败；随后补充请求转发测试单独通过。代码审查无阻断问题。
- 局限/人工事项：GET 上下文预览按已保存正文去重，可能与含未保存编辑内容的实际生成请求有差异；抽查保留的旧章片段是否仍有价值。阈值固定为本次要求的20字，本次不调整历史记录。


## T12 完成：精简抽取与正文记忆注入（2026-11-02）

- 抽取提示词要求 facts 最多8条，只保留影响后续的关系变化、承诺、秘密、关键物品/地点状态；排除看相册/收藏照片等一次性动作，同义内容只留一条。伏笔只收有明确回收可能的内容。不会重新抽取、清洗或删除已保存记忆。
- 注入事实最多6条、伏笔最多4条，先按近章排序、同章优先 locked 事实，再按 id；去重后再截条数，允许用后续有效候选补齐。只比较实际启用的章节摘要，摘要关闭时不能误删相同事实/伏笔。
- 去重采用规范化完整摘要/完整句子分句匹配，保留部分重叠、转述、不同主语和否定语义。冒号不是独立断言边界，不把“否认：某事实”中的后半句单独当成重复事实。
- 已保存第1章真实 memory_extract #81 输出、正文 v10 及 provenance 三份固定样本：输出8519字符、正文2779字符，SHA-256 校验与现有导出一致；测试不依赖未跟踪的 eval_export.md，不调用真实模型、不修改样本原文，也不混用旧#77。
- 验证：先复现提示词/注入上限/关闭摘要/否定及转述误删问题，再修复。T12专项7项通过，连同已有记忆抽取和RAG相关25项通过；最终T8–T12合并专项66项通过。最终全部代码全量 **252 passed / 5 failed**（217.22秒），5个失败项与独立旧基线逐项一致，无新增失败。前端全部5项通过，typecheck和diff检查通过。
- 局限/人工事项：是否影响后续、同义语义和伏笔回收可能性只能靠抽取提示词和后续人工抽查，本次mock不证明真实模型会严格遵守；重要性目前使用已有 locked 状态，不新建语义打分或数据库字段。
- 补充T8调查表述：事故报告已明确当前代码调用链不等于历史操作者证明；现有 confirmed/origin/source_hash 不能单独证明由用户手动确认或由历史代码自动确认。

## T8–T12 本轮最终验证与交付（2026-11-02）

- 用户授权连续完成五项；各任务分别验证、记录进度并创建一个本地commit。
- T8：`36ff817`；T9：`e4ddb8f`；T10：`9f0d598`；T11：`6014ac0`；T12为本次提交。
- 完整后端：`cd backend` 后运行 `python -u -m pytest tests -q -p deny_network --basetemp=.pytest-t8-t12-final-all`，**252 passed / 5 failed**。本轮临时 deny_network 插件阻断外部网络，仅放行Windows事件循环需要的本地回环；所有上游模型调用使用mock/用户已有固定输出。
- 专项：`test_constraint_resolution_safety.py` 10项、`test_story_time.py` 27项、`test_active_characters.py` 13项、`test_rag_dedup.py` 9项、`test_memory_compaction.py` 7项，合计**66 passed**。
- 前端：`node --test tests/*.test.mjs` **5 passed**；`npm run typecheck` 通过。
- 5个既有失败仍为M2人物时序/滚动章节三项、M3流式写作一项、M5长书时序一项；和本轮前已验证的独立基线一致，不掩盖为全绿。
- 现有57个数据库、密钥和SQLite侧文件的SHA-256与本轮只读调查前一致；未调用真实LLM、未执行恢复SQL、未重启真实服务、未迁移或修改小说数据。
- 需人工处理：审阅并决定是否运行 `constraint_incident.md` 的恢复SQL；补无法确定的 story_time；抽查场景名单、保留的RAG片段和新模型输出的记忆质量。GET上下文预览按保存版本去重，含未保存内容的实际生成请求可能与预览不同。


## 重新定稿的记忆批次与事务修复（2026-11-02）

### 第0步：真实库只读报告

- 详见 `memory_state_report.md`：使用 SQLite mode=ro/query_only=ON 和单次读取事务统计 origin × 确认状态 × is_stale；facts 的确认字段为 status，其余为 confirm_status。
- facts15、character_state_changes7、cognitive_records5、relationship_changes1、foreshadowing4、constraint_checks11，共43条；均 extracted/confirmed/is_stale=0，全部来自第1章《吃一口软糖》。六表 manual 均为0，无 manual 来源章节可列。
- 本次不重分类历史记录，也不据这些字段推断过去操作者；既有 manual 记录的保留策略通过隔离样本测试。

### 改动与行为

- 普通确认只变更确认状态，保留 origin/source_hash；携带 updated_text 的普通确认不会编辑内容。只有 action=edit 且正文内容实际变化才转 manual；同文本编辑保留来源。伏笔真正修改描述、回收区间或状态也转 manual，仅确认或不变的字段不转。
- 待确认队列（含各状态筛选）和伏笔列表默认排除 stale。单条/批量确认或编辑、直接伏笔更新都拒绝失效条目，返回409 MEMORY_ITEM_STALE；写入时再次使用 is_stale=0 条件，避免检查后失效的竞态。过期条目可丢弃，但不会被复活或夹带改文；不存在条目404。
- 摘要模型、记忆抽取与解析、embedding 计算先完成，不持有 SQLite 写事务。随后 BEGIN IMMEDIATE 短事务校验最新版本ID/正文哈希，统一完成旧抽取批次失效、新记录插入、章节摘要upsert、FTS和章节元数据发布。异常整体回滚 SQLite，摘要始终只有同章一行。
- 向量只预计算在事务外；通过版本校验后，在写锁内最后同步发布缓存，不再让被拒绝的旧定稿覆盖新版本索引。向量发布失败也会回滚尚未提交的SQLite变化。备份、已完成的生成调用日志及文件型向量缓存不是SQLite事务资源；极端SQLite commit失败不具有跨介质原子提交保证，本次未扩展成跨文件事务。
- 整批抽取失败时追加的兜底事实强制pending，不使旧批次失效；同一正文哈希已有有效摘要时保留该摘要。首次没有有效摘要仍创建摘要/待确认兜底；不会把已失效旧记忆重新置为有效。
- 真正人工创建/编辑的 manual 记忆不被重新定稿覆盖。约束判定仍进入pending，重新抽取不自动应用或回滚约束状态；作者明确确认判定后应用状态的现有流程保留。
- 不需要新字段或schema迁移；未修改真实库或重新运行真实章节定稿。

### 验证

- 新增 `test_memory_queue_freshness.py` **81 passed**，覆盖六类来源保留、真实编辑、stale过滤/拒绝、并发条件写入、直接伏笔更新与批量失败回滚。
- 新增 `test_refinalization_transaction.py` **21 passed**，覆盖连续定稿单一有效批次、manual保留、摘要唯一、模型/embedding无写事务、中途/FTS/索引失败回滚、兜底保护、约束状态不变、版本新增及原地改稿409。
- 新旧相关模块联合 **116 passed**。缺陷先红后绿；独立代码复审通过。
- 全量 `cd backend` 后 `python -u -m pytest tests -q -p deny_network --basetemp=.pytest-refinal-full`：**354 passed / 5 failed**（219.44秒）。5项失败与修复前全量逐项一致（M2时序/滚动3项、M3流式1项、M5长书时序1项），无新增失败。模型响应均mock，内存/临时测试库；本轮临时deny_network插件阻断外部网络。
- 前端 `node --test tests/*.test.mjs` **5 passed**；`npm run typecheck`通过；`git diff --check`通过。
- 本轮开始与提交前，真实数据目录57个数据库/密钥/SQLite侧文件SHA-256一致；未调用真实LLM、未写真实库、未重启服务。已有 `eval_export.md` 不纳入本次提交。
- 生效方式：本次只修改并提交源码，后端服务下次重启后加载修复；现有记录不会被自动清理或迁移。


## 2026-11-02：登记后续任务 T13–T16（仅计划）

- 在 `docs/loop/PLAN.md` 末尾新增 T13–T16，均标记为**待执行**，沿用每轮一个任务、独立验证、更新进度、一个 commit、不调用真实 LLM、不修改小说数据的总规则。
- T13 自动重写保守化与时间同义词：重写 prompt 加时间提示、只改被标出的重复片段、时间同义词（前一晚/前晚/前一天/前天/头天/隔夜）按实际相隔天数判断；用场景 3 初稿/重写样本断言“前一晚”检出、“那天晚上”不误报。
- T14 一致性审查逐条容错：`ref_label`/`ref_id` 允许 `None`，`issues` 逐条校验、不合格丢弃并记日志；审查与记忆抽取超时做成环境变量（默认 150 秒，范围 30–300，一次重试共享总预算）；用失败审查的 4 条原始 JSON 断言全部保留。
- T15 规划提示词：`generate_chapter_scenes` 注入上一章人物口癖/句式（3–5 条，仅取原文发言）；呼应节拍必须指明依据；“必须发生”需含内心判断与决定、“本场禁止出现”需写对方不得察觉/回头/回应；写正文不得复用上一章描写句。
- T16 上一章结尾片段：评估缩短末 1500 字或优先保留对话/动作、避开景物描写，给出利弊；实现为配置项并补测试，默认行为变化需在 `PROGRESS.md` 说明。
- 样本位置已核对：场景 3 初稿/重写 prompt 与输出见 `docs/loop/live_eval_export.md`（散见 `live_scene_3.json`、`live_calls.json`）；失败一致性审查原始 JSON 见 `docs/loop/live_test_log.md:189`。这些现场材料按既有约定不纳入提交。
- 本轮仅改文档，未运行应用测试、未访问/写入小说数据库、未调用 LLM；T13–T16 均无实现或验收结果。下一轮从 T13 开始。


## T13 完成：自动重写保守化与时间同义词（2026-11-02）

- 重写提示词（`rewrite_repetition`）新增时间锚点：上一章/本章 `story_time`、相隔天数；日期缺失时写“未指定”，不猜补。按实际天数列出禁止的相对时间词（`大前天`=3 天、`前天`=2 天，其余=1 天），并明确要求正文原有时间表述（如“那天晚上”）原样保留。
- 重写指令由“整场换用全新措辞”改为**最小改动**：只改写被标出的重复片段，其余字词、语序、人物动作和剧情原样保留；不得新增、删除或调换情节；保留原文最后一句收尾。system prompt 同步强调只改重复片段、时间表述不动。
- 时间检测新增同义词：`前一晚/前晚/前一天/头天/隔夜`，以及按实际天数判断的 `前天`(2 天)、`大前天`(3 天)。仍只在相隔 **>1 天**时检查；相隔 1 天保持原行为，不检查“前天”。长词先匹配并遮蔽，避免“大前天”被“前天”重复计为错误。
- 固定样本 `backend/tests/fixtures/scene3_time_rewrite.json`：场景 3 初稿含“那天晚上”、重写稿含“前一晚”，相隔 7 天。断言重写稿“前一晚”被检出、初稿“那天晚上”不误报。
- 改动文件：`backend/app/services/repetition_guard.py`、`repetition_service.py`、`writing_service.py`；测试 `tests/test_story_time.py`、`tests/test_repetition_guard.py`、新 fixture。
- 验证：T13 专项 `test_story_time.py` + `test_repetition_guard.py` **72 passed**；全量 `python -m pytest tests -q` **374 passed / 5 failed**（214.33 秒），5 项与既有基线逐项一致，无新增失败。全部模型调用为 mock/固定样本，未调真实 LLM；测试使用临时库，未写入小说数据。
- 局限 / 人工确认：① 时间词仍按词面触发，“前一天/隔夜”等可能并非指称上一章（例如“隔夜的茶”），需抽查警告；② 相隔 1 天时不做时间词检查（刻意保持旧行为）；③ 重写能否真正遵守“只改重复片段、保留时间表述”只能实际跑几章后看 `rewrite_repetition` 日志与 `repetition_checks` 记录，mock 通过不代表真实模型效果；④ 未清洗既有 `repetition_checks` 或正文数据。


## T14 完成：一致性审查逐条容错与可配置超时（2026-11-02）

- `ConsistencyIssue` 的可选文本字段（`ref_label`、`evidence_quote`、`historical_evidence`、`description`、`suggestion`、`suggested_rewrite`）现在接受 `None` 并归一化为空字符串；`ref_id` 原有的 `None`/`#905` 解析保持。前端 `ref_label: string` 类型不变。
- 新增纯函数 `app/services/memory/consistency_parse.py`：外层 JSON 仍整体解析（失败可重试），但 `issues` **逐条** `model_validate`；不合格条目丢弃并记录 `issues[i]: 字段/原因`，合法条目全部保留。`run_review` 记录 warning `consistency review dropped N invalid issue(s)`。
- 新增 `app/services/llm/timeout_budget.py`：`env_timeout_sec()` 读取环境变量，默认 **150 秒**，范围 **30–300**（非法值回退默认、越界夹紧并 warning）；`RetryBudget` 让首次与一次重试共享 `2 × 单次超时` 的总预算，每次尝试取 `min(单次超时, 剩余预算)`，并用 `asyncio.wait_for` 兜底取消。
- 环境变量：`YOUTHINK_CONSISTENCY_TIMEOUT_SEC`、`YOUTHINK_MEMORY_EXTRACT_TIMEOUT_SEC`。一致性审查在“外层解析失败或没有任何合法条目”时重试一次；记忆抽取沿用原有“整批不可用才重试”条件，但两次调用现在共享预算。
- 失败样本 `tests/fixtures/consistency_failed_review.json` 为 `live_test_log.md:189` 的真实 4 条意见（`issues[3].ref_label=null`），断言 4 条全部保留、返回 201。
- 改动文件：`app/schemas/consistency.py`、`app/services/memory/consistency.py`、新 `consistency_parse.py`、`app/services/memory/finalizer.py`、新 `app/services/llm/timeout_budget.py`；测试 `tests/test_consistency_review.py`、`tests/test_memory_extraction.py`。
- 验证：一致性/记忆抽取专项 **19 passed**；全量 `python -m pytest tests -q` **379 passed / 5 failed**（209.83 秒），5 项与既有基线逐项一致，无新增失败。全部模型调用为 mock/固定样本，未调真实 LLM；测试使用临时库，未写入小说数据。
- 局限 / 人工确认：① “两次共享总预算”实现为合计 `2 × 单次超时`（默认 300 秒），若你的本意是合计等于单次 150 秒，需要再调；② 逐条丢弃只记日志，未在审查响应里返回丢弃数量；③ 真实模型是否还会输出其他不可空字段异常，需上线后抽查 `consistency_review` 日志；④ 记忆抽取默认超时由原 60 秒变为 150 秒，长时间章节省略前应先观察实际耗时与成本。


## T15 完成：规划提示词的前文呼应依据（2026-11-02）

- 新增纯函数模块 `backend/app/services/prompt/character_voice.py`：只从上一章正文的中文引号（`“”`/`「」`/`『』`）内提取**发言**，不取叙述句；按“语气词数量 + 你/我称呼”排序，短句优先，去重后最多 5 条（至少 3 条时正常输出，不足则按实际条数）。纯应答（嗯/行吧/知道了等）不作为标志性句式。
- `generate_chapter_scenes` 的上下文新增“上一章中人物的标志性口癖或句式（仅摘自上一章原文发言，共 N 条）”，逐条以 `- “原句”` 列出。降级：无上一章时提示“本章为开篇，不得引用或虚构上一章台词”；上一章存在但无可提取发言时提示“未提取到可用发言，不得凭空引用或自造”。
- 规划任务指令新增两条硬规则：①【与前文呼应的依据】凡写“措辞/语气与前文一致”“沿用之前说法”，必须指明具体对应哪条摘录并逐字使用，不得只写“像之前那样说”，无摘录则不得写这类要求，正文不得自造旧聊天/旧台词；②【关键选择场景】must_happen 必须有一条写明人物明确的内心判断和决定（如“他判断……，决定……”），must_not_include 必须写明对方不得察觉该判断/决定，也不得回头、追问或回应。
- 写正文任务指令新增：“不得复用上一章已出现的描写句子（景物、动作、比喻均算），需要呼应时只承接事实与情绪，不照抄原句。”
- 改动文件：新 `app/services/prompt/character_voice.py`、`app/services/writing_service.py`；新增测试 `tests/test_previous_chapter_voice.py`。
- 验证：T15 专项与场景规划测试 **14 passed**；全量 `python -m pytest tests -q` **386 passed / 5 failed**（212.30 秒），5 项与既有基线（M2 时序/滚动 3 项、M3 流式 1 项、M5 长书 1 项）逐项一致，无新增失败。模型调用全部 mock，未调真实 LLM；测试使用临时库，未写入小说数据。
- 局限 / 人工确认：① 口癖摘录是词面启发式，可能选到普通短句而漏掉真正的标志性表达，且只识别中文引号内文本，聊天记录若未加引号不会被提取；② “3–5 条”在上一章发言不足时按实际条数降级；③ 真实模型是否遵守“逐字引用、不得自造旧聊天、关键选择需写内心判断、不得复用描写句”只能实际跑几章后抽查 prompt 与正文；④ 未回填或改写既有场景节拍与已生成正文。
