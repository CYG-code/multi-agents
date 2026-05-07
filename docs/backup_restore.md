# multi-agents ECS 本机备份与恢复指南

## 1. 当前数据存储结构说明

本项目在 ECS 上采用“本机轻量存储”：

1. PostgreSQL（本机）
- 连接信息来自：`/opt/multi-agents/backend/.env` 的 `DATABASE_URL`
- 业务主数据在 PostgreSQL：`users`、`rooms`、`room_members`、`messages`、`analysis_snapshots`、`tasks`、`room_task_scripts` 等

2. Redis（本机）
- 连接信息来自：`/opt/multi-agents/backend/.env` 的 `REDIS_URL`
- 保存实时协作与临时状态，例如：
  - `agent:task:*`
  - `room:{room_id}:writing_doc_state`
  - `room:{room_id}:writing_doc_change_log`
  - `active_rooms`
  - `room:{room_id}:online_users`
  - `room:{room_id}:online_user_conn_counts`
  - `room:{room_id}:last_msg_time`

---

## 2. 为什么必须同时备份 PostgreSQL + Redis

仅备份 PostgreSQL 不够，因为会缺失：
- 写作区实时内容（Redis）
- agent task 运行态/状态（Redis）
- 在线状态与部分协作实时键（Redis）

仅备份 Redis 也不够，因为会缺失：
- 用户、房间、消息、任务等核心结构化数据（PostgreSQL）

**结论：要恢复实验现场，必须同时备份 PostgreSQL 与 Redis。**

---

## 3. 备份脚本与恢复脚本

- `scripts/server_backup.sh`
- `scripts/server_restore.sh`

设计原则：
- 默认安全：不备份 `.env`，不恢复 `.env`，不恢复 nginx/systemd 配置
- 高风险动作必须显式参数开启
- 恢复前强制二次确认，必须输入 `RESTORE`

---

## 4. 一键备份命令（默认不含 `.env`）

```bash
sudo bash /opt/multi-agents/scripts/server_backup.sh
```

默认行为：
- 备份 PostgreSQL -> `postgres.dump`
- 备份 Redis -> `redis.rdb`
- 备份 nginx/systemd 配置
- 生成 `manifest.json` 与 `checksums.sha256`
- 打包为 `multi-agents-backup-YYYYmmdd-HHMMSS.tar.gz`
- 生成同名 `.sha256` 文件
- 默认不包含 `backend/.env`

> 默认备份目录：`/opt/backups/multi-agents`  
> 注意你曾手工使用过 `/backups/multi-agents`，两个目录不要混淆。

---

## 5. 带 `.env` 的备份命令（谨慎）

```bash
sudo bash /opt/multi-agents/scripts/server_backup.sh --include-env
```

> 警告：`backend/.env` 可能包含 API Key、数据库密码等敏感信息。  
> 仅在你明确需要“全量可恢复配置”时使用。

---

## 6. 备份后必须下载到本地电脑（重要）

只把备份包留在 ECS 上**不安全**。  
若 ECS 故障、磁盘损坏或实例丢失，服务器本机备份包也可能一起丢失。

请在备份后立即下载到本地电脑或其他独立存储。

### Windows PowerShell 示例

```powershell
scp root@121.43.104.192:/opt/backups/multi-agents/<backup>.tar.gz .
scp root@121.43.104.192:/opt/backups/multi-agents/<backup>.tar.gz.sha256 .
```

---

## 7. 如何校验备份包

在服务器或本地校验：

```bash
sha256sum -c <backup>.tar.gz.sha256
```

输出 `OK` 表示备份包完整。

---

## 8. 如何恢复（默认不恢复 env / config）

```bash
sudo bash /opt/multi-agents/scripts/server_restore.sh \
  --archive /opt/backups/multi-agents/multi-agents-backup-20260507-120000.tar.gz
```

恢复脚本会：
1. 显示高风险提示（覆盖 PostgreSQL、覆盖 Redis、重启服务）
2. 要求输入 `RESTORE` 二次确认
3. 停止后端服务
4. 恢复 PostgreSQL
5. 恢复 Redis
6. 重启 backend / nginx
7. 健康检查：
   - `systemctl is-active multi-agents-backend`
   - `redis-cli -u "$REDIS_URL" PING`
   - `curl http://127.0.0.1:8001/openapi.json`

---

## 9. Redis AOF 注意事项（恢复前）

