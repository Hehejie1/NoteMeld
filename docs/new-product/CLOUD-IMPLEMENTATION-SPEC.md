# NoteMeld Cloud 实现规格（1:1 实现依据）

状态：与当前 `cloud/` 实现对齐的权威实现规格。其他 AI 可依据本文件对云端产品做 1:1 复刻。本文件描述**已落地的真实实现**，不是目标愿景；产品概念词汇见 [CONTEXT.md](./CONTEXT.md)，跨端逻辑协议见 [CONVERSATION-STREAM-PROTOCOL.md](./CONVERSATION-STREAM-PROTOCOL.md)。

## 1. 技术栈与运行形态

| 项 | 选型 |
|---|---|
| 语言/框架 | Python 3.11 + FastAPI 0.11 + Pydantic v2 + Uvicorn（单 worker，开发端口 8583） |
| 数据库 | SQLite（WAL 模式，每连接 `PRAGMA foreign_keys=ON`），默认路径 `{data_dir}/cloud.db` |
| 出站 HTTP | `httpx.Client`（`trust_env=False`），所有 provider I/O 均为阻塞调用 |
| 凭据加密 | Fernet（master key 的 SHA-256 作 key），见 `security.encrypt_secret/decrypt_secret` |
| 口令哈希 | scrypt（`n=16384, r=8, p=1`，16 字节盐），格式 `scrypt$16384$8$1${salt}${digest}` |

启动入口：`python -m uvicorn cloud.main:app`，应用工厂 `cloud.app:create_app(settings=None)`；未传 settings 时由 `cloud.config.load_settings()` 从环境变量加载。开发启动脚本 `scripts/cloud/start.sh` 会 source `cloud/.env`、导出 `NOTEMELD_CLOUD_DATA_DIR` 等。

### 1.1 统一响应信封

除 SSE 流和静态文件外，所有 `/v1` 业务接口返回统一信封：

```json
{"code": 0, "msg": "success", "data": { ... }}
```

失败由 FastAPI 异常处理转换：业务校验错误 `{"detail": ...}`；HTTP 状态码语义遵循标准（400 参数/越界、401 未认证、403 无权限、404 不存在、409 冲突、422 请求体不合法）。

### 1.2 认证模型

- 登录成功返回不透明 bearer token（形如 `nmt_{token_id}.{secret}`），客户端以 `Authorization: Bearer <raw>` 发送。
- 服务端只存 `sha256(token_id + "." + secret)` 的 digest（`tokens.digest` 唯一），不存明文。
- Token 带 `audience`（默认 `cloud-api`）、`scopes_json`（默认 `["*"]`）、`expires_at`、`revoked_at`，可关联 `device_id`。
- 认证以依赖注入方式按路由要求声明 scope，例如 `Depends(_auth_dependency(db, required_scope="session.write"))`。

## 2. 核心领域与目录布局

```
cloud/
  main.py        # uvicorn 入口：app = create_app()
  app.py         # FastAPI 工厂、全部路由、中间件、辅助函数
  config.py      # CloudSettings（dataclass）、load_settings
  db.py          # SQLite SCHEMA（34 张表）、CloudDB、初始化/迁移
  security.py    # Fernet、scrypt、token 生成与解析
  workspace.py   # Workspace：root-jail 文件读写、配额、备份/恢复
  terminal.py    # SandboxedShell：受限 bash
  agent.py       # Agent runner 与 provider SSE 流式
  data/          # 运行数据（gitignore）：cloud.db、workspaces/、.cloud-secret-key
```

### 2.1 分配文件夹（Workspace Root）

每个用户的每个工作区对应磁盘上一个独立根目录：

```
{data_dir}/workspaces/{user_id}/{workspace_id}
```

- `user_id`、`workspace_id` 必须匹配 `^[A-Za-z0-9._-]+$`（单段安全名），否则拒绝构造。
- 终端与文件 API 都以该目录为逻辑根（root-jail），不保存会话正文到 SQLite。
- 默认会话工作区 `workspace_id = "default"`。

## 3. 数据模型（SQLite 表结构）

下列为权威表结构（省略 `IF NOT EXISTS`）。所有时间字段为 Unix 秒整数；JSON 字段为 TEXT。

### 3.1 身份与组织

