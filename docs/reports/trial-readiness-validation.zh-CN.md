# AlignSpace 试运行保障验证报告（中文）

> 执行者身份：本报告由实现模型（AI）在本地真实浏览器与真实后端上运行自动化试用用例后撰写，
> **不是真实用户，也不代表用户满意度**。本阶段交付的是现有初版本地试运行的可靠性与可操作证据，
> 不代表生产就绪或真实 AI 能力已验证。

## 1. 实施工作区与提交

- 工作区：`/Users/shawn_chen/Documents/GitHub/Design_Inspiration_Agents`
- 分支：`codex/trial-readiness`（从已验收基线 `shawn` @ `8deab24` 创建）
- 提交：
  1. `67d1721` docs: add trial readiness handoff plan
  2. `002eee6` test/fix: verify workflow restart and retry recovery
  3. `8248afe` test/fix: cover concurrent collaboration and session recovery
  4. `1f65b55` feat: add verified offline backup and restore tools
  5. `bb41246` docs: add internal trial runbook and verified handoff
  6. `fix: harden backup validation and extend trial coverage`（本轮修复与覆盖补齐）
- 迁移版本：v5。工作区状态：干净；**未合并、未推送、未部署、未调用外部付费模型**。

## 2. 任务 A–D 完成情况

| 任务 | 状态 | 主要文件 |
|---|---|---|
| A 中断/重启/网络重试 | 完成 | `tests/integration/workflow/test_restart_recovery.py`（7 项） |
| B 多标签页与双角色协作 | 完成 | `frontend/e2e/collaboration-resilience.spec.ts`（7 项）、`frontend/e2e/flow.ts` |
| C 离线备份/恢复 | 完成（含本轮修复） | `scripts/_trial_data.py`、`backup_local.py`、`restore_local.py`、`test_backup_restore.py`（6 项） |
| D 内部试用与交接 | 完成 | `docs/runbooks/internal-trial.zh-CN.md`、本报告、README/交接更新 |

场景 → 测试对应（本轮补齐后）：

| 计划/验收场景 | 测试 |
|---|---|
| 三等待节点重建应用后继续、内容保全 | `test_restart_at_homeowner_wait_continues`、`test_restart_at_designer_wait_continues`（逐项比较偏好/约束）、`test_restart_at_awaiting_approval_continues`、`test_restart_preserves_multiple_brief_versions`（两个方案版本） |
| 服务端已写入、客户端未收到响应，同键重试 | `test_answer_retry_after_restart_returns_the_same_result` 及既有重放测试 |
| 删除推进失败 / 推进后保存失败后重试（含重启） | `test_delete_retry_resumes_after_a_failed_advance`、`test_delete_retry_finalises_after_a_failed_response_save`、`test_delete_advance_recovery_survives_restart`、`test_delete_finalise_failure_completes_after_restart`（完成后重放不增版本/问题） |
| 同一约束并发编辑（同一 ID） | `editing the same constraint from two tabs keeps the stale input and resubmits` |
| 另一标签页改约束后审批失效并重新生成 | `an approval is rejected after another tab changes a constraint, then regenerated` |
| 旧问题标签页不得写入下一题 | `a stale tab cannot write its old answer into the next question` |
| 删除待答问题来源图后另一页面恢复下一步 | `deleting a question source image lets another tab reach the next step` |
| 跨标签页退出 | `logging out in one tab ends the session in the other tab` |
| 刷新响应晚于退出到达 | `a refresh response arriving after logout cannot restore the session` |
| 备份完整性/符号链接/清单集合/目标重叠 | `test_backup_restore.py`（6 项） |

## 3. 本轮确认的产品缺陷与修复

**1. [P1] 备份静默遗漏符号链接目录** — `scripts/_trial_data.py`
- 根因：`os.walk` 默认不进入符号链接目录，且未检查 `directories` 中的链接，导致链接目录内的文件被跳过却报告成功。
- 修复：`copy_tree`/`walk_files` 明确拒绝任何符号链接目录或文件。
- 回归：`test_backup_rejects_symlinked_directory`（返回非零、无输出目录、报错含 symlink）。

**2. [P2] 恢复清单未校验完整文件集合** — `scripts/_trial_data.py`
- 根因：只逐个校验清单中列出的文件，未比对实际文件集合，未登记/被改动的文件仍会被复制。
- 修复：`verify_manifest` 要求清单无重复、两个数据库均在清单中，且实际文件集合与清单**一一对应**。
- 回归：`test_restore_rejects_files_that_do_not_match_the_manifest`（移出清单的图片、缺失数据库条目均被拒绝）。

