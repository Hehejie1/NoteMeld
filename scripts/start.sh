#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLOUD_PORT="${NOTEMELD_CLOUD_PORT:-8583}"
CLOUD_LOG_DIR="${NOTEMELD_CLOUD_LOG_DIR:-${ROOT_DIR}/cloud/logs}"
CLOUD_PID=""

cleanup() {
  local status=$?
  if [[ -n "${CLOUD_PID}" ]] && kill -0 "${CLOUD_PID}" >/dev/null 2>&1; then
    kill "${CLOUD_PID}" >/dev/null 2>&1 || true
    wait "${CLOUD_PID}" >/dev/null 2>&1 || true
  fi
  exit "${status}"
}
trap cleanup EXIT INT TERM

mkdir -p "${CLOUD_LOG_DIR}"
if lsof -nP -iTCP:"${CLOUD_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "[NoteMeld] cloud port ${CLOUD_PORT} is already in use; reusing it"
else
  echo "[NoteMeld] starting cloud server on http://127.0.0.1:${CLOUD_PORT}"
  "${ROOT_DIR}/scripts/cloud/start.sh" &
  CLOUD_PID=$!
  for _ in {1..45}; do
    if curl -fsS "http://127.0.0.1:${CLOUD_PORT}/ready" >/dev/null 2>&1; then break; fi
    sleep 1
  done
  curl -fsS "http://127.0.0.1:${CLOUD_PORT}/ready" >/dev/null \
    || { tail -n 80 "${CLOUD_LOG_DIR}/cloud.log" >&2 || true; exit 1; }
fi

export VITE_CLOUD_BASE_URL="${VITE_CLOUD_BASE_URL:-http://127.0.0.1:${CLOUD_PORT}}"
echo "[NoteMeld] starting desktop backend and web frontend"
bash "${ROOT_DIR}/scripts/desktop/start.sh"
