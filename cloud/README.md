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

The first slice provides an isolated FastAPI control plane, SQLite metadata,
local-disk cloud workspaces, admin/user authentication, cloud-native session
commands, and an in-memory WebSocket relay fixture. The relay intentionally
does not persist payloads and is not a production deployment. WebSocket routing
uses the `RelayBroker` interface (`cloud/relay.py`); the default
`InMemoryRelayBroker` is intentionally single-process. A multi-instance
deployment must provide a transient Pub/Sub implementation behind that
interface before placing multiple workers behind a load balancer.
The service rejects `WEB_CONCURRENCY>1` while `NOTEMELD_CLOUD_RELAY_BACKEND=memory`;
this prevents an unsafe split-brain deployment. Redis/NATS values are reserved
until their transient Pub/Sub adapters are installed and configured.
Install `cloud/requirements.txt` for the optional client-side E2EE primitives
(X25519, Ed25519, HKDF and ChaCha20-Poly1305). The relay never imports or uses
the decrypt path.
Set `NOTEMELD_CLOUD_REQUIRE_DEVICE_PROOF=1` in production to require a recent
Ed25519 device proof before relay connections. The device must obtain a
challenge and sign `notemeld-device-proof-v1\\0<device_id>\\0<challenge>` with
its registered private key before calling the verify endpoint.
Workspace writes are bounded by `NOTEMELD_CLOUD_MAX_WORKSPACE_BYTES` (1 GB by
default) and `NOTEMELD_CLOUD_MAX_WORKSPACE_FILES` (10,000 by default), returning
HTTP 413 when either quota would be exceeded. Workspace ZIP
backups can be created/listed/restored through the `/v1/workspaces/.../backups`
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

For repeatable local deployment, copy the admin variables into an environment
file (see `cloud/.env.example`) and run `docker compose -f cloud/compose.yaml up --build` from the
repository root. The compose healthcheck uses `/ready` and persists data in
the `notemeld-cloud-data` volume.
