# 图片偏好分析 ＋ 空间联动 交付说明（2026-09-21）

> 分支 `codex/preference-space-integration`。本轮**不合并、不推送、不部署、不调用外部付费模型**。
>
> **真实 DeepSeek 联调待用户配置密钥后验收。** 模拟 provider 通过 **≠** 真实识图已验证。

## 1. 迁移与兼容说明

迁移全部为**增量**（`Base.metadata.create_all` + `schema_migrations` 版本标记），可重复执行：

| 版本 | 内容 | 兼容性 |
|---|---|---|
| v6 | `analysis_runs`、`design_entries`、`candidate_preferences` | 历史项目无行，仍走原说明书流程 |
| v7 | `space_versions` | 同上；不伪造历史空间审批 |
| v8 | `space_bindings`、`space_approvals` | 同上；不伪造历史绑定或联合审批 |

- 历史项目（无候选/空间数据）打开后 `GET /space` 返回 `version=null`、`plan=null`，说明书与审批流程完全不受影响。
- 说明书 schema 全层 `additionalProperties:false`；`ProjectState` 新增实体不会自动进入说明书 payload。
- 备份/恢复清单的 `migrationVersion` 现为 **8**；`scripts/backup_local.py`、`scripts/restore_local.py` 无需改动。
- 联合审批独立于既有 `Approval`：既有“说明书批准”**不会**被当作“说明书＋空间联合批准”。

## 2. 模型输入/输出协议

统一边界 `PreferenceAnalysisProvider`（`src/alignspace/providers/preference.py`）：

```
PreferenceAnalysisRequest:
  assets: [{ id, media_type, sha256, data(bytes) }]
  description: str
  prompt_version: str
  schema_version: str

PreferenceAnalysisResult:
  model: str
  provider_mode: "mock" | "deepseek"
  entries: [
    { sourceAssetId, targetElement,
      attentionDimensions: [colour|material|style|laying|lighting|other],
      candidates: [{ dimension, certainty: inferred|uncertain,
                     proposedValue: str|null,
                     evidence: [{ sourceType, sourceId, description }] }] }
  ]
```

- 三类事实严格分离：`attentionDimensions`（屋主所述）≠ `proposedValue`（模型推断/观察）≠ `confirmedValue`（屋主确认，写入正式 `Attribute`）。
- 模型推荐只产生候选；未确认的模型推断**不能**写入空间或绑定。
- 确定性 mock 为默认；`material` 候选一律 `uncertain` 且 `proposedValue=null`，不编造材质。

## 3. 空间与绑定协议（摘要）

- `GET /v1/projects/{id}/space`、`/space/versions`、`/materials`、`/space/bindings`、`/space/approvals`。
- 写入统一 `WriteEnvelope{ idempotencyKey, expectedStateVersion, data }`。
- `PATCH /space/rooms|objects` 仅接受白名单字段；整份 `plan` 覆盖 → 400 `INVALID_REQUEST`。
- 每次实质修改生成新 `SpaceVersion`（`version+1`、新 `content_hash`、`previous_version`）；同值重发不生成版本。
- 绑定支持 `exact` 与 `approximate`；近似替代必须 `confirmApproximation=true`，否则 409 `APPROXIMATION_REQUIRES_CONFIRMATION`；不支持取值 → 409 `UNSUPPORTED_MATERIAL`。
- 房间删除 / 偏好修改 → 相关绑定转 `needs_review`；空间变更后旧联合审批不再匹配。
- 权限：绑定仅屋主；应用材质与联合审批屋主＋设计师；删除房间/对象仅屋主。详见里程碑②③报告。

## 4. 环境变量

完整示例见仓库根目录 `.env.example`（`.env` 已被 git 忽略）。关键项：

| 变量 | 说明 |
|---|---|
| `ALIGNSPACE_VISION_MODE` | `mock`（默认）或 `deepseek` |
| `ALIGNSPACE_DEEPSEEK_API_KEY` | **仅后端**；缺省且选择 deepseek 时显式失败，不降级 |
| `ALIGNSPACE_DEEPSEEK_MODEL` | 默认 `deepseek-flash` |
| `ALIGNSPACE_DEEPSEEK_BASE_URL` | 默认 `https://api.deepseek.com` |
| `ALIGNSPACE_DATABASE_URL` / `ALIGNSPACE_CHECKPOINT_PATH` / `ALIGNSPACE_ASSET_DIR` | 测试必须指向隔离临时目录 |
| `ALIGNSPACE_AUTH_SECRET` / `ALIGNSPACE_DEV` / `ALIGNSPACE_ORIGINS` / `ALIGNSPACE_REGISTER_IP_LIMIT` | 认证与会话 |
| `API_PROXY_TARGET` / `VITE_OPENPLAN3D_URL` | 前端代理与本地 3D 预览来源 |

## 5. DeepSeek 后续配置与真实联调步骤（待用户）

协议依据为 `docs/references/deepseek.md`（已于 2026-09-21 抓取官方文档核对）。**当前未发起任何真实调用。**

1. 由用户提供密钥，仅写入后端运行环境（不得写入 `.env` 提交、前端、日志或快照）。
2. 复核 `docs/references/deepseek.md` 第 3 节“尚未核对”清单（GIF 策略、空内容频率、`max_tokens` 容量、计费/限流）。
3. 在**隔离临时目录**启动后端，设置 `ALIGNSPACE_VISION_MODE=deepseek`，上传 3–10 张真实参考图。
4. 在界面勾选“第三方模型传输同意”（`AnalysisRun.third_party_consent` 独立于图片处理同意）；未同意且真实模式 → 409 `THIRD_PARTY_CONSENT_REQUIRED`。
5. 运行分析，人工核对：只产生候选、不写正式偏好、不确定材质仍为 `uncertain`；确认后写入唯一 `pref-{candidateId}`。
6. 记录真实模型名、费用、耗时、失败重试与实际输出；**本地写幂等不代表模型只计费一次**。
7. 完成后回填本文件与 `docs/references/deepseek.md`，并将里程碑①报告从“模拟”升级为“真实联调已验证”。

> **真实 DeepSeek 联调待用户配置密钥后验收。**

## 6. OpenPlan3D 本地启动与上游归属

见 `docs/references/openplan3d.md`：固定 SHA `d68cadf703578f2cd3a7c77f820e18d342580c32`，MIT 许可证与素材归属副本在 `vendor/openplan3d/`，`scripts/fetch_openplan3d.sh` 负责拉取并做离线加固（移除 Firebase Analytics、禁用云端分享导入）。3D 预览仅连接本地来源，令牌不入 URL；`frontend/src/space/spaceNoCloud.test.ts` 做静态回归。

## 7. 验收结果索引

- 里程碑①：`docs/reports/preference-candidates-validation.zh-CN.md`
- 里程碑②：`docs/reports/space-persistence-validation.zh-CN.md`（后端 320、前端 134、浏览器 12）
- 里程碑③：`docs/reports/space-binding-validation.zh-CN.md`（后端 330、前端 142、浏览器 13）
- 交接入口：`docs/15-project-handoff.zh-CN.md` 顶部“下一轮接续入口”。
