# 图片偏好分析框架 ＋ OpenPlan3D 集成 设计规格

> 状态：**已定稿**（角色权限已于 2026-09-21 由用户确认，见第 7 节）。
> 日期：2026-09-21。基线：`codex/brief-reader` @ `5843774`；工作分支 `codex/preference-space-integration`。
> 本轮**不调用任何真实付费接口**，不合并、不推送、不部署。

## 0. 范围与不变量

必须在改造中始终保持的不变量（违反即视为缺陷）：

1. **三类事实分离**：屋主表达的关注维度 ≠ 模型观察/推断的取值 ≠ 屋主确认的设计需求。三者不得互相冒充。
2. **单一正式偏好体系**：只有 `Attribute` 是正式共享偏好。候选内容（设计条目/候选偏好）是*候选组织方式*，确认后才写入 `Attribute`，不建立第二套并行正式偏好。
3. **候选不是项目**：设计条目不新增成员、预算、独立审批，不成为独立业务实体。
4. **不默认整图喜欢**，不为未提及维度批量建空偏好。
5. **模型输出只能提出候选**，不能直接执行业务写入或空间修改。
6. **本地写幂等 ≠ 外部调用只计费一次**。外部调用重试必须与本地幂等分开描述。
7. **权威数据在后端**：浏览器本地存储只能作临时草稿。
8. 不改写既有已确认/人工修改内容；不删除历史结论换同步。
9. 参考图片删除后：未确认候选不得继续应用；已确认偏好按既有规则保留来源历史并标注「来源已删除」。

本轮明确**不包含**：普通平面图自动识别建模、任意家具精确复刻、任意自然语言直接改全部三维对象、施工可行性判断、自动估价、云部署、上游公共云分享/统计/账户功能。

## 1. 现状核对（实测，非历史报告）

- 主仓库当前分支 `codex/brief-reader`，HEAD `5843774`；试运行保障已合并为 `e31d23b`。
- 工作区存在 **6 个未提交文件**（他人进行中改动，已确认保留、不纳入本轮提交）：
  `frontend/e2e/auth-workflow.spec.ts`、`frontend/e2e/flow.ts`、`frontend/src/App.test.tsx`、`frontend/src/App.tsx`、`src/alignspace/auth/routes.py`、`tests/api/test_auth.py`。
  内容为「预算改为自由金额输入 + 注册密码下限 15→8」及配套测试。**本轮不修改、不覆盖、不提交这些文件**。
- 迁移版本 **v5**。`ProjectState` 为权威状态，按实体行持久化（`ProjectRepository._replace_entities`）。
- 视觉分析当前为 `MockVisionProvider`，每张图固定 4 条 `proposed` 观察；`Attribute` 是唯一正式偏好。
- 审批：`Approval(role, actorId, briefVersion, contentHash)`；`flag_brief_change()` 在属性/约束变化时清空审批并置 `brief_stale`；`can_draft_brief()`/`can_approve()` 决定可生成/可批准。
- 说明书 schema 全层 `additionalProperties:false`；`Attribute` 的字段集合被 schema 固定，**不能随意加字段**。`build_brief_payload()` 只挑选固定字段，故 `ProjectState` 新增字段不会自动泄入说明书。
- 认证：Argon2id、访问 JWT 15 分钟（内存）、刷新令牌 HttpOnly Cookie（7 天绝对）、Origin 校验、按 IP/用户限流。生产 `get_actor` 从成员关系取角色，不接受客户端身份头。

## 2. 数据模型

### 2.1 里程碑①：候选偏好分析

新增到 `ProjectState`（新的实体行，沿用 `_replace_entities` 模式；不进入说明书 payload）：

