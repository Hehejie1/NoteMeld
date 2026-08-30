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
commands, and an ephemeral WebSocket relay. The default in-memory relay is a
single-process fixture; a multi-instance deployment can set
`NOTEMELD_CLOUD_RELAY_BACKEND=redis` and `NOTEMELD_CLOUD_RELAY_URL` to use the
transient Redis Pub/Sub adapter. Redis only carries ephemeral frame publications
and short-lived presence markers; it does not persist payloads. The service
rejects `WEB_CONCURRENCY>1` while using the memory backend, preventing an
unsafe split-brain deployment. NATS remains reserved until a compatible
adapter is added.
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
