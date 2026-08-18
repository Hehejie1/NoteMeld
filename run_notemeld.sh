#!/usr/bin/env bash
set -euo pipefail

BACKEND_PORT=8483
FRONTEND_PORT=3015

if [[ "${1:-}" == "--help" ]]; then
  cat <<'EOF'
Usage: ./run_notemeld.sh

Starts NoteMeld in source mode:
- backend: http://127.0.0.1:8483
- mcp:     http://127.0.0.1:8483/mcp
- frontend: http://127.0.0.1:3015

Requirements (auto-installed if missing on macOS with Homebrew):
- python 3.11+
- ffmpeg
- node
- npm
- corepack

Agent SDK:
- set NOTEMELD_AGENT_SDK_WHEEL to the compiled notemeld-agent-sdk wheel
- the wheel is installed into the source-mode virtualenv automatically

After startup:
- open http://127.0.0.1:3015
- configure Trae MCP with url http://127.0.0.1:8483/mcp
- configure an LLM provider in Settings before generating notes
EOF
  exit 0
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
FRONTEND_DIR="${ROOT_DIR}/frontend"
VENV_DIR="${ROOT_DIR}/.venv"
NOTEMELD_RUNTIME_MODE="${NOTEMELD_RUNTIME_MODE:-source-script}"
LOG_DIR="${ROOT_DIR}/logs"
DATA_ROOT="${ROOT_DIR}/vector_db"
BACKEND_LOG="${LOG_DIR}/run_notemeld_backend.log"
FRONTEND_LOG="${LOG_DIR}/run_notemeld_frontend.log"
BACKEND_STAMP="${VENV_DIR}/.backend_deps_installed"
BACKEND_REQUIREMENTS="${BACKEND_DIR}/requirements.txt"
NOTEMELD_AGENT_SDK_WHEEL="${NOTEMELD_AGENT_SDK_WHEEL:-}"

BACKEND_PID=""
FRONTEND_PID=""
BACKEND_STATUS="not started"
PYTHON_BIN=""

log() {
  printf '[NoteMeld] %s\n' "$*"
}

warn() {
  printf '[NoteMeld] WARN: %s\n' "$*" >&2
}

fail() {
  printf '[NoteMeld] ERROR: %s\n' "$*" >&2
  exit 1
}

is_macos() {
  [[ "$(uname)" == "Darwin" ]]
}

cmd_exists() {
  command -v "$1" >/dev/null 2>&1
}

require_cmd() {
  cmd_exists "$1" || fail "Missing required command: $1"
}

brew_install() {
  local pkg="$1"
  if is_macos && cmd_exists brew; then
    log "Installing ${pkg} via Homebrew..."
    brew install "$pkg" || return 1
    return 0
  fi
  return 1
}

fix_expat_path() {
  if is_macos && cmd_exists brew; then
    local expat_lib
    expat_lib="$(brew --prefix expat 2>/dev/null)/lib"
    if [[ -d "${expat_lib}" ]]; then
      export DYLD_LIBRARY_PATH="${expat_lib}:${DYLD_LIBRARY_PATH:-}"
      return 0
    fi
  fi
  return 1
}

python_works() {
  local python_bin="$1"
  local test_venv
  test_venv=$(mktemp -d /tmp/notemeld_python_test_XXXXXX)
  if DYLD_LIBRARY_PATH="${DYLD_LIBRARY_PATH:-}" "${python_bin}" -m venv --without-pip "${test_venv}" >/dev/null 2>&1; then
    if DYLD_LIBRARY_PATH="${DYLD_LIBRARY_PATH:-}" "${test_venv}/bin/python" -c 'import sys; import xml.parsers.expat; sys.exit(0)' >/dev/null 2>&1; then
      rm -rf "${test_venv}"
      return 0
    fi
  fi
  rm -rf "${test_venv}"
  return 1
}

try_python_version() {
  local ver="$1"
  local bin_name="python${ver}"
  if cmd_exists "${bin_name}"; then
    if python_works "${bin_name}"; then
      PYTHON_BIN="${bin_name}"
      log "Found working Python ${ver}"
      return 0
    else
      warn "python${ver} found but broken, skipping..."
    fi
  fi
  return 1
}

