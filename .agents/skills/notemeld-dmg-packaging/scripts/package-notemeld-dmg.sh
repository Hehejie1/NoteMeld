#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${NOTEMELD_ROOT:-/Users/bytedance/ai/NoteMeld}"
BUILD_SCRIPT="${ROOT_DIR}/packaging/scripts/build-desktop-macos.sh"
X64_PYTHON="${NOTEMELD_X64_PYTHON:-${ROOT_DIR}/.venv-x64-003/bin/python}"
CLOUD_FILE="${NOTEMELD_CLOUD_FILE:-/Users/bytedance/ai/cloud.txt}"
REMOTE_DIR="${NOTEMELD_REMOTE_DIR:-/srv/filebox/releases/notemeld/stable}"
PUBLIC_BASE_URL="${NOTEMELD_PUBLIC_BASE_URL:-https://notemeld.wiki/releases/notemeld/stable}"

DO_BUILD=1
DO_UPLOAD=0
DO_PUBLIC_VERIFY=0
DO_RELEASE=0

usage() {
  cat <<USAGE
Usage: $0 [--no-build] [--upload] [--public-verify] [--release]

Default:
  Build and verify both NoteMeld macOS DMGs locally.

Options:
  --no-build        Reuse existing DMGs and only run verification/upload steps.
  --upload          Upload both DMGs atomically to ${REMOTE_DIR}.
  --public-verify   Download public DMGs and verify SHA256 + hdiutil.
  --release         Require Developer ID signing, notarization, staple, and Gatekeeper acceptance.

Release env:
  NOTEMELD_CODESIGN_IDENTITY   Developer ID Application identity, e.g. "Developer ID Application: Name (TEAMID)".
  NOTEMELD_NOTARY_PROFILE      notarytool keychain profile created by xcrun notarytool store-credentials.

Fixed paths:
  Repo:        ${ROOT_DIR}
  Build:       ${BUILD_SCRIPT}
  x64 Python:  ${X64_PYTHON}
  Cloud file:  ${CLOUD_FILE}
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-build)
      DO_BUILD=0
      ;;
    --upload)
      DO_UPLOAD=1
      ;;
    --public-verify)
      DO_PUBLIC_VERIFY=1
      ;;
    --release)
      DO_RELEASE=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

require_file() {
  local path="$1"
  local label="$2"
  if [[ ! -e "${path}" ]]; then
    echo "missing ${label}: ${path}" >&2
    exit 1
  fi
}

require_release_config() {
  if [[ -z "${NOTEMELD_CODESIGN_IDENTITY:-}" || "${NOTEMELD_CODESIGN_IDENTITY}" == "-" ]]; then
    echo "missing release signing identity: set NOTEMELD_CODESIGN_IDENTITY to a Developer ID Application certificate" >&2
    exit 1
  fi
  if [[ -z "${NOTEMELD_NOTARY_PROFILE:-}" ]]; then
    echo "missing notarization profile: set NOTEMELD_NOTARY_PROFILE after running xcrun notarytool store-credentials" >&2
    exit 1
  fi
  if ! security find-identity -v -p codesigning | grep -Fq "${NOTEMELD_CODESIGN_IDENTITY}"; then
    echo "Developer ID identity not found in keychain: ${NOTEMELD_CODESIGN_IDENTITY}" >&2
    exit 1
  fi
  if ! xcrun notarytool history --keychain-profile "${NOTEMELD_NOTARY_PROFILE}" >/dev/null 2>&1; then
    echo "notarytool profile is unavailable or invalid: ${NOTEMELD_NOTARY_PROFILE}" >&2
    exit 1
  fi
}

