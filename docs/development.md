# YouthInk 青春小说工作台 · 开发规范文档

> 适用范围：YouthInk 前后端工程开发与维护。所有开发者及 AI 编程助手在新增、修改或重构代码时须严格遵循本规范。架构与业务模型请同步参考 [设计文档 (design.md)](./design.md)。

---

## 目录

1. [代码文件规模与模块化规范](#1-代码文件规模与模块化规范)
2. [目录结构与分层架构](#2-目录结构与分层架构)
3. [前后端编码与工程规范](#3-前后端编码与工程规范)
4. [核心业务实现铁律](#4-核心业务实现铁律)
5. [API 与流式通信契约](#5-api-与流式通信契约)
6. [本地开发与验证流程](#6-本地开发与验证流程)
7. [Git 代码提交规范](#7-git-代码提交规范)

---

## 1. 代码文件规模与模块化规范

### 1.1 文件规模红线

| 规模区间 | 规范要求 | 处置动作 |
|---|---|---|
| **100 ～ 300 行** | **推荐区间**（单文件原则上不超过 300 行） | 保持良好内聚度 |
| **> 400 行** | **预警阈值** | 修改存量文件时主动评估模块拆分的必要性 |
| **> 500 行** | **拆分红线** | 原则上必须拆分；确有合理内聚原因方可保留 |
| **> 800 行** | **强制重构线** | 优先执行模块化重构（自动生成代码等特殊情况除外） |

### 1.2 模块化与设计原则

1. **单一职责原则**：避免单个文件同时承担 UI 渲染、复杂状态编排、网络请求或数据持久化等多种职责。
2. **按业务职责拆分**：优先按领域边界与功能职责拆分，**严禁**为了迎合行数指标进行无意义的机械截断。
3. **复用与下沉**：及时提取公共 UI 组件、纯函数工具、领域 Service 和状态 Slice，消除跨模块重复代码。
4. **安全重构**：重构时保持外部接口、数据契约和交互行为不变，关键逻辑须补充单元测试或回归验证。
5. **禁止负向优化**：**严禁**通过删除必要注释、压缩代码排版、合并多行语句或使用晦涩简写来凑行数。
6. **适度设计**：不为追求小文件而引入无意义的中间层抽象和碎片化文件。
7. **合理例外**：以下文件允许合理超出推荐行数：
   - 自动生成文件（如 OpenAPI 类型定义、数据库迁移脚本）
   - 纯静态数据声明（如内置 Prompt 模板、风格预设、AI 味检测词表）
   - 集中式 Schema 契约或复杂端到端测试用例

### 1.3 执行要求

- **新增代码**：创建文件前先规划职责边界，确保单文件粒度落在推荐区间（< 300 行）。
- **存量维护**：修改现有文件时若已超 400 行，应在本次变更前或变更后顺带完成安全拆分。
- **回归验证**：任何拆分与重构完成后，必须通过类型检查、单元测试或核心链路手动验证。

---

## 2. 目录结构与分层架构

本项目采用 **Web 前端（React + TypeScript + Vite） + 服务端（Python FastAPI）** 单体同源部署架构。

### 2.1 前端目录结构（`frontend/`）

```text
frontend/src/
├─ components/              # 全局通用组件
│  ├─ ui/                   # shadcn/ui 基础原子组件（Button, Dialog 等）
│  └─ common/               # 跨业务复用组件（锁定开关、Token 徽章、空状态等），单文件 < 150 行
├─ layouts/                 # 布局容器（三栏工作台、顶部导航、底部状态栏）
├─ features/                # 业务领域模块（按功能垂直聚合）
│  ├─ novels/               # 启动页作品列表、新建立项、备份管理
│  ├─ settings-entity/      # 设定中心（世界观、人物卡+状态时间轴、地点、主线剧情）
│  ├─ outline/              # 结构目录（分卷、情节弧、章节拖拽排序、场景细纲）
│  ├─ editor/               # 写作工作台
│  │  ├─ components/        # TipTap 编辑器、选区浮动工具栏、上下文预览面板
│  │  ├─ extensions/        # TipTap 自定义扩展（@实体提及、AI 味波浪线高亮）
│  │  ├─ hooks/             # 业务 Hook（useAutoSave, useStreamGenerate, useAiSmellCheck）
│  │  ├─ api.ts             # 编辑器相关接口调用与 TanStack Query Hooks
│  │  └─ types.ts           # 模块局部类型定义
│  ├─ memory/               # 记忆中心（待确认队列、事实库、伏笔台账）
│  └─ app-settings/         # 全局设置（模型档案、任务分配、Prompt 模板、Embedding 下载）
├─ hooks/                   # 全局通用自定义 Hook
├─ stores/                  # Zustand 客户端状态（按领域切分 Slice，禁止单文件大 Store）
├─ lib/                     # 基础设施封装（HTTP Client、SSE 流式读取器、通用常量）
├─ types/                   # 全局共享 TypeScript 类型与后端 Schema 映射
└─ utils/                   # 无副作用纯函数工具
```

**前端分层职责约束**：
- **Page / 容器组件**：仅负责布局拼装与子模块协调，不超过 200 行。
- **子组件下沉**：独立弹窗、复杂表单分组、卡片项超过 50～80 行时应拆分为独立子组件。
- **状态管理边界**：
  - **服务端数据**（作品、人物、章节、待确认队列等）统一由 **TanStack Query** 管理缓存与失效刷新。
  - **纯客户端 UI 状态**（三栏折叠、专注模式、当前选中章节 ID、流式生成临时缓冲区）由 **Zustand** 管理。

### 2.2 后端目录结构（`backend/`）

```text
backend/app/
├─ main.py                  # FastAPI 应用入口、生命周期管理、StaticFiles 挂载
├─ api/                     # 路由层（仅负责参数校验、调用 Service、返回响应）
│  ├─ deps.py               # 依赖注入（获取当前 novel.db 会话、全局配置等）
│  └─ v1/
│     ├─ novels.py          # 作品管理与立项路由（单文件 < 200 行）
│     ├─ entities.py        # 世界观、人物、地点、主线路由
│     ├─ outline.py         # 卷、弧、章、场景细纲路由
│     ├─ writing.py         # 正文保存、版本历史、定稿触发路由
│     ├─ stream.py          # SSE 流式生成与改写路由（/api/stream/*）
│     ├─ memory.py          # 待确认队列、事实、状态、认知、伏笔路由
│     └─ settings.py        # 模型档案、Prompt 模板、Embedding 管理路由
├─ services/                # 核心业务逻辑层（按领域拆分，单文件 < 300 行）
│  ├─ llm/                  # LLM 统一调度、流式转发、JSON 解析修复管线、Token 记账
│  ├─ prompt/               # Prompt 分层渲染、内置模板加载与用户覆盖管理
│  ├─ context/              # 上下文组装器（Token 预算分配、硬约束提取）
│  ├─ rag/                  # 混合检索（元数据过滤 + LanceDB 向量 + FTS5 + RRF 融合）
│  ├─ memory/               # 定稿闭环（场景切分、分层摘要、事实与状态抽取、信任模式分发）
│  ├─ embedding/            # bge-m3 ONNX 推理封装、模型下载与校验
│  └─ backup_service.py     # 作品目录自动备份与恢复
├─ db/                      # 数据持久化层
│  ├─ manager.py            # 双库连接管理（global.db 单例 + <novel_id>/novel.db 动态池）
│  ├─ init_schema.py        # SQLite 建表、FTS5 虚拟表与触发器初始化
│  ├─ vector_store.py       # LanceDB 向量表读写封装
│  └─ repositories/         # 数据访问层（按实体拆分 CRUD 与复杂时序查询）
├─ schemas/                 # Pydantic 数据契约（API 请求/响应、LLM 结构化输出 Schema）
├─ core/                    # 基础设施与全局配置
│  ├─ config.py             # 环境变量与路径解析（YOUTHINK_DATA_DIR 等）
│  ├─ security.py           # API Key 本机加解密（cryptography.fernet）
│  └─ exceptions.py         # 统一业务异常定义与全局异常处理器
└─ builtin/                 # 随包发布的静态资源（默认 Prompt 模板、预设风格、AI 味词表）
```

**后端分层职责约束**：
- **禁止胖 Router**：路由处理函数（Endpoint）只做入参校验、调用 Service、包装响应，单函数建议不超过 30 行，**严禁**在路由层直接拼接 SQL 或组装 Prompt。
- **Repository 隔离数据访问**：所有 SQL 查询、FTS5 检索及 LanceDB 操作必须封装在 `repositories/` 或 `vector_store.py` 中，Service 层通过方法调用获取领域数据。

---

## 3. 前后端编码与工程规范

### 3.1 前端规范（TypeScript + React）

1. **严格类型检查**：开启 `strict: true`，禁止使用隐式或显式 `any`；遇到不确定外部数据先定义为 `unknown` 并通过类型守卫收窄。
2. **命名约定**：
   - 组件文件与组件名：`PascalCase`（如 `CharacterCard.tsx`）。
   - Hook 文件与函数名：`camelCase` 且以 `use` 开头（如 `useStreamGenerate.ts`）。
   - 工具、Store、API 文件：`camelCase` 或 `kebab-case`（保持目录内统一）。
   - 常量枚举：`UPPER_SNAKE_CASE`。
3. **流式请求生命周期**：所有 SSE 流式生成请求必须绑定 `AbortController`，支持用户点击「停止」及组件卸载时主动中断连接，防止内存泄漏与幽灵写入。
4. **中文输入法兼容**：TipTap 编辑器扩展与快捷键监听必须处理 `isComposing`（IME 组合输入状态），避免打断中文拼音选词。

### 3.2 后端规范（Python + FastAPI）

1. **类型注解与校验**：所有函数签名（含参数与返回值）必须标注完整 Python Type Hints；跨层复杂数据结构统一使用 Pydantic `BaseModel` 或 `dataclass`。
2. **命名约定**：模块名、文件名、函数名、变量名统一使用 `snake_case`；类名使用 `PascalCase`；全局常量使用 `UPPER_SNAKE_CASE`。
3. **事件循环防阻塞**：
   - FastAPI 异步路由（`async def`）中**严禁**直接调用耗时同步阻塞操作。
   - `onnxruntime` 向量推理、`jieba` 大文本分词、文件压缩备份等 CPU / 同步 IO 密集型任务，必须定义为同步函数由 FastAPI 线程池调度，或显式使用 `asyncio.to_thread()` 执行。
4. **资源与事务管理**：SQLite 写操作须在上下文事务中执行；跨表批量更新（如定稿后写入摘要与抽取记录）须保证原子性，异常时完整回滚。

---

## 4. 核心业务实现铁律

为保障设计文档中「防幻觉」与「百万字一致性」目标落地，开发中必须严格遵守以下业务约束：

### 4.1 双库隔离与存储边界
- **`global.db`**：仅存放跨作品全局配置（`llm_profiles`、`task_model_assignments`、`prompt_templates`、`style_templates`），**不随单部作品备份**。
- **`<novel_id>/novel.db`**：每部作品独立 SQLite 数据库，存放该书全部设定、目录、正文与记忆数据。每次章节「定稿」入库前，自动触发 `novel.db` 快照备份至 `<novel_id>/backups/`。
- **密钥安全**：模型档案的 `api_key` 严禁明文落盘或出现在日志、前端响应中；入库前必须经 `core/security.py`（`cryptography.fernet`）加密，前端展示时仅返回脱敏掩码（如 `sk-****1234`）。

### 4.2 锁定保护（Locking）与状态确认（Trust Mode）
- **生成 → 编辑 → 锁定**：世界观、人物卡、地点、主线、章节均包含 `locked` 字段（`0` / `1`）。触发「AI 重新生成全部」时，后端必须过滤并保留所有 `locked = 1` 的记录，仅覆盖未锁定项。
- **定稿才入库**：章节处于 `draft`（草稿）状态时，反复保存或改写**绝不触发**向量入库、摘要更新和事实抽取；仅当状态流转为 `final`（定稿）时才启动记忆闭环。
- **确认状态过滤**：组装写作上下文时，人物状态变更、认知记录、关系变更、伏笔、事实库**仅查询已确认/已锁定**（`confirm_status = 'confirmed'` 或 `status IN ('confirmed', 'locked')`）的记录，`pending` 与 `discarded` 记录严禁注入生成上下文。

### 4.3 时序查询与浮点排序（`sort_order`）
- **排序与展示解耦**：卷、情节弧、章节、场景均使用 `REAL`（浮点数）类型的 `sort_order` 控制顺序。插入新节点时取相邻节点均值（如 `(1.0 + 2.0) / 2 = 1.5`），严禁将数据库主键 `id` 当作章节顺序使用。
- **时序状态回溯**：查询「第 N 章（排序号为 $S_N$）某人物的当前状态」时，必须关联 `chapters.sort_order <=` $S_N$，按 `chapters.sort_order DESC, id DESC` 取每个 `field` 最新的一条已确认记录，再与人物卡静态基准属性合并。

### 4.4 全文检索分词与向量同步
- **FTS5 中文预分词**：SQLite FTS5 采用 `unicode61` 分词器，所有写入 `chapters_fts` 与 `facts_fts` 的文本必须先经 Python `jieba` 分词并以空格拼接；检索 Query 同样须经 `jieba` 分词后再执行 `MATCH`。
- **模型标识记录**：写入 LanceDB 向量块时必须记录当前 Embedding 模型标识；当检测到全局切换了 Embedding 模型时，提示用户重建作品向量索引。

### 4.5 LLM 调用、前缀缓存与结构化解析
1. **Prompt 顺序固定**：严格按照 `①系统角色 → ②风格模板 → ③作品核心设定 → ④动态上下文 → ⑤任务指令 → ⑥输出格式要求` 顺序拼装，最大化命中云端 API 前缀缓存。
2. **结构化 JSON 降级管线**：不强依赖厂商专有 `json_schema` 参数。所有 JSON 输出任务统一经过：`直接 json.loads → 提取 Markdown 代码块 → 宽松语法修复 → 调用便宜模型修复（最多重试 2 次） → 失败保留原文并抛出可恢复提示`。
3. **全量调用记账**：无论成功或中途停止，每次 LLM 调用均须写入 `generation_logs` 表（记录任务类型、模型、模板版本、Token 消耗与耗时）。

---

## 5. API 与流式通信契约

### 5.1 RESTful 接口规范
- 业务接口统一挂载在 `/api/v1/` 前缀下，资源路径使用复数名词（如 `/api/v1/novels/{novel_id}/characters`）。
- 统一错误响应结构（HTTP 状态码配合标准 JSON 体）：
  ```json
  {
    "error": {
      "code": "LLM_JSON_PARSE_FAILED",
      "message": "模型返回格式解析失败，请重试或手动修改",
      "detail": "..."
    }
  }
  ```

### 5.2 SSE 流式输出协议（`/api/stream/*`）
流式生成接口统一使用 `text/event-stream`，按事件类型区分生命周期：

```text
event: meta
data: {"generation_id": 42, "model": "deepseek-chat", "context_tokens": 18420}

event: delta
data: {"content": "窗外的蝉鸣声渐渐稀疏，"}

event: done
data: {"input_tokens": 18420, "output_tokens": 856, "elapsed_ms": 12400}

event: error
data: {"code": "UPSTREAM_API_ERROR", "message": "API 连接超时，已保存当前已生成片段"}
```

---

## 6. 本地开发与验证流程

### 6.1 环境变量约定

| 变量名 | 默认值 | 说明 |
|---|---|---|
| `YOUTHINK_DATA_DIR` | `./backend/data` | 存储 `global.db`、`models/` 及所有作品目录的根路径 |
| `YOUTHINK_HOST` | `0.0.0.0` | 后端监听地址 |
| `YOUTHINK_PORT` | `8000` | 后端监听端口 |

### 6.2 开发态与生产态运行方式
- **开发态（前后端热重载）**：
  - 后端：在 `backend/` 下启动 `uvicorn app.main:app --reload --port 8000`。
  - 前端：在 `frontend/` 下启动 `vite`，通过 `vite.config.ts` 将 `/api` 代理至 `http://localhost:8000`。
- **生产态 / 交付验证**：
  - 前端执行 `npm run build`，产物输出至后端静态目录。
  - 后端单进程通过 FastAPI `StaticFiles` 直接挂载前端产物，浏览器访问 `http://localhost:8000` 即可完整使用（无跨域问题）。

### 6.3 提交前自检清单（Definition of Done）
1. 新增或修改的文件均符合第 1 节「文件规模红线」（推荐 < 300 行）。
2. 前端通过 `tsc --noEmit` 类型检查与 ESLint 校验，无报错。
3. 后端通过单元测试（`pytest`）及类型/语法检查，SQL 与事务无裸露风险。
4. 涉及数据库表结构或 API 契约变更时，已同步更新 `docs/design.md`。

---

## 7. Git 代码提交规范

代码提交信息统一遵循 Conventional Commits 中文规范：

### 7.1 格式要求

```text
type(scope): 中文描述
```

- **type**（必须）：提交类别，使用小写英文标识。
- **scope**（推荐）：本次修改涉及的模块或领域范围。
- **中文描述**（必须）：清晰陈述本次提交的目的或改动内容，**动词开头**，简明扼要，结尾不加句号。

### 7.2 允许的 Type 列表

| Type | 说明 | 示例 |
|---|---|---|
| `feat` | 新增功能或业务逻辑 | `feat(editor): 支持选中文字后改写功能` |
| `fix` | 修复缺陷或 Bug | `fix(memory): 修复事实抽取时引用位置偏移的问题` |
| `refactor` | 重构代码（既不新增功能，也不修复缺陷） | `refactor(db): 拆分超长的人物卡时序查询逻辑` |
| `docs` | 仅文档变更 | `docs(dev): 优化开发规范文档与分层指引` |
| `style` | 代码格式调整（不影响逻辑的空格、分号等） | `style(frontend): 修正 ESLint 与 Prettier 格式告警` |
| `perf` | 性能优化 | `perf(vector): 优化 LanceDB 批量向量写入速度` |
| `test` | 新增或修改测试用例 | `test(api): 增加章节版本回滚接口测试` |
| `build` | 构建系统、打包或依赖调整 | `build(deps): 升级 onnxruntime 到最新稳定版` |
| `chore` | 构建流程、启动脚本或杂项配置变更 | `chore(docker): 更新 docker-compose 模型目录挂载配置` |

### 7.3 Scope 建议取值

- **前端 Scope**：`ui`, `layout`, `novels`, `worldview`, `character`, `location`, `outline`, `editor`, `memory`, `settings`, `store`, `hook`
- **后端 Scope**：`api`, `stream`, `llm`, `prompt`, `context`, `rag`, `memory`, `embedding`, `db`, `vector`, `fts`, `backup`, `security`, `config`
- **通用 Scope**：`deps`, `docker`, `scripts`, `docs`

### 7.4 提交示例

- `feat(outline): 支持情节弧与章节拖拽浮点排序`
- `fix(security): 修复模型档案 API Key 解密异常的问题`
- `refactor(context): 拆分上下文组装策略，单文件保持 300 行内`
- `perf(fts): 将 jieba 预分词移入线程池避免阻塞事件循环`
- `docs(dev): 补充核心业务实现铁律与 SSE 流式协议规范`