```sql
users(
  id TEXT PK, username TEXT NOT NULL, email TEXT, display_name TEXT, avatar TEXT,
  password_hash TEXT NOT NULL, email_verified_at INTEGER, last_login_at INTEGER,
  role TEXT NOT NULL CHECK(role IN ('admin','user')),
  disabled INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL
);
organizations(id TEXT PK, name TEXT NOT NULL, created_at INTEGER, updated_at INTEGER);
organization_members(
  organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK(role IN ('owner','admin','member')),
  created_at INTEGER NOT NULL, PK(organization_id, user_id)
);
organization_preferences(
  organization_id TEXT PK REFERENCES organizations(id) ON DELETE CASCADE,
  preferences_json TEXT NOT NULL DEFAULT '{}', updated_at INTEGER NOT NULL
);
organization_memories(
  id TEXT PK, organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  content TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'admin',
  created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
```

### 3.2 Token 与设备

```sql
tokens(
  id TEXT PK, user_id TEXT NOT NULL REFERENCES users(id),
  digest TEXT NOT NULL UNIQUE, expires_at INTEGER, revoked_at INTEGER,
  audience TEXT NOT NULL DEFAULT 'cloud-api',
  scopes_json TEXT NOT NULL DEFAULT '["*"]',
  device_id TEXT REFERENCES devices(id), created_at INTEGER NOT NULL
);
devices(
  id TEXT PK, user_id TEXT NOT NULL REFERENCES users(id), public_key TEXT,
  platform TEXT NOT NULL, display_name TEXT NOT NULL,
  connectivity_json TEXT NOT NULL DEFAULT '{}',
  revoked_at INTEGER, last_seen_at INTEGER, created_at INTEGER NOT NULL
);
pairings(
  id TEXT PK, user_id TEXT NOT NULL REFERENCES users(id),
  code_hash TEXT NOT NULL UNIQUE, expires_at INTEGER NOT NULL,
  status TEXT NOT NULL, device_id TEXT, created_at INTEGER NOT NULL
);
grants(
  id TEXT PK, user_id TEXT NOT NULL REFERENCES users(id),
  controller_device_id TEXT NOT NULL, host_device_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('standard','super_admin')),
  scopes_json TEXT NOT NULL, workspace_refs_json TEXT NOT NULL,
  expires_at INTEGER, revoked_at INTEGER, created_at INTEGER NOT NULL
);
```

### 3.3 会话、命令、事件

```sql
sessions(
  id TEXT PK, user_id TEXT NOT NULL REFERENCES users(id),
  kind TEXT NOT NULL, title TEXT NOT NULL, workspace_id TEXT NOT NULL,
  status TEXT NOT NULL, copied_from TEXT,
  next_sequence INTEGER NOT NULL DEFAULT 1,
  next_event_sequence INTEGER NOT NULL DEFAULT 1,
  authority_epoch INTEGER NOT NULL DEFAULT 1, model_id TEXT,
  lease_owner TEXT, lease_expires_at INTEGER,
  created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
session_archives(
  user_id TEXT NOT NULL REFERENCES users(id),
  session_id TEXT NOT NULL REFERENCES sessions(id),
  device_id TEXT, archived_at INTEGER NOT NULL,
  PK(user_id, session_id, device_id)
);
commands(
  id TEXT PK, session_id TEXT NOT NULL REFERENCES sessions(id),
  request_id TEXT NOT NULL, payload_hash TEXT NOT NULL, sequence INTEGER NOT NULL,
  input_text TEXT NOT NULL,
  attachments_json TEXT NOT NULL DEFAULT '[]',
  options_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL, lease_owner TEXT, lease_expires_at INTEGER,
  attempt_count INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL,
  UNIQUE(session_id, request_id), UNIQUE(session_id, sequence)
);
events(
  id TEXT PK, session_id TEXT NOT NULL REFERENCES sessions(id),
  sequence INTEGER NOT NULL, event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL, created_at INTEGER NOT NULL,
  UNIQUE(session_id, sequence)
);
approvals(
  id TEXT PK, user_id TEXT NOT NULL REFERENCES users(id),
  session_id TEXT NOT NULL REFERENCES sessions(id),
  command_id TEXT, tool_name TEXT NOT NULL,
  arguments_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected','expired')),
  requested_by TEXT NOT NULL, resolved_by TEXT, resolution_note TEXT,
  created_at INTEGER NOT NULL, resolved_at INTEGER,
  UNIQUE(session_id, command_id, tool_name, arguments_json)
);
```

### 3.4 模型目录

