#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${NOTEMELD_PYTHON_BIN:-${ROOT_DIR}/.venv/bin/python3}"
DIST_BIN="${ROOT_DIR}/dist/notemeld-backend"
STAGE_DIR="${ROOT_DIR}/desktop/src-tauri/bin/backend"
STAGE_BIN="${STAGE_DIR}/notemeld-backend"
WINDOWS_STAGE_BIN="${STAGE_DIR}/notemeld-backend.exe"
FFMPEG_STAGE_DIR="${ROOT_DIR}/desktop/src-tauri/resources/ffmpeg"
FFMPEG_ARCHIVE="${FFMPEG_STAGE_DIR}/ffmpeg-runtime-macos.zip"
FFMPEG_SOURCE_DIR="${FFMPEG_BIN_PATH:-}"
PORTABLE_FFMPEG_SOURCE_DIR="${NOTEMELD_PORTABLE_FFMPEG_DIR:-${FFMPEG_STAGE_DIR}/macos-portable}"

validate_ffmpeg_runtime() {
  local binary
  for binary in ffmpeg ffprobe; do
    "${FFMPEG_SOURCE_DIR}/${binary}" -version >/dev/null
    if [[ "${NOTEMELD_SKIP_PORTABILITY_CHECK:-0}" == "1" ]]; then
      echo "skipping portability check (NOTEMELD_SKIP_PORTABILITY_CHECK=1)"
      return 0
    fi
    if otool -L "${FFMPEG_SOURCE_DIR}/${binary}" | grep -E '/usr/local/Cellar|/usr/local/opt|/opt/homebrew' >/dev/null; then
      echo "refusing non-portable ${binary}: Homebrew dylib dependency detected" >&2
      otool -L "${FFMPEG_SOURCE_DIR}/${binary}" >&2
      exit 1
    fi
  done
}

if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

if [[ -z "${FFMPEG_SOURCE_DIR}" ]]; then
  if [[ -x "${PORTABLE_FFMPEG_SOURCE_DIR}/ffmpeg" && -x "${PORTABLE_FFMPEG_SOURCE_DIR}/ffprobe" ]]; then
    FFMPEG_SOURCE_DIR="${PORTABLE_FFMPEG_SOURCE_DIR}"
  else
    FFMPEG_BIN="$(command -v ffmpeg || true)"
    if [[ -n "${FFMPEG_BIN}" ]]; then
      FFMPEG_SOURCE_DIR="$(dirname "${FFMPEG_BIN}")"
    fi
  fi
fi

if [[ -z "${FFMPEG_SOURCE_DIR}" || ! -x "${FFMPEG_SOURCE_DIR}/ffmpeg" || ! -x "${FFMPEG_SOURCE_DIR}/ffprobe" ]]; then
  echo "expected ffmpeg and ffprobe in FFMPEG_BIN_PATH or PATH before desktop packaging" >&2
  exit 1
fi
validate_ffmpeg_runtime

cd "${ROOT_DIR}"
rm -rf "${ROOT_DIR}/build"
rm -f "${DIST_BIN}"
NOTEMELD_ROOT_DIR="${ROOT_DIR}" "${PYTHON_BIN}" -m PyInstaller packaging/backend/pyinstaller/backend.spec

if [[ ! -f "${DIST_BIN}" ]]; then
  echo "expected backend binary not found at ${DIST_BIN}" >&2
  exit 1
fi

mkdir -p "${STAGE_DIR}"
rm -f "${STAGE_BIN}" "${WINDOWS_STAGE_BIN}"
cp "${DIST_BIN}" "${STAGE_BIN}"
cp "${DIST_BIN}" "${WINDOWS_STAGE_BIN}"
chmod +x "${STAGE_BIN}"
chmod +x "${WINDOWS_STAGE_BIN}"

mkdir -p "${FFMPEG_STAGE_DIR}"
rm -f "${FFMPEG_ARCHIVE}"
"${PYTHON_BIN}" - <<PY
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

archive = Path(${FFMPEG_ARCHIVE@Q})
source_dir = Path(${FFMPEG_SOURCE_DIR@Q})

with ZipFile(archive, "w", compression=ZIP_DEFLATED) as zip_file:
    zip_file.write(source_dir / "ffmpeg", arcname="ffmpeg")
    zip_file.write(source_dir / "ffprobe", arcname="ffprobe")
PY

echo "staged backend sidecar at ${STAGE_BIN}"
echo "staged ffmpeg runtime archive at ${FFMPEG_ARCHIVE}"
