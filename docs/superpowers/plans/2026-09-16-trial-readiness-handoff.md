# AlignSpace 试运行保障交接计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不接入真实模型、不新增装修可视化、不部署云端的前提下，让现有本地双账户产品具备可验证的恢复能力、多标签页协作保护、离线备份恢复流程及内部试用手册。

**Architecture:** 保留 FastAPI、SQLite 业务库、LangGraph 检查点和本地图片存储；围绕现有业务接口补充故障与协作测试，只修复测试证实的缺陷。备份采用停服后的一致性备份，不实现在线分布式快照。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy/SQLite、LangGraph、pytest、React/TypeScript、Vitest、Playwright。

## 0. 交接基线与全局约束

- 本地仓库：`/Users/shawn_chen/Documents/GitHub/Design_Inspiration_Agents`。
- 已验收集成基线：本地 `shawn` @ `8deab24`；屋主访谈来源提交 `c3a290c` 已合并，原功能分支已清理。
- 上一轮实际验证为后端 229 项、前端 58 项、浏览器 E2E 1 项通过，Ruff 和构建通过。这是历史基线，不可代替本轮运行。
- 数据库迁移当前 v5；幂等记录有 `completed`，删除与访谈推进是可恢复的两阶段操作。
- 不处理 `origin/jaspin`，不拉取或合并其他分支，不推送、不部署、不调用付费模型。
- 在新的 `codex/trial-readiness` 分支实施；如分支已存在，先检查，不覆盖。若使用 worktree，先检查已存在的工作区；不要改动历史 `.worktrees/authenticated-frontend`。
- 保护现有未提交内容。所有试验使用新建临时数据库、检查点和图片目录，不使用实际用户数据库或图片。
- 不做邮箱验证、密码找回、邮件系统；不新增说明书导出/历史版本 UI、自由文本理解、自动估价或空间建模。
- 允许修复本计划测试中发现的局部可靠性缺陷；需要更换存储、认证架构或大幅改变业务协议时，先报告并请求方向，不自行扩张。
- 多模态仍延期。真实上传不代表真实识图，每图四条固定模拟观察，备注不解析；不得在试用报告中暗示真实 AI 已验证。
- 每个任务按“明确断言 → 运行测试 → 对失败做最小修复 → 回归 → 独立提交”执行。新增覆盖若首次就通过，记录为新增验证，不制造虚假失败。
- 该文档是任务与验收合同；执行者应先阅读相关代码，将各任务细化到实际测试夹具与函数，再实施，不应为了符合预想方案重构已正确的代码。

## 1. 开始前核对与阅读

- [ ] 运行以下只读命令，记录实际分支、HEAD、工作区及与基线的差异：

```bash
git status --short --branch
git log -5 --oneline
git worktree list
git diff --stat 8deab24...HEAD
```

- [ ] 阅读 `README.backend.md`、`README.frontend.md`、`docs/15-project-handoff.zh-CN.md` 顶部及屋主访谈规格。交接文档现有部分数字、分支、迁移说明过时，以代码和本计划基线为准。
- [ ] 阅读核心实现：`src/alignspace/application/service.py`、`resources.py`、`persistence/repository.py`、`migrations.py`、`workflow/graph.py`、`workflow/runtime.py`、`frontend/src/api.ts`、`frontend/src/workflow/Workspace.tsx`。
- [ ] 先运行第 7 节基线命令。环境失败与产品失败分开记录，不通过弱化断言或恢复假身份头来让测试变绿。
- [ ] 创建实施分支，后续每组任务单独提交；本轮结束等待用户要求的统一验收，不自行合并。

## 2. 任务 A：中断、重启与网络重试

**主要文件**：扩展 `tests/api/test_interview.py`、`tests/integration/workflow/test_resume.py`、`tests/integration/application/test_idempotent_write.py`、`frontend/src/api.test.ts`；新增 `tests/integration/workflow/test_restart_recovery.py`。仅在复现失败后修改对应服务/工作流代码。

**接口边界**：使用现有分析、回答、约束、说明书、审批和删除接口；不新增业务接口。使用现有 `idempotencyKey`、`expectedStateVersion` 和错误码。

- [ ] 检查已有覆盖，为下面场景建立“已有测试 / 新增测试 / 未覆盖原因”清单，避免重复堆测试。
- [ ] 在屋主待答、设计师待反馈、待双方审批三个节点分别关闭应用并重新创建应用，复用同一临时业务库、检查点与图片目录、同一测试密钥；重新登录后继续操作。必须真正重建应用和关闭旧连接，不仅刷新页面。
- [ ] 断言账户和项目成员未变化，偏好/约束/历史说明书未丢失，图片能读，待办角色与问题正确，后续可完成审批，不产生重复问题或重复版本。
- [ ] 模拟服务端写入已成功但客户端没有收到响应；客户端使用同键同体重试。至少覆盖回答、约束新增、图片删除：业务副作用只发生一次，完成响应保持一致。
- [ ] 保留并补强删除故障恢复：推进前失败、推进后响应保存失败；重启应用后同键重试也可恢复，完成后再重试不推进、不增加版本。
- [ ] 同键不同体拒绝；版本过时返回 409，不自动以新版本覆盖用户意图。非法/越权请求不改变业务状态。
- [ ] 有限重试后显示可操作错误，不无限请求；用户输入在 409 后保留。明确未提交表单刷新后不保证保存是现有边界，不在本轮引入浏览器草稿数据库。
- [ ] 新增测试运行通过后，执行关联 API/工作流/API 客户端测试；提交 `test/fix: verify workflow restart and retry recovery`。

