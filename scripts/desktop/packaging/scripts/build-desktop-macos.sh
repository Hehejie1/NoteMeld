#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
TARGET_DIR="${ROOT_DIR}/desktop/src-tauri/target"
LOG_DIR="${ROOT_DIR}/desktop/logs/packaging"
LOG_FILE="${LOG_DIR}/build-desktop-macos-$(date +%Y%m%d-%H%M%S).log"
LOCK_DIR="${TARGET_DIR}/.build-desktop-macos.lock"
DIST_BIN="${ROOT_DIR}/dist/notemeld-backend"
STAGED_BACKEND="${ROOT_DIR}/desktop/src-tauri/bin/backend/notemeld-backend"
STAGED_FFMPEG="${ROOT_DIR}/desktop/src-tauri/resources/ffmpeg/ffmpeg-runtime-macos.zip"
VERSION="$(
  ROOT_DIR="${ROOT_DIR}" "${ROOT_DIR}/.venv/bin/python3" - <<'PY'
import json
import os
from pathlib import Path

root = Path(os.environ["ROOT_DIR"])
config = json.loads((root / "desktop" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
print(config["version"])
PY
)"
TARGET_ARCH="${NOTEMELD_TARGET_ARCH:-$("${ROOT_DIR}/.venv/bin/python3" - <<'PY'
import platform
print(platform.machine())
PY
)}"

case "${TARGET_ARCH}" in
  arm64|aarch64)
    DMG_SUFFIX="aarch64"
    TAURI_TARGET_TRIPLE="aarch64-apple-darwin"
    export RUSTUP_TOOLCHAIN="stable-aarch64-apple-darwin"
    ;;
  x86_64|amd64)
    DMG_SUFFIX="x64"
    TAURI_TARGET_TRIPLE="x86_64-apple-darwin"
    export RUSTUP_TOOLCHAIN="stable-x86_64-apple-darwin"
    ;;
  *)
    DMG_SUFFIX="${TARGET_ARCH}"
    TAURI_TARGET_TRIPLE="${TARGET_ARCH}-apple-darwin"
    ;;
esac

TARGET_OUTPUT_DIR="${TARGET_DIR}/${TAURI_TARGET_TRIPLE}/release"
APP_PATH="${TARGET_OUTPUT_DIR}/bundle/macos/NoteMeld.app"
DMG_DIR="${TARGET_OUTPUT_DIR}/bundle/dmg"
DMG_STAGE_DIR="${DMG_DIR}/stage"
DESKTOP_BIN="${TARGET_OUTPUT_DIR}/notemeld-desktop"
DMG_PATH="${DMG_DIR}/NoteMeld_${VERSION}_${DMG_SUFFIX}.dmg"

mkdir -p "${TARGET_DIR}" "${LOG_DIR}"
if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  echo "another desktop macOS build is already running; lock=${LOCK_DIR}" >&2
  exit 1
fi
export PATH="${HOME}/.cargo/bin:${PATH}"
if [[ -z "${TAURI_SIGNING_PRIVATE_KEY:-}" && -z "${TAURI_SIGNING_PRIVATE_KEY_PATH:-}" ]]; then
  DEFAULT_UPDATER_KEY="${HOME}/.tauri/notemeld-updater.key"
  if [[ -f "${DEFAULT_UPDATER_KEY}" ]]; then
    export TAURI_SIGNING_PRIVATE_KEY_PATH="${DEFAULT_UPDATER_KEY}"
    export TAURI_SIGNING_PRIVATE_KEY="$(<"${DEFAULT_UPDATER_KEY}")"
  fi
fi

cleanup() {
  local rc=$?
  rm -rf "${LOCK_DIR}" "${DMG_STAGE_DIR}"
  if [[ ${rc} -ne 0 ]]; then
    echo "[notemeld] status=failed exit_code=${rc} log=${LOG_FILE}" >&2
  else
    echo "[notemeld] status=success log=${LOG_FILE}"
  fi
}

trap cleanup EXIT
if [[ -t 1 ]]; then
  exec > >(tee -a "${LOG_FILE}") 2>&1
else
  exec >> "${LOG_FILE}" 2>&1
fi

