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