```sql
providers(
  id TEXT PK, organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  display_name TEXT NOT NULL, vendor_id TEXT NOT NULL DEFAULT 'custom',
  protocol TEXT NOT NULL CHECK(protocol IN ('openai-compatible','anthropic-messages','ollama')),
  base_url TEXT NOT NULL, auth_type TEXT NOT NULL DEFAULT 'bearer',
  api_key_ciphertext TEXT, created_by TEXT NOT NULL REFERENCES users(id),
  created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
  UNIQUE(organization_id, display_name)
);
models(
  id TEXT PK, user_id TEXT NOT NULL REFERENCES users(id),
  name TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
  base_url TEXT, api_key_ciphertext TEXT,
  enabled INTEGER NOT NULL DEFAULT 1, is_default INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
  organization_id TEXT REFERENCES organizations(id),
  provider_id TEXT REFERENCES providers(id) ON DELETE CASCADE,
  display_name TEXT, context_window INTEGER NOT NULL DEFAULT 128000,
  modalities TEXT NOT NULL DEFAULT 'text',
  test_status TEXT NOT NULL DEFAULT 'unknown', model_id TEXT
);
model_usage_records(
  id TEXT PK, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  command_id TEXT NOT NULL REFERENCES commands(id) ON DELETE CASCADE,
  model_id TEXT, provider TEXT, model TEXT NOT NULL,
  prompt_tokens INTEGER NOT NULL DEFAULT 0,
  completion_tokens INTEGER NOT NULL DEFAULT 0,
  total_tokens INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL
);
```

### 3.5 Workspace、备份与其他

```sql
workspaces(
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  id TEXT NOT NULL, display_name TEXT NOT NULL,
  created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
  PK(user_id, id)
);
workspace_backups(
  user_id TEXT NOT NULL, workspace_id TEXT NOT NULL, id TEXT NOT NULL,
  archive_path TEXT NOT NULL, bytes INTEGER NOT NULL, created_at INTEGER NOT NULL,
  PK(user_id, id),
  FOREIGN KEY(user_id, workspace_id) REFERENCES workspaces(user_id, id) ON DELETE CASCADE
);
share_tokens(
  id TEXT PK, user_id TEXT NOT NULL REFERENCES users(id),
  session_id TEXT NOT NULL REFERENCES sessions(id),
  token_digest TEXT NOT NULL UNIQUE,
  role TEXT NOT NULL CHECK(role IN ('viewer','standard','super_admin')),
  scopes_json TEXT NOT NULL, expires_at INTEGER, revoked_at INTEGER,
  created_at INTEGER NOT NULL
);
session_payloads(
  session_id TEXT PK REFERENCES sessions(id),
  payload_json TEXT NOT NULL, created_at INTEGER NOT NULL
);
session_import_requests(
  user_id TEXT NOT NULL REFERENCES users(id), request_id TEXT NOT NULL,
  payload_hash TEXT NOT NULL, session_id TEXT NOT NULL REFERENCES sessions(id),
  created_at INTEGER NOT NULL, PK(user_id, request_id)
);
relay_cursors(
  session_id TEXT NOT NULL REFERENCES sessions(id),
  sender_device_id TEXT NOT NULL, last_sequence INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL, PK(session_id, sender_device_id)
);
login_attempts(key TEXT PK, window_started INTEGER NOT NULL, failed_count INTEGER NOT NULL);
user_preferences(
  user_id TEXT PK REFERENCES users(id),
  preferences_json TEXT NOT NULL DEFAULT '{}', updated_at INTEGER NOT NULL
);
verification_codes(
  id TEXT PK, email TEXT NOT NULL, purpose TEXT NOT NULL,
  code_hash TEXT NOT NULL, expires_at INTEGER NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0, used_at INTEGER,
  created_at INTEGER NOT NULL, request_ip TEXT
);
access_requests(
  id TEXT PK, email TEXT NOT NULL, display_name TEXT NOT NULL,
  reason TEXT NOT NULL, password_hash TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected','expired')),
  reviewed_by TEXT, reviewed_at INTEGER,
  created_at INTEGER NOT NULL, expires_at INTEGER
);
invitations(
  id TEXT PK, email TEXT NOT NULL, display_name TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('user')),
  token_hash TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL CHECK(status IN ('pending','accepted','revoked','expired')),
  created_by TEXT NOT NULL REFERENCES users(id),
  created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, accepted_at INTEGER
);
-- config_sync_state / config_sync_items / config_sync_idempotency
-- 用于端侧配置同步（修订号 + 幂等键），结构见 db.py SCHEMA。
```