**3. [P2] 恢复目标未禁止与备份重叠** — `scripts/_trial_data.py`
- 根因：未检查目标与备份目录的包含关系，允许恢复到备份目录内部，存在递归复制风险。
- 修复：创建目标前用 `resolve()` 规范化路径（跟随符号链接祖先），拒绝源与目标互相包含。
- 回归：`test_restore_rejects_a_destination_inside_the_backup`。

补充（支持性改动，非缺陷）：注册的按 IP 限流上限改为可配置 `ALIGNSPACE_REGISTER_IP_LIMIT`（默认 10），
端到端测试环境设为 100，以容纳一次运行内多条用例的集中注册；回归 `test_register_ip_limit_is_configurable`。

**说明**：上一轮报告曾称“未确认新缺陷、A–D 全部完成”，该结论在备份工具上不成立；本报告已按事实修正。

## 4. 测试命令与结果（本轮实际运行）

工作区根目录：

```bash
uv run pytest -q                       # 243 passed
uv run ruff check src tests scripts    # All checks passed
```

`frontend/`：

```bash
npm test        # 58 passed
npm run build   # 成功
npm run test:e2e # 连续三次：8 passed (44.4s) / 8 passed (44.5s) / 8 passed (44.3s)
```

浏览器套件 8 条 = `auth-workflow`(1) + `collaboration-resilience`(7)。环境失败：无。

## 5. 三类案例的实际执行记录（真实浏览器）

每类均由自动化在真实 Chromium + 真实后端执行；截图由运行生成于被忽略的 `frontend/test-results/`。

| 案例 | 角色 | 步骤（摘要） | 预期 | 实际 | 阻塞 |
|---|---|---|---|---|---|
| 一 普通对齐成功 | 屋主+设计师 | 注册/登录 → 创建 → 项目码加入 → 上传 3 图 → 启动分析 → 广选部位 → 逐部位“喜欢” → 显式偏好 → 设计师约束+反馈 → 生成 v1 → 双方批准 | 双人审批 `approved` | `auth-workflow` 通过（26s），含 1600×1200 上传/预览/删除/审批 | 无 |
| 二 冲突后修改并重新审批 | 屋主+设计师 | 生成方案后设计师改约束 → 旧审批被拒 → 屋主重新生成 v2 → 双方批准 v2 | 409 拒绝旧审批、v2 通过 | `an approval is rejected ... then regenerated` 通过 | 无 |
| 三 跳过/删除来源图/中断重试/备份恢复 | 屋主（两标签） | 跳过问题不建偏好 → 删除唯一来源图退役问题 → 另一标签刷新到下一步 → 重启后继续 → 备份/恢复后继续 | 不建空记录、不卡流程、恢复后可继续 | `deleting a question source image ...`、`test_restart_*`、`test_offline_backup_restore_and_resume` 均通过 | 无 |

未在浏览器中单独重跑的三类案例中的“服务中断”以应用重建测试覆盖（真实关闭并重建应用，而非仅刷新页面）。

## 6. 备份恢复演练

`test_offline_backup_restore_and_resume`：真实两账户 + 3 图 + 已确认偏好 + 约束 + 两版本方案历史 + 待审批检查点 →
停服 → 备份（`database.sqlite3`/`checkpoints.sqlite3`/`assets/`/`manifest.json`，迁移版本 5，清单无绝对路径）→
恢复到新目录 → 用恢复后三路径重建应用 → 登录并双方批准。故障拒绝用例（缺文件、篡改图片、清单集合不符、
目标已存在、缺 `--confirm-stopped`、目标重叠、符号链接、缺失源）全部被拒绝，且验证原库原图未改变。备份包未提交。

## 7. 手册与报告路径、剩余风险

- 手册：`docs/runbooks/internal-trial.zh-CN.md`、`docs/runbooks/local-backup-restore.zh-CN.md`
- 报告：`docs/reports/trial-readiness-validation.zh-CN.md`
- 剩余风险：备份仅限停服离线一致性；恢复需手动切换三路径并重启；仅换密钥不撤销既有会话；访谈为结构化选择、不做自由文本理解；图片分析仍为每图四条固定模拟观察；`realign` 手动触发。
- 建议后续：评审/合并本分支，或经确认后接入真实多模态/语言 provider 并做真实评估与部署。

## 8. 结论

A–D 已按要求补齐缺陷修复与验收覆盖；后端 243、前端 58、浏览器 8×3 全部通过；工作区干净。
**明确声明：未合并、未推送、未部署、未调用外部付费模型，等待统一验收。**
