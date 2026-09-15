# AlignSpace 本地离线备份与恢复手册（中文）

本手册只覆盖**明确停服后**的一致性备份与恢复到**全新目录**。它不提供在线快照、不保证运行中备份的一致性，也不会自动启动或停止任何服务。

一套数据由三部分组成，必须一起处理：

1. 业务数据库（默认 `alignspace-accounts.db`）
2. LangGraph 检查点数据库（默认 `alignspace-accounts-checkpoints.db`）
3. 参考图片目录（`ALIGNSPACE_ASSET_DIR`，默认 `var/assets/`）

## 1. 命令合同

```bash
# 备份（必须先停止所有写入进程）
uv run python scripts/backup_local.py \
  --database ABS_DB --checkpoint ABS_CHECKPOINT --assets ABS_ASSETS \
  --output NEW_ABS_DIR --confirm-stopped

# 恢复（恢复到全新目录）
uv run python scripts/restore_local.py \
  --backup ABS_BACKUP_DIR --destination NEW_ABS_DIR
```

- `ABS_*` 是操作者明确选择的**绝对路径**；`NEW_ABS_DIR` 必须**不存在**。
- `--confirm-stopped` 是**操作者确认**服务已停止，不是程序自动检测；不加该参数脚本会拒绝执行。
- 备份失败不会生成“成功”的目录：脚本在临时目录中构建，成功后才改名；失败会清掉本次临时目录，且**永不覆盖已有目录**。

## 2. 备份包含什么

```text
<备份目录>/
  database.sqlite3      # 业务库（SQLite backup API 导出，含已提交数据）
  checkpoints.sqlite3   # 检查点库
  assets/               # 参考图片（内容寻址）
  manifest.json         # 格式版本、创建时间、业务迁移版本、每个文件的相对路径/大小/SHA-256
```

清单只包含相对路径、大小与哈希，**不写密钥、令牌或源机器绝对路径**。脚本会拒绝：非绝对路径、缺失源、源为符号链接、目标已存在、目标与源重叠、以及宽泛目标（根目录、主目录）。

## 3. 完整演练（临时目录，可直接运行）

```bash
# 1. 准备一个隔离的数据目录
SRC="$(mktemp -d /tmp/alignspace-drill.XXXXXX)"
export ALIGNSPACE_DATABASE_URL="sqlite:///$SRC/alignspace.db"
export ALIGNSPACE_CHECKPOINT_PATH="$SRC/checkpoints.db"
export ALIGNSPACE_ASSET_DIR="$SRC/assets"
export ALIGNSPACE_AUTH_SECRET="$(openssl rand -hex 32)"   # 不要打印或提交
export ALIGNSPACE_DEV=1

# 2. 启动并产生数据（另开终端），然后停止服务
uv run uvicorn alignspace.main:app --host 127.0.0.1 --port 8000
# ...注册两个账户、创建/加入项目、上传图片并完成一次方案审批...
# Ctrl+C 停止服务，确认没有其他写入进程

# 3. 备份
BK="$(mktemp -d /tmp/alignspace-backup.XXXXXX)" && rmdir "$BK"
uv run python scripts/backup_local.py \
  --database "$ALIGNSPACE_DATABASE_URL#sqlite:///" \
  --checkpoint "$ALIGNSPACE_CHECKPOINT_PATH" \
  --assets "$ALIGNSPACE_ASSET_DIR" \
  --output "$BK" --confirm-stopped
# 注意：--database 需要文件路径，直接写实际路径，例如
#   --database "$SRC/alignspace.db"

# 4. 恢复到全新目录
DST="$(mktemp -d /tmp/alignspace-restore.XXXXXX)" && rmdir "$DST"
uv run python scripts/restore_local.py --backup "$BK" --destination "$DST"

# 5. 用恢复后的数据启动（三个路径在恢复输出中给出）
export ALIGNSPACE_DATABASE_URL="sqlite:///$DST/database.sqlite3"
export ALIGNSPACE_CHECKPOINT_PATH="$DST/checkpoints.sqlite3"
export ALIGNSPACE_ASSET_DIR="$DST/assets"
uv run uvicorn alignspace.main:app --host 127.0.0.1 --port 8000
# 重新登录，确认成员、原图、方案历史与待办流程均可继续
```

> 上面的 `$ALIGNSPACE_DATABASE_URL#sqlite:///` 只是说明用途；实际运行时请给 `--database` 传文件绝对路径（例如 `$SRC/alignspace.db`），不要传 `sqlite:///` URL。

## 4. 恢复后如何指向新数据

恢复脚本会打印三条路径，直接用于启动：

```text
restored database:   <DST>/database.sqlite3
restored checkpoint: <DST>/checkpoints.sqlite3
restored assets:     <DST>/assets
```

对应环境变量：`ALIGNSPACE_DATABASE_URL`（写成 `sqlite:///<绝对路径>`）、`ALIGNSPACE_CHECKPOINT_PATH`、`ALIGNSPACE_ASSET_DIR`。

## 5. 安全与保留

- 备份包含**账户密码哈希、会话记录和用户图片**，属于敏感资料：**不要提交到 Git、不要上传到公开附件**。
- 备份本身**不包含 `ALIGNSPACE_AUTH_SECRET`**；密钥由操作者另行安全保管。用新密钥启动恢复后的数据是可行的，但**只更换密钥不会撤销所有会话**——已有访问 JWT 在过期前仍可能有效，刷新令牌也会继续工作。需要强制下线时，应另行撤销会话或轮换后清理 `auth_sessions`/`refresh_tokens`。
- 旧数据目录在恢复验证通过前**保留**，不要删除。

## 6. 重置演示

重置演示的方式是**切换到一组全新的数据路径**（新的数据库、检查点与图片目录），不要清空正在使用的目录。本仓库**不提供**默认清空主仓库数据库或图片的脚本；旧环境保留以便回退或恢复。

## 7. 故障排查

| 现象 | 含义与处理 |
|---|---|
| `refusing to back up without --confirm-stopped` | 忘记加 `--confirm-stopped`；确认已停服后重新执行 |
| `output already exists` / `destination already exists` | 目标必须不存在；换一个新的绝对路径 |
| `output must not overlap the source data` | 备份/恢复目标不能位于源数据内部或包含源数据 |
| `manifest ... hash mismatch` / `size mismatch` | 备份文件被改动或损坏；不要恢复，改用其它备份 |
| `database.sqlite3 failed its integrity check` | 备份中的数据库损坏；不要恢复 |
| 恢复后登录失败或会话异常 | 使用了不同密钥；按第 5 节处理会话，不要把密钥写进备份或 Git |

备份的大小、哈希与迁移版本都在 `manifest.json` 中，可用于核对。
