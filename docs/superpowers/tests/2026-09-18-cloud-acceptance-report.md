# NoteMeld Cloud acceptance report

## Candidate identity

- Source commit: `88f48833713db998df112d7476c588cb36d85f49`
- Cloud image digest: `sha256:1cc83f6487a9f4ee619ae7b120c083b68ad97f6c9294d9b5f1abbcd39db0d021`
- Runtime endpoint: `http://127.0.0.1:18583`
- Runtime environment: `development` (intentionally not reported as production)
- Agent backend: `canonical-sdk`
- Image inspection: `/app/cloud-web-dist/index.html` and `/opt/notemeld-agent-sdk/libnotemeld_agent.so` are present; the bundled Cloud Web does not contain `/docs/new-product` references.
- Production fail-closed check: starting the image with `NOTEMELD_CLOUD_ENV=production` and incomplete SMTP configuration is rejected before serving traffic (`production requires SMTP-backed OTP delivery`).

## Verified against the candidate

| Area | Evidence | Result |
| --- | --- | --- |
| Cloud readiness | `/ready` reports database, workspace, canonical SDK, commit and image digest | PASS |
| Cloud Web bundle | C01-C06 deep links return the production bundle and do not reference `/docs/new-product` | PASS |
| Real Cloud Web flow | `tests/cloudLiveSmoke.spec.cjs` logs in, exercises C01-C06 controls, saves a model, submits attachments and completes a real Provider turn with no console or API errors | PASS |
| English localization | `tests/cloudEnglishSmoke.spec.cjs` | PASS |
| Cloud backend | `pytest desktop/backend/tests/test_cloud*.py` | 253 PASS, 1 skipped; Redis test run separately |
| Redis Relay | `test_cloud_redis_relay.py` against isolated Redis 7 | PASS |
| SDK/UI contracts | Cloud frontend contracts and `@notemeld/ui-contract`/`@notemeld/ui-web` tests | PASS |
| Crypto/security contracts | Cloud verifier, crypto, E2EE, LAN authorization/transport and security audit tests | 45 PASS |
| Compose packaging | SDK build args and RC metadata forwarding tests | PASS |

## Latest live refresh

- Current live refresh (2026-09-19): rebuilt and restarted `notemeld-cloud-current` from source commit `88f48833713db998df112d7476c588cb36d85f49` using image digest `sha256:1cc83f6487a9f4ee619ae7b120c083b68ad97f6c9294d9b5f1abbcd39db0d021`; `/ready` reports `agent_backend=canonical-sdk`, database/workspace checks `ok`, and the build commit/digest pair.
- Current live smoke (2026-09-19): `tests/cloudLiveSmoke.spec.cjs` passed in `25.7s` after updating the acceptance locator to the live settings label `通用`; it exercised login/access request, model creation/listing, attachment paste/file selection, device/member operations, and a real Provider Agent turn with no console or API errors.
- Current model evidence: the persisted default model displays `凭据已保存`; the older `ark-code-latest` record remains visible but correctly displays `凭据不可解密，请重新保存` and is not used as the default.
- Current Computer Use probe (2026-09-19): `mcp__cua_repl` initialization timed out twice and reset its kernel before a browser surface became available. This is recorded as an environment blocker; no Computer Use PASS is claimed.
- Current runtime hygiene probe (2026-09-19): `/ready` remained healthy after the restart, Cloud container logs contained zero matches for the configured admin password/API-key-shaped patterns, and the data volume contains the dedicated `.cloud-secret-key` plus SQLite files; secret values were not emitted into evidence.
- Current runtime guard tests (2026-09-19): canonical runner, production configuration fail-closed, release-startup guard, and config-sync regression tests passed `39/39`; the image contains both `/opt/notemeld-agent-sdk/libnotemeld_agent.so` and `/app/cloud-web-dist/index.html`. An incomplete production container start exits non-zero before serving traffic.
- Current Cloud backend suite (2026-09-19): all 28 `test_cloud*.py` files passed in three isolated groups: `155 passed`, `23 passed`, and `75 passed, 1 skipped`; the skipped Redis case was then rerun against an isolated Redis 7 container and passed (`254 passed` total, no remaining skips for the Cloud suite).
- Current Web bundle refresh (2026-09-19): `build:cloud-web` passed, all six Cloud frontend contracts passed, and live deep-link probes returned HTTP 200 for login, access-request, workbench, sessions, people, devices, and settings; none of the returned production pages referenced `/docs/new-product`.
- Current C01 OTP probe (2026-09-19): against the running development Cloud, password login, `/v1/auth/me`, verification-code delivery, and verification-code login all returned success; the probe printed no email, code, token, or other secret values. Production OTP behavior remains covered by the no-code-leak backend test.
- Current browser smoke refresh (2026-09-19): corrected the English/live smoke locators to match the current settings navigation label `通用`; English route smoke passed in `8.5s`, and the full real-provider Cloud smoke passed in `26.9s` after the correction.
- Current config-sync live probe (2026-09-19): against the running Cloud API, a unique preference change returned 200, repeating the same idempotency key returned the same successful result, a stale revision returned 409, and deleting the probe key returned 200 with a tombstone visible in the subsequent snapshot. No secret values were printed.
- Current persistence refresh (2026-09-21): without rebuilding or replacing the running container, the real-provider Cloud smoke passed again in `19.6s`, confirming the existing data volume, configured default model, C01-C06 controls, attachment flow, and Agent turn remain usable after the service stayed running.
- Computer Use refresh (2026-09-21): `mcp__cua_repl.getState()` again timed out during kernel/browser initialization and reset the kernel before exposing a browser surface; no CU evidence is claimed.

