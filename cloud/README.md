# NoteMeld Cloud (first backend slice)

Local development:

```bash
NOTEMELD_CLOUD_ADMIN_USERNAME=admin \
NOTEMELD_CLOUD_ADMIN_PASSWORD='change-me-please-123' \
NOTEMELD_CLOUD_SECRET_KEY='replace-with-a-long-random-secret' \
NOTEMELD_CLOUD_MAX_WORKSPACE_BYTES=1000000000 \
NOTEMELD_CLOUD_MAX_WORKSPACE_FILES=10000 \
NOTEMELD_CLOUD_AGENT_MAX_RETRIES=2 \
NOTEMELD_CLOUD_RELAY_MAX_FRAME_BYTES=262144 \
NOTEMELD_CLOUD_CORS_ORIGINS='https://app.example.com' \
PYTHONPATH=. uvicorn cloud.main:app --host 127.0.0.1 --port 8583
```

验证码默认使用开发模式，固定返回可配置的 `dev_code`（默认 `888888`）。生产环境设置
`NOTEMELD_CLOUD_OTP_DEV_MODE=0`，并配置
`NOTEMELD_CLOUD_SMTP_HOST`、`NOTEMELD_CLOUD_SMTP_PORT`、
`NOTEMELD_CLOUD_SMTP_SENDER`；可选配置 SMTP 用户名、密码和
`NOTEMELD_CLOUD_SMTP_STARTTLS`。生产响应不会返回验证码，邮件发送失败时
验证码会立即失效并返回 503。

管理员邀请在生产模式下也通过同一 SMTP 适配器发送。配置
`NOTEMELD_CLOUD_INVITE_BASE_URL` 为公开 Cloud 前端地址（例如
`https://app.example.com`）；邮件链接进入 `/invite/<token>`，服务端只保存
token 摘要，创建邀请接口不会返回原始 token。开发 OTP 模式仍返回一次性邀请
token，便于本地 smoke test；SMTP 投递失败会撤销邀请并返回 503。

Workspace 备份开发环境默认写入 Cloud 数据目录下的本地文件系统。生产环境设置
`NOTEMELD_CLOUD_BACKUP_STORAGE=s3`，并配置 `NOTEMELD_CLOUD_S3_BUCKET` 及 S3
兼容服务的 endpoint、region 和凭证；SQLite 仅保存备份索引，ZIP 内容由对象存储负责。
同一账号可以保存多个 Agent Provider/模型配置，并通过用户偏好或管理员组织偏好选择默认模型。

生产部署必须设置 `NOTEMELD_CLOUD_ENV=production`。启动校验会拒绝开发验证码、
缺失 OpenAI-compatible Agent Provider、local backup、memory relay、未启用设备
签名证明、非 HTTPS 邀请地址或未显式配置 CORS 的配置，避免 Cloud 在生产中静默
退回 deterministic runner 或单进程内存状态。

The first slice provides an isolated FastAPI control plane, SQLite metadata,
local-disk cloud workspaces, admin/user authentication, cloud-native session
commands, and an ephemeral WebSocket relay. The default in-memory relay is a
single-process fixture; a multi-instance deployment can set
`NOTEMELD_CLOUD_RELAY_BACKEND=redis` and `NOTEMELD_CLOUD_RELAY_URL` to use the
transient Redis Pub/Sub adapter. Redis only carries ephemeral frame publications
and short-lived presence markers; it does not persist payloads. The service
rejects `WEB_CONCURRENCY>1` while using the memory backend, preventing an
unsafe split-brain deployment. NATS remains reserved until a compatible
adapter is added.

For a two-worker deployment, start Redis and configure the service before
launching Uvicorn workers:

```bash
NOTEMELD_CLOUD_RELAY_BACKEND=redis \
NOTEMELD_CLOUD_RELAY_URL='rediss://redis.example.internal:6380/0' \
WEB_CONCURRENCY=2 \
uvicorn cloud.main:app --host 0.0.0.0 --port 8583
```

