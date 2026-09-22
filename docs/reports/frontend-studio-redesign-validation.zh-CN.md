# Frontend Studio Redesign 验证报告（2026-09-22）

> 依据规格 `docs/superpowers/specs/2026-09-22-frontend-studio-redesign.md` 与计划 `docs/superpowers/plans/2026-09-22-frontend-studio-redesign.md` 实施。**未合并、未推送、未部署**。

## 1. 实际提交与基线

- 起始基线：`be273dc`（执行前实测，非永久事实）。
- 本改造提交：`abe597d` 路由与壳层、`b968aa8` 五页与草稿生命周期、`1455eb2` 视觉与空状态、`69e317b` 既有浏览器流程导航与新导航验收，以及本报告所在文档提交。
- 工作区仍保留执行前的 **6 个未提交文件**（预算自填与密码下限）：`frontend/e2e/auth-workflow.spec.ts`、`frontend/e2e/flow.ts`、`frontend/src/App.test.tsx`、`frontend/src/App.tsx`、`src/alignspace/auth/routes.py`、`tests/api/test_auth.py`。提交时仅挑选本任务可归属的 hunk，未整文件暂存；提交后脏文件 diffstat 与基线一致（59 insertions / 18 deletions）。

## 2. 实际命令与结果

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端 | `uv run pytest -q` | **336 passed** |
| Python 静态检查 | `uv run ruff check src tests scripts` | **All checks passed** |
| 前端单测 | `cd frontend && npm test` | **184 passed（14 文件）** |
| 类型与构建 | `cd frontend && npm run build`（含 `tsc --noEmit`） | **通过** |
| 浏览器验收 | `cd frontend && npm run test:e2e` | **16 passed**（含真实 OpenPlan3D 与双人联合审批） |

新增/更新测试：

- `frontend/src/navigation/workspaceRoute.test.ts`（7）：缺省概览、五个 page、非法回落、旧 brief 地址映射审批、构造 URL 保留 project 并删除 view/version。
- `frontend/src/layout/PersistentPanel.test.tsx`（2）、`WorkspaceShell.test.tsx`（4）：隐藏不卸载、隐藏内容移出可访问树、五入口、`aria-current`、Escape 关闭并归还焦点。
- `frontend/src/space/JointApproval.test.tsx`（2）：联合审批展示与双哈希提交。
- `frontend/src/workflow/Workspace.test.tsx`（42）：既有断言按页面导航后保留；新增切页保留未保存偏好、空间面板跨页不卸载。
- `frontend/e2e/studio-navigation.spec.ts`（1）：五页导航、草稿跨页保留、隐藏页不在可访问树、刷新保留页面、前进后退、1440/820/390/320 截图与 320px 无横向溢出、移动菜单 Escape 焦点归还。
- 既有 e2e（`auth-workflow`、`brief-reader`、`collaboration-resilience`、`preference-candidates`、`space-3d`、`space-binding`、`space-draft`、`space-joint-approval`）全部补充页面导航步骤后通过；三维、联合审批、并发冲突断言均保留，未删除。

## 3. 页面与能力映射

| 页面 | 现有能力 |
|---|---|
| 项目概览 | 项目状态/版本、偏好/约束/冲突/方案版本计数、等待提示、进入各页入口 |
| 灵感与偏好 | 参考图片上传/删除、PreferenceBoard、显式偏好、修改已有偏好、结构化访谈与未提交回答 |
| 设计协商 | 设计师反馈、约束新增/编辑/撤销、冲突与处理决定 |
| 空间方案 | SpaceBoard 房间/对象、2D/3D 预览、材质绑定与复核、同步与冲突提示 |
| 方案审批 | 方案目标、保存/重新生成/批准、说明书阅读入口（壳层全局按钮）、联合审批 |

- 联合审批从 `BindingPanel` 抽取为 `JointApproval`，在审批页使用；后端仍校验 `briefVersion/hash` 与 `spaceVersion/hash`，规则未重复实现。
- 旧 `?project=...&view=brief&version=...` 继续进入 `BriefDetail`；返回落到审批页。

## 4. 视觉与响应式

- 采用暖白 #F6F3EC、卡片 #FFFDF8、正文 #292B25、强调 #565D3D、边线 #DDD8CD；标题衬线、正文系统无衬线；8px 间距；`[hidden]{display:none!important}`；按钮/输入 ≥44px；焦点可见环。
- 断点 1024/768px：桌面左导航、平板折叠菜单、手机单列与抽屉。
- 浏览器在 1440/820/390/320px 截图保存于 `frontend/test-results/studio-*.png`（git-ignored），320px 断言无页面级横向溢出。

## 5. 未完成项与边界（不标为通过）

- **截图人工视觉审查未由本模型完成**：本执行环境的模型不支持读取图片，仅完成程序化的宽度/溢出/可访问性断言与截图采集。四档截图需由人工查看确认遮挡、字号与配色对比度；对比度按 4.5:1 目标实现但未逐项仪器测量。
- **真实 DeepSeek 联调待用户配置密钥后验收**；模拟分析仍明确标注，不冒充真实识图。
- 三维编辑仍是矩形化后端约束下的受控能力；上游 OpenPlan3D 需先运行 `scripts/fetch_openplan3d.sh`，未安装时 3D 用例自动跳过（本次已安装并通过）。
- 未新增聊天、收藏、在线成员、云依赖、付费调用或后端能力。

## 6. 风险

- `PersistentPanel` 依赖 `hidden` 与 CSS 的 `[hidden]` 规则；若后续新增 grid 规则覆盖需回归隐藏行为。
- e2e 页面导航依赖壳层导航的可访问名称；重命名页面需同步更新 `flow.ts` 的 `PAGE_LABELS` 与相关断言。
