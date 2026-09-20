# 只读设计说明书详情页 Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for isolated units, and test-driven-development for implementation. Execute continuously; user has approved the spec and requested implementation without another approval gate.

**Goal:** 独立页面完整阅读固定版本快照，支持历史导航，保留原工作区写操作。

**Architecture:** 复用已鉴权的项目 state GET；纯显示转换层处理未知 payload，页面负责加载与刷新，App 负责查询参数导航。无后端协议或数据库变更。

**Tech Stack:** React/TypeScript、Vitest、Playwright、现有 ApiClient。

## Global Constraints

- 规格：`docs/superpowers/specs/2026-09-20-brief-reader-design.md`；基线 `0b10ae5`，实现分支 `codex/brief-reader`。
- 正文只用选定快照；不把当前属性/约束混入历史；不显示未经确认的模板项目字段。
- 审批按版本与哈希同时匹配；历史缺失标记不可用，过时标记失效。
- 详情只读；所有编辑/重生成/审批留在工作区；无导出、对比、模型调用或部署。
- 每组先测试失败再实现；最终全量测试与独立审查。保留功能分支，不自动合并或推送。

### Task 1: 快照安全显示模型

Files: 新建 `frontend/src/briefs/briefPresentation.ts`、`briefPresentation.test.ts`。

接口：`presentBrief(brief: BriefVersion, projectId: string): BriefPresentation`，返回 `{projectId, goals: string[] | null, sections: {title: string, items: string[] | null}[]}`；畸形顶层、错误项目 ID、错误版本抛出可读 Error。`approvalSummary(brief: BriefVersion, state: ProjectState): string[]` 返回中文审批文案。

- [x] 测试快照与当前共享状态隔离、缺失/空字段、畸形结构、未知枚举、项目 ID 不匹配、模板项目字段不展示；再实现纯函数。
- [x] sections 展示偏好（部位/维度/值/状态/证据）、约束（类别/对象/内容/理由/严重程度/专业核验）、冲突（状态/摘要/影响/结论）与未决事项。用户文字不作为 HTML；不用 JSON.stringify 大对象替代阅读布局。
- [x] 审批测试最新未过时、最新过时、历史缺失、错误哈希、匹配记录；实现只读文案。
- [x] 运行 `npm test -- src/briefs/briefPresentation.test.ts`，核对 RED/GREEN。

### Task 2: 只读详情页与异步保护

Files: 新建 `frontend/src/briefs/BriefDetail.tsx`、`BriefDetail.test.tsx`，修改 `frontend/src/styles.css`。

接口：`BriefDetail({client, projectId, version: string|null, onVersion(version:number, replace?:boolean), onBack()})`。

- [x] 测试只读正文、版本选择、缺版本固定最新 URL、明确非法版本不回退、无说明书、鉴权失败、刷新错误保留同版本快照并警示、请求逆序与卸载后忽略。
- [x] 实现 GET 加载；手动与 focus 刷新；请求序号/卸载保护；403/404 清除内容；项目切换不复用旧快照。
- [x] 版本固定不随新版本自动跳转；按钮只包括返回、刷新与版本导航；纯文本渲染恶意字符串。
- [x] 添加受限宽度和换行样式，移动页面不横向溢出；运行组件与模型单测。

### Task 3: App 导航与工作区离开保护

Files: 修改 `frontend/src/App.tsx`、`App.test.tsx`、`frontend/src/workflow/Workspace.tsx`、`Workspace.test.tsx`。

- [x] 测试 `?project=p1&view=brief&version=1` 深链接、登录恢复、版本前进后退、返回清理参数、退出清理敏感页面。
- [x] App 将 query route 一起存储；现有工作区 GET/写入合同不变；详情页固定 project key 避免跨项目数据污染。
- [x] Workspace 新增 `onOpenBrief?: (version:number)=>void`，只有存在最新版本时显示入口。以当前表单状态判断未保存输入，存在则 window.confirm；取消保留输入，确认才调用导航。不做全站草稿重构。
- [x] 测试未改输入直接进入、目标/偏好/问题/约束修改时取消与确认；保留既有写入/409/审批测试。

### Task 4: 真实浏览器与交接

Files: 新建 `frontend/e2e/brief-reader.spec.ts`，复用 `frontend/e2e/flow.ts`；更新 README.frontend 和交接文档顶部。

- [x] 先写真实两账户 E2E：创建说明书 v1、修改目标生成 v2，双方查看 v1/v2 的差异，刷新/返回/切换，确认阅读不产生业务 POST/PATCH/DELETE，不改变版本与哈希。
- [x] 测试未保存目标离开取消/确认、无写操作按钮、移动视口和截图；用响应与明确 UI 状态等待，不硬编码延时。
- [x] 执行后端 `uv run pytest -q` 与 `uv run ruff check src tests scripts`；前端 `npm test`、`npm run build`、`npm run test:e2e`。
- [x] 独立审查整个分支、修复实际问题、重跑覆盖测试；记录测试数字、功能边界、分支和提交，不声称生产就绪。

## Progress

- 基线：58 项前端测试通过；规格批准，分支已创建。
- Task 1–4：已完成（2026-09-21）。独立审查发现浏览器历史导航绕过未保存保护，已补失败回归、修复并复核。
- 最终验证：后端 245 项、前端 111 项、浏览器 10 项通过；Ruff 与构建通过。详细证据见 `docs/reports/brief-reader-validation.zh-CN.md`。
- 仅本地功能分支，未合并、未推送、未部署。
