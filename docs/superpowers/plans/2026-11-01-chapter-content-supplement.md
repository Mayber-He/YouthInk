# 正文内容补充功能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在章节正文的指定光标位置生成一段可预览、可重生成的补充内容，并在作者确认后插入并保存新版本。

**Architecture:** 新建独立 SSE 补充接口，服务端以章节全文、插入标记及写作上下文提示模型生成候选。前端记录正文快照和光标偏移，在候选预览期间不修改正文，确认插入且快照未变化时才保存新版本。

**Tech Stack:** FastAPI、Pydantic、React、TypeScript、TanStack Query、现有 SSE 客户端和章节版本保存接口。

---

### Task 1: 定义补充请求并创建服务端生成提示

**Files:**
- Modify: `backend/app/schemas/writing.py`
- Modify: `backend/app/services/writing_service.py`

- [ ] 新增 `StreamSupplementRequest`，包含 `chapter_id`、`content`、`insertion_index`、`instruction` 与 `disabled_context_keys`；校验偏移不大于正文长度、指令非空。
- [ ] 新增提示组装方法：通过上下文组装器加载章节写作背景，将完整正文在偏移处标成“补充插入位置”，要求生成独立、连贯、不过度复述的正文段落。
- [ ] 输出约束只允许正文文本，不得输出标题或解释。

### Task 2: 暴露 SSE 接口

**Files:**
- Modify: `backend/app/api/v1/stream.py`

- [ ] 新增 `/supplement` 路由，使用写作模型和流式客户端，调用补充提示组装方法。
- [ ] 为请求使用独立 task type `supplement_content`，沿用 SSE 响应头。

### Task 3: 前端流式请求 hook

**Files:**
- Modify: `frontend/src/features/editor/hooks/useStreamGenerate.ts`

- [ ] 新增 `startSupplementStream`，向 `/supplement` 发送当前章节、正文快照、插入偏移、作者要求和禁用上下文块。
- [ ] 将流式增量累积为候选；结束后将完整候选交给调用方，不自动修改正文。
- [ ] 保持取消、错误与 `isStreaming` 状态行为和既有 SSE 方法一致。

### Task 4: 预览、重生成与插入交互

**Files:**
- Modify: `frontend/src/features/editor/components/SelectionToolbar.tsx`
- Modify: `frontend/src/features/editor/WritingWorkbench.tsx`

- [ ] 工具栏在有无选中文本时都显示“补充内容”入口；该入口使用折叠输入面板收集作者要求。
- [ ] 点击生成时保存当前正文快照与光标偏移，并展示流式候选预览。
- [ ] 提供“重新生成”“取消”“插入正文”；重新生成沿用同一要求和插入位置。
- [ ] 正文快照已变化时禁用插入并提示重新生成。
- [ ] 插入成功后仅更新光标位置处的内容，调用保存接口创建 AI 新版本，并定位光标到新增段落之后。
- [ ] 不改变选区扩写的替换行为。

### Task 5: 静态验证与差异检查

**Files:**
- Review: `backend/app/schemas/writing.py`
- Review: `backend/app/services/writing_service.py`
- Review: `backend/app/api/v1/stream.py`
- Review: `frontend/src/features/editor/hooks/useStreamGenerate.ts`
- Review: `frontend/src/features/editor/components/SelectionToolbar.tsx`
- Review: `frontend/src/features/editor/WritingWorkbench.tsx`

- [ ] 运行 Python 语法编译，确认新增服务端代码可解析。
- [ ] 运行前端 TypeScript 检查和生产构建，确认请求类型、回调和组件属性一致。
- [ ] 运行 `git diff --check`，确认补丁没有空白错误。
- [ ] 不运行测试套件，除非用户另行要求。