**验收证据**：每个断点的注入位置、失败前后版本和对象数量、重试结果、重建应用后的下一步结果。不得只断言 HTTP 200。

## 3. 任务 B：多标签页与双角色协作

**主要文件**：新增 `frontend/e2e/collaboration-resilience.spec.ts`；扩展 `frontend/src/api.test.ts`、`frontend/src/workflow/Workspace.test.tsx`；检查 `tests/integration/persistence/test_concurrency.py`。必要修复局限在 API 客户端、Workspace 与实际有缺陷的后端写路径。

**接口边界**：同一角色的两个标签页使用同一浏览器 context；屋主和设计师使用两个独立 context。浏览器场景必须真实注册/登录，不绕过认证。

- [ ] 同一设计师两标签页读取相同版本，分别编辑同一约束：第一份成功，第二份 409；第二份输入保留，刷新后由用户明确重新提交；不能静默覆盖。
- [ ] 一页已完成当前问题，另一页仍保留旧问题输入：后者不得把旧回答写入下一题；错误/刷新后旧输入仍可辨认和复制。
- [ ] 屋主修改偏好或设计师修改约束后，另一页的旧方案批准请求被后端拒绝；刷新后提示过时，重新生成并由双方批准同一新版本。
- [ ] 同一账户一页退出，另一页会话失效；刷新请求在退出时完成也不能复活登录。继承已有覆盖，增加真实标签页证明，不只测模拟 BroadcastChannel。
- [ ] 断言完成操作后的共享状态一致，确认记录、冲突和审批不会重复；图片删除退役问题后其他页面刷新能进入正确下一步。
- [ ] 等待真实响应和明确的新问题/新版本 UI；不用固定长 sleep 掩盖竞态，不通过重试次数把不稳定测试变成“通过”。
- [ ] 完整浏览器套件连续运行 3 次，全部通过。出现不稳定先定位是产品还是测试同步，再修复并重新计数。
- [ ] 提交 `test/fix: cover concurrent collaboration and session recovery`。

**验收证据**：每个场景角色与 context 关系、两个请求各自的结果、最终状态，以及脱敏截图或失败说明。不得保存含真实令牌/密码的网络 trace。

## 4. 任务 C：离线一致性备份、恢复与安全重置

**新增文件**：`scripts/backup_local.py`、`scripts/restore_local.py`、`tests/integration/persistence/test_backup_restore.py`、`docs/runbooks/local-backup-restore.zh-CN.md`。

**方式**：第一版只支持明确停服后的本地备份。业务 SQLite、检查点 SQLite 和图片目录必须作为同一组处理；不声称支持在线一致性。

**建议固定命令合同**（由两个脚本实现）：

```text
uv run python scripts/backup_local.py --database ABS_DB --checkpoint ABS_CHECKPOINT --assets ABS_ASSETS --output NEW_ABS_DIR --confirm-stopped
uv run python scripts/restore_local.py --backup ABS_BACKUP_DIR --destination NEW_ABS_DIR
```

`ABS_*` 为操作者显式选择的绝对路径，`NEW_ABS_DIR` 必须不存在。运行手册给出临时目录演练的完整实例，不把这里的参数说明误当作可直接运行的路径。

- [ ] 先测试参数校验：拒绝根目录/主目录等宽泛目标、已存在目标、目标位于源目录内部、缺失源、符号链接和备份校验不通过；失败不得改写原数据。
- [ ] 备份包固定包含 `database.sqlite3`、`checkpoints.sqlite3`、`assets/`、`manifest.json`。清单记录格式版本、创建时间、业务迁移版本、文件相对路径、大小和 SHA-256；不写密码、JWT 密钥或源机器的敏感绝对路径。
- [ ] 两个数据库使用 SQLite backup API 导出，保证 WAL 中已提交数据不被漏掉；整个过程仍要求先停止所有写入服务。说明 `--confirm-stopped` 是操作者确认，不是自动证明服务已停止。
- [ ] 备份不得在半完成时显示成功；失败删除仅本次创建且已验证路径的临时输出，或保留明确未完成标志供诊断，不能覆盖已有备份。
- [ ] 恢复前校验完整清单、两个数据库完整性、文件哈希以及相对路径不得越界；恢复到全新目录，不覆盖运行中的数据，不自动启动服务。
- [ ] 报告恢复后的三个明确路径供环境变量使用。备份含账户哈希、会话及用户图片，是敏感资料，不进 Git、不上传公开附件；密钥由操作者另行安全保管。使用同一临时密钥验证恢复，轮换密钥的会话影响写入手册，不承诺仅换密钥就撤销所有会话。
- [ ] 测试：创建两真实账户和包含图片、已确认偏好、约束、说明书历史及待答检查点的项目；停止应用；备份；恢复到新目录；重新启动并登录。验证成员权限、原图读取、历史内容、版本及待答流程可继续。
- [ ] 测试缺文件、篡改图片、损坏数据库、已有恢复目录：必须拒绝，并证明原库原图不变。
- [ ] 重置演示采用切换到一组全新数据路径；不提供默认清空主仓库数据库/图片的脚本。旧环境保留供恢复。
- [ ] 提交 `feat: add verified offline backup and restore tools`。