Use `rediss://` for a remote Redis instance and restrict its network access to
the cloud workers. Delivery acknowledgements are bounded by a short timeout;
a missing acknowledgement is reported as an offline/failed delivery.
Install `cloud/requirements.txt` for the cloud runtime and device-proof cryptography.
Desktop/Python client-side E2EE (X25519, Ed25519, HKDF and AES-256-GCM)
lives in `backend/app/cloud_sync/e2ee.py`; the cloud service does not import the
desktop module or hold session keys. The relay never imports or uses the decrypt
path.
LAN-first clients do not forward that bearer to a `ws://` peer. A configured
Host uses its bound device token over HTTPS with `POST /v1/lan/authorize` to
obtain a maximum 60-second controller public-key/Grant assertion, then verifies
the controller's one-time Ed25519 LAN challenge locally. Direct command frames
remain AES-GCM encrypted; cloud relay fallback is still used when LAN
authentication or reachability fails.
Set `NOTEMELD_CLOUD_REQUIRE_DEVICE_PROOF=1` in production to require a recent
Ed25519 device proof before relay connections. The device must obtain a
challenge and sign `notemeld-device-proof-v1\\0<device_id>\\0<challenge>` with
its registered private key before calling the verify endpoint.
After successful proof, `POST /v1/devices/{device_id}/token` exchanges the
account bearer for a short-lived, least-privilege `device-api` bearer. The raw
device token is returned once and only its digest is stored. Revoking a device
atomically revokes all bearers bound to that device. This first slice proves
key possession at issuance; per-request DPoP signatures remain a later
hardening step, so TLS and platform secure token storage are still mandatory.
The exchange revokes its source account token by default so the target device
does not retain a reusable bootstrap credential. A separate trusted management
client may explicitly retain its source token when provisioning another device.
Workspace writes are bounded by `NOTEMELD_CLOUD_MAX_WORKSPACE_BYTES` (1 GB by
default) and `NOTEMELD_CLOUD_MAX_WORKSPACE_FILES` (10,000 by default), returning
HTTP 413 when either quota would be exceeded. Workspace ZIP
backups can be created/listed/restored/deleted through the `/v1/workspaces/.../backups`
endpoints; restore is a validated file overlay.

`POST /v1/cloud/sessions/import` creates a new cloud-native session from an
explicitly allowlisted local snapshot. It validates the registered source
device, request idempotency, sensitive configuration keys, file paths,
Base64 content, declared size and SHA-256 before atomically publishing the
workspace and metadata. Local-only paths such as `.env`, private-key files,
credential/secret files, VCS metadata, and `skills/`, `plugins/`, or
`applications/` packages are rejected rather than uploaded. Skill, plugin and
Application package fields are also not part of the accepted schema.

Cloud-native commands use `CloudAgentRunner`. Set the optional
`NOTEMELD_CLOUD_AGENT_BASE_URL`, model and API key variables to call an
OpenAI-compatible `/chat/completions` provider. With no base URL, the service
uses an explicit deterministic runner for protocol smoke tests; that fallback
is not an LLM deployment and should not be used as a production configuration.
When a provider is configured, the runner may list and read UTF-8 files from
the current session workspace. Mutation tools are approval-gated and are never
executed implicitly.
Write/delete tools are exposed only as approval-producing capabilities. They
never mutate the workspace until an authorized caller resolves the approval as
`approved`; the approval endpoint then executes through the same safe resolver.
Provider API keys are accepted only when `NOTEMELD_CLOUD_SECRET_KEY` is set.
Keep this key stable across restarts and backups; the administrator password is
never reused as an encryption master key.

Container build/run from the NoteMeld repository root:

```bash
docker build -f cloud/Dockerfile -t notemeld-cloud .
docker run --rm -p 8583:8583 \
  -e NOTEMELD_CLOUD_ADMIN_USERNAME=admin \
  -e NOTEMELD_CLOUD_ADMIN_PASSWORD='change-me-please-123' \
  -v notemeld-cloud-data:/var/lib/notemeld-cloud \
  notemeld-cloud
```

For the bundled two-worker relay profile, set
`NOTEMELD_CLOUD_RELAY_BACKEND=redis`,
`NOTEMELD_CLOUD_RELAY_URL=redis://redis:6379/0`, and
`WEB_CONCURRENCY=2` in the compose environment, then run:

```bash
docker compose -f cloud/compose.yaml --profile relay up --build
```

The bundled Redis profile disables Redis persistence because relay payloads are
ephemeral by design; use a separately managed TLS Redis service when durable
infrastructure or high availability is required.

For repeatable local deployment, copy the admin variables into an environment
file (see `cloud/.env.example`) and run `docker compose -f cloud/compose.yaml up --build` from the
repository root. The compose healthcheck uses `/ready` and persists data in
the `notemeld-cloud-data` volume.

移动端 Cloud-native 纵向烟测：先启动 Cloud，再执行以下命令。脚本使用与
Android/iOS 相同的 HTTP 顺序，覆盖登录、设备注册与 heartbeat、创建会话、提交命令、
轮询命令状态、读取事件游标和读取快照；不会输出 bearer token 或密码。

```bash
NOTEMELD_CLOUD_ADMIN_USERNAME=admin \
NOTEMELD_CLOUD_ADMIN_PASSWORD='change-me-please-123' \
python3 scripts/cloud/smoke_mobile_cloud.py \
  --base-url http://127.0.0.1:8583
```

成功时输出脱敏 JSON，包含 `session_id`、终态 `command_status`、`snapshot_seq`
和事件类型。该脚本适合接入 Cloud 部署后的 smoke gate；移动端运行时仍负责
保存 session/event cursor，并从 `/v1/sessions/{id}/events?after=N` 增量同步。
# Cloud layout

云端 FastAPI 服务的源码全部位于本目录。`frontend` 是桌面 React 前端的唯一源码入口映射，用于让云端网页复用同一套页面与服务契约，避免复制和分叉。
