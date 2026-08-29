# NoteMeld Cloud (first backend slice)

Local development:

```bash
NOTEMELD_CLOUD_ADMIN_USERNAME=admin \
NOTEMELD_CLOUD_ADMIN_PASSWORD='change-me-please-123' \
NOTEMELD_CLOUD_MAX_WORKSPACE_BYTES=1000000000 \
NOTEMELD_CLOUD_MAX_WORKSPACE_FILES=10000 \
NOTEMELD_CLOUD_CORS_ORIGINS='https://app.example.com' \
PYTHONPATH=. uvicorn cloud.main:app --host 127.0.0.1 --port 8583
```

The first slice provides an isolated FastAPI control plane, SQLite metadata,
local-disk cloud workspaces, admin/user authentication, cloud-native session
commands, and an in-memory WebSocket relay fixture. The relay intentionally
does not persist payloads and is not a production deployment.
Install `cloud/requirements.txt` for the optional client-side E2EE primitives
(X25519, Ed25519, HKDF and ChaCha20-Poly1305). The relay never imports or uses
the decrypt path.
Workspace writes are bounded by `NOTEMELD_CLOUD_MAX_WORKSPACE_BYTES` (1 GB by
default) and return HTTP 413 when the quota would be exceeded. Workspace ZIP
backups can be created/listed/restored through the `/v1/workspaces/.../backups`
endpoints; restore is a validated file overlay.

`POST /v1/cloud/sessions/import` creates a new cloud-native session from an
explicitly allowlisted local snapshot. It validates the registered source
device, request idempotency, sensitive configuration keys, file paths,
Base64 content, declared size and SHA-256 before atomically publishing the
workspace and metadata. Skill, plugin and Application package fields are not
part of the accepted schema.

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
