# 图片偏好分析框架 ＋ OpenPlan3D 集成 实施计划

> 配套规格：`docs/superpowers/specs/2026-09-21-preference-space-integration-design.md`
> 分支：`codex/preference-space-integration`（已创建，保留全部未提交改动）
> 方式：**后端优先 → 前端随后 → 测试驱动**；每个里程碑可独立测试与验收；每步先写断言、失败、再最小实现、再回归、单独提交。
> 约束：不合并、不推送、不部署、不调用外部付费模型；不改无关代码；保留他人未提交改动。

## 阶段 0：准备（本轮）

- [x] 核对真实 Git 状态与工作区，记录未提交改动清单（6 文件，保留不动）。
- [x] 创建独立功能分支 `codex/preference-space-integration`。
- [x] 编写设计规格与大方向计划（本文件）。
- [ ] **等待用户确认第 7 节两个权限问题**（里程碑②的写入路径依赖此答案）。
- [ ] 运行基线：`uv run pytest -q`、`uv run ruff check src tests scripts`、`cd frontend && npm test && npm run build`，记录真实数字（不沿用历史报告）。

## 里程碑①：候选偏好闭环

### ①.1 领域模型（后端，TDD）
1. 测试：`tests/unit/domain/test_preference_candidates.py`
   - `CandidatePreference` 校验：`dimension` 必须受支持；`uncertain` 必须有 `certainty` 且允许 `proposed_value=None`；`status=confirmed` 必须带 `confirmed_value`。
   - `DesignEntry`：`attention_dimensions` 只能来自允许集合；`status` 迁移合法。
   - `AnalysisRun.input_fingerprint` 稳定（同输入同哈希，改描述/图集则变化）。
2. 实现：`src/alignspace/domain/preferences.py`（新模型，复用 `DomainModel`/`Evidence`/`AttributeStatus` 风格）。
3. 加入 `ProjectState`（`analysis_runs`/`design_entries`/`candidates`）+ `patches.py` 的 Upsert 操作。
4. 持久化：`tables.py` 三张新表（`analysis_runs`、`design_entries`、`candidate_preferences`）+ `repository.py` 的 `_replace_entities`/`load` 扩展。
5. 迁移：`migrations.py` 增到 **v6**（`CREATE TABLE IF NOT EXISTS` + `schema_migrations` 记录）；测试 `tests/integration/persistence/test_migrations.py` 断言 v5→v6 幂等且旧库可升级。

### ①.2 供应商接口（后端，TDD）
1. 测试：`tests/unit/providers/test_preference_provider.py`
   - `MockPreferenceAnalysisProvider` 对同一输入确定性输出；只产出候选，不产出 `Attribute`。
   - `MockPreferenceAnalysisProvider` 对未提及维度**不产生**候选；不默认整图。
   - `DeepSeekPreferenceAnalysisProvider` 在缺密钥时抛 `ProviderNotConfigured`，**不回退到 mock**（关键回归）。
   - 结构化输出：非法输出经一次修复重试后仍非法 → `ProviderOutputError`；超时/5xx 映射为可重试错误且不写入业务状态。
2. 实现：`src/alignspace/providers/preference.py`（Mock）、`src/alignspace/providers/deepseek.py`（真实适配器，**本轮不实际调用**）、`src/alignspace/providers/factory.py`（按 `ALIGNSPACE_VISION_MODE` 构造，缺密钥显式失败）。
3. 测试：`tests/unit/providers/test_deepseek_contract.py` —— 用本地 stub transport 断言官方协议字段（模型名、图文消息结构、结构化输出参数、错误处理），依据文档路径写入 `docs/references/deepseek.md`。

### ①.3 应用服务与 API（后端，TDD）
1. 测试：`tests/api/test_preference_analyses.py`
   - 屋主可发起分析；设计师发起 → 403。
   - 缺第三方同意却启用真实模式 → 明确错误。
   - 分析结果只产生候选；`GET state` 无新 `Attribute`。
