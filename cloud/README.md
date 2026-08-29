# NoteMeld Cloud (first backend slice)

Local development:

```bash
NOTEMELD_CLOUD_ADMIN_USERNAME=admin \
NOTEMELD_CLOUD_ADMIN_PASSWORD='change-me-please-123' \
NOTEMELD_CLOUD_MAX_WORKSPACE_BYTES=1000000000 \
PYTHONPATH=. uvicorn cloud.main:app --host 127.0.0.1 --port 8583
```

The first slice provides an isolated FastAPI control plane, SQLite metadata,
local-disk cloud workspaces, admin/user authentication, cloud-native session
commands, and an in-memory WebSocket relay fixture. The relay intentionally
does not persist payloads and is not a production deployment.
Workspace writes are bounded by `NOTEMELD_CLOUD_MAX_WORKSPACE_BYTES` (1 GB by
default) and return HTTP 413 when the quota would be exceeded. Workspace ZIP
backups can be created/listed/restored through the `/v1/workspaces/.../backups`
endpoints; restore is a validated file overlay.
