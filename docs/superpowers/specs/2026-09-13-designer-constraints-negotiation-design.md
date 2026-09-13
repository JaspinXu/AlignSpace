# AlignSpace：设计师真实约束录入与基于约束的协商闭环设计

日期：2026-09-13
状态：已确认并实现（含第一轮验收修复）；后端与前端已接入。
范围：本轮目标——设计师真实约束录入/修改/撤销，以及基于实际约束的双方协商闭环。

## 1. 背景

真实运行流程此前由 `build_mock_agents()` 注入固定预算约束与冲突；`Constraint` 缺少作用对象/关联偏好、
提出者账户与撤销生命周期，也没有设计师写入 API，且约束变化不会使既有方案审批失效。

本轮用真实设计师输入替换固定 fixture，并打通“设计师录入/修改/撤销约束 → 屋主回应 → 调整偏好 →
解决冲突 → 重新生成说明书 → 双方重新审批”。

## 2. 本轮已确认的边界

- 替换真实流程中的固定预算约束与冲突；保留模拟 fixture 供独立测试使用。
- 复用现有数据结构，仅记录实际输入；对可明确比较的结构化条件使用规则检查。
- 专业可行性与成本判断由设计师明确提出，不得伪装成系统自动估价或自动理解。
- 屋主可查看理由、回应、修改偏好；未解决的冲突不得被自动标记为已解决。
- 影响说明书的变更必须使过时方案失效，且不能无条件覆盖双方已确认内容。
- 推迟多模态模型；不开发平面图/三维/效果图；不推送 GitHub、不部署云端、不调用付费模型。

## 3. 数据模型

### 3.1 Constraint 扩展

```text
applies_to: str = ""                 # 作用对象或关联偏好描述
attribute_id: str | None = None      # 可选：关联的偏好属性 id
proposed_by: str = ""                # 提出者账户 id
withdrawn: bool = False              # 撤销标记；保留历史，不进入方案
revision: int = 1                    # 实质变更时递增，用于区分历史与新冲突
incompatible_with: list[str] = []    # 设计师明确声明该约束排除的取值
```

字段映射：类别 `category`、内容 `statement`、理由 `rationale`、限制性质 `severity`、
提出者 `owner`＋`proposed_by`、确认状态 `verification_status`。

- 设计师新建默认 `owner=designer`、`verification_status=designer_asserted`、`proposed_by=当前账户`、
  `evidence` 至少一条 `designer_note`。
- 撤销保留记录（`withdrawn=True`），不进入对齐与说明书。
- **`revision` 仅在实质字段（内容、限制性质、作用对象、关联偏好、不兼容取值）变化时 +1**；
  仅改理由不递增。

### 3.2 Conflict 扩展

新增 `constraint_id: str | None`，标记该冲突由哪条约束、哪个版本派生。

### 3.3 方案 schema

`design-brief.schema.json` 的 `constraint` 允许可选 `appliesTo`、`attributeId`、`proposedBy`；
`revision`、`incompatibleWith`、`withdrawn` 为内部字段，不写入方案。`draft_brief` 只导出未撤销约束。

### 3.4 ProjectState

新增 `brief_stale: bool`，随项目行持久化（迁移 v4）。它表示当前最新方案已不再反映最新状态。

## 4. 规则化冲突推导（结构化、显式、非估价）

**只有当设计师在 `incompatible_with` 中明确列出与所关联已确认偏好取值相同（忽略大小写/空白）的项时，
才创建派生冲突；仅“有关联”不构成矛盾。**

- 派生冲突 id = `constraint-conflict-{constraintId}-r{revision}-{matchedValueTag}`，绑定约束版本**与当时匹配到的偏好取值**；`constraint_id=constraintId`，
  `type=preference_vs_constraint`，`severity` 取约束严重度，`status=open`。
  因此对某个取值的决定不会自动覆盖后来出现的**另一个不兼容取值**（会建立新的待处理冲突，旧结论保留为历史）。
- 每次协调（约束写入、偏好变更）都重算：保留所有人工已解决/接受未决的记录作为历史；对每条约束，
  至多保留一个 `open` 冲突，且只针对其**当前 revision**；旧 revision 的 open 冲突被新版本取代。