**验收证据**：完整备份—恢复—续答演练记录和故障测试结果。仅复制文件成功不等于恢复成功。

## 5. 任务 D：内部试用、启动手册与交接同步

**新增文件**：`docs/runbooks/internal-trial.zh-CN.md`、`docs/reports/trial-readiness-validation.zh-CN.md`。

**更新文件**：`README.backend.md`、`README.frontend.md`、`docs/15-project-handoff.zh-CN.md`。

- [ ] 手册明确：内部模拟试用不等于真实用户研究；屋主与设计师使用不同账户，开始前说明图片分析仍模拟，不能评价真实识图准确率。
- [ ] 给出环境准备、三个数据路径、密钥本地设置、两个服务启动、测试端口占用处理、打开页面、注册两账户、加入项目及正常退出流程。密钥不硬编码、不打印、不提交。
- [ ] 准备三份案例：普通对齐成功；预算/材质冲突后修改并重新审批；跳过问题、删除来源图、服务中断与重试。候选部位按现有模拟输出选择，不暗示模型理解了图片。
- [ ] 每份案例记录步骤、预期结果、实际结果、角色、阻塞点和截图；最后一份包含备份恢复后继续工作。
- [ ] 问题清单分为阻塞缺陷、非阻塞体验建议、明确不在范围内三类。局部阻塞缺陷先补回归再修复；说明书导出、视觉模型等不作为试用缺陷强行实现。
- [ ] 可由执行模型通过真实浏览器完成内部模拟试用，不需等待招募真实用户；明确报告执行者身份，不能写“用户认可/满意度达标”。
- [ ] 提供错误排查：401/会话失效、409/保留输入后重新提交、网络失败、图片缺失、无待办、备份校验失败；说明哪些可由用户恢复、哪些需要日志与 correlationId。
- [ ] 更新交接文档顶部到实际分支和 HEAD、迁移版本、实测数量、剩余限制；纠正已经过时的图片开发分支和“下一步必须接多模态”提示。历史快照保留但明确不作为执行入口。
- [ ] 提交 `docs: add internal trial runbook and verified handoff`。

## 6. 顺序与协作边界

1. 先核对基线和建立清单。
2. A、B、C 可以并行，但后端服务修改由一个负责人整合，避免多个模型同时修改 `resources.py` / `service.py`。
3. D 的手册草稿可同步开始；最终案例试跑与报告必须基于 A–C 集成后的代码。
4. 所有实现集成后运行最终套件并审查，保留功能分支等待统一验收。

若多个模型参与：一个负责 A 和必要的后端修复，一个负责 B 和前端测试，一个负责 C；集成人负责 D 与最终验收准备。共享文件修改先沟通，不覆盖他人工作。

## 7. 最终验收命令与通过条件

从实际实施工作区根目录运行：

```bash
uv run pytest -q
uv run ruff check src tests scripts
```

从该工作区 `frontend` 目录运行：

```bash
npm test
npm run build
npm run test:e2e
npm run test:e2e
npm run test:e2e
```

- [ ] 全部测试与构建通过；不只报新增测试，不凭上一轮数字推断结果。
- [ ] A/B/C 每项都有自动化测试或具体人工证据；遗漏必须明确列出，不默认视为完成。
- [ ] 新增恢复测试确实销毁并重建应用；新增多标签测试确实操作多个页面；备份测试确实从恢复目录启动。
- [ ] 浏览器完整套件连续三次通过；运行失败不得从报告中删除。
- [ ] 日志、截图、报告没有密码、访问/刷新令牌、真实用户数据和真实图片隐私泄漏。
- [ ] 所有代码和文档已提交；`git status --short` 干净；未合并/推送/部署。

## 8. 交给下一位验收者的最终报告

报告必须包含：

1. 实施工作区绝对路径、分支、基线、最终 HEAD、提交列表及是否干净。
2. A–D 各任务完成情况、文件清单，以及本计划场景与测试名称的对应表。
3. 实际发现的缺陷、根因、修复方式及回归证据；区分旧问题与本轮引入的问题。
4. 完整测试命令、结果、浏览器三次运行结果；环境失败另列。
5. 备份恢复演练步骤及结果，报告脱敏，备份包本身不提交。
6. 手册与验证报告文件路径、剩余风险、建议后续工作。
7. 明确声明未合并、未推送、未部署、未调用外部付费模型，等待统一验收。

本阶段完成不代表产品已经生产就绪，也不代表真实 AI 能力或真实用户价值已验证；它交付的是现有初版本地试运行的可靠性与可操作证据。