find_python() {
  local min_major=3
  local min_minor=11

  try_python_version "3.11" && return 0
  try_python_version "3.12" && return 0
  try_python_version "3.13" && return 0
  try_python_version "3.14" && return 0

  if cmd_exists python3; then
    local version
    version=$(python3 -c 'import sys; print("%d.%d" % (sys.version_info.major, sys.version_info.minor))' 2>/dev/null || echo "0.0")
    local major minor
    major=$(echo "$version" | cut -d. -f1)
    minor=$(echo "$version" | cut -d. -f2)
    if [[ "$major" -ge "$min_major" && "$minor" -ge "$min_minor" ]] || [[ "$major" -gt "$min_major" ]]; then
      if python_works python3; then
        PYTHON_BIN="python3"
        log "Using python3 (${version})"
        return 0
      fi
    fi
  fi

  if is_macos && cmd_exists brew; then
    log "Trying Homebrew for Python ${min_major}.${min_minor}+..."
    if brew install python@3.11 2>/dev/null; then
      if cmd_exists python3.11 && python_works python3.11; then
        PYTHON_BIN="python3.11"
        return 0
      fi
    fi
    warn "python@3.11 install failed or broken, trying python@3.12..."
    if brew install python@3.12 2>/dev/null; then
      if cmd_exists python3.12 && python_works python3.12; then
        PYTHON_BIN="python3.12"
        return 0
      fi
    fi
  fi

  if cmd_exists pyenv; then
    log "Checking pyenv for Python ${min_major}.${min_minor}+..."
    local pyenv_python
    pyenv_python=$(pyenv versions --bare 2>/dev/null | grep -E '^3\.(1[1-9]|[2-9][0-9])\.' | sort -V -r | head -1 || true)
    if [[ -n "$pyenv_python" ]]; then
      local pyenv_bin
      pyenv_bin="$(pyenv prefix "$pyenv_python")/bin/python3"
      if python_works "${pyenv_bin}"; then
        log "Found working pyenv Python ${pyenv_python}"
        PYTHON_BIN="${pyenv_bin}"
        return 0
      fi
    fi

    if is_macos; then
      warn "No working Python found in pyenv. Attempting to install Python 3.11 via pyenv (this may take a while)..."
      if pyenv install 3.11.9 2>/dev/null; then
        PYTHON_BIN="$(pyenv prefix 3.11.9)/bin/python3"
        return 0
      fi
      warn "pyenv install failed"
    fi
  fi

  return 1
}

ensure_node() {
  if cmd_exists node && cmd_exists npm && cmd_exists corepack; then
    return 0
  fi

  if is_macos && cmd_exists brew; then
    log "Installing node via Homebrew..."
    if brew install node 2>/dev/null; then
      corepack enable 2>/dev/null || true
      if cmd_exists node && cmd_exists npm; then
        return 0
      fi
    fi
  fi

  if cmd_exists npm && ! cmd_exists corepack; then
    log "Enabling corepack..."
    npm install -g corepack 2>/dev/null || true
    corepack enable 2>/dev/null || true
  fi

  return 1
}

ensure_ffmpeg() {
  if cmd_exists ffmpeg; then
    return 0
  fi

  if is_macos && cmd_exists brew; then
    log "Installing ffmpeg via Homebrew..."
    if brew install ffmpeg 2>/dev/null; then
      return 0
    fi
  fi

  return 1
}

port_in_use() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

get_port_pids() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null || true
}

kill_port_processes() {
  local port="$1"
  local pids
  pids=$(get_port_pids "$port")
  if [[ -z "$pids" ]]; then
    return 0
  fi
  log "Port ${port} is in use. Killing processes..."
  for pid in $pids; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      log "  Killing PID ${pid}"
      kill "$pid" 2>/dev/null || true
    fi
  done
  sleep 1
  for pid in $pids; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      warn "  PID ${pid} still alive, force killing..."
      kill -9 "$pid" 2>/dev/null || true
    fi
  done
  sleep 0.5
  if port_in_use "$port"; then
    warn "  Port ${port} still in use after kill attempts"
    return 1
  fi
  log "  Port ${port} freed"
  return 0
}