- Rebuilt `notemeld-cloud:rc-current` from source commit `88f48833713db998df112d7476c588cb36d85f49`.
- Restarted the service on `http://127.0.0.1:18583` using the existing Cloud data volume and no placeholder Provider URL; `/ready` reports the new image digest and canonical SDK backend.
- Canonical bootstrap now depends on the immutable SDK artifact while the per-session Provider is resolved from the authoritative Cloud model registry; an empty bootstrap Provider fails closed instead of calling a fake endpoint.
- Rebalanced the C02 workbench lower grid so the seven-day usage card has a readable desktop width instead of collapsing into a narrow column; the responsive single-column breakpoint remains unchanged.
- Re-ran the live Cloud Web and English smoke suites serially with one worker: `2 passed (41.4s)`; the real Provider turn completed successfully. The Cloud smoke now deletes its temporary no-credential model after the create/list assertion and explicitly requires a configured default for the real turn.
- Fixed acceptance-data hygiene in both live and visual smoke harnesses: device baselines are captured before browser login, and devices registered by the current run are removed afterward. A post-run API audit currently reports one retained browser device, zero Cloud sessions, and two persisted models; repeated acceptance runs no longer accumulate browser devices or sessions.
- Re-ran the corrected real-provider smoke after the baseline-order fix: `1 passed (25.7s)`; the post-run API audit again reports one device, zero sessions, and two models. The browser Computer Use probe still times out while initializing and resets its kernel, so CU evidence remains externally blocked.
- Re-ran the focused live Cloud smoke after that cleanup change: `1 passed (32.2s)`; the shared acceptance account retained only the configured default and the pre-existing unreadable model.
- Rebuilt the visual matrix against the same image digest: 84 actual screenshots, reference comparison, and feature-evidence contracts all passed; comparison remains `PENDING_REVIEW` because the static reference uses a different data state.
- Added a fail-closed repair path for models whose encrypted credential cannot be read: editing now requires a newly entered API Key and shows localized guidance instead of reporting a misleading success.
- Re-captured the dark C03 session evidence. Command status now renders inside the composer with a readable dark-theme status surface; attachment previews remain above the input.
- The visual matrix produced 84 live screenshots for C01-C06 across 1440×960, 1024×768, and 390×844, light/dark themes, and normal/reduced-motion media settings under `/tmp/notemeld-acceptance/cloud-c01-c06/visual-matrix/`.
- A matching 84-case reference matrix was captured from `docs/new-product` and compared against the live screenshots. Reference PNGs are under `/tmp/notemeld-acceptance/cloud-c01-c06/visual-matrix/reference/`; pixel diff PNGs and the comparison manifest are under `/tmp/notemeld-acceptance/cloud-c01-c06/visual-matrix/diff/` and `/tmp/notemeld-acceptance/cloud-c01-c06/visual-matrix/comparison/`.
- The comparison is intentionally `PENDING_REVIEW`: `new-product` is a demo/data-state reference, while the live Cloud has authenticated account, model, session, device, and settings data. The largest observed changed-pixel ratio is recorded in the comparison manifest; this is evidence for design review, not a visual PASS/FAIL gate.
- The comparison manifest is bound to the live candidate commit/image digest and the static preview version; it contains 84 cases and no credential fields.
- `tests/cloudFeatureEvidenceContracts.test.mjs` verifies that every C01-C06 feature ID from `feature-registry.json` has a report row and actual/reference/diff evidence.