> 迁移注意：旧库 `models` 表是“先建表后 ALTER 加 provider_id”，该列没有真实外键约束，因此删除 provider 不会自动级联删模型。provider 删除必须在同一 `BEGIN IMMEDIATE` 事务内先 `DELETE FROM models WHERE provider_id=? AND organization_id=?` 再删 provider。

## 4. API 清单（按领域）

路径同时保留 `/v1/...` 与 `/v1/cloud/...` 两套别名（表中标注主路径）。`🔒` 表示需要认证。

### 4.1 系统与认证

| 方法 路径 | 说明 |
|---|---|
| `GET /health` | 健康检查 `{"ok":true,"service":"notemeld-cloud"}` |
| `GET /ready` | 就绪检查 |
| `GET /v1/capabilities` | 服务能力声明 🔒 |
| `POST /v1/auth/login` | 用户名/口令登录，返回 token |
| `POST /v1/auth/login/password` | 同上（显式密码入口） |
| `POST /v1/auth/code/send` | 发送邮箱验证码（开发模式返回固定码 888888） |
| `POST /v1/auth/login/code` | 验证码登录 |
| `POST /v1/auth/password/reset` | 申请重置口令 |
| `POST /v1/auth/revoke` 🔒 | 吊销当前 token |
| `GET /v1/auth/me` 🔒 | 当前身份 |
| `PUT /v1/auth/me` 🔒 | 更新自身资料 |
| `POST /v1/auth/rotate` 🔒 | 轮换 token |
| `POST /v1/auth/tokens` 🔒 | 颁发个人 token |
| `GET /v1/auth/tokens` 🔒 | 列出个人 token |
| `POST /v1/auth/tokens/{id}/revoke` 🔒 | 吊销指定 token |

### 4.2 准入、组织与偏好

| 方法 路径 | 说明 |
|---|---|
| `POST /v1/access-requests` | 提交访问申请 |
| `POST /v1/admin/invitations` 🔒 | 邀请成员（管理员） |
| `GET /v1/admin/invitations` 🔒 | 邀请列表 |
| `POST /v1/invitations/{token}/accept` | 受邀者设置口令 |
| `GET /v1/preferences` / `PUT` 🔒 | 用户偏好读写 |
| `GET/PUT /v1/admin/organization/preferences` 🔒 | 组织偏好 |
| `GET/POST/DELETE /v1/admin/organization/memories[/{id}]` 🔒 | 组织长期记忆 |
| `GET /v1/admin/users` 🔒 | 成员列表 |
| `POST /v1/admin/users` 🔒 | 管理员创建成员 |
| `PUT/DELETE /v1/admin/users/{id}` 🔒 | 编辑/删除成员 |
| `GET /v1/admin/access-requests` 🔒 | 申请列表 |
| `POST /v1/admin/access-requests/{id}/review` 🔒 | 审核申请 |
| `GET /v1/admin/audits` / `GET /v1/audits` 🔒 | 审计查询 |

### 4.3 模型目录（Provider/Model 两级）

| 方法 路径 | 说明 |
|---|---|
| `GET /v1/catalog/providers` 🔒 | 列出 Provider 及其模型 |
| `POST /v1/catalog/providers` 🔒 | 新建 Provider（owner/admin 可写） |
| `PATCH /v1/catalog/providers/{id}` 🔒 | 更新 Provider（密钥留空保留原值） |
| `DELETE /v1/catalog/providers/{id}` 🔒 | 删除 Provider（同事务先删其模型） |
| `POST /v1/catalog/providers/{id}/models/batch` 🔒 | 批量入库模型 |
| `PATCH/DELETE /v1/catalog/models/{row_id}` 🔒 | 更新/删除单个模型 |
| `POST /v1/catalog/models/{row_id}/default` 🔒 | 设为默认 |
| `POST /v1/catalog/discover` 🔒 | 代理发现上游模型（SSRF 防护） |
| `POST /v1/catalog/test-connection` 🔒 | 测试连接 |
| `GET/POST/PUT/DELETE /v1/models[/{id}]` 🔒 | 旧扁平 facade（兼容保留） |

### 4.4 设备、配对与 Grant

