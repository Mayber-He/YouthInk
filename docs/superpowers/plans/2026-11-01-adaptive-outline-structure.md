# 自适应分卷与情节弧生成实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让模型根据故事内容决定分卷数量和每卷情节弧数量，并在覆盖目录前审查结构重复。

**Architecture:** 前端不再发送数量，后端 schema 接收结构偏好并限制模型返回范围。用户确认后，后端先提交清空旧目录和派生数据，再生成可变数量结构并进行一次模型复核；最终结果通过校验后才插入新结构，失败时保持空目录。

**Tech Stack:** React、TypeScript、FastAPI、Pydantic、SQLite、OpenAI-compatible LLM client。

---

### Task 1：移除固定数量输入与请求字段

**Files:**
- Modify: `frontend/src/features/outline/OutlineSection.tsx`
- Modify: `frontend/src/features/outline/api.ts`
- Modify: `backend/app/schemas/outline.py`
- Modify: `backend/app/api/v1/outline.py`

- [x] 删除前端分卷数和每卷弧数状态、输入框和固定默认值，只提交 `instruction`。
- [x] 将结构生成按钮改为“AI 按故事结构生成分卷与情节弧”，并提示数量由模型决定且各卷弧数可不同。
- [x] 将 `AiGenerateStructureRequest` 收敛为 `instruction` 字段；API 路由不再读取或传递数量。

### Task 2：生成自然数量并约束结构范围

**Files:**
- Modify: `backend/app/schemas/outline.py`
- Modify: `backend/app/services/setting_generator.py`

- [x] 移除 `generate_outline_structure` 的 `volume_count` / `arcs_per_volume` 参数。
- [x] 提示模型依照故事阶段、主线变化和因果节点决定 1–10 卷；每卷独立决定 1–6 条情节弧，不均分、不凑数。
- [x] 要求卷目标/梗概描述阶段变化；情节弧有独立目标、核心冲突和可辨识结果，不能重述相邻弧。
- [x] 在 Pydantic 输出模型中约束卷数和每卷弧数；最终保存前再检查数量与必要字段。

### Task 3：清空旧目录并增加结构复核

**Files:**
- Modify: `backend/app/db/repositories/outline_repo.py`
- Modify: `backend/app/services/setting_generator.py`
- Modify: `frontend/src/features/outline/api.ts`
- Modify: `frontend/src/features/outline/OutlineSection.tsx`

- [x] 确认重生成请求后，先删除目录、章节派生数据和摘要并立即提交，再清理旧向量，然后才读取设定并请求模型。
- [x] 将完整结构交给复核任务，检查重复卷弧、过场拆分、因果顺序和阶段覆盖；允许复核合并或调整数量。
- [x] 复核结果通过 1–10 卷、每卷 1–6 弧及必填字段校验后，只插入新结构，不重复清空。
- [x] 任一模型调用、解析或校验失败时不插入结构，已清空状态保持；前端在请求成功或失败后都刷新目录缓存并说明失败后的空目录状态。

### Task 4：非测试验证

**Files:**
- Review: `docs/superpowers/specs/2026-11-01-adaptive-outline-structure-design.md`

- [x] 运行 `npm run typecheck`，确认前端类型通过。
- [x] 对修改的 Python 文件运行 `python -m py_compile`。
- [x] 运行 `git diff --check`，确认无空白错误。
- [x] 核对 diff：数量输入及精确数量校验已移除；清空发生在模型请求前，新结构插入发生在复核和校验之后。