**`AnalysisRun`（分析任务）**
| 字段 | 说明 |
|---|---|
| `id` | |
| `status` | `completed` / `failed` / `rejected_input` |
| `requested_by` / `requested_role` | 发起人 |
| `description` | 屋主自然语言描述（原样保存，**不解析**为查询/指令） |
| `input_assets` | `[{assetId, sha256}]` 快照 |
| `input_fingerprint` | `sha256(assetIds+hashes+description+promptVersion)`，用于判定任务结果是否已过时 |
| `provider_mode` | `mock` / `deepseek` |
| `model` / `prompt_version` / `schema_version` | 可追溯 |
| `third_party_consent` | bool，**独立于**图片处理同意 |
| `error` | 失败时的安全错误码/信息 |
| `created_at` / `completed_at` | |

**`DesignEntry`（设计条目）**
| 字段 | 说明 |
|---|---|
| `id` | |
| `analysis_run_id` | 来源任务 |
| `source_asset_id` | 来源图片（可被删除） |
| `target_element` | 部位（如 `wall`、`floor`、`bed`） |
| `attention_dimensions` | **屋主表达的关注维度**（如 `["colour","style"]`），只来自屋主描述或屋主编辑 |
| `note` | 屋主自由文本备注（保存，不解析） |
| `status` | `open` / `partially_confirmed` / `confirmed` / `dismissed` / `source_deleted` |

**`CandidatePreference`（候选偏好）**
| 字段 | 说明 |
|---|---|
| `id` | |
| `entry_id` | |
| `dimension` | `colour` / `material` / `style` / `laying` / `lighting` / `other` |
| `proposed_value` | **模型观察/推断取值**，可为 `null` |
| `certainty` | `inferred` / `uncertain` —— 无法确定的材质必须为 `uncertain`，界面显示「不确定」 |
| `evidence` | 复用 `Evidence`（`source_type=image`，`source_id=assetId`），可含 `region` |
| `status` | `proposed` / `confirmed` / `rejected` / `dismissed` |
| `confirmed_value` | **屋主确认的设计需求**，可与 `proposed_value` 不同 |
| `attribute_id` | 确认后写入的正式 `Attribute` 稳定 ID（未确认为 `null`） |
| `decided_by` / `decided_at` | |

关键语义：`CandidatePreference.status=confirmed` 表示「屋主确认希望采用 `confirmed_value`」，**不等于**核实了图片真实材质。`certainty` 描述模型置信，与屋主确认相互独立。

### 2.2 里程碑②：空间模型

**`SpaceVersion`**（与 `BriefVersion` 同构的不可变版本行）
| 字段 | 说明 |
|---|---|
| `version` | 从 1 递增 |
| `content_hash` | 规范化 payload 的 SHA-256 |
| `payload` | 空间文档（见下） |
| `created_by` / `created_role` / `created_at` | |
| `source` | `manual` / `rectangular_dimensions` / `material_application` / `binding` |
| `previous_version` | 便于历史追踪 |

空间 payload（本轮最小可用集）：
```
{
  "schemaVersion": "1.0.0",
  "units": "mm",
  "rooms": [
    { "id": "room-<uuid>", "name": "客厅", "roomType": "living_room",
      "origin": {"x":0,"y":0}, "size": {"width":4000,"depth":5000},
      "walls": [ {"id":"wall-<uuid>","from":{...},"to":{...},"thickness":100} ],
      "floor": { "id": "floor-<uuid>", "materialOptionId": null, "bindingId": null } }
  ],
  "objects": [ {"id":"obj-<uuid>","roomId":"...","kind":"furniture","label":"...","geometry":{...}} ]
}
```
- **稳定 ID**：房间/墙/地面/对象 ID 由后端生成，持久化后可重新加载；客户端不得自造权威 ID。
- 本轮**不依赖平面图自动识别**；房间仅由「手动画房间」或「填写尺寸创建矩形房间」产生。
- 服务端校验：尺寸范围、对象引用完整性、对象数/字节上限、不接受客户端提供的 `projectId` 归属。
- 沿用 `WriteEnvelope`（`idempotencyKey`/`expectedStateVersion`）；**禁止整份 JSON 覆盖保存**绕过校验：`PATCH` 只接受受支持的字段集合。