| 方法 路径 | 说明 |
|---|---|
| `POST /v1/devices` / `POST /v1/devices/register` 🔒 | 注册设备 |
| `GET /v1/devices` 🔒 | 设备列表（含在线状态） |
| `GET/PUT /v1/devices/{id}/permissions` 🔒 | 设备权限读/写 |
| `POST /v1/devices/{id}/revoke` / `DELETE /v1/devices/{id}` 🔒 | 撤销设备 |
| `POST /v1/devices/{id}/rotate-key` 🔒 | 轮换设备密钥 |
| `POST /v1/devices/{id}/heartbeat` 🔒 | 心跳（在线判定） |
| `POST /v1/devices/{id}/challenge` 🔒 | 发起证明挑战 |
| `POST /v1/devices/{id}/challenge/verify` 🔒 | 验证私钥持有 |
| `POST /v1/devices/{id}/token` 🔒 | 换取设备 token |
| `POST /v1/pairings/start` 🔒 | 生成短时配对码（5 分钟） |
| `POST /v1/pairings/confirm` 🔒 | 确认配对 |
| `POST /v1/grants` 🔒 | 创建定向控制授权 |
| `GET /v1/grants` 🔒 | Grant 列表 |
| `POST /v1/lan/authorize` 🔒 | LAN 授权 |
| `POST /v1/grants/{id}/revoke` / `DELETE` 🔒 | 撤销 Grant |

### 4.5 会话、命令、流式与终端

| 方法 路径 | 说明 |
|---|---|
| `POST /v1/cloud/sessions` 🔒 | 创建云端会话（默认 workspace=default） |
| `POST /v1/cloud/sessions/import` 🔒 | 导入本地会话 |
| `GET /v1/cloud/sessions` 🔒 | 会话列表 |
| `PATCH /v1/cloud/sessions/{id}` 🔒 | 更新会话（标题等） |
| `DELETE /v1/cloud/sessions/{id}` 🔒 | 删除会话 |
| `POST /v1/cloud/sessions/{id}/archive` / `restore` 🔒 | 归档/恢复 |
| `POST /v1/cloud/sessions/{id}/copy` 🔒 | 复制会话 |
| `POST /v1/cloud/sessions/{id}/authority/rotate` / `lease` 🔒 | authority 纪元/租约 |
| `GET /v1/cloud/sessions/{id}/snapshot` 🔒 | 会话快照 |
| `GET /v1/cloud/sessions/{id}/events` 🔒 | 事件投影（支持 after 游标） |
| `GET /v1/cloud/sessions/{id}/approvals` 🔒 | 审批列表 |
| `POST /v1/cloud/sessions/{id}/approvals/{approval_id}/resolve` 🔒 | 解决审批 |
| `POST /v1/cloud/sessions/{id}/commands` 🔒 | 非流式提交命令 |
| `POST /v1/cloud/sessions/{id}/stream` 🔒 | **SSE 流式一轮**（见第 5 节） |
| `POST /v1/cloud/sessions/{id}/terminal` 🔒 | **沙箱终端执行**（见第 6 节） |
| `GET /v1/cloud/sessions/{id}/commands` 🔒 | 命令列表 |
| `GET /v1/cloud/sessions/{id}/commands/{command_id}` 🔒 | 命令状态 |
| `POST /v1/cloud/sessions/{id}/commands/{command_id}/recover` 🔒 | 恢复命令 |

### 4.6 Workspace 文件与备份

| 方法 路径 | 说明 |
|---|---|
| `GET /v1/workspaces` 🔒 | Workspace 列表 |
| `GET /v1/workspaces/{id}/stats` 🔒 | 文件数/字节统计 |
| `GET /v1/workspaces/{id}/capacity` 🔒 | 卷容量 |
| `GET /v1/workspaces/{id}/files` 🔒 | 列文件（prefix/limit） |
| `GET /v1/workspaces/{id}/files/{logical_path:path}` 🔒 | 读文件 |
| `PUT /v1/workspaces/{id}/files/{logical_path:path}` 🔒 | 写文件（原子替换） |
| `DELETE /v1/workspaces/{id}/files/{logical_path:path}` 🔒 | 删除文件 |
| `POST /v1/workspaces/{id}/backups` 🔒 | 创建备份 |
| `GET /v1/workspaces/{id}/backups` 🔒 | 备份列表 |
| `GET /v1/workspaces/{id}/backups/{backup_id}/download` 🔒 | 下载备份 zip |
| `DELETE /v1/workspaces/{id}/backups/{backup_id}` 🔒 | 删除备份 |
| `POST /v1/workspaces/{id}/backups/restore` 🔒 | 恢复备份 |

