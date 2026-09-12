# AlignSpace 后端

这是 AlignSpace 第一阶段的可运行后端。它把屋主的样本图片偏好、设计师约束、双方问答和冲突处理组织成一个版本化的共享状态，最终生成需要屋主与设计师分别确认的设计规格。当前版本使用确定性样本数据，不上传或存储真实图片，也不包含装修效果图生成。

## 当前能力

- FastAPI 版本化接口和 OpenAPI 文档。
- SQLite 领域数据、审计事件、幂等记录和 LangGraph 检查点。
- Vision Analyst、Homeowner Interview、Designer、Alignment、Review 五个逻辑 Agent。
- 3–10 个本地图片样本记录、图片处理同意门槛和删除流程。
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
uv run uvicorn alignspace.main:app --reload
```

服务默认监听 `http://127.0.0.1:8000`，交互式 OpenAPI 位于 `http://127.0.0.1:8000/docs`。真实账户版本默认数据文件为 `alignspace-accounts.db` 和 `alignspace-accounts-checkpoints.db`，两者已被 Git 忽略。认证密钥不得打印或提交；缺少密钥时服务拒绝启动，换密钥会使已有访问令牌失效。

业务接口使用真实 Bearer 身份，屋主创建项目后通过一次性项目码邀请设计师。前端启动及双账户浏览器验收见 [前端运行说明](README.frontend.md)。

## 验证

```bash
uv run pytest -q
uv run ruff check src tests
```

所有测试都使用本地确定性 provider，不需要模型凭据或网络连接。验收测试会通过公开 API 完成以下闭环：

```text
创建项目与成员
  → 登记 3 张合法样本图
  → 视觉观察与屋主广泛提问
  → 细化偏好并确认共享状态
  → 设计师预算约束与冲突
  → 屋主选择低成本替代方案
  → 生成并校验设计规格
  → 屋主与设计师审批同一版本
```

## 调用约定

项目范围接口要求两个请求头：

```text
X-Actor-Id: homeowner-1
X-Actor-Role: homeowner
```

写请求使用统一 envelope：

```json
{
  "idempotencyKey": "client-generated-unique-key",
  "expectedStateVersion": 3,
  "data": {}
}
```

客户端每次写入前应读取最新 `stateVersion`。相同幂等键和相同内容会返回第一次的结果；相同键配不同内容会返回 `409`。公开错误统一包含 `code`、`message`、`correlationId`、`recoverable` 和安全的 `details`。

## 主要接口

```text
POST   /v1/projects
GET    /v1/projects/{projectId}
DELETE /v1/projects/{projectId}
POST   /v1/projects/{projectId}/assets
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

当前身份由测试请求头模拟；接入真实前端或部署前，需要把它替换为经过验证的登录令牌与项目成员声明。AWS/Lightsail 和赛事 JSON LLM API 仍位于 provider 适配层之后，不属于本地验收的前置条件。
