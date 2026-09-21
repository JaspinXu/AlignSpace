# 里程碑① 候选偏好闭环 验证报告（中文）

> 执行者：实现模型（AI）在本地真实后端 + Chromium 上运行自动化用例后撰写。
> 日期：2026-09-21。分支 `codex/preference-space-integration`。
> **本报告只覆盖里程碑①（候选偏好闭环）**；里程碑②③与 OpenPlan3D 尚未开始。
> **未调用任何真实付费模型**；模拟通过 **不等于** 真实识图能力已验证。

## 1. 交付与提交

| 提交 | 内容 |
|---|---|
| `1a5d1bc` | 设计规格 + 实施计划 + 候选领域模型起步 |
| `b4e51aa` | 供应商边界（mock / DeepSeek / factory）+ 官方协议核对；权限定稿 |
| `baa54f1` | `ProjectState` 接入、持久化、迁移 **v6** |
| `1a14ff5` | 应用服务 + API（候选闭环） |
| `9f49d96` | 前端候选看板 + 浏览器验收 |

## 2. 已实现的规则（均有自动化断言）

- 分析**只产生候选**；`projectState.attributes` 为空，确认后才写入正式偏好。
- 三类事实分离：`DesignEntry.attentionDimensions`（屋主关注维度）、`CandidatePreference.proposedValue`+`certainty`（模型推断）、`confirmedValue`+`attributeId`（屋主确认）。
- 无法确定的材质标为 `uncertain` 且**不编造取值**；界面显示「不确定」。
- 确认写入**唯一**正式偏好：`Attribute.id = pref-{candidateId}`，重复确认不重复创建。
- 确认后重算冲突、completeness，并触发 `brief_stale` 与清空既有审批。
- **重新分析不覆盖**已确认 / 已拒绝 / 人工编辑过的候选（`human_edited` 标记）。
- 删除设计条目只删候选组织，**已确认偏好保留**。
- 删除来源图 → 条目转 `source_deleted`、运行标记 `stale`，之后确认被拒绝。
- 屋主可写、设计师只读（分析/确认 → 403）。
- 幂等：同键同内容重放；同键不同内容 409；版本过期 409。
- 缺 DeepSeek 密钥时**显式失败**，不静默降级为模拟成功。
- 真实模式需**第三方传输同意**，与本地图片处理同意分离，否则 409。

## 3. 测试结果（本轮实际运行）

| 检查 | 结果 |
|---|---|
| `uv run pytest -q` | **293 passed** |
| `uv run ruff check src tests scripts` | All checks passed |
| `cd frontend && npm test` | **119 passed**（6 文件） |
| `npm run build` / `npx tsc --noEmit` | 成功 / 无错误 |
| `npm run test:e2e` ×3 | **11 passed (50.6s) / 11 passed (50.6s) / 11 passed (50.8s)** |

新增测试分布：领域 11、供应商 17、持久化 2、迁移 1、API 14、前端组件 6、浏览器 1。

## 4. 关键修复（由测试驱动，非猜测）

1. **候选看板版本过期**：看板在图片上传前加载，`stateVersion` 停留在 0，生成候选时报 `expected version 0, current version 3`。修复：看板接收项目 `stateVersion` 并在其变化时重新加载，写入使用两者中较新的值。
2. **旧浏览器用例选择器脆弱**：新增 `<fieldset>` 使用例中裸 `locator('fieldset')` 命中 2 个元素。修复：改为按可访问名称定位问题分组。
3. **迁移版本连带更新**：v5→v6 后，备份清单断言与迁移版本断言同步更新（迁移的真实后果）。

## 5. DeepSeek 协议核对（已实际抓取官方文档）

见 `docs/references/deepseek.md`。要点：`deepseek-flash` 接受图文输入；JSON 输出需 `response_format={"type":"json_object"}` **加** prompt 中出现 “json” 与格式示例；终止性错误码 400/401/402/422，可重试 429/5xx。

**适配器已实现但本轮未调用。** 5 项联调前待复核事项已列在该文件。

## 6. 边界与未完成

- 里程碑①的**模拟**分析只能证明管线正确，**不能**证明真实识图能力。
- 前端候选看板已可用；但「运行分析」目前要求屋主手动选择图片与填写描述，未做自动预选。
- 结构化访谈入口保留并共存；两入口共用同一正式偏好写入规则（`Attribute`）。
- **未开始**：里程碑②空间持久化、三维预览、OpenPlan3D 集成、里程碑③地板联动、联合审批。
- 工作区仍保留他人 6 个未提交文件（预算金额输入 + 密码下限改动）；浏览器用例 `flow.ts` 目前依赖其中的预算字段改动才能通过。
- 未合并、未推送、未部署。

> **真实 DeepSeek 联调待用户配置密钥后验收。**