## 5. SSE 流式一轮（`/stream`）

### 5.1 请求

`POST /v1/cloud/sessions/{session_id}/stream`，请求体（模块级 Pydantic 模型 `StreamCreate`，`extra="forbid"`）：

```json
{
  "input": "5+5=",
  "request_id": "客户端生成的 UUID",
  "model_id": "可选；缺省走 Auto",
  "authorization_mode": "default"
}
```

| 字段 | 规则 |
|---|---|
| `input` | 1–65536 字符 |
| `request_id` | 1–64 字符；同一 session 内幂等，重复提交复用原命令 |
| `model_id` | 可空；空 = Auto，由服务端解析组织默认模型 |
| `authorization_mode` | `default` 或 `full`，仅为意图，不绕过服务端裁决 |

### 5.2 处理流程

1. 校验会话归属（`_owned_session`：session 必须属于当前用户）。
2. 同步插入 running 命令（`_persist_running_command`）：在 `BEGIN IMMEDIATE` 事务中占用 `sessions.next_sequence/next_event_sequence`，写 `commands(status='running')` 与 `command.queued` 事件；相同 `request_id` 复用。
3. 构建模型上下文：`_cloud_history`（有界历史）+ 当前用户消息。
4. 通过 `_open_model_stream` 解析模型的 protocol/base_url/解密 API key，得到 provider 流函数。
5. 在**线程池**中迭代阻塞的 provider SSE，逐块转发，结束后落终态。

### 5.3 SSE 事件格式

`Content-Type: text/event-stream`，每帧 `data: {json}\n\n`：

| `type` | 附加字段 | 语义 |
|---|---|---|
| `reasoning` | `text` | 思考增量（来自 provider `delta.reasoning_content`） |
| `delta` | `text` | 正文增量（来自 `delta.content`） |
| `error` | `message` | 本轮失败 |
| `done` | `status` | 终态：`completed` / `failed` |

provider SSE 在 `reasoning` 段结束、`delta` 开始时把整段 reasoning 计入 `reasoning_parts`；`turn.completed` 事件 payload 带 `output` 与 `reasoning`（字符串数组，每段一轮思考）。

### 5.4 事件循环关键约束（最重要的坑）

provider I/O 全部阻塞。`async def` 中**绝不能直接迭代**阻塞的 httpx 流，否则事件循环卡死、响应头发不出去。正确模式：

```python
from starlette.concurrency import run_in_threadpool, iterate_in_threadpool

session = await run_in_threadpool(_owned_session, db, session_id, user_id)
command_id, sequence = await run_in_threadpool(_persist_running_command, db, ...)
history = await run_in_threadpool(_cloud_history, db, session_id)

def blocking_events():
    stream = _open_model_stream(...)
    for event in stream(messages):
        # 累积 reasoning / answer
        yield event
    # finally: 落终态命令 + turn.completed/failed 事件
    yield {"type": "done", "status": status}

async def event_generator():
    async for event in iterate_in_threadpool(blocking_events()):
        yield _sse(event)

return StreamingResponse(event_generator(), media_type="text/event-stream",
    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```

> Pydantic 请求体模型必须定义在**模块级**。定义在 `create_app()` 内部的嵌套类无法被 FastAPI 解析为 body（表现为 422 `{"loc":["query","payload"]}`）。

## 6. 沙箱终端（`/terminal`）

### 6.1 请求

`POST /v1/cloud/sessions/{session_id}/terminal`，模块级模型 `TerminalExec`（`extra="forbid"`）：

```json
{"command": "ls -la", "cwd": null}
```

- `command`：1–4096 字符。`cwd`：相对根的逻辑路径，空/`.` 表示根目录。

### 6.2 响应

```json
{"code":0,"msg":"success","data":{
  "stdout": "...", "stderr": "...", "exit_code": 0, "cwd": "."
}}
```

`cwd` 是命令执行后相对根的安全路径（任何越界结果都被规整为 `.`）。

### 6.3 安全策略（纵深防御）