2. 测试：`tests/api/test_candidate_confirmation.py`
   - 确认候选 → 新 `Attribute(status=confirmed)`；重复确认同键/不同键都**不重复创建**。
   - 确认后 `conflicts` 重算、`brief_stale` 置位、既有审批清空（复用现有断言风格）。
   - 重新分析**不覆盖**已确认/人工修改的候选与偏好。
   - 删除设计条目：未确认候选消失，已确认偏好保留。
   - 删除来源图：条目转 `source_deleted`，未确认候选不可再确认；已确认偏好保留并标注来源已删除。
   - 并发：`expectedStateVersion` 过期 → 409；幂等键复用不同内容 → 409。
3. 实现：`src/alignspace/application/preferences_service.py` + `api/routes/preferences.py`，接入 `main.py`。
4. 契约测试：错误码/`recoverable`/`details` 与既有错误处理一致 → `tests/api/test_preference_errors.py`。

### ①.4 前端（后端完成后）
1. `frontend/src/preferences/*`：图片＋描述输入、条目/候选列表（区分关注维度/模型推断/已确认）、编辑/确认/忽略、显示「不确定」。
2. 第三方传输同意 UI：真实模式未配置时明确提示，不静默降级。
3. 单测 `*.test.tsx` + 浏览器流 `frontend/e2e/preference-analysis.spec.ts`（隔离数据目录）。
4. **保留原结构化访谈入口**作为备用，两入口共用正式偏好写入规则。

### ①.5 验收报告
- `docs/reports/preference-candidates-validation.zh-CN.md`：真实运行的后端/前端/构建/浏览器结果；明确「模拟通过 ≠ 真实识图」。

## 里程碑②：空间持久化闭环

> 依赖用户对第 7 节权限问题的答复。

1. 领域：`src/alignspace/domain/space.py`（空间 payload + 校验）、`space_catalog.py`（材质目录）。
2. 持久化：`space_versions` 表（迁移 v7），`content_hash` 同 `BriefVersion` 模式。
3. 服务/API：房间创建（手绘/尺寸）、对象 PATCH（**受支持字段白名单**，拒绝整份 JSON 覆盖）、版本冲突、幂等、失败恢复。
4. 测试：项目隔离、角色权限、并发 409、重启后重新加载、**旧项目无空间数据仍走原说明书流程**（迁移不得伪造历史空间审批）。
5. 前端：`frontend/src/space/spaceAdapter.ts` + 2D 编辑与 3D 预览入口；本地存储仅草稿；iframe `message` 来源校验。
6. OpenPlan3D：固定上游 SHA、许可证与素材归属、本地启动说明、**不向云服务发送数据**的验收检查。

## 里程碑③：地板联动闭环

1. `SpaceBinding`（迁移 v8）+ 绑定/复核/应用接口。
2. 联动路径：已确认地板偏好 → 绑定房间 → 受支持材质 → 预览与适配说明 → 用户确认 → 新空间版本 → 重载保持。
3. 规则：不支持材质明确报错；近似替代标注 + 用户确认；未确认模型输出/设计师意见**不得**覆盖空间；空间对象拆分/合并/删除或导入改变身份时绑定 `needs_review`，不静默转移。
4. 联合审批：后端校验 `briefVersion/hash` 与 `spaceVersion/hash` 都有效；旧说明书审批不能当作新空间方案已批准。
5. 前端联动 UI + 浏览器验收。

## 交付物清单（最终）

- 代码、设计规格与本计划、迁移与兼容说明、模型输入输出协议、环境变量示例、DeepSeek 后续配置与真实联调步骤、OpenPlan3D 本地启动说明、上游提交与素材归属清单、更新后的交接文档、实际运行的后端/前端/构建/浏览器结果。
- 报告须列明：实际提交、已完成/未完成项、已知风险、模拟与真实运行边界，并**单独标记**：
  > **真实 DeepSeek 联调待用户配置密钥后验收。**

## 立即可执行的第一步

在用户答复权限问题之前，先做里程碑①（不依赖权限答复的默认：屋主写、设计师只读）。第一步为 `①.1` 的领域模型测试。