### 2.3 里程碑③：偏好↔空间绑定

**`SpaceBinding`**
| 字段 | 说明 |
|---|---|
| `id` | |
| `room_id` / `floor_object_id` | 空间对象（稳定 ID） |
| `target` | 本轮仅 `floor`（可扩展 `wall`） |
| `attribute_id` | 已确认正式偏好（地板） |
| `candidate_id` | 可选，来源候选 |
| `material_option_id` | 映射到受支持材质目录的条目 |
| `approximation` | `exact` / `approximate`（近似替代必须标注并要求确认） |
| `status` | `active` / `needs_review` / `invalidated` |
| `bound_by` / `bound_at` / `space_version` | |

**材质目录**（代码内静态、可测试）：`src/alignspace/domain/space_catalog.py`，形如
`MATERIAL_OPTIONS = {"floor.light-oak.engineered": {...}, ...}`，含 `id`、`label`、`targets`、`colors`、`patterns`。不支持的值必须明确报错，不得静默近似。

## 3. 模型接口与 DeepSeek 适配器

统一协议（替换现有 `VisionProvider`，保留其向后兼容）：

```python
class PreferenceAnalysisProvider(Protocol):
    def analyze(self, request: PreferenceAnalysisRequest) -> PreferenceAnalysisResult: ...

@dataclass(frozen=True)
class PreferenceAnalysisRequest:
    assets: list[AssetRef]          # id, media_type, sha256, bytes
    description: str
    prompt_version: str
    schema_version: str

class PreferenceAnalysisResult(BaseModel):
    entries: list[ProposedEntry]    # ProposedEntry -> attention dimensions + candidates
```

- **Mock 模式**（本轮默认、验收使用）：`MockPreferenceAnalysisProvider`，确定性、可解释，输出与输入图片/描述相关但完全由本地规则产生。**不得**宣称具备真实识图能力。
- **DeepSeek 模式**：`DeepSeekPreferenceAnalysisProvider`
  - `ALIGNSPACE_VISION_MODE` = `mock` | `deepseek`
  - `ALIGNSPACE_DEEPSEEK_API_KEY`（**仅后端环境变量**；不进前端、日志、快照、Git）
  - `ALIGNSPACE_DEEPSEEK_MODEL`（默认 `deepseek-flash`）
  - `ALIGNSPACE_DEEPSEEK_BASE_URL`（可覆盖）
  - 结构化输出按官方图文输入协议实现；**实施时重新核对官方文档并把依据记录在 `docs/references/`**。
  - 复用 `generate_validated()` 的「一次修复重试」模式；超时、失败、有限重试、错误码映射独立于本地幂等。
  - **缺密钥时明确报错**（`provider_not_configured`），**绝不静默降级为模拟成功**。
- **第三方传输同意**：启用真实分析前，界面必须明确告知参考图片与描述会发送至第三方模型服务，并单独记录用户同意（`AnalysisRun.third_party_consent`）。原有「本地图片处理同意」**不视为**第三方传输授权。

## 4. API 契约（新增）

