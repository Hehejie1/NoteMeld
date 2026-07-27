#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CHANNEL="${NOTEMELD_RELEASE_CHANNEL:-stable}"
BASE_URL="${NOTEMELD_RELEASE_BASE_URL:-http://43.167.164.213/releases/notemeld/${CHANNEL}}"
REMOTE="${NOTEMELD_RELEASE_REMOTE:-}"
BUNDLE_DIR="${ROOT_DIR}/desktop/src-tauri/target/release/bundle"
STAGE_DIR="${ROOT_DIR}/packaging/dist/releases/notemeld/${CHANNEL}"
VERSION="$(
  python3 - <<'PY' "${ROOT_DIR}/desktop/src-tauri/tauri.conf.json"
import json
import sys
from pathlib import Path

print(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["version"])
PY
)"

rm -rf "${STAGE_DIR}"
mkdir -p "${STAGE_DIR}"

find "${BUNDLE_DIR}" -type f \( \
  -name "*.app.tar.gz" -o \
  -name "*.app.tar.gz.sig" -o \
  -name "*.msi.zip" -o \
  -name "*.msi.zip.sig" -o \
  -name "*.AppImage.tar.gz" -o \
  -name "*.AppImage.tar.gz.sig" -o \
  -name "*.dmg" -o \
  -name "*.msi" \
\) -exec cp {} "${STAGE_DIR}/" \;

python3 - <<'PY' "${STAGE_DIR}" "${BASE_URL}" "${VERSION}"
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

stage_dir = Path(sys.argv[1])
base_url = sys.argv[2].rstrip("/")
version = sys.argv[3]


def current_darwin_platform() -> str:
    dmg_names = [path.name.lower() for path in stage_dir.glob("*.dmg")]
    if any("aarch64" in name or "arm64" in name for name in dmg_names):
        return "darwin-aarch64"
    if any("x64" in name or "x86_64" in name for name in dmg_names):
        return "darwin-x86_64"
    machine = platform.machine().lower()
    arch = "aarch64" if machine in {"arm64", "aarch64"} else "x86_64"
    return f"darwin-{arch}"


def read_signature(path: Path) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if "Public signature:" not in text:
        return text
    return text.split("Public signature:", 1)[1].strip().splitlines()[0].strip()


def platform_key(path: Path):
    name = path.name.lower()
    if name.endswith(".app.tar.gz"):
        if "aarch64" in name or "arm64" in name:
            return "darwin-aarch64"
        if "x64" in name or "x86_64" in name:
            return "darwin-x86_64"
        return current_darwin_platform()
    if name.endswith(".msi.zip"):
        return "windows-x86_64"
    if name.endswith(".appimage.tar.gz"):
        return "linux-x86_64"
    return None


platforms = {}
for artifact in sorted(stage_dir.iterdir()):
    key = platform_key(artifact)
    if not key:
        continue

    signature_path = artifact.with_name(f"{artifact.name}.sig")
    if not signature_path.exists():
        raise SystemExit(f"missing signature for updater artifact: {artifact.name}")

    platforms[key] = {
        "signature": read_signature(signature_path),
        "url": f"{base_url}/{artifact.name}",
    }

if not platforms:
    raise SystemExit(f"no updater artifacts found in {stage_dir}")

latest = {
    "version": version,
    "notes": "NoteMeld desktop update. User data stays in the application data directory.",
    "pub_date": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "platforms": platforms,
}

(stage_dir / "latest.json").write_text(
    json.dumps(latest, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY

echo "Release staged at: ${STAGE_DIR}"
echo "Update manifest: ${STAGE_DIR}/latest.json"

if [[ -n "${REMOTE}" ]]; then
  ssh "${REMOTE%%:*}" "mkdir -p '${REMOTE#*:}'"
  scp "${STAGE_DIR}"/* "${REMOTE}/"
  echo "Release uploaded to: ${REMOTE}"
else
  echo "Set NOTEMELD_RELEASE_REMOTE='root@43.167.164.213:/srv/filebox/releases/notemeld/${CHANNEL}' to upload."
fi