恢复脚本会在恢复 Redis 前检查：

```bash
redis-cli -u "$REDIS_URL" --raw CONFIG GET appendonly
```

- 若 `appendonly=yes`：脚本会**默认中止**恢复  
  原因：仅覆盖 `dump.rdb` 可能不会生效，AOF 仍会回放旧数据。
- 若 `appendonly=no`：按 RDB 方式继续恢复。

---

## 10. 如何恢复 `.env`

仅当备份包内含 `config/backend.env` 且你显式允许时：

```bash
sudo bash /opt/multi-agents/scripts/server_restore.sh \
  --archive /opt/backups/multi-agents/multi-agents-backup-20260507-120000.tar.gz \
  --restore-env
```

脚本会先自动备份当前 env：
- `/opt/multi-agents/backend/.env.before-restore-YYYYmmdd-HHMMSS`

再恢复包内 env。

---

## 11. 如何恢复 nginx/systemd 配置

默认不恢复配置。需要显式开启：

```bash
sudo bash /opt/multi-agents/scripts/server_restore.sh \
  --archive /opt/backups/multi-agents/multi-agents-backup-20260507-120000.tar.gz \
  --restore-config
```

会恢复：
- `/etc/nginx/nginx.conf`
- `/etc/nginx/sites-enabled/*`
- `/etc/nginx/conf.d/*`
- `/etc/systemd/system/multi-agents-backend.service`
- 并执行 `systemctl daemon-reload`

恢复前会先备份当前关键配置：
- `/etc/nginx/nginx.conf.before-restore-时间戳`
- `/etc/systemd/system/multi-agents-backend.service.before-restore-时间戳`

---

## 12. 如何设置 cron 定时备份

示例：每天凌晨 03:30 自动备份

```bash
sudo crontab -e
```

加入：

```cron
30 3 * * * /bin/bash /opt/multi-agents/scripts/server_backup.sh >> /var/log/multi-agents-backup.log 2>&1
```

如果要包含 env（不推荐默认）：

```cron
30 3 * * * /bin/bash /opt/multi-agents/scripts/server_backup.sh --include-env >> /var/log/multi-agents-backup.log 2>&1
```

---

## 13. 哪些文件不应该提交到 GitHub

不要提交：
- `backend/.env`
- 任意备份包（`*.tar.gz`）
- 任意校验结果（可选提交脚本但不提交产物）
- 临时日志、调试输出、`.ai_scratch/` 结果文件

---

## 14. 安全提醒（务必遵守）

1. 备份包可能包含学生实验数据（消息、协作过程、写作内容）
2. 使用 `--include-env` 时，包内可能包含 API Key 和密码
3. 不要公开上传备份包
4. 不要把备份包提交到 GitHub
5. 不要把真实 `backend/.env` 提交到 GitHub
6. 建议备份目录权限 `700`，备份文件权限 `600`
7. 只把备份留在 ECS 上不安全，务必下载到本地或异地安全存储
8. 建议将备份包同步到离线/异地安全存储（例如本地加密盘或私有对象存储）

---

## 15. 常用命令速查

### 备份（默认）
```bash
sudo bash /opt/multi-agents/scripts/server_backup.sh
```

### 备份（含 env）
```bash
sudo bash /opt/multi-agents/scripts/server_backup.sh --include-env
```

### 自定义输出目录和文件名
```bash
sudo bash /opt/multi-agents/scripts/server_backup.sh \
  --output-dir /opt/backups/multi-agents \
  --name multi-agents-backup-manual.tar.gz
```

### 恢复（默认）
```bash
sudo bash /opt/multi-agents/scripts/server_restore.sh \
  --archive /opt/backups/multi-agents/<backup>.tar.gz
```

### 恢复（含 env）
```bash
sudo bash /opt/multi-agents/scripts/server_restore.sh \
  --archive /opt/backups/multi-agents/<backup>.tar.gz \
  --restore-env
```

### 恢复（含 nginx/systemd 配置）
```bash
sudo bash /opt/multi-agents/scripts/server_restore.sh \
  --archive /opt/backups/multi-agents/<backup>.tar.gz \
  --restore-config
```

### 恢复（env + config）
```bash
sudo bash /opt/multi-agents/scripts/server_restore.sh \
  --archive /opt/backups/multi-agents/<backup>.tar.gz \
  --restore-env \
  --restore-config
```