里程碑①（全部走 `WriteEnvelope`，除 GET）：
```
POST   /v1/projects/{id}/preference-analyses            # 运行分析（本轮 mock）
GET    /v1/projects/{id}/preference-analyses            # 列表（含状态/过时）
GET    /v1/projects/{id}/preference-analyses/{runId}
GET    /v1/projects/{id}/design-entries
PATCH  /v1/projects/{id}/design-entries/{entryId}       # 关注维度/备注/忽略
POST   /v1/projects/{id}/candidates/{candidateId}/confirm
POST   /v1/projects/{id}/candidates/{candidateId}/reject
PATCH  /v1/projects/{id}/candidates/{candidateId}       # 修改 proposed/confirmed 值、certainty
DELETE /v1/projects/{id}/design-entries/{entryId}       # 删除候选组织，不删已确认偏好
```
里程碑②③：
```
GET    /v1/projects/{id}/space                          # 最新空间版本
GET    /v1/projects/{id}/space/versions
POST   /v1/projects/{id}/space/rooms                    # 手动画房间 / 尺寸矩形房间
PATCH  /v1/projects/{id}/space/rooms/{roomId}
DELETE /v1/projects/{id}/space/rooms/{roomId}
PATCH  /v1/projects/{id}/space/objects/{objectId}       # 受支持字段集合
POST   /v1/projects/{id}/space/bindings                 # 偏好↔对象绑定
POST   /v1/projects/{id}/space/bindings/{bindingId}/apply   # 应用材质 → 新空间版本
POST   /v1/projects/{id}/space/bindings/{bindingId}/review   # 复核
POST   /v1/projects/{id}/space/approvals                # 空间+说明书联合审批
GET    /v1/projects/{id}/materials                      # 受支持材质目录
```

### 候选确认的写入规则（里程碑①核心）
1. 确认 `CandidatePreference` → 目标 `Attribute.id` 由**候选 ID 派生且稳定**：`pref-{candidateId}`；重复确认**幂等**，不重复创建。
2. 只允许把 `confirmed_value`（或屋主的编辑值）写入 `Attribute.value`，`status=confirmed`，`actor=homeowner`。
3. 证据：保留 `image` 证据（含来源 asset id），追加 `homeowner_answer` 证据并把 `candidateId` 记录在证据描述/关联表中。
4. 确认后调用 `reconcile_constraints` + `calculate_completeness` + `flag_brief_change`，接入既有冲突、版本与审批失效机制。
5. **重新分析不得覆盖**已确认或人工修改的内容：写入以确定性 ID 幂等 upsert，且已 `confirmed`/`rejected` 的候选在重跑分析时保留人工结论。
6. 删除候选条目：仅删除该条目的**未确认**候选；已确认 `Attribute` 保留，其 `bindingId` 关联表保留并标记来源条目已删除。

## 5. 版本与审批规则表

`SpaceVersion` 独立于 `BriefVersion`。术语区分：
- **确认应用到空间草案**：允许保存一次具体修改（生成新空间版本），**不等于**双方认可整个方案。
- **双方批准交付方案**：屋主 + 设计师对**同一** `spaceVersion`/`spaceHash` 且**同一** `briefVersion`/`briefHash` 的联合批准。

| 操作 | 版本变化 | 说明书状态 | 空间状态 | 审批影响 |
|---|---|---|---|---|
| 确认候选 → 正式偏好 | state +1 | 若无说明书：无；若有：`brief_stale=true` | 未变 | 清空既有说明书审批 |
| 修改/撤销正式偏好 | state +1 | `brief_stale=true` | 相关绑定 `needs_review` | 清空说明书审批；空间审批失效 |
| 构造/修改设计师约束 | state +1 | `brief_stale=true` | 未变 | 清空说明书审批 |
| 手动编辑空间（几何/对象） | state +1；`spaceVersion+1` | 未变 | 新版本 | 旧空间审批保留为历史、不适用于新版本；联合审批失效 |
| 应用材质（已确认偏好→受支持材质） | state +1；`spaceVersion+1` | 未变 | 新版本；绑定 `active` | 同上 |
| 仅转动/缩放/未保存预览 | **无** | 未变 | 未变 | 无 |
| 回退到历史空间版本 | state +1；新 `spaceVersion`（`source=rollback`，payload 复制旧版本） | 未变 | 新版本 | 联合审批失效；**不删除**历史版本 |
| 重新生成说明书（realign） | state +1；`briefVersion+1` | `brief_stale=false` | 未变 | 清空说明书审批 |
| 联合审批（说明书+空间） | state +1 | 记录批准 | 记录批准 | 需两者版本与哈希都匹配当前值 |

