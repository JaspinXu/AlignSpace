# AlignSpace 后端

这是 AlignSpace 第一阶段的可运行后端。它把屋主的样本图片偏好、设计师约束、双方问答和冲突处理组织成一个版本化的共享状态，最终生成需要屋主与设计师分别确认的设计规格。参考图片是真实上传并保存在本地 `ALIGNSPACE_ASSET_DIR`（默认 `var/assets/`）下的；视觉分析仍为确定性模拟，直到第 2 步接入真实模型，也不包含装修效果图生成。

## 当前能力

- FastAPI 版本化接口和 OpenAPI 文档。
- SQLite 领域数据、审计事件、幂等记录和 LangGraph 检查点。
- Vision Analyst、Homeowner Interview、Designer、Alignment、Review 五个逻辑 Agent。
- 3–10 张真实参考图片的本地存储（JPEG / PNG / WebP，单张不超过 10MB）、图片处理同意门槛和删除流程。
- 稀疏偏好记录：系统不会因为属性未被提及就预先创建空数据；人工明确补充的偏好才会新增。
- 广泛提问后再细化、最多 10 个屋主问题、设计约束冲突和人工解决。
- JSON Schema 方案校验、内容哈希、版本化编辑和同版本双人审批。
- 结构、电气、法规、安全、精确价格和实时库存声明的专业复核门槛。

## 本地启动

需要 Python 3.12 和 [uv](https://docs.astral.sh/uv/)。在仓库根目录执行：

```bash
uv sync --extra dev
export ALIGNSPACE_AUTH_SECRET="$(openssl rand -hex 32)"
export ALIGNSPACE_DEV=1
export ALIGNSPACE_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"
# 可选：真实参考图片的本地存储目录（默认 var/assets/）
# export ALIGNSPACE_ASSET_DIR="var/assets"
uv run uvicorn alignspace.main:app --reload
```

服务默认监听 `http://127.0.0.1:8000`，交互式 OpenAPI 位于 `http://127.0.0.1:8000/docs`。真实账户版本默认数据文件为 `alignspace-accounts.db` 和 `alignspace-accounts-checkpoints.db`，两者已被 Git 忽略。认证密钥不得打印或提交；缺少密钥时服务拒绝启动，换密钥会使已有访问令牌失效。

上传的参考图片按内容寻址保存在 `ALIGNSPACE_ASSET_DIR`（默认 `var/assets/`）下。正常删除请使用资产或项目删除接口，避免数据库留下失效引用。要运行全新演示，请同时指定新的数据库、检查点和图片目录；备份或恢复时也应保持三者一致。不要只清空图片目录。

业务接口使用真实 Bearer 身份，屋主创建项目后通过一次性项目码邀请设计师。前端启动及双账户浏览器验收见 [前端运行说明](README.frontend.md)。

## 验证

```bash
uv run pytest -q
uv run ruff check src tests
```

所有测试都使用本地确定性 provider，不需要模型凭据或网络连接。验收测试会通过公开 API 完成以下闭环：

```text
创建项目与成员
  → 上传 3 张真实参考图片
  → 视觉观察与屋主广泛提问
  → 细化偏好并确认共享状态
  → 设计师预算约束与冲突
  → 屋主选择低成本替代方案
  → 生成并校验设计规格
  → 屋主与设计师审批同一版本
```

## 调用约定

业务接口要求经过验证的访问令牌；角色从项目成员关系确定，不接受客户端伪造身份头：

```text
Authorization: Bearer <accessToken>
```

工作流版本化写请求使用统一 envelope：

```json
{
  "idempotencyKey": "client-generated-unique-key",
  "expectedStateVersion": 3,
  "data": {}
}
```

客户端每次写入前应读取最新 `stateVersion`。相同幂等键和相同内容会返回第一次的结果；相同键配不同内容会返回 `409`。公开错误统一包含 `code`、`message`、`correlationId`、`recoverable` 和安全的 `details`。

图片上传例外：使用 `multipart/form-data` 的 `file`、`expectedStateVersion`、`idempotencyKey` 三个字段，不再支持公开 `fixtureId` 登记。图片读取同样需要 Bearer 令牌，前端通过 Blob URL 展示。项目创建只传 `roomType`、`budgetBand`、`consent`，不传 `designerId`；设计师使用一次性项目码加入。注册/登录返回访问令牌，刷新令牌由 HttpOnly Cookie 管理；Cookie 认证请求需合法 Origin。

## 主要接口

```text
POST   /v1/projects
GET    /v1/projects
POST   /v1/projects/join
POST   /v1/projects/{projectId}/join-code
GET    /v1/projects/{projectId}/state
GET    /v1/projects/{projectId}
DELETE /v1/projects/{projectId}
POST   /v1/projects/{projectId}/assets
GET    /v1/projects/{projectId}/assets/{assetId}/content
DELETE /v1/projects/{projectId}/assets/{assetId}
POST   /v1/projects/{projectId}/analysis-runs
PATCH  /v1/projects/{projectId}/attributes/{attributeId}
GET    /v1/projects/{projectId}/questions/next
POST   /v1/projects/{projectId}/questions/{questionId}/answer
POST   /v1/projects/{projectId}/designer-reviews
POST   /v1/projects/{projectId}/conflicts/{conflictId}/resolve
GET    /v1/projects/{projectId}/briefs/latest
PATCH  /v1/projects/{projectId}/briefs/{version}
POST   /v1/projects/{projectId}/briefs/{version}/approvals
```

当前已实现邮箱密码注册、登录、刷新与退出，不包含邮箱验证与密码找回。真实模型与云端部署尚未实施；任何赛事指定供应商要求应以赛事原始规则为准。
