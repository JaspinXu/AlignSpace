# AlignSpace：设计师真实约束录入与基于约束的协商闭环设计

日期：2026-09-13
状态：设计草案，待用户复核；尚未实施。
范围：本轮目标——设计师真实约束录入/修改/撤销，以及基于实际约束的双方协商闭环（后端优先、前端随后）。

## 1. 背景

当前 `Constraint` 模型已有类别、内容、理由、限制性质、确认状态、提出角色与证据，但：

- 真实运行流程由 `build_mock_agents()` 注入固定预算约束与冲突；
- 缺少“作用对象或关联偏好”“提出者账户”“撤销”生命周期；
- 约束只能被读取，没有设计师写入 API；
- 约束变化不会使既有方案审批失效。

本轮用真实设计师输入替换固定 fixture，并打通“设计师录入约束 → 屋主回应 → 调整偏好或约束 → 解决冲突 → 更新说明书 → 双方重新审批”。

## 2. 本轮已确认的边界

- 替换真实流程中的固定预算约束与冲突；**保留模拟 fixture 供独立测试**使用。
- 复用现有数据结构，仅记录**实际输入**的约束，不预建空约束。
- 对**可明确比较的结构化条件**使用规则检查；专业可行性与成本判断由设计师明确提出，
  不得伪装成系统自动估价或自动理解。
- 屋主可查看理由、回应、修改偏好；**未解决的冲突不得被自动标记为已解决**。
- 影响说明书的约束变化必须重新检查方案并使过时审批失效，不能无条件覆盖双方已确认内容。
- 推迟多模态模型接入；不开发平面图建模、三维设计或效果图生成。
- 不推送 GitHub、不部署云端、不调用付费模型。

## 3. 数据模型

### 3.1 Constraint 扩展

在现有字段基础上新增（沿用其余字段）：

```text
applies_to: str = ""            # 作用对象或关联偏好描述，例如 "living_room" / "worktop"
attribute_id: str | None = None # 可选：关联的偏好属性 id
proposed_by: str = ""           # 提出者的账户 id（历史追溯）
withdrawn: bool = False         # 撤销标记；保留记录用于历史
```

字段语义映射（本轮要求 → 现有/新增）：

| 要求 | 字段 |
|---|---|
| 约束类别 | `category`（已有） |
| 作用对象或关联偏好 | `applies_to`（新）+ `attribute_id`（新） |
| 内容 | `statement`（已有） |
| 理由 | `rationale`（已有） |
| 限制性质 | `severity`（已有：advisory/important/critical） |
| 提出者 | `owner`（已有） + `proposed_by`（新） |
| 确认状态 | `verification_status`（已有） |

- 设计师新建约束默认 `owner=designer`、`verification_status=designer_asserted`、`proposed_by=当前账户`、
  `evidence` 至少一条 `designer_note`。
- `verified` 仍要求专业身份归属与专业复核证据（沿用现有校验），设计师普通陈述不得提升为“已核验事实”。
- 撤销（withdraw）不删除记录：置 `withdrawn=True` 并保留历史；`withdrawn` 的约束不进入对齐与说明书。

### 3.2 Conflict 扩展

新增 `constraint_id: str | None = None`，标记该冲突由哪条约束派生，便于生命周期联动。

### 3.3 方案 schema

`schemas/design-brief.schema.json` 的 `constraint` 允许新增可选字段 `appliesTo`、`attributeId`、`proposedBy`。
`draft_brief` 只导出**未撤销**的约束；已撤销约束不写入说明书。

## 4. 规则化冲突推导（结构化、非估价）

在设计师**新增或修改**约束时执行：

- 若 `severity ∈ {important, critical}` 且 `attribute_id` 指向一条 **`confirmed`** 偏好，
  则创建/刷新一条派生冲突：
  - `id = "constraint-conflict-" + constraintId`
  - `type = preference_vs_constraint`
  - `summary = constraint.statement`
  - `impact = "与已确认偏好「<属性值>」冲突，需屋主或设计师决定"`
  - `severity = constraint.severity`，`status = open`
  - `constraint_id = constraintId`
- 若已存在同 id 且已被人工 `resolved`/`accepted_unresolved`，则**不重新打开**。
- 这是结构化规则：只比较“关联偏好是否已确认 + 限制性质”，不做成本或可行性推断。

约束**修改或撤销**后：

- 若派生冲突仍为 `open` 且冲突条件不再成立（关联被移除、属性不再 confirmed、严重度降为 advisory、
  或约束被撤销），则**移除该派生 open 冲突**——它是派生产物，不是“人工解决”。