wait_for_url() {
  local url="$1"
  local retries="${2:-60}"
  local sleep_seconds="${3:-2}"

  for ((i=1; i<=retries; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$sleep_seconds"
  done

  return 1
}

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM

  if [[ -n "${FRONTEND_PID}" ]] && kill -0 "${FRONTEND_PID}" >/dev/null 2>&1; then
    kill "${FRONTEND_PID}" >/dev/null 2>&1 || true
    wait "${FRONTEND_PID}" 2>/dev/null || true
  fi

  if [[ -n "${BACKEND_PID}" ]] && kill -0 "${BACKEND_PID}" >/dev/null 2>&1; then
    kill "${BACKEND_PID}" >/dev/null 2>&1 || true
    wait "${BACKEND_PID}" 2>/dev/null || true
  fi

  exit "${exit_code}"
}

trap cleanup EXIT INT TERM
export NOTEMELD_RUNTIME_MODE

log "Checking environment..."

fix_expat_path || true

if ! find_python; then
  fail "Python 3.11+ not found. Please install Python 3.11 or later (try: brew install python@3.11)"
fi
log "Python binary: ${PYTHON_BIN}"
"${PYTHON_BIN}" --version

if ! ensure_ffmpeg; then
  fail "ffmpeg not found and could not be auto-installed. Please install ffmpeg (try: brew install ffmpeg)"
fi
log "ffmpeg: $(ffmpeg -version 2>&1 | head -1)"

if ! ensure_node; then
  fail "node/npm/corepack not found and could not be auto-installed. Please install Node.js (try: brew install node)"
fi
log "node: $(node --version), npm: $(npm --version)"
if cmd_exists corepack; then
  corepack enable 2>/dev/null || true
fi

require_cmd curl
require_cmd lsof

[[ -d "${BACKEND_DIR}" ]] || fail "Backend directory not found: ${BACKEND_DIR}"
[[ -d "${FRONTEND_DIR}" ]] || fail "Frontend directory not found: ${FRONTEND_DIR}"
mkdir -p "${LOG_DIR}" "${DATA_ROOT}/tmp"

if port_in_use "${FRONTEND_PORT}"; then
  warn "Port ${FRONTEND_PORT} is already in use, attempting to free..."
  kill_port_processes "${FRONTEND_PORT}" || fail "Could not free port ${FRONTEND_PORT}"
fi

if [[ ! -f "${ROOT_DIR}/.env" ]]; then
  if [[ -f "${ROOT_DIR}/.env.example" ]]; then
    cp "${ROOT_DIR}/.env.example" "${ROOT_DIR}/.env"
    log "Created .env from .env.example"
  else
    fail "Missing .env.example in repo root"
  fi
fi

if [[ ! -d "${VENV_DIR}" ]]; then
  log "Creating Python virtual environment"
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

if ! "${VENV_DIR}/bin/python" -m pip --version >/dev/null 2>&1; then
  log "Bootstrapping pip in virtual environment"
  "${VENV_DIR}/bin/python" -m ensurepip --upgrade 2>/dev/null || "${PYTHON_BIN}" -m ensurepip --upgrade --root "${VENV_DIR}" 2>/dev/null || {
    warn "ensurepip failed, trying get-pip.py..."
    curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py 2>/dev/null || fail "Cannot bootstrap pip"
    "${VENV_DIR}/bin/python" /tmp/get-pip.py
    rm -f /tmp/get-pip.py
  }
fi

if [[ ! -f "${BACKEND_STAMP}" || "${BACKEND_REQUIREMENTS}" -nt "${BACKEND_STAMP}" ]]; then
  log "Installing backend dependencies"
  "${VENV_DIR}/bin/python" -m pip install --upgrade pip 2>/dev/null || true
  "${VENV_DIR}/bin/python" -m pip install -r "${BACKEND_REQUIREMENTS}"
  touch "${BACKEND_STAMP}"
fi

ensure_agent_sdk() {
  if "${VENV_DIR}/bin/python" -c 'import notemeld_agent_sdk.runtime as sdk_runtime; raise SystemExit(0 if sdk_runtime.SDK_VERSION == "0.1.0" and sdk_runtime.SCHEMA_VERSION == "1" else 1)' >/dev/null 2>&1; then
    return 0
  fi
  [[ -n "${NOTEMELD_AGENT_SDK_WHEEL}" ]] || fail "notemeld-agent-sdk is not installed. Set NOTEMELD_AGENT_SDK_WHEEL to the compiled wheel before starting NoteMeld."
  [[ -f "${NOTEMELD_AGENT_SDK_WHEEL}" ]] || fail "NOTEMELD_AGENT_SDK_WHEEL does not exist: ${NOTEMELD_AGENT_SDK_WHEEL}"
  log "Installing standalone notemeld-agent-sdk from ${NOTEMELD_AGENT_SDK_WHEEL}"
  "${VENV_DIR}/bin/python" -m pip install --disable-pip-version-check --no-deps --force-reinstall "${NOTEMELD_AGENT_SDK_WHEEL}"
  "${VENV_DIR}/bin/python" -c 'import notemeld_agent_sdk.runtime as sdk_runtime; raise SystemExit(0 if sdk_runtime.SDK_VERSION == "0.1.0" and sdk_runtime.SCHEMA_VERSION == "1" else 1)' >/dev/null 2>&1 \
    || fail "Installed notemeld-agent-sdk is incompatible (expected SDK_VERSION=0.1.0 SCHEMA_VERSION=1)"
}

ensure_agent_sdk

log "Preparing default transcriber"
(
  cd "${BACKEND_DIR}"
  export NOTEMELD_DATA_DIR="${DATA_ROOT}"
  export NOTEMELD_LOG_DIR="${LOG_DIR}"
  "${VENV_DIR}/bin/python" "${BACKEND_DIR}/app/services/transcriber_bootstrap.py"
) || warn "Transcriber bootstrap failed, continuing anyway"

if [[ ! -d "${FRONTEND_DIR}/node_modules" ]]; then
  log "Installing frontend dependencies"
  (
    cd "${FRONTEND_DIR}"
    if ! corepack pnpm install --registry https://registry.npmjs.org; then
      if corepack pnpm approve-builds esbuild core-js 2>/dev/null; then
        log "Approved build scripts, retrying install..."
        corepack pnpm install --registry https://registry.npmjs.org
      else
        exit 1
      fi
    fi
  )
fi

rm -f "${BACKEND_LOG}" "${FRONTEND_LOG}"

if port_in_use "${BACKEND_PORT}"; then
  warn "Backend port ${BACKEND_PORT} is already in use, attempting to free..."
  if kill_port_processes "${BACKEND_PORT}"; then
    log "Freed backend port ${BACKEND_PORT}"
  else
    BACKEND_STATUS="startup skipped because port ${BACKEND_PORT} is already in use"
    warn "Backend ${BACKEND_STATUS}"
  fi
fi

if ! port_in_use "${BACKEND_PORT}"; then
  log "Starting backend on ${BACKEND_PORT}"
  (
    cd "${BACKEND_DIR}"
    export NOTEMELD_DATA_DIR="${DATA_ROOT}"
    export NOTEMELD_LOG_DIR="${LOG_DIR}"
    "${VENV_DIR}/bin/python" main.py
  ) >"${BACKEND_LOG}" 2>&1 &
  BACKEND_PID=$!

  if ! wait_for_url "http://127.0.0.1:${BACKEND_PORT}/api/sys_check" 90 2; then
    tail -n 60 "${BACKEND_LOG}" >&2 || true
    warn "Backend failed to become ready; continuing with frontend only"
    BACKEND_STATUS="failed to become ready"
    if kill -0 "${BACKEND_PID}" >/dev/null 2>&1; then
      kill "${BACKEND_PID}" >/dev/null 2>&1 || true
      wait "${BACKEND_PID}" 2>/dev/null || true
    fi
    BACKEND_PID=""
  else
    BACKEND_STATUS="running"
  fi
fi

if port_in_use "${FRONTEND_PORT}"; then
  warn "Frontend port ${FRONTEND_PORT} still in use, retrying..."
  kill_port_processes "${FRONTEND_PORT}" || fail "Could not free port ${FRONTEND_PORT}"
fi

log "Starting frontend on ${FRONTEND_PORT}"
(
  cd "${FRONTEND_DIR}"
  VITE_API_BASE_URL="http://127.0.0.1:${BACKEND_PORT}/api" \
  VITE_SCREENSHOT_BASE_URL="http://127.0.0.1:${BACKEND_PORT}/static/screenshots" \
  corepack pnpm dev --host 0.0.0.0 --port "${FRONTEND_PORT}"
) >"${FRONTEND_LOG}" 2>&1 &
FRONTEND_PID=$!

if ! wait_for_url "http://127.0.0.1:${FRONTEND_PORT}" 90 2; then
  tail -n 60 "${FRONTEND_LOG}" >&2 || true
  fail "Frontend failed to become ready"
fi

log "NoteMeld is running"
log "Frontend: http://127.0.0.1:${FRONTEND_PORT}"
if [[ -n "${BACKEND_PID}" ]]; then
  log "Backend:  http://127.0.0.1:${BACKEND_PORT}"
  log "MCP:      http://127.0.0.1:${BACKEND_PORT}/mcp"
  log "Trae MCP: configure HTTP MCP URL http://127.0.0.1:${BACKEND_PORT}/mcp"
else
  warn "Backend unavailable: ${BACKEND_STATUS}"
fi
log "Next step: open the frontend and configure an LLM provider in Settings"
log "Stop: press Ctrl+C"

if [[ -n "${BACKEND_PID}" ]]; then
  wait "${BACKEND_PID}" "${FRONTEND_PID}"
else
  wait "${FRONTEND_PID}"
fi
