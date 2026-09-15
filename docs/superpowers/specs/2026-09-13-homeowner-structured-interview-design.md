# AlignSpace：屋主结构化偏好收集与细化问答设计

日期：2026-09-13
状态：已确认并实现（后端与前端）。
范围：交接文档“本阶段之后”的屋主偏好阶段。不接入多模态或自由文本理解模型。

## 1. 目标与边界

闭环：屋主选择参考图片 → 指明喜欢的部位 → 先泛问 → 再细问 → 确认偏好写入共享状态 →
与设计师约束协商 → 双方审批。

- 不接入真实视觉/语言模型；图片分析仍为确定性模拟并明确标注。
- 不加入平面图识别、空间建模、三维编辑、效果图生成、云部署、付费模型。
- 复用现有版本检查、幂等、成员权限、审计与冲突/审批机制。
- 自由文本只作备注，**不假装已自动提取含义**；未来模型通过同一数据接口接入。

## 2. 术语与数据映射

| 概念 | 落点 |
|---|---|
| 参考图片 | 资产 `assetId` |
| 部位 | 参考图片中的元素 `Attribute.target_element`（**不是**实际房屋的几何对象） |
| 属性 | `Attribute.dimension`（colour/material/lighting/…） |
| 偏好 | `(assetId, targetElement, dimension, value, status)` |
| 来源 | `Evidence`：视觉观察 `sourceType=image, sourceId=assetId`；屋主确认追加 `homeowner_answer`；备注只在问题上 |

一条偏好示例：“图片 A—墙面—颜色—暖米色” = 属性 `target_element=wall, dimension=colour,
value=warm beige`，其 `evidence` 内含 `sourceId=图片A`。

## 3. 关键决策

1. 偏好**必须关联来源图片与部位**；只有被选择/确认的部位与维度写入偏好。
2. 未确认观察（`proposed`）与屋主明确确认（`confirmed`）严格区分，不把观察当偏好。
3. **跳过 ≠ 不在意**：跳过表示暂未回答，不创建任何属性；“不在意”表示明确无偏好，
   仅对被问到的 `(assetId, targetElement, dimension)` 建一条 `not_applicable` 记录。
4. 不为未提及属性批量建空记录；不默认屋主喜欢整张图片。
5. 修改已有偏好保持原 `attribute.id` 与 evidence 追溯；触发现有冲突重检、`brief_stale`、审批失效。
6. 自由文本仅存为备注，不自动抽取；图片分析继续标注为模拟。

## 4. 数据模型改动

仅改 `Question`（不影响设计说明书 schema；Attribute 字段不变）：

```text
QuestionKind = broad_parts | detail | conflict

QuestionOption {
  label: str                      # 供界面显示，如“图片A · 墙面 · 颜色 · 暖米色”
  value: str | None
  assetId: str | None
  targetElement: str | None
  dimension: str | None
  attributeId: str | None         # 指向已有观察，便于确认时复用其 id 与 evidence
}

Question {
  ...(现有字段)...
  kind: QuestionKind = detail
  assetId: str | None = None
  targetElement: str | None = None
  dimension: str | None = None
  options: list[QuestionOption] = []   # 由 list[str] 改为结构化选项
  skipped: bool = False
  response: dict[str, object] | None = None  # 已记录的结构化回答摘要
}
```

- 偏好的来源图片继续通过 `evidence.source_id` 表达（不新增 Attribute 字段），部位用
  `target_element`；避免改动设计说明书 schema。

## 5. 访谈流程

- **广问（`broad_parts`）**：候选部位 = 所有 `proposed` 观察按 `(assetId, targetElement)` 去重，
  label “图片X · 部位”。问题询问“还喜欢这些图片中的哪些部位”。
- 屋主回答（结构化，见第 6 节）：选择部位集合、可跳过、可写备注。**不直接建属性**，只记录选择。
- **细化（`detail`）**：对每个被选部位，按观察到的 `dimension` 生成问题，选项为观察候选值
  （可确认、拒绝、自定义、不在意、跳过）。
- **冲突（`conflict`）**：沿用现有逻辑；允许通过结构化选择“调整关联偏好”或确认约束。
- 生成时使用历史指纹去重；已跳过的部位允许后补答（生成新的细化问题或直接补偏好）。

## 6. 回答合约（`POST /questions/{id}/answer`）

`data`：

