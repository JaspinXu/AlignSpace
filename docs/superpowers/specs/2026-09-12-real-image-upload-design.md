# AlignSpace：真实图片上传与存储设计

日期：2026-09-12
状态：设计已确认，待用户复核书面规格；尚未实施。
范围：交接文档第 14 节“本阶段之后”的第 1 步。

## 1. 背景

当前“参考图片”只是元数据登记：`POST /v1/projects/{projectId}/assets` 接收
`{fixtureId, mediaType, sizeBytes}`，不接收任何文件字节，视觉分析据此返回写死的观察。
这无法支撑后续真实视觉分析与原图追溯。

本设计引入真实的图片上传、存储、读取与删除，并保证每条分析观察都能追溯到具体图片。
真实视觉识别（从像素提取元素/颜色/材质）属于第 2 步，不在本次范围。

## 2. 已确认的决策

| 决策 | 结论 |
|---|---|
| 存储位置 | 本地文件系统，放在 `Storage` 接口之后；将来迁移 S3 只替换实现 |
| 资产模型 | 单一“资产 = 一张真实图片”概念；公开 API 只接受真实上传，不再提供 fixture 登记 |
| 删除语义 | 允许删除；由该图产生的观察保留，并标注“来源图片已删除” |

## 3. 用户可见行为

1. 屋主在项目内选择真实图片上传：JPEG / PNG / WebP，单张 ≤ 10MB，每个项目最多 10 张**有效**图。
2. 项目内显示真实缩略图（点击看大图）。
3. 屋主可删除某张图。删除后观察保留，相关观察显示“来源图片已删除”。
4. 界面文案保持诚实：**图片是真实上传的；视觉分析在第 2 步接入前仍是模拟结果**，
   不再声称“演示样本图片”。

## 4. 技术设计

### 4.1 存储层

- `Storage` 接口：`save(data, sha256) -> key`、`open(key)`、`delete(key)`、`exists(key)`。
- 本地实现：目录由 `ALIGNSPACE_ASSET_DIR` 配置，默认 `var/assets/`（gitignored）。
- 内容寻址：文件名用图片内容的 `sha256`（加扩展名），天然去重且可校验完整性。
- 存储键不包含用户提供的文件名，避免路径穿越。

### 4.2 API 合约

**上传**（替换原 fixture 登记端点）

```
POST /v1/projects/{projectId}/assets
Content-Type: multipart/form-data
  file: <binary>
  expectedStateVersion: <int>
  idempotencyKey: <string>
```

- 屋主限定；项目需已同意处理图片（consent）；有效图数量上限 10。
- 请求哈希基于 `expectedStateVersion + idempotencyKey + mediaType + sizeBytes + sha256`；
  同键同内容返回首次结果，同键不同内容返回 409。
- 响应 201：`AssetWriteView { id, originalFilename, mediaType, sizeBytes, sha256, stateVersion }`。

**资产视图字段**（列表与上传响应统一）

```
AssetView      = { id, originalFilename, mediaType, sizeBytes, sha256, deleted, deletedAt }
AssetWriteView = AssetView + { stateVersion }
```

**读取内容**

```
GET /v1/projects/{projectId}/assets/{assetId}/content
```

- 仅项目成员可访问；返回图片字节与正确 `Content-Type`，`Cache-Control: private`。
- 已删除或不存在的资产返回 404。

**删除**（沿用 JSON envelope，无文件）

```
DELETE /v1/projects/{projectId}/assets/{assetId}
{ "idempotencyKey": ..., "expectedStateVersion": ..., "data": {} }
```

- 屋主限定。**软删除**：保留元数据行（tombstone），删除磁盘字节，递增状态版本。
- 不删除工作流检查点，也不改写已有观察（保持可追溯）。

**项目视图**

- `ProjectView.assets` 返回全部资产，每项带 `deleted: boolean` 与 `deletedAt`；
  界面据此把引用已删除图片的观察标注为“来源图片已删除”。
- 分析就绪检查与数量上限只统计 `deleted == false` 的资产（3–10 张）。

### 4.3 校验与隐私

- 声明的 `Content-Type` 与实际扩展名之外，必须做**文件头 magic bytes 嗅探**并尝试解码；
  不一致或无法解码 → `UNSUPPORTED_MEDIA_TYPE` / `INVALID_IMAGE`。
- 大小超过 10MB → `ASSET_TOO_LARGE`。
- **去除 EXIF/GPS 等元数据**后再存储（隐私），不保留原始文件。
- 不信任客户端提供的文件名用于任何路径拼接（仅作展示字段）。

### 4.4 数据与迁移

- `image_assets` 增加 `deleted_at`（可空整数）列；其余新字段（`sha256`、`storage_key`、
  `original_filename`、宽高）放在现有 JSON `payload` 中，无需改列。
- 迁移升级到版本 2，SQLite 增量、可重复执行。

### 4.5 追溯与模拟视觉

- 观察的 `Evidence.sourceId` 改为真实 `assetId`。
- 第 1 步保持确定性模拟视觉：`MockVisionProvider` 改为对每个有效资产各产生一条
  `proposed` 观察，`sourceId = assetId`，不直接认定为屋主偏好。
- 分析前置条件：项目有 3–10 张**未删除**资产且已 consent。

### 4.6 前端改动

- 用文件选择 + 上传按钮替换“登记演示样本”。
- 缩略图通过带 token 的 `fetch` 转 blob URL 渲染（`<img>` 无法携带 Authorization 头）。
- 每个资产提供删除按钮与二次确认。
- 观察列表按来源资产是否被删除显示标注。
- 顶部徽标改为“真实图片 · 分析为模拟（第 2 步接入）”。

## 5. 安全

- 上传/删除限屋主；读取限项目成员；所有入口沿用现有认证与成员校验。
- 不信任声明的类型与文件名；内容寻址键杜绝路径穿越；不做目录列表。
- 上传接口纳入服务端限流（沿用现有固定窗口机制）。

## 6. 测试计划

- 后端单测：magic bytes/解码/大小校验、屋主权限与非成员 403、幂等与版本冲突、
  软删除后计数与分析就绪、内容读取对已删除/非成员返回 404/403、EXIF 被剥离。
- 后端验收：两个真实账户 → 上传真实图 → 分析 → 删除 → 观察保留且标“来源已删除”。
- 前端：上传控件、缩略图渲染、删除确认、来源已删除标注。
- 现有 fixture 相关测试改写为测试内直接构造资产数据（按决策 A）。

## 7. 非目标

- 真实视觉识别（第 2 步）。
- S3/对象存储与线上部署（第 4 步）。
- 缩略图生成、批量上传、图片编辑、原图元数据保留。

## 8. 验收标准

- 屋主可上传真实 JPEG/PNG/WebP，项目内可见真实缩略图。
- 非法格式、超限、无 consent、非屋主、超过 10 张均被正确拒绝。
- 观察可通过 `sourceId` 追溯到具体资产；删除图片后观察仍在并标注来源已删除。
- 全套后端与前端测试通过，界面不再宣称样本图片为真实分析。

## 9. 后续阶段

真实视觉分析 → 真实语言理解 → 真实案例评估与部署（见交接文档第 14 节）。
