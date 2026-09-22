# DeepSeek 图片 ID 完整性修复设计

## 问题

真实 DeepSeek 联调中，模型把提示词示例里的 `asset-1` 当成 `sourceAssetId` 返回，而请求中的真实图片 ID 是 UUID。后端只做结构校验，未知 ID 因而进入候选状态，前端将来源判断为已删除并禁止确认。

## 目标

1. 模型能明确看到每张图片对应的真实 `assetId`。
2. 模型只能返回本次请求提供的图片 ID。
3. `entry.sourceAssetId`、图片证据 `evidence.sourceId` 与所属 entry 必须一致。
4. 首次违约进入现有的一次修复流程；修复后仍违约则整体失败，且业务状态不写入。

## 设计

- 在每个图片 content block 前增加文本标记 `Reference image assetId: <真实 ID>`，保留输入顺序。
- system prompt 使用 `<provided-asset-id>` 占位符，明确禁止复制示例 ID，并要求只使用用户消息中列出的 ID。
- provider 在 Pydantic 结构校验后执行请求相关的语义校验：
  - entry ID 必须属于请求资产集合；
  - `sourceType=image` 的 evidence ID 必须等于 entry ID；
  - 不允许通过模糊匹配、顺序或“只有一张图”静默纠正未知 ID。
- 修复提示携带允许的 ID 列表与具体错误摘要，使第二次输出有机会纠正。

## 错误与安全边界

- 未知或错配 ID 统一视为 `ProviderOutputError`，复用既有一次修复机制。
- 第二次仍非法时返回稳定的 provider 输出错误；不记录分析运行、不创建条目和候选。
- 错误信息可包含资产 ID，但绝不包含 API 密钥或图片内容。

## 验收

- 契约测试证明请求中每张图均带真实 ID。
- 契约测试证明未知 entry ID 会触发修复并可恢复。
- 契约测试证明未知 ID 或 evidence/entry 错配在修复后仍存在时会失败。
- 既有 mock provider、API、前端与构建测试不回归。