```json
{
  "answer": "可选自由文本备注，不解析",
  "parts": [{"assetId": "a1", "targetElement": "wall"}],
  "selection": [
    {"attributeId": "mock-a1-wall-colour", "decision": "confirmed", "value": "warm beige"},
    {"attributeId": "mock-a1-floor-colour", "decision": "not_applicable"},
    {"assetId": "a2", "targetElement": "chair", "dimension": "material",
     "value": "solid oak", "decision": "confirmed"}
  ],
  "skipped": false
}
```

规则：

- `parts` 仅用于广问；写入问题 `response`，不直接建属性。
- `selection` 每项写为/更新一条 `Attribute`：
  - 有 `attributeId` → **复用该 id**（保留原 evidence，如图片来源），更新 `value`/`status`；
  - 无 `attributeId` → 生成稳定 id `pref-{assetId}-{targetElement}-{dimension}`；
  - `decision ∈ {confirmed, rejected, not_applicable}` → 对应 `AttributeStatus`；
  - `confirmed` 追加 `homeowner_answer` evidence；若来自观察则保留 `image` evidence。
- `skipped=true`：问题标记 `skipped`，不建属性，工作流继续。
- `answer` 备注只写在问题上，**不做任何解析**。
- **校验**：选择必须属于当前问题允许的属性/部位/维度（广问只接受所选部位；细问只接受该问题选项的属性或匹配的 (assetId, 部位, 维度)），且来源图片仍有效；否则返回 400，且**不修改任何偏好**。
- 新建偏好（无 `attributeId`）时，除 `homeowner_answer` 外还写入 `image` evidence（`sourceId=assetId`），以保持来源可追溯。
- 版本/幂等沿用统一 envelope：同键同体返回首次结果，同键不同体 409，版本过期 409。
- 至少提供 `answer`、`parts`、`selection`、`skipped` 之一；`skipped` 与 `selection` 互斥语义以 `skipped` 优先。

## 7. 失效与边界处理

- **来源图片删除**：引用该资产的 `proposed` 观察被移除，**同时从待答问题中移除该图片的选项**；若某个待答问题因此没有选项，则标记为 `skipped`（不再作为 pending）。提交已失效选项返回 400；已确认偏好保留并显示“来源图片已删除”。不得因此卡住工作流。
- **重复回答**：按新回答覆盖该问题的 `response`；已确认偏好按 id 更新，不重复创建。
- **重新选择部位**：更新广问题 `response`，细化问题据此增删；不覆盖无关偏好。
- **跳过后补答**：允许对同一部位/维度再次提出细化问题或直接补充偏好。
- **旧问题失效**：若问题引用的观察/资产已不存在或被更高优先级问题取代，标记 `superseded`，
  不再作为 `pending`。

## 8. API

- `GET /v1/projects/{id}/questions/next`：返回结构化问题（含 `options`）。
- `POST /v1/projects/{id}/questions/{questionId}/answer`：接受第 6 节的结构化 `data`。
- `PATCH /v1/projects/{id}/attributes/{attributeId}`：编辑已有偏好（保持不变，复用）。
- `POST /v1/projects/{id}/analysis-runs`：生成观察与广问（保持入口）。

## 9. 前端

- 广问：以“图片X · 部位”多选呈现，提供“跳过”与备注；备注明确标注“仅备注，系统不会自动理解”。
- 细化：显示“图片X · 部位 · 维度”，候选值可选、可自定义、可拒绝/不在意/跳过。
- 确认后刷新共享偏好，侧栏按“图片/部位”分组展示，并标注来源与置信度。
- 仍显示“真实图片 · 分析为模拟”的诚实文案；不伪造已识别。

## 10. 测试计划

- 后端：广问候选来自观察、选择后细化、确认写入偏好且 id/evidence 正确、
  拒绝/不在意/跳过语义、重复回答幂等、修改同一偏好保留 id、来源删除后不卡住、
  冲突重检与审批失效。
- 前端：结构交互、跳过、不在意、备注标注、按图片/部位分组。
- E2E（两账户）：来源关联、先泛后细、跳过与不在意、修改同一偏好、冲突重算、审批后变更。
- 重新验证基线（不沿用旧结果）：后端 215、前端 55、双账户浏览器 1。

## 11. 非目标

真实多模态/自由文本理解、平面图/空间建模/三维/效果图、云部署、付费模型、GitHub push。

## 12. 验收标准

- 偏好可追溯到具体图片、部位与维度；观察与确认分离。
- 先泛问后细化，支持跳过与“不在意”，不批量建空记录。
- 结构化回答写入共享偏好；修改保持 id 与来源。
- 约束冲突、方案过时与审批失效机制继续生效。
- 后端、前端与双账户浏览器测试通过；本地提交，不推送。