- 约束被撤销、关联被移除、偏好不再为 confirmed、或不兼容取值不再匹配时，其 open 派生冲突被移除
  （派生产物的收回，不等于把未解决冲突标记为已解决）。
- 实质变更（revision +1）若仍构成不兼容，会建立**新的** open 冲突，同时保留旧结论作为历史。

## 5. API 合约

```text
POST   /v1/projects/{projectId}/constraints                    # 设计师新增
PATCH  /v1/projects/{projectId}/constraints/{constraintId}     # 设计师修改
POST   /v1/projects/{projectId}/constraints/{constraintId}/withdraw  # 设计师撤销
GET    /v1/projects/{projectId}/constraints                    # 成员查看
POST   /v1/projects/{projectId}/realign                        # 成员：依据当前状态重新生成方案
```

`data`：`category`、`statement`、`rationale`、`severity`、`appliesTo`、`attributeId`、`incompatibleWith`。

权限与错误：仅设计师可写，成员可读，非成员 403；未知约束 404；已撤销约束不可编辑（400）；
版本过期/幂等冲突 409；错误沿用现有统一格式。

## 6. 方案失效与重新生成

- 任何影响说明书的变更（属性、约束、冲突）在有既有方案时：清除审批、置 `brief_stale=True`、
  状态回到 `alignment`；不改写既有 `brief_versions`。
- 过时方案**不可再审批**：`approve_brief` 在 `brief_stale` 为真时返回 `APPROVAL_NOT_ALLOWED`。
- `POST /realign` 依据当前状态生成**新版本**方案（版本号递增），清空审批、`brief_stale=False`、
  状态 `awaiting_approval`；若当前不满足生成条件（完整性 <0.85 或有 open critical 冲突），
  则保持/回到 `alignment`，不生成新方案。
- `realign` 从**最新方案**出发：仅覆盖系统派生字段（项目/状态/完整性/版本/审批/属性/约束/冲突/未决项），
  保留用户已编辑内容（如 `goals`）；仅在无历史方案时才回退到示例模板。
- 过时方案执行普通编辑（`edit_brief`）时：先按当前状态重建内容（含最新约束），
  再叠加请求中的用户可编辑字段（如 `goals`），生成新版本；不会保存过时的约束集合。
- 双方随后对**同一新版本与同一内容哈希**重新审批。

## 7. 真实流程与测试 fixture 分离

- `build_mock_agents()` 为真实流程：视觉仍为确定性模拟，设计师约束来自真实输入。
- `build_fixture_agents()` 保留原预算约束与冲突，仅供隔离测试。

## 8. 前端

- 设计师：约束录入与**编辑**（类别、作用对象、可选关联偏好、不兼容取值、内容、理由、限制性质）、
  撤销；角色化写权限。
- 屋主：查看约束与理由、**修改已有偏好**（含被约束关联的偏好）、提交冲突决定；无设计师写控件。
- 方案面板：`brief_stale` 时显示“方案已过时，请重新生成后再审批”，隐藏“批准此版本”并提供
  “重新生成方案”；非过时时才可审批。
- 显式偏好按维度写入稳定的 `manual-<dimension>` 属性，避免相互覆盖。

## 9. 测试计划

- 领域/单元：显式不兼容判定、revision、协调（含保留历史与新版本冲突）、`flag_brief_change`。
- API：权限、版本、幂等、撤销、冲突生命周期、**偏好变更重新协调**、**过时方案阻断再审批**与
  `realign` 重新生成后再审批。
- 前端：约束录入/编辑/撤销、不兼容取值、修改已有偏好、过时方案按钮切换。
- 浏览器：两账户走通“录入约束→冲突→解决→生成方案→审批→审批后修改约束→方案过时→重新生成→
  重新审批”。

## 10. 非目标

多模态模型、平面图/三维/效果图、云部署、付费模型调用、GitHub push。

## 11. 验收标准

- 设计师可新增/编辑/撤销约束，屋主不可写；非成员不可见。
- 只有显式声明不兼容才产生冲突；实质变更后建立新的待处理冲突且保留历史结论。
- 偏好变化会重新检查关联冲突。
- 过时方案不可再审批；重新生成新版本后双方重新审批。
- 后端、前端、双账户浏览器测试全部通过；本地提交，不推送。
