# Frontend Studio Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 AlignSpace 全站改造为暖白、炭灰、橄榄绿的建筑设计工作室风，并以五页导航组织现有业务。

**Architecture:** 保留 React、现有查询参数路由、ApiClient 和项目级状态容器。先引入页面导航与不卸载的页面面板，再搬移现有展示模块；业务请求、幂等、认证、空间同步和审批校验不重写。说明书阅读保留旧地址兼容。

**Tech Stack:** React 19、TypeScript、CSS、Vite、Vitest/Testing Library、Playwright。

## Global Constraints

- 依据已批准规格 `docs/superpowers/specs/2026-09-22-frontend-studio-redesign.md`。
- 背景 #F6F3EC，卡片 #FFFDF8，正文 #292B25，强调色 #565D3D，边线 #DDD8CD；普通文本对比度至少 4.5:1。
- 桌面 >=1024px，平板 768–1023px，手机 <=767px；320px 页面无横向溢出；触控目标至少 44px。
- 不新增聊天、收藏、在线成员、云依赖、付费模型调用或后端业务能力。
- 不合并、不推送、不部署。保持现有密码契约、固定 SGD 自填预算与按项目角色规则。
- 禁止把模拟/未配置模型伪装为已验证真实分析；审批过时、空间同步冲突不可隐藏。
- 当前基线核对为 `be273dc`；执行前重新核对，不能将该 SHA 当永久事实。

## 0. 执行前保护

- [ ] 运行 `git status --short`、`git diff --stat`、`git log -1 --oneline`，记录真实基线。
- [ ] 阅读并保留现有六个脏文件：`frontend/e2e/auth-workflow.spec.ts`、`frontend/e2e/flow.ts`、`frontend/src/App.test.tsx`、`frontend/src/App.tsx`、`src/alignspace/auth/routes.py`、`tests/api/test_auth.py`。本计划与 App 和浏览器流程有重叠，不直接 stash、覆盖或整文件暂存。
- [ ] 执行 using-git-worktrees 技能选择隔离方式。若新 worktree 缺少这些预算/密码改动，不能把它误认成等价工作基线；先明确如何保留依赖和独立提交，再实施。
- [ ] 在 frontend 执行 `npm test`、`npm run build`，记录实际基线；失败先分类，不沿用报告数字。

## 文件职责

- 新建 `frontend/src/navigation/workspaceRoute.ts` 与测试：URL 页面解析/构造，兼容旧 brief 地址。
- 新建 `frontend/src/layout/WorkspaceShell.tsx` 与测试：桌面侧栏、移动菜单、导航语义。
- 新建 `frontend/src/layout/PersistentPanel.tsx` 与测试：隐藏但不卸载业务面板。
- 修改 `frontend/src/App.tsx`：路由接线、账户/项目页视觉容器；不改变认证行为。
- 修改 `frontend/src/workflow/Workspace.tsx`：保留状态与请求，按职责分配已有 JSX；展示区可抽取至 `frontend/src/workflow/views/`，不复制状态源。
- 修改 `frontend/src/styles.css`：设计变量、布局、组件样式、响应式与可访问性。
- 修改 `frontend/src/space/SpaceBoard.tsx`、`frontend/src/space/BindingPanel.tsx`、`frontend/src/briefs/BriefDetail.tsx`：仅必要展示边界与响应式适配。
- 新建 `frontend/e2e/studio-navigation.spec.ts`：导航、草稿与响应式验收。

## Task 1：页面路由与稳定导航壳层

**Interfaces:** `WorkspacePage = 'overview' | 'inspiration' | 'negotiation' | 'space' | 'approval'`；`parseWorkspacePage(url: URL): WorkspacePage`；`workspacePageUrl(url: URL, page: WorkspacePage): string`。WorkspaceShell 接收 `page`、`onNavigate(page)` 与 `children`，不持有业务状态。

- [ ] 新建路由测试，覆盖缺省概览、合法 page、非法 page 回落概览、现有查询参数保留。核心断言：