version() {
  ROOT_DIR="${ROOT_DIR}" python3 - <<'PY'
import json
import os
from pathlib import Path

root = Path(os.environ["ROOT_DIR"])
config = json.loads((root / "desktop/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
print(config["version"])
PY
}

VERSION="$(version)"
AARCH64_DMG="${ROOT_DIR}/desktop/src-tauri/target/aarch64-apple-darwin/release/bundle/dmg/NoteMeld_${VERSION}_aarch64.dmg"
X64_DMG="${ROOT_DIR}/desktop/src-tauri/target/x86_64-apple-darwin/release/bundle/dmg/NoteMeld_${VERSION}_x64.dmg"

require_file "${BUILD_SCRIPT}" "build script"
if [[ ${DO_BUILD} -eq 1 ]]; then
  require_file "${X64_PYTHON}" "Intel Python"
fi

log() {
  printf '[notemeld-dmg] %s\n' "$*"
}

sha256_file() {
  shasum -a 256 "$1" | awk '{print $1}'
}

verify_dmg_app() {
  local arch="$1"
  local dmg="$2"
  local expected_format="$3"
  local mount_dir

  require_file "${dmg}" "${arch} DMG"
  log "verify hdiutil ${arch}: ${dmg}"
  hdiutil verify "${dmg}"

  mount_dir="$(mktemp -d "/tmp/notemeld-${arch}-mount.XXXXXX")"
  hdiutil attach -nobrowse -readonly -mountpoint "${mount_dir}" "${dmg}" >/dev/null
  cleanup_mount() {
    hdiutil detach "${mount_dir}" >/dev/null 2>&1 || true
    rm -rf "${mount_dir}" >/dev/null 2>&1 || true
  }
  trap cleanup_mount RETURN

  local app="${mount_dir}/NoteMeld.app"
  require_file "${app}" "${arch} app bundle"
  if [[ ! -L "${mount_dir}/Applications" ]]; then
    echo "missing /Applications shortcut in ${arch} DMG" >&2
    exit 1
  fi
  if [[ "$(readlink "${mount_dir}/Applications")" != "/Applications" ]]; then
    echo "invalid Applications shortcut in ${arch} DMG" >&2
    exit 1
  fi

  log "verify codesign ${arch}"
  codesign --verify --deep --strict --verbose=4 "${app}"

  local details
  details="$(codesign -dv --verbose=4 "${app}" 2>&1 || true)"
  printf '%s\n' "${details}" | grep -E 'Identifier|Format|Signature|TeamIdentifier' || true
  if ! printf '%s\n' "${details}" | grep -Fq "${expected_format}"; then
    echo "unexpected app architecture for ${arch}; expected ${expected_format}" >&2
    exit 1
  fi

  if ! spctl -a -vv --type execute "${app}"; then
    if [[ ${DO_RELEASE} -eq 1 ]]; then
      echo "Gatekeeper rejected ${arch} app in release mode" >&2
      exit 1
    fi
    log "warning: spctl rejected ${arch}; allowed only for ad-hoc/unnotarized builds after codesign verify passed"
  fi

  cleanup_mount
  trap - RETURN
}

notarize_one() {
  local arch="$1"
  local dmg="$2"

  require_file "${dmg}" "${arch} DMG"
  log "notarize ${arch}: ${dmg}"
  xcrun notarytool submit "${dmg}" \
    --keychain-profile "${NOTEMELD_NOTARY_PROFILE}" \
    --wait
  log "staple ${arch}: ${dmg}"
  xcrun stapler staple "${dmg}"
  xcrun stapler validate "${dmg}"
  spctl -a -vv --type open "${dmg}"
}

notarize_all() {
  notarize_one "aarch64" "${AARCH64_DMG}"
  notarize_one "x64" "${X64_DMG}"
}

build_all() {
  log "build Apple Silicon DMG"
  (
    cd "${ROOT_DIR}"
    bash "${BUILD_SCRIPT}"
  )

  log "build Intel x64 DMG"
  (
    cd "${ROOT_DIR}"
    NOTEMELD_TARGET_ARCH=x86_64 \
      NOTEMELD_PYTHON_BIN="${X64_PYTHON}" \
      bash "${BUILD_SCRIPT}"
  )
}

verify_local() {
  verify_dmg_app "aarch64" "${AARCH64_DMG}" "Mach-O thin (arm64)"
  verify_dmg_app "x64" "${X64_DMG}" "Mach-O thin (x86_64)"

  log "local artifacts"
  ls -lh "${AARCH64_DMG}" "${X64_DMG}"
  log "local sha256"
  shasum -a 256 "${AARCH64_DMG}" "${X64_DMG}"
}

upload_all() {
  require_file "${CLOUD_FILE}" "cloud config"
  log "upload DMGs atomically to ${REMOTE_DIR}"
  ROOT_DIR="${ROOT_DIR}" \
  CLOUD_FILE="${CLOUD_FILE}" \
  REMOTE_DIR="${REMOTE_DIR}" \
  AARCH64_DMG="${AARCH64_DMG}" \
  X64_DMG="${X64_DMG}" \
  python3 - <<'PY'
import os
import re
from pathlib import Path

import paramiko

cloud = Path(os.environ["CLOUD_FILE"]).read_text(encoding="utf-8")

def field(name: str) -> str:
    match = re.search(rf"^{re.escape(name)}:\s*(.+)$", cloud, re.MULTILINE)
    if not match:
        raise SystemExit(f"missing field in cloud file: {name}")
    return match.group(1).strip()

host = field("ip")
username = field("name")
password = field("password")
remote_dir = os.environ["REMOTE_DIR"]
local_files = [Path(os.environ["AARCH64_DMG"]), Path(os.environ["X64_DMG"])]

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(hostname=host, port=22, username=username, password=password, timeout=30)
try:
    stdin, stdout, stderr = client.exec_command(f"mkdir -p {remote_dir}")
    if stdout.channel.recv_exit_status() != 0:
        raise RuntimeError(stderr.read().decode())

    sftp = client.open_sftp()
    try:
        for local in local_files:
            tmp = f"{remote_dir}/{local.name}.uploading"
            final = f"{remote_dir}/{local.name}"
            print(f"upload {local.name} bytes={local.stat().st_size}")
            sftp.put(str(local), tmp)
            stdin, stdout, stderr = client.exec_command(f"mv {tmp} {final}")
            if stdout.channel.recv_exit_status() != 0:
                raise RuntimeError(stderr.read().decode())
    finally:
        sftp.close()

    stdin, stdout, stderr = client.exec_command(
        f"cd {remote_dir} && sha256sum {' '.join(p.name for p in local_files)} && stat -c '%n %s %y' {' '.join(p.name for p in local_files)}"
    )
    if stdout.channel.recv_exit_status() != 0:
        raise RuntimeError(stderr.read().decode())
    print(stdout.read().decode(), end="")
finally:
    client.close()
PY
}

verify_public_one() {
  local name="$1"
  local expected_sha="$2"
  local expected_format="$3"
  local url="${PUBLIC_BASE_URL}/${name}?verify=$(date +%Y%m%d%H%M%S)"
  local out="/tmp/${name}.public-verify"

  rm -f "${out}"
  log "download public ${name}"
  URL="${url}" OUT="${out}" EXPECTED_SHA="${expected_sha}" python3 - <<'PY'
import hashlib
import os
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

url = os.environ["URL"]
out = Path(os.environ["OUT"])
expected_sha = os.environ["EXPECTED_SHA"]

req = Request(url, headers={"User-Agent": "notemeld-dmg-public-verify/1.0"})
h = hashlib.sha256()
total = 0
with urlopen(req, timeout=60) as resp, out.open("wb") as f:
    print("status", resp.status)
    print("content_length", resp.headers.get("Content-Length"))
    while True:
        chunk = resp.read(1024 * 1024)
        if not chunk:
            break
        f.write(chunk)
        h.update(chunk)
        total += len(chunk)

actual_sha = h.hexdigest()
print("bytes", total)
print("sha256", actual_sha)
if actual_sha != expected_sha:
    raise SystemExit(f"sha mismatch: expected {expected_sha}, got {actual_sha}")

r = subprocess.run(["hdiutil", "verify", str(out)], text=True, capture_output=True)
print("hdiutil_exit", r.returncode)
print((r.stdout + r.stderr).strip())
if r.returncode != 0:
    raise SystemExit(r.returncode)
PY
  verify_dmg_app "public-${name}" "${out}" "${expected_format}"
  rm -f "${out}"
}

verify_public() {
  verify_public_one "$(basename "${AARCH64_DMG}")" "$(sha256_file "${AARCH64_DMG}")" "Mach-O thin (arm64)"
  verify_public_one "$(basename "${X64_DMG}")" "$(sha256_file "${X64_DMG}")" "Mach-O thin (x86_64)"
}

main() {
  log "version=${VERSION}"
  log "aarch64=${AARCH64_DMG}"
  log "x64=${X64_DMG}"

  if [[ ${DO_RELEASE} -eq 1 ]]; then
    require_release_config
    export NOTEMELD_CODESIGN_IDENTITY
    log "release mode enabled: Developer ID signing and Apple notarization required"
  fi

  if [[ ${DO_BUILD} -eq 1 ]]; then
    build_all
  fi

  if [[ ${DO_RELEASE} -eq 1 ]]; then
    notarize_all
  fi

  verify_local

  if [[ ${DO_UPLOAD} -eq 1 ]]; then
    upload_all
  fi

  if [[ ${DO_PUBLIC_VERIFY} -eq 1 ]]; then
    verify_public
  fi

  log "success"
}

main "$@"
