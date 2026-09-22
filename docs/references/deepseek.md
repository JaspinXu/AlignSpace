# DeepSeek 官方 API 协议依据（实现核对记录）

> 核对日期：**2026-09-21**（Asia/Singapore）。核对方式：直接抓取 DeepSeek 官方文档站点 `https://api-docs.deepseek.com`。
> **本轮没有发起任何真实模型调用**，本文件只是把适配器所依据的协议事实固定下来，供后续真实联调时复核。

## 1. 事实（来自官方文档）

| 项目 | 官方说明 | 来源页面 |
|---|---|---|
| 默认模型 | `deepseek-flash` **接受图文输入**（另有 `deepseek-v4-pro`）。旧名 `deepseek-v4-flash-vision-exp` 已退役，请求由最新 Flash 模型服务。 | `/guides/vision/`、`/api/list-models` |
| 图片格式 | JPEG、PNG、GIF、WebP；**按文件实际内容识别**，不看文件名或声明的 MIME。 | `/guides/vision/` |
| Base URL | `https://api.deepseek.com`；端点 `/chat/completions`。 | `/guides/vision/` |
| 内联图片 | OpenAI 兼容的 content 数组：`{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,<B64>"}}`。 | `/guides/vision/` |
| 请求体上限 | 内联 base64 计入 **48 MiB** 请求体上限。 | `/guides/vision/` |
| 外链图片 | 公开 http(s) 链接，URL ≤ 8192 字符、文件 ≤ 32 MiB、下载 ≤ 60 秒。 | `/guides/vision/` |
| JSON 输出 | 必须 `response_format={"type":"json_object"}`，**并且**在 system/user prompt 中出现 “json” 字样并提供目标 JSON 示例；建议设置 `max_tokens` 防止截断；官方提示偶发返回空内容。 | `/guides/json_mode` |
| 错误码 | 400 格式错误、401 认证失败、402 余额不足、422 参数无效（均为终止性）；429 限流、500 服务器错误、503 过载（可重试）。 | `/quick_start/error_codes` |

## 2. 适配器与官方协议的对应

`src/alignspace/providers/deepseek.py`：

- `model` 默认 `deepseek-flash`，端点 `{base_url}/chat/completions`，Header `Authorization: Bearer <key>`。
- 图片以 `data:{media_type};base64,...` 内联；文本与图片同属一个 content 数组。
- 每个图片块前都发送 `Reference image assetId: <真实 ID>`；system prompt 中的 JSON
  示例只使用 `<provided-asset-id>` 占位符，并明确禁止模型虚构、缩写或复制示例 ID。
- `SYSTEM_PROMPT` 显式包含 “json” 与目标 JSON 示例；payload 固定 `response_format={"type":"json_object"}`、`max_tokens=4096`、`temperature=0`。
- Pydantic 结构校验后还会按本次请求做语义校验：所有 `sourceAssetId` 必须属于输入
  图片集合，且 `sourceType=image` 的 `evidence.sourceId` 必须等于所属条目的
  `sourceAssetId`。违约会进入一次修复；第二次仍违约则整体返回 `ProviderOutputError`，
  不创建分析运行、候选条目或正式偏好。系统不会把未知 ID 静默映射到第一张图片。
- 错误映射：400/401/402/403/422 → 终止（401/403 归为 `ProviderAuthError`，402 单列余额不足）；429/5xx → 可重试 `ProviderRequestError`；结构化输出非法 → 一次修复重试后 `ProviderOutputError`。
- 空/非 JSON 内容按 `ProviderOutputError` 处理（对应官方“偶发空内容”提示）。
- **密钥仅来自后端环境变量**，不写入日志、错误信息、测试快照或 Git；测试断言错误信息不含密钥。

## 3. 尚未核对 / 联调前必须复核

1. **本仓库应用只允许 JPEG/PNG/WebP**（GIF 被上传层拒绝）；DeepSeek 额外支持 GIF，但本轮不改上传策略。
2. 官方“偶发空内容”的实际频率与重试策略需要在真实联调时观察；当前仅走一次修复重试。
3. `max_tokens=4096` 是否足以容纳多图多条目输出，需要在真实图片数量下实测。
4. 计费与限流：本地写幂等**不代表**模型请求只计费一次；真实联调前需确认预算与限流设置。
5. 文档页面为 SPA，抓取时以 `-L` 跟随 302；后续复核应以官方当前页面为准，若与本文件冲突，以官方为准。

> 2026-09-23 已完成一次真实 DeepSeek 调用，确认模型曾把旧提示词示例中的
> `asset-1` 当作来源 ID 返回；本次请求绑定与输出校验即针对该实测缺陷。修复后的
> 真实多图复测仍需单独执行并记录，自动化契约测试通过不等于真实识图质量已验收。