echo "[notemeld] log=${LOG_FILE}"
cd "${ROOT_DIR}"
echo "[notemeld] step=backend"
bash "${ROOT_DIR}/scripts/desktop/packaging/scripts/build-backend-macos.sh"
if [[ ! -f "${DIST_BIN}" ]]; then
  echo "expected backend binary not found at ${DIST_BIN}" >&2
  exit 1
fi
if [[ ! -x "${STAGED_BACKEND}" ]]; then
  echo "expected staged backend binary not found at ${STAGED_BACKEND}" >&2
  exit 1
fi
if [[ ! -f "${STAGED_FFMPEG}" ]]; then
  echo "expected staged ffmpeg archive not found at ${STAGED_FFMPEG}" >&2
  exit 1
fi

cd "${ROOT_DIR}/desktop"
if [[ -n "${TAURI_SIGNING_PRIVATE_KEY:-}" || -n "${TAURI_SIGNING_PRIVATE_KEY_PATH:-}" ]]; then
  TAURI_CONFIG_OVERRIDE_ARGS=(--config '{"bundle":{"createUpdaterArtifacts":true}}')
  echo "[notemeld] updater-signing=enabled"
else
  TAURI_CONFIG_OVERRIDE_ARGS=(--config '{"bundle":{"createUpdaterArtifacts":false}}')
  echo "[notemeld] updater-signing=disabled"
fi

echo "[notemeld] step=clean"
rm -rf "${TARGET_OUTPUT_DIR}/bundle"
rm -f "${DMG_PATH}"

echo "[notemeld] step=tauri-build"
corepack pnpm tauri build --no-bundle --target "${TAURI_TARGET_TRIPLE}" "${TAURI_CONFIG_OVERRIDE_ARGS[@]}"
if [[ ! -x "${DESKTOP_BIN}" ]]; then
  echo "expected desktop binary not found at ${DESKTOP_BIN}" >&2
  exit 1
fi

echo "[notemeld] step=tauri-bundle"
corepack pnpm tauri bundle --bundles app --target "${TAURI_TARGET_TRIPLE}" "${TAURI_CONFIG_OVERRIDE_ARGS[@]}"
if [[ ! -x "${DESKTOP_BIN}" ]]; then
  echo "expected desktop binary not found at ${DESKTOP_BIN}" >&2
  exit 1
fi

if [[ ! -d "${APP_PATH}" ]]; then
  echo "expected bundled app not found at ${APP_PATH}" >&2
  exit 1
fi

echo "[notemeld] step=codesign-app"
CODESIGN_IDENTITY="${NOTEMELD_CODESIGN_IDENTITY:--}"
if [[ "${CODESIGN_IDENTITY}" == "-" ]]; then
  codesign --force --deep --sign - --timestamp=none "${APP_PATH}"
else
  codesign --force --deep --options runtime --timestamp --sign "${CODESIGN_IDENTITY}" "${APP_PATH}"
fi
codesign --verify --deep --strict --verbose=4 "${APP_PATH}"
if ! spctl -a -vv --type execute "${APP_PATH}"; then
  echo "[notemeld] warning=gatekeeper-rejected identity=${CODESIGN_IDENTITY}" >&2
  echo "[notemeld] warning=installing without Apple notarization may require right-click Open or removing quarantine" >&2
fi

echo "[notemeld] step=dmg"
mkdir -p "${DMG_DIR}"
rm -rf "${DMG_STAGE_DIR}"
mkdir -p "${DMG_STAGE_DIR}"
cp -R "${APP_PATH}" "${DMG_STAGE_DIR}/NoteMeld.app"
ln -s /Applications "${DMG_STAGE_DIR}/Applications"
hdiutil create -volname NoteMeld -srcfolder "${DMG_STAGE_DIR}" -ov -format UDZO -fs HFS+ "${DMG_PATH}"
hdiutil verify "${DMG_PATH}"

shopt -s nullglob
DMG_FILES=("${DMG_DIR}"/*.dmg)
shopt -u nullglob
if [[ ${#DMG_FILES[@]} -eq 0 ]]; then
  echo "expected dmg artifact not found in ${DMG_DIR}" >&2
  exit 1
fi

echo "[notemeld] artifact.app=${APP_PATH}"
printf '[notemeld] artifact.dmg=%s\n' "${DMG_FILES[@]}"
