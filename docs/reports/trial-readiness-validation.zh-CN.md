# AlignSpace 试运行保障验证报告（中文）

> 执行者身份：本报告由实现模型（AI）在本地真实浏览器与真实后端上运行自动化试用用例后撰写，
> **不是真实用户，也不代表用户满意度**。本阶段交付的是现有初版本地试运行的可靠性与可操作证据，
> 不代表生产就绪或真实 AI 能力已验证。

## 1. 实施工作区与提交

- 工作区：`/Users/shawn_chen/Documents/GitHub/Design_Inspiration_Agents`
- 分支：`codex/trial-readiness`（从已验收基线 `shawn` @ `8deab24` 创建）
- 最终 HEAD：`1f65b55`
- 提交：
  1. `67d1721` docs: add trial readiness handoff plan
  2. `002eee6` test/fix: verify workflow restart and retry recovery
  3. `8248afe` test/fix: cover concurrent collaboration and session recovery
  4. `1f65b55` feat: add verified offline backup and restore tools
- 工作区状态：`git status --short` 干净；**未合并、未推送、未部署、未调用外部付费模型**。
- 迁移版本：v5（幂等记录含 `completed`）。

## 2. 任务完成情况与文件清单

### 任务 A：中断、重启与网络重试

| 文件 | 说明 |
|---|---|
| `tests/integration/workflow/test_restart_recovery.py`（新增） | 关闭并重建应用的真实恢复测试 |
| `tests/api/test_interview.py`（已有） | 删除两阶段幂等与故障恢复 |

计划场景 → 测试对应：

| 计划场景 | 测试 |
|---|---|
| 屋主待答节点重建应用后继续 | `test_restart_at_homeowner_wait_continues` |
| 设计师待反馈节点重建后继续 | `test_restart_at_designer_wait_continues` |
| 待双方审批节点重建后继续 | `test_restart_at_awaiting_approval_continues` |
| 服务端已写入、客户端未收到响应，同键同体重试 | `test_answer_retry_after_restart_returns_the_same_result`；另见 `tests/api/test_workflow.py`（回答重放）、`test_constraints.py`（约束重放）、`test_interview.py`（删除重放） |
| 删除推进失败 / 最终响应保存失败后重试 | `test_delete_retry_resumes_after_a_failed_advance`、`test_delete_retry_finalises_after_a_failed_response_save` |
| 重启后删除恢复 | `test_delete_advance_recovery_survives_restart` |
| 同键不同体 409 / 版本过时 409 | `test_asset_upload.py`、`test_constraints.py`、`test_workflow.py`（已有） |
| 有限重试与 409 保留输入 | `frontend/src/api.test.ts`、`frontend/src/workflow/Workspace.test.tsx`（已有） |

### 任务 B：多标签页与双角色协作

| 文件 | 说明 |
|---|---|
| `frontend/e2e/collaboration-resilience.spec.ts`（新增） | 真实浏览器多标签/双角色协作 |
| `frontend/e2e/flow.ts`（新增） | 共享的浏览器流程辅助 |

| 计划场景 | 测试 |
|---|---|
| 同一约束并发编辑：第一份成功、第二份 409、保留输入并重新提交 | `concurrent constraint edits keep the stale tab input and allow a resubmit` |
| 旧问题所在标签页不得把旧回答写入下一题 | `a stale tab cannot write its old answer into the next question` |
| 另一标签页改变约束后旧审批被拒，重新生成并双方批准 | `an approval is rejected after another tab changes a constraint, then regenerated` |
| 同账户一页退出、另一页会话失效 | `logging out in one tab ends the session in the other tab`（并沿用 `auth-workflow.spec.ts` 的跨标签页退出覆盖） |

### 任务 C：离线备份、恢复与安全重置

| 文件 | 说明 |
|---|---|
| `scripts/_trial_data.py`（新增） | 备份/恢复共享逻辑与校验 |
| `scripts/backup_local.py`（新增，可执行） | 离线备份 CLI |
| `scripts/restore_local.py`（新增，可执行） | 恢复到全新目录 CLI |
| `tests/integration/persistence/test_backup_restore.py`（新增） | 备份/恢复/续答与故障拒绝 |
| `docs/runbooks/local-backup-restore.zh-CN.md`（新增） | 操作手册 |

### 任务 D：内部试用、启动手册与交接同步