联合审批与保存**必须**在后端验证其依据的版本仍然有效（`expectedStateVersion` + `briefVersion/hash` + `spaceVersion/hash`）。

## 6. OpenPlan3D 集成

- 上游：`https://github.com/laanlabs/openPlan3D`。**固定上游提交**（在规格定稿时记录确切 SHA），保留 LICENSE 与第三方模型/贴图归属说明（写入 `docs/14-data-and-asset-register.md` 与新增 `docs/references/openplan3d.md`）。
- 以**独立本地模块**接入，**不重写既有 React 主前端**；在项目内提供 2D 编辑与 3D 预览入口。
- **不使用**上游公共云分享、分析统计、账户系统；验收须检查不向任何上游云服务发送项目数据（网络层面断言：仅本地静态资源与本地 API）。
- OpenPlan3D 的只读 MCP **不能**代替编辑接口 —— 必须实现受控数据适配层（`frontend/src/space/spaceAdapter.ts`），所有模型建议、手动修改、允许的导入都经**同一套**后端权限/结构校验/版本检查/审批失效规则。
- iframe/跨窗口通信：校验 `message` 来源与协议白名单；**不把访问令牌放入 URL**；继续使用现有认证。

## 7. 权限模型（已由用户确认，2026-09-21）

用户确认：

1. **空间草稿编辑权 = 共享可写**：屋主与设计师对同一份空间草稿具有同等编辑权。
2. **删除权 = 仅限屋主**：删除房间/对象仅屋主可执行（删除会移动对方已建立的绑定）。

据此定稿（里程碑②③按此实现）：

| 能力 | 屋主 | 设计师 |
|---|---|---|
| 运行图片偏好分析 | ✅ | ❌（只读结果） |
| 编辑/确认/删除候选偏好 | ✅ | ❌ |
| 查看候选偏好 | ✅ | ✅（只读） |
| 查看空间 | ✅ | ✅ |
| 创建/编辑空间草稿 | ✅ | ✅（**同等可写**，确认项 1） |
| **删除**房间/对象 | ✅ | ❌（确认项 2） |
| 将已确认偏好绑定到空间对象 | ✅ | ❌ |
| 应用材质（生成新空间版本） | ✅ | ✅（可编辑草稿范围内） |
| **确认应用到空间草案** | ✅ | ✅ |
| **双方批准交付方案** | ✅ | ✅ |

共享可写**不**等于放宽权限：角色仍从成员关系判定，项目隔离、结构校验与版本检查一律照旧。

## 8. 里程碑与验收

1. **候选偏好闭环**：图片＋描述 → 显式模拟候选；屋主编辑/逐项确认；正式偏好正确写入；重复确认不重复创建；冲突与审批失效符合规则；删除候选条目不影响已确认偏好；来源图删除后未确认候选不再应用。
2. **空间持久化闭环**：创建房间、2D 编辑、3D 预览、后端保存与重新加载；项目隔离、角色权限、并发冲突、失败恢复、历史项目兼容（无空间数据的旧项目仍走原说明书流程）。
3. **地板联动闭环**：确认偏好 → 绑定房间 → 选择受支持材质 → 预览/说明 → 用户确认 → 保存新空间版本 → 重载保持；覆盖不支持映射、过时提案、绑定失效、空间变更后的重新审批。

每个里程碑**独立测试、独立报告**，不等待全部完成才验证。实施顺序：**后端优先 → 前端随后 → 测试驱动**。

## 9. 已知风险与边界

- 真实 DeepSeek 联调本轮**不做**；模拟通过**不能**声称真实识图已验证。
- 上游 OpenPlan3D 体积、构建与许可证需在集成时实测，可能影响本地起服务方式。
- `ProjectState` 新增实体将增加每次写入的序列化量；需监控 `state_version` 写入放大。
- 未提交的预算/密码改动与本轮无依赖关系，但同处一个工作区，**合并顺序需用户决定**。