```ts
expect(parseWorkspacePage(new URL('http://localhost/?project=p'))).toBe('overview');
expect(parseWorkspacePage(new URL('http://localhost/?project=p&page=space'))).toBe('space');
expect(new URL(workspacePageUrl(new URL('http://localhost/?project=p&view=brief&version=2'), 'approval'))).searchParams.has('view')).toBe(false);
```

- [ ] 运行 `npm test -- src/navigation/workspaceRoute.test.ts`，确认新行为测试失败。
- [ ] 实现纯函数：仅接受五个 page；构造 URL 保留 project，设置 page，删除 view/version。进入 brief 保留 page=approval，返回审批页；旧 `?project=...&view=brief&version=...` 继续使用原 BriefDetail。
- [ ] 新增壳层导航测试：五个入口、当前入口 `aria-current="page"`、菜单 Escape 关闭并归还焦点；实现语义 nav/链接或按钮，移动菜单使用原生 dialog 的焦点约束或等价已测试机制。
- [ ] App 原有 `routeFromUrl` 增加 page；沿用 pushState/popstate，不引入另一套路由依赖。项目切换清除旧 page；同项目切页不更换 Workspace key。
- [ ] 跑路由、壳层与 App 测试及 build。检查 diff，只提交本任务可归属的修改，不夹带已有脏改动。

## Task 2：五页内容分配与草稿生命周期

**Interfaces:** `PersistentPanel({active, id, children})` 用原生 hidden 隐藏面板；Workspace 继续持有现有表单状态，接收 `page` 与 `onNavigate`。模型/约束/空间组件不得在 JSX 中按 page 条件卸载。

- [ ] 新建 PersistentPanel 测试：输入后切换 active=false 再 true，输入值仍在；隐藏时可访问查询不能找到内部按钮。跑 `npm test -- src/layout/PersistentPanel.test.tsx` 验证红灯。
- [ ] 实现：

```tsx
export function PersistentPanel({ active, id, children }: {
  active: boolean; id: string; children: React.ReactNode;
}) {
  return <section id={id} hidden={!active}>{children}</section>;
}
```

- [ ] 将现有 JSX 按规格分配，不搬移业务请求：概览放真实状态/任务入口；灵感放图片、PreferenceBoard、屋主访谈、偏好；协商放设计师问题、约束和冲突；空间放 SpaceBoard；审批放方案目标、重新生成、审批和阅读入口。
- [ ] 现有联合审批位于空间区域时抽取其展示控件为共享展示单元，保持一个状态/请求拥有者；审批页通过受控 props 使用相同能力，禁止复制审批网络实现。抽取前阅读实际组件确定 props，逐个保留原处理函数签名。
- [ ] 增加 Workspace/App 测试：屋主/设计师操作不越权；待办导航正确；偏好备注、约束编辑、方案目标切页不丢；旧 brief URL 和返回继续有效。
- [ ] 新增空间生命周期测试：触发 409 保留草稿，切到其他页再返回，重试仍使用原草稿/基线；导航过程不重新挂载 SpaceBoard、不重建 iframe。如果必须卸载，先实现离开确认，取消必须留在原页且无数据丢失。
- [ ] 跑 `npm test -- src/workflow/Workspace.test.tsx src/space/SpaceBoard.test.tsx src/App.test.tsx src/layout/PersistentPanel.test.tsx`。旧测试若依赖所有控件同时可见，应导航到真实页面，不能改为查询隐藏控件来假通过。
- [ ] 独立审查、提交本任务改动。

## Task 3：全站视觉与账户/项目页

**Interfaces:** 公共 CSS 变量供所有组件消费；不改变组件业务 props。

- [ ] 为 AuthScreen/ProjectsScreen 保留和补充测试：注册密码边界、SGD 自填预算、项目角色、空列表、失败提示；执行 `npm test -- src/App.test.tsx` 记录基线。
- [ ] 在 styles.css 定义已批准的色彩变量、8px 间距、标题字体与正文系统字体；统一按钮、输入、卡片、状态条。保证 `[hidden] { display: none !important; }`，避免页面 grid 规则让隐藏面板重新出现。

