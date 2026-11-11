# 一致性审查多选采用

已确认方案：可采用建议提供复选框、全选、取消全选及“采用所选（N）”；保留单条采用。批量请求只保存一个新版本，之后统一复核。原文不唯一、建议重叠或报告过期时整批拒绝。

1. 扩展 `backend/app/schemas/consistency.py`，兼容单条 `issue_index` 和批量 `issue_indices`，要求二选一且非空、非负。
2. 在 `backend/tests/test_review_revision.py` 先覆盖批量一次保存、替换文本不串扰、重叠/歧义/过期/非法索引无保存及单条兼容；运行失败后实现 `backend/app/services/review_revision.py`。在原始正文定位所有区间，排序检查重叠，倒序替换后一次保存。
3. 修改 `frontend/src/features/memory/ConsistencyReviewModal.tsx` 增加勾选及操作条，报告切换或关闭时清空选择，提交期间禁用操作，失败保留选择并显示错误。更新 `api.ts` 和 `WritingWorkbench.tsx` 传递索引数组，共用一次保存和复核流程。
4. 运行 `python -m pytest tests/test_review_revision.py tests/test_consistency_review.py -q`、前端 `npm run build` 及报告交互测试，检查差异仅覆盖本需求。不提交已有未提交工作。

验证结果：14 项采用单元测试、11 项原有一致性测试及 2 项新增接口测试通过；接口测试确认成功只增加一个版本，重叠不增加版本。前端构建和 `python tests/consistencyReview.browser.py` 通过，浏览器覆盖勾选/全选/清空、批量及单条参数、失败保留勾选、切换/关闭清空和过期禁用。Windows 沙箱阻塞 asyncio 本机 socketpair，因此 TestClient 和浏览器测试在沙箱外运行，全部使用模拟报告、模拟模型及独立数据库。