- **绝不**自动把未解决冲突标记为 resolved；已有 resolved/ accepted_unresolved 记录保留为历史。

## 5. API 合约

均为版本化 envelope；角色从项目成员关系解析。

```text
POST   /v1/projects/{projectId}/constraints                    # 设计师新增
PATCH  /v1/projects/{projectId}/constraints/{constraintId}     # 设计师修改（仅自己提出的约束）
POST   /v1/projects/{projectId}/constraints/{constraintId}/withdraw  # 设计师撤销
GET    /v1/projects/{projectId}/constraints                    # 项目成员查看
```

`POST` / `PATCH` 的 `data`：

```json
{
  "category": "budget",
  "statement": "天然石材工作台超出当前预算档位",
  "rationale": "改用石材效果饰面可在预算内实现相近观感",
  "severity": "important",
  "appliesTo": "worktop",
  "attributeId": "manual-material"
}
```

规则：`statement`、`category` 必填；`severity` 默认 `important`；`rationale` 可空；
`attributeId` 可空，但若提供必须指向本项目已有属性。

权限与错误：

- 仅 `designer` 可写；`homeowner` 或非成员写 → 403。
- 仅项目成员可读；非成员 → 403。
- `constraintId` 不存在 → 404；修改他人/已撤销约束 → 409。
- `expectedStateVersion` 过期 → 409；同键不同内容 → 409；同键同内容重放 → 返回首次结果。
- 全部走现有 `AuthorizationError` / `StaleStateError` / `IdempotencyConflictError` 错误格式。

## 6. 审批失效与方案重检

任何**影响说明书的变更**（属性、约束、冲突）在存在既有审批时：

- 清除 `approvals`，并将状态置回 `alignment`（需要重新生成方案与重新审批）；
- 不修改已存在的 `brief_versions` payload；
- 版本按常规 +1。

`approve_brief` 继续要求同一版本 + 同一内容哈希，且 `can_draft_brief` 成立（完整性 ≥0.85 且无 open critical 冲突）。
由此实现“约束变化使过时审批失效”，且不覆盖双方已确认内容。

## 7. 真实流程与测试 fixture 分离

- `build_mock_agents()` 改为**真实流程**：视觉仍为确定性模拟，`DesignerAgent` 不再注入 fixture 约束/冲突。
- 新增 `build_fixture_agents()`（测试专用）保留原预算约束与冲突，供隔离测试使用；
  需要既有 fixture 的测试显式注入该 builder。
- `create_app` 默认使用真实流程。

## 8. 前端（后端完成后）

- 设计师：约束录入表单（类别、作用对象、可选关联偏好、内容、理由、限制性质）、修改、撤销、
  冲突列表与提交决定；仅设计师可见写操作。
- 屋主：查看约束及理由、修改**关联偏好**、提交冲突决定；看不到设计师写控件。
- 复用现有版本/idempotency/409 处理；等待视图行为不变。
- 文案保持诚实：约束来自设计师实际输入，不做自动估价或自动可行性判断。

## 9. 测试计划

- 领域/单元：Constraint 字段与校验、撤销语义、规则化冲突推导与撤销联动、审批失效策略。
- API：设计师新增/修改/撤销/查询；屋主不可写、非成员不可读写；版本过期、幂等重放与冲突；
  规则派生冲突生命周期；约束变更清除审批。
- 验收：两个真实账户——设计师录入约束 → 屋主查看理由 → 屋主调整偏好/回应 → 解决冲突 →
  重新生成并双方重新审批。不同实际输入产生对应协商结果。
- 前端：角色化约束 UI、撤销、冲突、审批失效；双账户浏览器流程。
- 重新验证基线（不沿用旧结果）：后端 193、前端 49、双账户浏览器 1。

## 10. 非目标

多模态模型、平面图/三维/效果图、云部署、付费模型调用、GitHub push。

## 11. 验收标准

- 设计师可新增/修改/撤销约束，屋主不可写；非成员不可见。
- 不同实际约束输入产生不同的冲突/协商结果；同输入重放幂等。
- 未解决冲突不会被自动标记为已解决。
- 约束变化会使过时审批失效，并走“重新对齐—更新说明书—双方重新审批”。
- 真实流程不再出现固定预算约束；独立测试仍可用 fixture。
- 后端、前端、双账户浏览器测试全部通过；更新交接文档与运行说明；本地提交，不推送。
