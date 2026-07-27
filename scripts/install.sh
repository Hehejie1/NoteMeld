#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${NOTEMELD_REPO_URL:-https://github.com/Hehejie1/NoteMeld.git}"
REPO_BRANCH="${NOTEMELD_REPO_BRANCH:-main}"

INSTALL_ROOT="${NOTEMELD_HOME:-$HOME/.notemeld}"
APP_DIR="${INSTALL_ROOT}/app"
DATA_DIR="${INSTALL_ROOT}/data"
LOG_DIR="${INSTALL_ROOT}/logs"
MODEL_DIR="${INSTALL_ROOT}/models"
CONFIG_DIR="${INSTALL_ROOT}/config"
BIN_DIR="${NOTEMELD_BIN_DIR:-$HOME/.local/bin}"
CLI_PATH="${BIN_DIR}/notemeld"

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

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

detect_shell_rc() {
  case "${SHELL:-}" in
    */zsh) printf '%s\n' "$HOME/.zshrc" ;;
    */bash) printf '%s\n' "$HOME/.bashrc" ;;
    *) printf '%s\n' "$HOME/.profile" ;;
  esac
}

ensure_path() {
  mkdir -p "$BIN_DIR"

  case ":${PATH}:" in
    *":${BIN_DIR}:"*) return 0 ;;
  esac

  local rc_file
  rc_file="$(detect_shell_rc)"
  touch "$rc_file"

  if ! grep -q 'export PATH="$HOME/.local/bin:$PATH"' "$rc_file" 2>/dev/null; then
    {
      printf '\n'
      printf '# NoteMeld CLI\n'
      printf 'export PATH="$HOME/.local/bin:$PATH"\n'
    } >> "$rc_file"
  fi

  warn "${BIN_DIR} is not in PATH yet."
  warn "Restart your terminal or run: source ${rc_file}"
}

install_repo() {
  mkdir -p "$INSTALL_ROOT" "$DATA_DIR" "$LOG_DIR" "$MODEL_DIR" "$CONFIG_DIR"

  if [[ -d "$APP_DIR/.git" ]]; then
    log "Updating existing NoteMeld repository"
    git -C "$APP_DIR" fetch origin "$REPO_BRANCH"
    git -C "$APP_DIR" checkout "$REPO_BRANCH"
    git -C "$APP_DIR" pull --ff-only origin "$REPO_BRANCH"
    return 0
  fi

  if [[ -e "$APP_DIR" ]]; then
    fail "${APP_DIR} exists but is not a git repository. Move it away and retry."
  fi

  log "Cloning NoteMeld from ${REPO_URL}"
  git clone --branch "$REPO_BRANCH" "$REPO_URL" "$APP_DIR"
}

install_backend() {
  log "Installing backend dependencies"

  cd "$APP_DIR"

  if [[ ! -d ".venv" ]]; then
    python3.11 -m venv .venv
  fi

  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r backend/requirements.txt
}

install_frontend() {
  log "Installing frontend dependencies"

  cd "$APP_DIR/frontend"
  corepack enable
  corepack pnpm install --registry https://registry.npmjs.org
}

init_env() {
  cd "$APP_DIR"

  if [[ ! -f ".env" && -f ".env.example" ]]; then
    cp .env.example .env
    log "Created ${APP_DIR}/.env from .env.example"
  fi
}

install_cli() {
  mkdir -p "$BIN_DIR"

  cat > "$CLI_PATH" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

export NOTEMELD_HOME="${NOTEMELD_HOME:-$HOME/.notemeld}"
exec "$NOTEMELD_HOME/app/scripts/notemeld" "$@"
EOF

  chmod +x "$CLI_PATH"
  log "Installed CLI at ${CLI_PATH}"
}

main() {
  log "Installing NoteMeld"

  require_cmd git
  require_cmd curl
  require_cmd python3.11
  require_cmd node
  require_cmd corepack
  require_cmd ffmpeg

  ensure_path
  install_repo
  install_backend
  install_frontend
  init_env
  install_cli

  log "Install complete."
  log "Run: notemeld"

  if ! command -v notemeld >/dev/null 2>&1; then
    warn "If 'notemeld' is not found, restart your terminal or run: source $(detect_shell_rc)"
  fi
}

main "$@"
