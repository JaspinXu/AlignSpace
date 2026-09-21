# 里程碑②：空间持久化闭环 验证报告（2026-09-21）

> 分支 `codex/preference-space-integration`（接续点 `5eda6ce`，本报告提交前的实现提交见下）。本轮**不合并、不推送、不部署、不调用外部付费模型**。
>
> **真实 DeepSeek 联调待用户配置密钥后验收。** 本里程碑为空间持久化，不涉及真实模型调用；里程碑①的模拟通过同样不代表真实识图已验证。

## 1. 范围

里程碑②在里程碑①（候选偏好闭环）与已有 `space.py`/`space_catalog.py` 领域层、`space_versions` 表（迁移 v7）基础上，完成：

- 后端服务 `application/space_service.py` 与路由 `api/routes/space.py`。
- 受权限控制的空间草稿读写；删除仅限屋主。
- 每次实质修改生成新的不可变 `SpaceVersion`（`version+1`、新 `content_hash`、`previous_version`）；同值重发不生成新版本。
- 前端 `frontend/src/space/spaceAdapter.ts`（受控适配层）与 `SpaceBoard.tsx`（2D 编辑 + 3D 预览入口），接入 `Workspace.tsx`。
- OpenPlan3D 上游固定、许可证与素材归属、本地启动与离线加固。

## 2. 权限模型（按用户确认实现）

| 能力 | 屋主 | 设计师 |
|---|---|---|
| 查看空间 | ✅ | ✅ |
| 创建/编辑房间与对象 | ✅ | ✅（同等可写） |
| 删除房间/对象 | ✅ | ❌（403 FORBIDDEN） |
| 查看材质目录 | ✅ | ✅ |

## 3. 接口

```
GET    /v1/projects/{id}/space                    # 最新空间版本 + 计划
GET    /v1/projects/{id}/space/versions           # 版本列表（倒序）
GET    /v1/projects/{id}/materials?target=floor   # 受支持材质目录
POST   /v1/projects/{id}/space/rooms              # 矩形尺寸或手绘轮廓（outline）
PATCH  /v1/projects/{id}/space/rooms/{roomId}     # 白名单字段
DELETE /v1/projects/{id}/space/rooms/{roomId}     # 仅屋主
POST   /v1/projects/{id}/space/objects
PATCH  /v1/projects/{id}/space/objects/{objectId} # 白名单字段
DELETE /v1/projects/{id}/space/objects/{objectId} # 仅屋主
```

- 所有写入走 `WriteEnvelope`（`idempotencyKey` / `expectedStateVersion`）。
- PATCH 仅接受白名单字段；整份 `plan` 覆盖请求返回 400 `INVALID_REQUEST`。
- 结构校验（唯一 ID、对象必须引用存在的房间、尺寸 1000–20000mm、房间 ≤12、对象 ≤200）在每次变更后重新执行。

## 4. 实际运行结果（2026-09-21）

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端全量 | `uv run pytest -q` | **320 passed** |
| 静态检查 | `uv run ruff check src tests scripts` | **All checks passed** |
| 前端单测 | `cd frontend && npm test` | **134 passed（9 文件）** |
| 前端构建/类型 | `cd frontend && npm run build`（含 `tsc --noEmit`） | **通过** |
| 浏览器验收 | `cd frontend && npm run test:e2e` | **12 passed（含新增 space-draft）** |

新增/相关测试：

- `tests/api/test_space.py`（13）：新项目无空间仍走原说明书流程、稳定 ID 与版本、设计师可写不可删、尺寸变更重建墙、对象 PATCH 白名单、项目隔离、非成员 403、过期版本 409、幂等重放与同键异内容 409、版本列表、同值不产生版本、材质目录、真实认证 401。
- `tests/integration/persistence/test_space_recovery.py`（2）：重启后重载一致、并发写入基于旧版本被拒。
- `frontend/src/space/spaceAdapter.test.ts`（5）、`SpaceBoard.test.tsx`（4）、`spaceNoCloud.test.ts`（6）。
- `frontend/e2e/space-draft.spec.ts`（1）：屋主与设计师共享草稿、仅屋主删除、重载保持。

## 5. 已知边界与风险

- OpenPlan3D 上游源码不提交进仓库；`vendor/openplan3d/upstream/` 由 `scripts/fetch_openplan3d.sh` 按固定 SHA 拉取并做离线加固（移除 Firebase Analytics、禁用 Google Storage 分享导入）。本报告未实际构建上游体量较大的 SvelteKit 应用，3D 预览的互操作以受控适配层与消息协议单测为准，端到端只断言入口与本地/无云约束。
- 手绘轮廓按多边形包围盒推导 `size`；后续若需任意墙体编辑，需在③之后单独设计。
- 未提交的预算/密码改动与本轮无关，仍保留在工作区、未纳入提交。

## 6. 结论

里程碑②后端、前端与浏览器验收全部通过；空间草稿为共享可写，删除仅限屋主，实质修改均产生可追溯的新空间版本，历史项目无空间数据时不受影响。