1. **命令校验**：拒绝空命令、`\x00`、`shlex` 解析失败。
2. **危险命令**：token 末段命中 `sudo/su/mkfs/dd/shutdown/reboot/halt/mount/umount/chroot/launchctl/systemctl` 即拒绝。
3. **绝对路径**：除重定向 `/dev/null` 外，任何 `/` 开头 token 一律拒绝。
4. **路径越界**：`_escapes_root` 按路径段压栈，`..` 在深度 0 时即判定越界（`../x`、`../../x` 拒绝；`sub/../x` 这类仍在根内的允许）。
5. **cwd 解析**：`resolve_cwd` 用 `os.path.commonpath` 校验解析后真实路径仍在根内。
6. **shell 前缀**：执行脚本覆盖 bash 的 `cd/pushd`，切换后用 `case "$PWD/" in "$ROOT"/*` 校验，越界回滚并报错。
7. **最小环境**：不继承宿主环境，`HOME` 指向根，固定 `PATH` 与 `LANG/TERM/PS1`。
8. **执行约束**：`/bin/bash --noprofile --norc -c`，30 秒超时，输出截断 256 KiB；通过 `__CLOUD_CWD__` 标记行回传真实 cwd。

> 这是**应用层沙箱**：macOS 非特权进程无法 chroot，靠 cwd + 路径策略约束。生产 Linux 应把终端放进以 workspace 为根的容器/chroot，做内核级隔离。

## 7. Root-Jail 算法（Workspace 权威实现）

`Workspace.path(logical_path)` 是文件 API 与终端共同的边界算法：

1. 拒绝空路径、含 `\x00`、含 `\` 或 `:`、以 `/` 开头。
2. 按 `/` 分段，段数 ≤ 32，任何段为 `""`/`.` /`..` 直接拒绝。
3. `candidate = (root / logical_path).resolve(strict=False)`。
4. 用 `os.path.commonpath((root, candidate)) != root` 判定越界。
5. 逐级父目录若为符号链接即拒绝（防 symlink 逃逸）。

构造 Workspace 时从根向上逐级检查 `is_symlink()`（根自身也不能是符号链接）。写入采用“同目录临时文件 + fsync + 原子 `replace` + 目录 fsync”，避免半写；临时文件名形如 `.{name}.*.tmp`，启动时清理残留。

## 8. 关键状态机

### 8.1 Command 状态

```text
queued -> running -> completed
                   \-> failed
running -> waiting_approval -> running
running -> needs_attention | interrupted
```

一个 session 同时只运行一个 turn；命令按 `sequence` 顺序领取。租约 `lease_owner/lease_expires_at` 用于 worker 崩溃恢复：reconciler 周期（`command_lease_seconds/3`）回收过期 running 命令。

### 8.2 Session 状态

`sessions.status`：`running` / `completed` / `archived` 等；`next_sequence`（命令序号）与 `next_event_sequence`（事件序号）在同一事务内单调推进，保证顺序无冲突。

## 9. 安全与秘密边界

- Provider API Key 经 Fernet 加密入库；任何列表/回显/分享/日志只返回 `has_api_key`/掩码，编辑留空表示保留原密钥。
- Master key：生产必须由 `NOTEMELD_CLOUD_SECRET_KEY` 提供（≥32 字符）；开发模式从 `{data_dir}/.cloud-secret-key`（0600）读取一次性生成的本地 key，保证重启后已存凭据仍可解密。
- Token 只存 digest；设备私钥不下发、不展示。
- 面向用户的错误与事件不得包含原始异常栈、密钥、provider payload 或系统提示词。
- catalog discover/test-connection 做 SSRF 防护：非本地（ollama）目标经 DNS 解析后拒绝 loopback/私网地址。

## 10. 前端对接要点（cloud-web）

- 构建：在 `desktop/frontend` 执行 `corepack pnpm run build:cloud-web`（vite 配置 `apps/cloud-web/vite.config.ts`），产物输出到 `dist-cloud-web/`。
- 流式：用原生 `fetch` + `response.body.getReader()`，`TextDecoder` 缓冲后按 `\n\n` 分帧，取 `data:` 行 `JSON.parse` 回调。
- 渲染：思考过程为可折叠面板（默认折叠，展开逐段显示，streaming 时显示“思考中”三点动画）；正文用 Markdown 渲染器（react-markdown + remark-gfm），按 delta 实时拼接。
- 时间：回合时间默认隐藏（`opacity:0`），hover 该回合显示（`opacity:1`）。
- 终端/资源管理器：均调用第 6/4.6 节真实 API，逻辑根为分配文件夹。