```css
:root {
  --paper: #f6f3ec; --surface: #fffdf8; --ink: #292b25;
  --olive: #565d3d; --line: #ddd8cd;
}
[hidden] { display: none !important; }
button, input, select { min-height: 44px; }
button:focus-visible, a:focus-visible { outline: 3px solid var(--olive); outline-offset: 3px; }
```

- [ ] 账户页改为品牌介绍与表单的简洁布局；项目页改为已有项目内容的卡片，不虚构封面/成员头像。没有图片显示中性空状态。所有创建/加入/项目码动作保持原权限。
- [ ] 工作区提供清楚的当前项目、角色与返回项目列表入口；大图用于用户参考素材，说明书以阅读宽度排版，空间画布保留可用宽度。
- [ ] 运行 `npm test` 和 `npm run build`；在浏览器检查长中文、长文件名、空数据、错误状态，不以构建成功代替视觉检查。
- [ ] 独立提交本任务可归属改动。

## Task 4：响应式与可访问性

**Interfaces:** CSS 断点统一为 1024/768px；手机空间摘要仍读取同一 SpaceBoard 状态，不能另发竞争性请求。

- [ ] 新建浏览器测试检查 390px 和 320px 页面宽度；核心断言：

```ts
await page.setViewportSize({ width: 320, height: 780 });
const fits = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
expect(fits).toBe(true);
```

- [ ] 实现桌面左侧栏、平板折叠辅助区、手机单列菜单。图片网格降为单列；表格与画布用容器内 overflow，不撑宽整个文档。
- [ ] 手机空间页展示真实版本、摘要、材质绑定/待复核状态；复杂画布提供电脑操作提示，不让隐藏视图继续获取键盘焦点。
- [ ] 键盘完整走通菜单与表单；关闭菜单焦点返回触发按钮；当前导航可识别；状态提示保留 status/alert。禁用与错误状态不只改变颜色。
- [ ] 检查 1440/820/390/320px 截图，修正遮挡、溢出和过小文字；尊重 prefers-reduced-motion。记录配色对比度检查，未测项目不得标为通过。
- [ ] 执行 `npm test`、`npm run build` 和新增导航浏览器测试；独立提交。

## Task 5：全链路验收与交接

- [ ] 更新既有浏览器流程的页面导航步骤，保留原业务断言；不删除三维、联合审批和并发冲突验证以迁就新页面。
- [ ] 在 `frontend/e2e/studio-navigation.spec.ts` 补齐真实双角色导航、刷新/前进后退、草稿保留、手机偏好确认与审批。使用后端响应或明确 UI 状态等待，不用固定睡眠。
- [ ] 前端运行 `npm test`、`npm run build`、`npm run test:e2e`；真实上游未运行时明确记录跳过，不将 skipped 算通过。
- [ ] 项目根运行 `uv run pytest -q`、`uv run ruff check src tests scripts`。不调用真实付费模型；本地测试服务器若受沙箱限制走授权流程。
- [ ] 新建 `docs/reports/frontend-studio-redesign-validation.zh-CN.md`：记录实际 SHA、命令/结果、设备截图、原有脏文件状态、未完成项、测试失败和是否修复；更新 `docs/15-project-handoff.zh-CN.md` 与前端运行说明。
- [ ] 最终审查页面功能映射，特别确认历史说明书/导出、结构化访谈、模拟提示、权限和审批失效无遗漏。只有实际验证的能力可标完成。
- [ ] 提交可归属改动；不自动合并、推送、部署。将余留风险与真实 DeepSeek 待验收边界交给用户。

## 计划自审

五页、账户、视觉、响应式、权限、草稿、旧路由、三维同步和验证分别覆盖于 Task 1–5。新导航类型仅一处定义；页面面板生命周期由 Task 2 管理，不能被 Task 3/4 的布局修改破坏。本计划不授权补开发样图额外能力。
