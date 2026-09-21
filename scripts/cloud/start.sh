#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# 加载本地开发凭据（cloud/.env 已被 gitignore 忽略）。
if [[ -f "${ROOT_DIR}/cloud/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/cloud/.env"
  set +a
fi

PYTHON_BIN="${NOTEMELD_CLOUD_PYTHON_BIN:-${ROOT_DIR}/.venv/bin/python}"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="${NOTEMELD_CLOUD_PYTHON_BIN:-$(command -v python3)}"
fi

CLOUD_HOST="${NOTEMELD_CLOUD_HOST:-127.0.0.1}"
CLOUD_PORT="${NOTEMELD_CLOUD_PORT:-8583}"
CLOUD_DATA_DIR="${NOTEMELD_CLOUD_DATA_DIR:-${ROOT_DIR}/cloud/data}"
CLOUD_LOG_DIR="${NOTEMELD_CLOUD_LOG_DIR:-${ROOT_DIR}/cloud/logs}"

mkdir -p "${CLOUD_DATA_DIR}" "${CLOUD_LOG_DIR}"
export NOTEMELD_CLOUD_DATA_DIR="${CLOUD_DATA_DIR}"
export NOTEMELD_CLOUD_ADMIN_USERNAME="${NOTEMELD_CLOUD_ADMIN_USERNAME:-hehejie}"
export NOTEMELD_CLOUD_ADMIN_EMAIL="${NOTEMELD_CLOUD_ADMIN_EMAIL:-hehejie@notemeld.local}"
export NOTEMELD_CLOUD_CORS_ORIGINS="${NOTEMELD_CLOUD_CORS_ORIGINS:-http://127.0.0.1:3015,http://localhost:3015}"
: "${NOTEMELD_CLOUD_ADMIN_PASSWORD:?NOTEMELD_CLOUD_ADMIN_PASSWORD must be set}"

if [[ "${NOTEMELD_CLOUD_ENV:-development}" == "production" ]]; then
  : "${NOTEMELD_CLOUD_SECRET_KEY:?NOTEMELD_CLOUD_SECRET_KEY is required in production}"
  : "${NOTEMELD_CLOUD_AGENT_BASE_URL:?NOTEMELD_CLOUD_AGENT_BASE_URL is required in production}"
  : "${NOTEMELD_AGENT_SDK_LIBRARY:?NOTEMELD_AGENT_SDK_LIBRARY is required in production}"
  : "${NOTEMELD_CLOUD_SMTP_HOST:?NOTEMELD_CLOUD_SMTP_HOST is required in production}"
  : "${NOTEMELD_CLOUD_SMTP_SENDER:?NOTEMELD_CLOUD_SMTP_SENDER is required in production}"
  : "${NOTEMELD_CLOUD_INVITE_BASE_URL:?NOTEMELD_CLOUD_INVITE_BASE_URL is required in production}"
  : "${NOTEMELD_CLOUD_S3_BUCKET:?NOTEMELD_CLOUD_S3_BUCKET is required in production}"
  : "${NOTEMELD_CLOUD_S3_ACCESS_KEY_ID:?NOTEMELD_CLOUD_S3_ACCESS_KEY_ID is required in production}"
  : "${NOTEMELD_CLOUD_S3_SECRET_ACCESS_KEY:?NOTEMELD_CLOUD_S3_SECRET_ACCESS_KEY is required in production}"
  : "${NOTEMELD_CLOUD_RELAY_BACKEND:?NOTEMELD_CLOUD_RELAY_BACKEND is required in production}"
  : "${NOTEMELD_CLOUD_RELAY_URL:?NOTEMELD_CLOUD_RELAY_URL is required in production}"
  : "${NOTEMELD_CLOUD_BUILD_COMMIT:?NOTEMELD_CLOUD_BUILD_COMMIT is required in production}"
  : "${NOTEMELD_CLOUD_IMAGE_DIGEST:?NOTEMELD_CLOUD_IMAGE_DIGEST is required in production}"
  if [[ ! -f "${NOTEMELD_AGENT_SDK_LIBRARY}" ]]; then
    echo "NOTEMELD_AGENT_SDK_LIBRARY does not point to a readable native SDK library" >&2
    exit 1
  fi
  if [[ "${CLOUD_HOST}" == "127.0.0.1" || "${CLOUD_HOST}" == "localhost" || "${CLOUD_HOST}" == "::1" ]]; then
    echo "CLOUD_HOST must be externally reachable in production" >&2
    exit 1
  fi
  export NOTEMELD_CLOUD_OTP_DEV_MODE="0"
else
  export NOTEMELD_CLOUD_OTP_DEV_MODE="${NOTEMELD_CLOUD_OTP_DEV_MODE:-1}"
  export NOTEMELD_CLOUD_DEV_OTP_CODE="${NOTEMELD_CLOUD_DEV_OTP_CODE:-888888}"
  export NOTEMELD_CLOUD_SECRET_KEY="${NOTEMELD_CLOUD_SECRET_KEY:-}"
fi

cd "${ROOT_DIR}"
exec env PYTHONPATH="${ROOT_DIR}${PYTHONPATH:+:${PYTHONPATH}}" \
  "${PYTHON_BIN}" -m uvicorn cloud.main:app \
  --host "${CLOUD_HOST}" --port "${CLOUD_PORT}" "$@" \
  >>"${CLOUD_LOG_DIR}/cloud.log" 2>&1
