# 里程碑③：地板联动与联合审批 验证报告（2026-09-21）

> 分支 `codex/preference-space-integration`。本轮**不合并、不推送、不部署、不调用外部付费模型**。
>
> **真实 DeepSeek 联调待用户配置密钥后验收。** 本里程碑使用确定性模拟与受支持材质目录，模拟通过 **≠** 真实识图或真实材质识别已验证。

## 1. 范围

在里程碑②空间持久化之上完成：

- `SpaceBinding`（迁移 **v8**）与 `SpaceApproval` 持久化。
- 绑定 / 应用 / 复核接口，以及说明书＋空间联合审批接口。
- 闭环：已确认地板偏好 → 绑定房间 → 受支持材质 → 适配说明（近似需确认）→ 应用生成新空间版本 → 重载保持。
- 规则：不支持材质明确报错；近似替代需显式确认；未确认的模型推断/设计师意见不能绑定；房间删除导致绑定转 `needs_review`，不静默转移；偏好被修改时相关绑定转 `needs_review` 且清空空间审批；旧空间审批不适用于新版本。
- 前端 `BindingPanel` 联动 UI，接入 `SpaceBoard`/`Workspace`。

## 2. 数据模型与迁移

- `SpaceBinding`：`roomId`、`target=floor`、`attributeId`、`candidateId?`、`materialOptionId`、`approximation(exact|approximate)`、`note`、`status(active|needs_review|invalidated)`、`boundBy/boundAt`、`spaceVersion`、`appliedSpaceVersion?`。
- `SpaceApproval`：`role`、`actorId`、`briefVersion/briefHash`、`spaceVersion/spaceHash`、`approvedAt`；与既有 `Approval`（仅说明书）分离。
- 迁移 **v8** 新增 `space_bindings`、`space_approvals`；历史项目无行，不伪造历史绑定或联合审批。

## 3. 接口

```
GET    /v1/projects/{id}/space/bindings
POST   /v1/projects/{id}/space/bindings                 # 仅屋主
POST   /v1/projects/{id}/space/bindings/{bindingId}/apply
POST   /v1/projects/{id}/space/bindings/{bindingId}/review
GET    /v1/projects/{id}/space/approvals
POST   /v1/projects/{id}/space/approvals                # 联合审批
```

错误码：`UNSUPPORTED_MATERIAL`（409）、`APPROXIMATION_REQUIRES_CONFIRMATION`（409）、`SPACE_STATE_INVALID`（409）、`SPACE_APPROVAL_MISMATCH`（409）。

## 4. 权限（按用户确认）

| 能力 | 屋主 | 设计师 |
|---|---|---|
| 创建绑定（已确认偏好→空间对象） | ✅ | ❌（403） |
| 应用材质（生成新空间版本） | ✅ | ✅ |
| 复核/作废绑定 | ✅ | ✅ |
| 联合批准交付方案 | ✅ | ✅ |
| 查看绑定与审批 | ✅ | ✅ |

## 5. 实际运行结果（2026-09-21）

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端全量 | `uv run pytest -q` | **330 passed** |
| 静态检查 | `uv run ruff check src tests scripts` | **All checks passed** |
| 前端单测 | `cd frontend && npm test` | **142 passed（10 文件）** |
| 前端构建/类型 | `cd frontend && npm run build`（含 `tsc --noEmit`） | **通过** |
| 浏览器验收 | `cd frontend && npm run test:e2e` | **13 passed** |

新增/相关测试：

- `tests/api/test_space_bindings.py`（10）：绑定+应用+重载、仅屋主可绑定/设计师可应用、未确认偏好被拒、不支持材质报错、近似需确认、删除房间标记 `needs_review` 且不转移、复核重绑/作废、联合审批需双方版本+哈希、旧空间审批不适用于新版本、仅说明书审批不算联合批准。
- `frontend/src/space/BindingPanel.test.tsx`（5）、`spaceNoCloud.test.ts`（新增 BindingPanel 覆盖）。
- `frontend/e2e/space-binding.spec.ts`（1）：确认地板偏好 → 绑定 → 应用 → 重载后材质与绑定保持，且联合审批入口可见。

## 6. 边界与风险

- 浏览器验收覆盖了“偏好→绑定→应用→重载”的完整联动；联合审批的完整双人浏览器流程由后端 API 集成测试覆盖，未在浏览器中重复跑完整访谈，以避免与既有 `auth-workflow` 套件重复。
- 材质目录为代码内静态表（地面 4 项、墙面 1 项），地板与墙面目录隔离；不支持取值一律报错，不做静默近似。
- 真实 DeepSeek 材质识别未接入；`CandidatePreference` 的材质候选仍为 `uncertain`，必须由屋主给出确认值后才能绑定。

## 7. 结论

里程碑③闭环全部通过：已确认地板偏好可受控映射到受支持材质、生成新空间版本并在重载后保持；不支持/近似/未确认输入均被正确拒绝；房间身份变化与偏好修改会显式触发复核，联合审批严格绑定说明书与空间两者的版本与哈希。

## 8. 评审修复与 OpenPlan3D 真实集成（2026-09-21 追加）

针对代码评审提出的 5 项 P1：

| 评审项 | 处理 |
|---|---|
| OpenPlan3D 无可运行集成 | 在固定 SHA `d68cadf…` 上安装双向桥并注入 `editor/+page.svelte`：ready→导入（保留房间/对象 ID、按材质设置地板纹理）→ `currentProject` 变更回传→受控 API 落库；新增真实启动的浏览器验收 `frontend/e2e/space-3d.spec.ts` |
| 地板材质未进入 3D | handoff 新增 `alignspaceFloorMaterials` 与 `section.color`，桥按材质设置 `floorTexture`/颜色 |
| brief_stale 时联合审批仍显示已批准 | `_approval_view()` 在 `brief_stale` 时判为失效，历史批准保留 |
| 手选材质绕过近似确认 | 手选目标与偏好映射一致时沿用 `approximate`；不同项视为替代仍需确认 |
| 重新绑定绕过屋主且默认 rooms[0] | 复核仅屋主（403），必须显式选择目标房间，重算近似并要求必要确认 |

追加实测（本机隔离临时目录）：后端 **334**、前端 **149**、浏览器 **14**（含真实 OpenPlan3D）、Ruff/构建/`tsc` 通过。提交 `71d09df` 及后续 3D 集成提交。

> **真实 DeepSeek 联调待用户配置密钥后验收。**
