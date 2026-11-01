# 章节拆分与正文节奏优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让情节弧按事件密度自然决定章节数量，并让正文把篇幅集中在推动剧情、改变关系或人物状态的内容上。

**Architecture:** 移除前端和后端默认固定 5 章的约束，生成模型按本弧目标、冲突和事件转折规划合理章数，并保留用户明确指定章数的兼容方式。统一加强大纲与正文的节奏原则：合并没有独立事件结果的微章节，关键转折充分展开，过场压缩；不改变现有单章目标字数缓冲算法。

**Tech Stack:** React、TypeScript、FastAPI、Pydantic、SQLite、pytest、Vitest。

---

### Task 1：为自适应章数和节奏提示建立回归用例

**Files:**
- Modify: `backend/tests/test_m2_entities_outline.py`
- Modify: `backend/tests/test_m3_writing_stream.py`
- Modify: `frontend/src/features/outline/OutlineSection.test.tsx`（若现有组件测试组织不同，先沿用仓库现存模式，不另建平行测试设施）

- [ ] 验证默认请求不再隐含要求恰好 5 章，且明确传入 `chapter_count` 时仍按指定数量生成。
- [ ] 验证大纲提示词明确要求按独立事件/状态变化切章：无新事件结果的准备、等待、重复对话应合并；关键决定、冲突升级及结果需要保留展开空间。
- [ ] 验证正文提示词要求按戏剧重要性分配细节，并且不为达到目标字数重复心理、动作或解释。
- [ ] 运行对应测试，确认新断言在实现前失败。

### Task 2：把章节数从固定值改为按剧情规划

**Files:**
- Modify: `frontend/src/features/outline/OutlineSection.tsx`
- Modify: `frontend/src/features/outline/api.ts`
- Modify: `backend/app/schemas/outline.py`
- Modify: `backend/app/api/v1/outline.py`
- Modify: `backend/app/services/setting_generator.py`
- Test: `backend/tests/test_m2_entities_outline.py`

- [ ] 将 API 的 `chapter_count` 改为可选值；未指定时代表“由模型规划”，显式指定时维持 1–20 的范围。
- [ ] 前端生成入口不再硬传 `chapterCount: 5`；按钮旁/确认步骤说明默认按剧情自然拆分，避免用户误以为章数固定。
- [ ] 在 `generate_arc_chapters` 中仅在用户指定数量时向模型要求固定数量；自适应模式要求模型根据本弧的独立事件、转折和因果结果决定章数，并设置合理上限以保护 JSON 输出规模。
- [ ] 更新复核提示，使其检查章节是否过度拆分、相邻章是否各有独立推进，并允许自适应模式修正章数；固定数量模式仍须保持章数不变。
- [ ] 保留当前时间线校验和跨章连续性复核，确认模型返回异常数量时不会写入半成品。

### Task 3：使大纲和正文使用同一节奏尺度

**Files:**
- Modify: `backend/app/services/setting_generator.py`
- Modify: `backend/app/services/writing_service.py`
- Modify: `backend/app/builtin/prompt_templates.py`（只在默认模板承担具体场景节拍/正文要求时修改；保留用户自定义模板）
- Test: `backend/tests/test_m2_entities_outline.py`
- Test: `backend/tests/test_m3_writing_stream.py`

- [ ] 大纲梗概要求明确本章的核心事件、角色选择/变化、结果及与下一章的推进关系，不把单纯动作步骤当作独立情节。
- [ ] 正文指令区分“需要展开”的冲突、决定、关系变化和后果，与“应压缩”的通勤、整理、等待、重复确认等过场。
- [ ] 不降低或重新固定章节目标字数，不改变已有目标字数缓冲；模型必须以叙事完整和推进效率为先，禁止用无结果段落填满目标。
- [ ] 检查场景节拍生成与整章写作使用同一原则，避免大纲合并了微事件、场景拆解时又将其膨胀回清单。
- [ ] 运行两类后端定向测试及前端 typecheck/build；确认既有固定章数请求仍兼容。

### Task 4：用真实生成结果验收质量

**Files:**
- No source files; use the selected arc after Tasks 1–3 are implemented.

- [ ] 重新生成所选情节弧大纲，检查模型章数是否由剧情密度决定，而非回到固定 5 章。
- [ ] 逐章检查每章是否有独立事件或状态推进；重复日常步骤应并入过场，重要节点应有足够因果和情绪展开。
- [ ] 基于确认后的新大纲重新生成该弧正文，检查正文未用重复动作/心理补字数，且章间推进更快。
- [ ] 若结果仍出现一章一小步或过场冗长，依据实际生成 prompt/输出再收紧规则后复验，不以“提示词已修改”代替效果验收。
