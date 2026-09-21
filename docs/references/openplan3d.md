# OpenPlan3D 本地集成（上游固定与离线约束）

## 1. 上游与固定版本

| 项目 | 值 |
|---|---|
| 仓库 | https://github.com/laanlabs/openPlan3D |
| 固定提交 SHA | `d68cadf703578f2cd3a7c77f820e18d342580c32` |
| 固定时包名/版本 | `open3dfloorplan` 0.9.0 |
| 许可证 | MIT（版权归 theLodgeStudio） |
| 许可证副本 | `vendor/openplan3d/LICENSE` |
| 模型/贴图归属 | `vendor/openplan3d/MODEL_SOURCES.md` |
| 归属索引 | `docs/14-data-and-asset-register.md`（ASSET-OPENPLAN3D-001） |

上游源码**不进入**本仓库提交；`vendor/openplan3d/upstream/` 已被 `.gitignore` 忽略。用固定脚本获取并核验 SHA：

```bash
bash scripts/fetch_openplan3d.sh
# 输出：OpenPlan3D pinned at d68cadf... and hardened for offline local use.
```

脚本在 checkout 后执行以下步骤：

1. **离线加固**：用惰性模块覆盖 `src/lib/firebase.ts`，移除 Firebase Analytics 初始化。
2. 把 iOS 云端分享导入（Google Storage inbox 拉取）的 URL 改为不受支持的 `local://disabled-upstream-share`，使其无法访问外网。
3. **安装编辑桥**：把 `vendor/openplan3d/bridge/alignspaceBridge.ts` 复制为 `src/lib/alignspaceBridge.ts`，并在 `src/routes/editor/+page.svelte` 的 `onMount` 中调用 `startAlignSpaceBridge()`。
4. 最后静态扫描 `$TARGET/src`，若仍出现 `google-analytics.com`、`googletagmanager.com`、`firebaseapp.com`、`firebaseio.com`、`firebasestorage.googleapis.com` 则拒绝继续。

## 2. 受控适配层与双向桥

- 前端适配层：`frontend/src/space/spaceAdapter.ts`。把后端持久化的毫米级 `SpacePlan` 转成 OpenPlan3D 的 handoff JSON（`openplanHandoffVersion: 1`，米制），并附带扩展字段：`alignspaceFloorMaterials`（房间→材质）、`alignspaceRoomIds`/`alignspaceObjectIds`（保持权威身份）、`alignspaceFingerprint`（去重）。
- 上游桥（`vendor/openplan3d/bridge/alignspaceBridge.ts`，由固定脚本安装）：
  - 启动后向父窗口发送 `alignspace:ready`；
  - 收到 `alignspace:space` 后校验并 `importRoomPlan()` 导入，按房间保留我方 `alignspaceRoomId`，按 `alignspaceFloorMaterials` 设置地板纹理（`light-oak`/`porcelain`/`vinyl`/`concrete`）与房间颜色；
  - 订阅 `currentProject`，防抖后回传 `alignspace:project`。导入后的短暂窗口内抑制回传，避免自回写循环。
- 编辑回传：前端 `SpaceBoard` 收到 `alignspace:project` 后用 `upstreamPatches()` 与权威计划做差，把房间名称/几何、家具位置、以及新增/删除（删除仅屋主）经**现有受控 API** 落库。非有限坐标会被忽略，避免污染权威几何；后端仍执行结构校验、版本检查、权限与审批失效规则。
- 只读 MCP 不能替代编辑接口；所有写入都走本仓库后端。
- **令牌不进 URL**：预览 iframe 只连接本地地址；数据通过 `postMessage` 在 `ready` 握手后传输。`isAllowedPreviewOrigin` 仅接受精确的本地来源。

## 3. 本地启动

后端与前端（主仓库）：

```bash
uv run uvicorn alignspace.main:app --host 127.0.0.1 --port 8013
cd frontend && API_PROXY_TARGET=http://127.0.0.1:8013 npm run dev -- --port 5174
```

3D 预览（独立本地模块，默认地址 `http://127.0.0.1:4173`）：

```bash
bash scripts/fetch_openplan3d.sh
cd vendor/openplan3d/upstream
npm install
npm run dev -- --host 127.0.0.1 --port 4173
```

前端打开“空间草稿 → 打开 3D 预览”（iframe 指向 `http://127.0.0.1:4173/editor`）。只有收到来自该精确来源的 `alignspace:ready` 才发送当前空间草稿。

## 4. 验收：真实启动与不向上游云发送数据

- `frontend/e2e/space-3d.spec.ts`（当日实测通过）：真实启动固定上游 dev server，验证 2D 计划导入 3D 编辑器、保存的地板材质可见（`floorTexture`）、权威房间 ID 保留、以及在编辑器内移动家具后经受控 API 落库并重载保持。未安装上游时该用例自动跳过。
- 网络层面检查：

1. 仅允许到 `127.0.0.1` / `localhost` 的请求；拦截并列出所有其他域名。
2. 打开空间草稿与 3D 预览、编辑房间、应用材质，触发一次完整消息往返。
3. 确认没有请求发往 `*.google-analytics.com`、`*.googletagmanager.com`、`*.firebaseapp.com`、`*.firebaseio.com`、`firebasestorage.googleapis.com` 或任何上游账户/分享端点。
4. 确认预览 iframe 的 URL 与 `Referer` 中不含访问令牌。

`frontend/src/space/spaceNoCloud.test.ts` 对本地适配层做静态回归：失败条件包括引入非本地 URL、把 `token`/`access_token` 放入查询串、或恢复上游分析/分享端点。