| 文件 | 说明 |
|---|---|
| `docs/runbooks/internal-trial.zh-CN.md`（新增） | 内部模拟试用手册 |
| `docs/reports/trial-readiness-validation.zh-CN.md`（本文） | 验证报告 |
| `README.backend.md`、`README.frontend.md`、`docs/15-project-handoff.zh-CN.md`（更新） | 运行说明与交接顶部同步 |

## 3. 实际发现的缺陷

**本轮未确认新的产品缺陷，`src/` 未做任何修改。** 计划中的 A、B、C 场景新增覆盖首次即通过
（重启恢复 4 项、回答重试 1 项、协作 4 项、备份恢复 3 项），按计划要求记录为**新增验证**，未制造虚假失败。

- 参考：`git diff --name-only 8deab24..1f65b55 -- src` 为空。
- 编写协作用例时出现的两次失败均为**测试同步问题**（设计师页面在屋主推进流程后仍是旧快照，未刷新即写入导致 409），已在 `flow.ts`/spec 中通过显式刷新与确定性等待修正，非产品缺陷。
- 删除的两阶段幂等恢复（推进前失败、推进后保存失败）属**上一轮**已修复并合入基线 `8deab24` 的问题（`ec6d2ce`、`c3a290c`），本轮以重启场景再次回归。

## 4. 测试命令与结果（本轮实际运行）

工作区根目录：

```bash
uv run pytest -q                 # 237 passed
uv run ruff check src tests scripts   # All checks passed
```

`frontend/`：

```bash
npm test        # 58 passed
npm run build   # tsc --noEmit && vite build 成功
npm run test:e2e  # 连续三次：5 passed (36.6s) / 5 passed (36.5s) / 5 passed (36.7s)
```

浏览器套件共 5 条：`auth-workflow.spec.ts` 1 条 + `collaboration-resilience.spec.ts` 4 条。
三次连续运行全部通过；本轮另有一次 5 passed（36.9s）用于采集截图证据。

- 环境失败：无（无网络依赖、无外部模型）。
- 截图：由浏览器运行生成于被忽略的 `frontend/test-results/`（如 `workspace-desktop.png`、`workspace-mobile.png`），不提交仓库。

## 5. 备份恢复演练

由 `tests/integration/persistence/test_backup_restore.py::test_offline_backup_restore_and_resume` 作为可复现演练：

1. 用真实账户建立项目：两名成员、3 张真实图片、已确认偏好、设计师约束、方案历史（v1）与待审批检查点。
2. 停止应用（关闭引擎与检查点连接）。
3. `backup_local.py` 生成包含 `database.sqlite3`、`checkpoints.sqlite3`、`assets/` 与 `manifest.json` 的备份（迁移版本 5，清单无绝对路径）。
4. `restore_local.py` 恢复到全新目录。
5. 用恢复后的三个路径重建应用并登录：成员权限、原图读取、方案版本与内容哈希一致，待审批流程可继续，双方批准后项目 `approved`。

故障拒绝用例：缺少文件、篡改图片哈希、目标已存在、缺少 `--confirm-stopped`、目标与源重叠、缺失源——均被拒绝，且验证原库原图**未改变**。备份包本身未提交仓库（敏感资料）。

## 6. 手册与报告路径

- 内部试用手册：`docs/runbooks/internal-trial.zh-CN.md`
- 备份恢复手册：`docs/runbooks/local-backup-restore.zh-CN.md`
- 本验证报告：`docs/reports/trial-readiness-validation.zh-CN.md`
- 交接文档顶部：`docs/15-project-handoff.zh-CN.md`

## 7. 剩余风险与建议后续

- 备份仅支持**停服后的离线一致性**；无在线快照，`--confirm-stopped` 依赖操作者确认。
- 恢复只写入全新目录，需操作者手动切换三个数据路径并重启服务。
- 仅更换 `ALIGNSPACE_AUTH_SECRET` **不会**撤销已有会话；强制下线需另行处理会话表。
- 访谈为结构化选择；自由文本仅为备注、不解析；图片分析仍为每图四条固定模拟观察，不可用于评估真实识图。
- `realign` 需手动触发；无平面图/空间建模/三维/效果图/云部署。
- 建议后续：接入真实多模态与语言 provider（统一数据接口）、真实数据评估、部署到赛事指定环境。

## 8. 结论

A–D 均已完成并有自动化或可复现证据；后端 237、前端 58、浏览器 3×5 全部通过；
`src/` 无改动；分支干净。**明确声明：未合并、未推送、未部署、未调用外部付费模型，等待统一验收。**
