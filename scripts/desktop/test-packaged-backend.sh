#!/usr/bin/env bash
set -euo pipefail

# Verify the real PyInstaller sidecar, not the source Python entry point.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_BIN="${NOTEMELD_PACKAGED_BACKEND:-${ROOT_DIR}/desktop/src-tauri/bin/backend/notemeld-backend}"
PORT="${NOTEMELD_PACKAGED_PORT:-18990}"
TIMEOUT_SECONDS="${NOTEMELD_PACKAGED_TIMEOUT:-180}"
SMOKE_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/notemeld-packaged-smoke.XXXXXX")"
PID=""

cleanup() {
  if [[ -n "${PID}" ]] && kill -0 "${PID}" >/dev/null 2>&1; then
    kill "${PID}" >/dev/null 2>&1 || true
    pkill -P "${PID}" >/dev/null 2>&1 || true
    wait "${PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

[[ -x "${BACKEND_BIN}" ]] || {
  echo "packaged backend is missing or not executable: ${BACKEND_BIN}" >&2
  exit 2
}

mkdir -p \
  "${SMOKE_ROOT}/data/uploads" \
  "${SMOKE_ROOT}/data/static/screenshots" \
  "${SMOKE_ROOT}/data/chroma" \
  "${SMOKE_ROOT}/data/models" \
  "${SMOKE_ROOT}/data/tmp" \
  "${SMOKE_ROOT}/logs"

env \
  NOTEMELD_DATA_DIR="${SMOKE_ROOT}/data" \
  NOTEMELD_LOG_DIR="${SMOKE_ROOT}/logs" \
  BACKEND_HOST=127.0.0.1 \
  BACKEND_PORT="${PORT}" \
  NOTEMELD_RUNTIME_MODE=desktop \
  "${BACKEND_BIN}" >"${SMOKE_ROOT}/logs/backend.log" 2>&1 &
PID=$!

for _ in $(seq 1 "${TIMEOUT_SECONDS}"); do
  if health="$(curl -fsS --max-time 2 "http://127.0.0.1:${PORT}/api/sys_check" 2>/dev/null)"; then
    printf 'PACKAGED_BACKEND_HEALTH_OK\n%s\n' "${health}"
    descriptor="${SMOKE_ROOT}/data/run/agent-runtime.json"
    [[ -s "${descriptor}" ]] || {
      echo "packaged backend is healthy but Agent runtime descriptor is missing: ${descriptor}" >&2
      exit 1
    }
    deploy_status="${SMOKE_ROOT}/deploy-status.json"
    curl --fail --silent --show-error --max-time 5 \
      "http://127.0.0.1:${PORT}/api/deploy_status" >"${deploy_status}"
    python3 - "${descriptor}" "${deploy_status}" <<'PY'
import json
import sys
from pathlib import Path

descriptor = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
status = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
if not isinstance(descriptor.get("pid"), int) or descriptor["pid"] <= 0:
    raise SystemExit("Agent runtime descriptor has no valid pid")
if descriptor.get("sdk_version") != "0.1.0" or descriptor.get("abi_version") != 1:
    raise SystemExit("Agent runtime descriptor has an unexpected SDK identity")
data = status.get("data")
if not isinstance(data, dict):
    raise SystemExit("deploy_status response has no data object")
if data.get("backend", {}).get("status") != "running":
    raise SystemExit("deploy_status backend is not running")
if data.get("mcp", {}).get("status") != "running":
    raise SystemExit("deploy_status MCP is not running")
PY
    echo "PACKAGED_BACKEND_RUNTIME_OK"
    exit 0
  fi
  if ! kill -0 "${PID}" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo "packaged backend did not become healthy within ${TIMEOUT_SECONDS}s" >&2
tail -80 "${SMOKE_ROOT}/logs/backend.log" >&2 || true
exit 1
