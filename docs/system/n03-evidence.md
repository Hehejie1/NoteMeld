# N03 evidence: plugin installation and runtime control plane

状态：`Implemented`（N03 scope；链接业务插件迁移、candidate 与 N02 adapter 不在本提交）

| Requirement | Evidence | Result |
| --- | --- | --- |
| HTTPS GitHub/Gitee Release resolver | `backend/app/services/plugins/release_resolver.py`; HTTPS/host allowlist, release-page asset lookup, max 3 redirects, 64 MiB limit and bounded timeout | covered |
| Supply-chain verification | `backend/app/services/plugins/verifier.py`; SHA-256, SDK manifest id/version/sdk/license, ZIP path/symlink/install-script rejection, unique 0700 staging | covered |
| Immutable activation | `backend/app/services/plugins/manager.py`; version directories, atomic `os.replace` active pointer, first-install activation, upgrade retains prior versions, rollback audit | covered |
| Permission authority and runtime safety | `authorize_permissions`; manifest requests are not grants; enable starts only discovered active runtime; startup crash is fail-closed and audited | covered |
| API/UI/ready gate | `/api/plugins` wrapper endpoints and `/settings/plugins`; `/api/plugins/ready` reports failed enabled runtimes | covered |
| Fixture regression | `PYTHONPATH=backend pytest -q backend/tests/test_plugin_control_plane.py`; `cd frontend && corepack pnpm test:contracts` | 7 passed；contracts passed |

No install, setup, preinstall or postinstall script is invoked anywhere in the install path. N03 changes do not touch Note adapter, link business implementation, or candidate code.