## C01-C06 feature matrix

This is intentionally feature-level rather than page-level. The registry currently contains 25 Cloud feature IDs. `Playwright` means the live Cloud Web smoke exercised the control against the running API. `CU` remains `UNVERIFIED` because the native Computer Use browser surface is not available in this environment. `Visual` is `PARTIAL` where the screenshot exists but the reference is a different data state.

| Feature ID | Route / primary control | API-backed automation | Screenshot | CU | Overall |
| --- | --- | --- | --- | --- | --- |
| C01.auth | `/cloud/login`, password login | Playwright PASS | C01 access error | UNVERIFIED | UNVERIFIED |
| C01.access-request | `/cloud/access-request`, submit/review request | Playwright PASS | C01 access error | UNVERIFIED | UNVERIFIED |
| C02.dashboard | `/cloud/workbench`, status/metrics | Playwright PASS | C02 workbench | UNVERIFIED | UNVERIFIED |
| C02.storage | `/cloud/workbench`, Workspace usage | Playwright PASS | C02 workbench | UNVERIFIED | UNVERIFIED |
| C03.session | `/cloud/sessions`, session/event view | Playwright PASS | C03 dark session | UNVERIFIED | UNVERIFIED |
| C03.send-command | session composer / send | Playwright PASS, real Provider turn completed | C03 dark session | UNVERIFIED | UNVERIFIED |
| C03.attachments | add file / paste image preview | Playwright PASS | C03 empty session | UNVERIFIED | UNVERIFIED |
| C03.model | composer model menu | Playwright PASS | C03 empty session | UNVERIFIED | UNVERIFIED |
| C03.permissions | permission menu / default mode | Playwright PASS | C03 empty session | UNVERIFIED | UNVERIFIED |
| C03.create-session | new-session control | Playwright PASS | C03 empty session | UNVERIFIED | UNVERIFIED |
| C03.panels | runtime and summary panel toggles | Playwright PASS | C03 empty session | UNVERIFIED | UNVERIFIED |
| C04.members | `/cloud/people`, member table | Playwright PASS | C04 people | UNVERIFIED | UNVERIFIED |
| C04.requests | people access-request review | Playwright PASS via API + UI state | C04 people | UNVERIFIED | UNVERIFIED |
| C04.invite | add-user modal / invite | Playwright PASS | C04 people | UNVERIFIED | UNVERIFIED |
| C04.member-actions | edit, disable, delete member | Playwright PASS | C04 people | UNVERIFIED | UNVERIFIED |
| C05.devices | `/cloud/devices`, trusted devices/pairing | Playwright PASS | C05 devices | UNVERIFIED | UNVERIFIED |
| C05.manage | device permissions save | Playwright PASS | C05 devices | UNVERIFIED | UNVERIFIED |
| C05.revoke | device revoke | Playwright PASS | C05 devices | UNVERIFIED | UNVERIFIED |
| C05.scope-filter | trusted devices / runtime nodes tabs | Playwright PASS | C05 devices | UNVERIFIED | UNVERIFIED |
| C06.settings | `/cloud/settings`, settings categories | Playwright PASS | C06 security | UNVERIFIED | UNVERIFIED |
| C06.preferences | preference save/sync and language | Playwright PASS | C06 general | UNVERIFIED | UNVERIFIED |
| C06.workspace | workspace files/capacity/backup | Playwright PASS | C06 general | UNVERIFIED | UNVERIFIED |
| C06.security | security settings and organization memory | Playwright PASS | C06 security | UNVERIFIED | UNVERIFIED |
| C06.audits | audit load | Playwright PASS | C06 security | UNVERIFIED | UNVERIFIED |
| C06.categories | settings category navigation | Playwright PASS | C06 model dialog | UNVERIFIED | UNVERIFIED |

## Not yet PASS

- Production HTTPS deployment with real SMTP OTP delivery, S3-compatible backup storage, Redis durable relay and explicit production CORS.
- Official Computer Use browser evidence for every C01-C06 feature ID; the available local automation evidence is Playwright-based.
- Same-state golden screenshot comparison for every required case. The new-product reference/diff set now exists, but it is not a same-state golden and therefore remains pending design review.

These items remain unverified or blocked by external environment requirements. They must not be converted to PASS by changing thresholds, using the static prototype, or running the development container with a production label.
