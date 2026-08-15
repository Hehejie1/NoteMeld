#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-1577836800}"

TARGET="${1:?usage: build-python.sh <rust-target-triple>}"
SDK_VERSION="${NOTEMELD_SDK_VERSION:-0.1.0}"
SCHEMA_VERSION="${NOTEMELD_SCHEMA_VERSION:-1}"
BINDING_VERSION="${NOTEMELD_BINDING_VERSION:-0.1.0}"
DIST_ROOT="${NOTEMELD_ARTIFACT_DIR:-$ROOT/agent-sdk/dist}"
CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$ROOT/agent-sdk/target}"
export CARGO_TARGET_DIR
CARGO_COMMAND=(cargo)
if [[ -n "${NOTEMELD_CARGO_CONFIG:-}" ]]; then
  CARGO_COMMAND+=(--config "$NOTEMELD_CARGO_CONFIG")
fi

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN=python3
else
  PYTHON_BIN=python
fi

# This is a real target cargo build; cross compilers must be installed by the caller.
"${CARGO_COMMAND[@]}" build --manifest-path agent-sdk/Cargo.toml --locked \
  -p agent-ffi --release --target "$TARGET"

LICENSE_METADATA="$CARGO_TARGET_DIR/cargo-metadata.json"
LICENSE_INVENTORY="$CARGO_TARGET_DIR/license-inventory.json"
# cargo metadata is the source of the shipped dependency license inventory.
"${CARGO_COMMAND[@]}" metadata --manifest-path agent-sdk/Cargo.toml \
  --locked --format-version 1 > "$LICENSE_METADATA"
"$PYTHON_BIN" agent-sdk/scripts/verify-artifact-manifest.py licenses \
  --cargo-metadata "$LICENSE_METADATA" --output "$LICENSE_INVENTORY"

case "$TARGET" in
  *-pc-windows-*)
    NATIVE_NAME="notemeld_agent.dll"
    WHEEL_PLATFORM="win_amd64"
    ;;
  x86_64-apple-darwin)
    NATIVE_NAME="libnotemeld_agent.dylib"
    WHEEL_PLATFORM="macosx_11_0_x86_64"
    ;;
  aarch64-apple-darwin)
    NATIVE_NAME="libnotemeld_agent.dylib"
    WHEEL_PLATFORM="macosx_11_0_arm64"
    ;;
  x86_64-unknown-linux-gnu)
    NATIVE_NAME="libnotemeld_agent.so"
    WHEEL_PLATFORM="manylinux_2_28_x86_64"
    ;;
  aarch64-unknown-linux-gnu)
    NATIVE_NAME="libnotemeld_agent.so"
    WHEEL_PLATFORM="manylinux_2_28_aarch64"
    ;;
  *)
    echo "unsupported Python host target: $TARGET" >&2
    exit 2
    ;;
esac

NATIVE_SOURCE="$CARGO_TARGET_DIR/$TARGET/release/$NATIVE_NAME"
if [[ ! -f "$NATIVE_SOURCE" ]]; then
  echo "cargo did not produce $NATIVE_SOURCE" >&2
  exit 3
fi

OUTPUT="$DIST_ROOT/$TARGET"
rm -rf "$OUTPUT"
mkdir -p "$OUTPUT/native" "$OUTPUT/python" "$OUTPUT/include"
cp "$NATIVE_SOURCE" "$OUTPUT/native/$NATIVE_NAME"
cp agent-sdk/bindings/python/notemeld_agent_sdk/__init__.py "$OUTPUT/python/"
cp agent-sdk/bindings/python/notemeld_agent_sdk/runtime.py "$OUTPUT/python/"
cp agent-sdk/include/notemeld_agent.h "$OUTPUT/include/"
cp agent-sdk/bindings/abi-v1.json "$OUTPUT/"
cp "$LICENSE_INVENTORY" "$OUTPUT/"

WHEEL_NAME="notemeld_agent_sdk-${SDK_VERSION}-py3-none-${WHEEL_PLATFORM}.whl"
"$PYTHON_BIN" - "$OUTPUT" "$WHEEL_NAME" "$SDK_VERSION" "$WHEEL_PLATFORM" "$NATIVE_NAME" <<'PY'
import base64
import csv
import hashlib
import io
from pathlib import Path
import sys
import zipfile

output = Path(sys.argv[1])
wheel_name, version, platform, native_name = sys.argv[2:]
dist_info = f"notemeld_agent_sdk-{version}.dist-info"
files = {
    "notemeld_agent_sdk/__init__.py": (output / "python" / "__init__.py").read_bytes(),
    "notemeld_agent_sdk/runtime.py": (output / "python" / "runtime.py").read_bytes(),
    f"notemeld_agent_sdk/native/{native_name}": (output / "native" / native_name).read_bytes(),
    f"{dist_info}/METADATA": (
        "Metadata-Version: 2.1\n"
        "Name: notemeld-agent-sdk\n"
        f"Version: {version}\n"
        "Summary: NoteMeld Agent SDK Python binding\n"
        "License: MIT\n"
    ).encode(),
    f"{dist_info}/WHEEL": (
        "Wheel-Version: 1.0\n"
        "Generator: notemeld-agent-sdk\n"
        "Root-Is-Purelib: false\n"
        f"Tag: py3-none-{platform}\n"
    ).encode(),
}
rows = []
for path, data in sorted(files.items()):
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    rows.append((path, f"sha256={digest}", str(len(data))))
record_path = f"{dist_info}/RECORD"
rows.append((record_path, "", ""))
record = io.StringIO(newline="")
csv.writer(record, lineterminator="\n").writerows(rows)
files[record_path] = record.getvalue().encode()

wheel = output / wheel_name
timestamp = (2020, 1, 1, 0, 0, 0)
with zipfile.ZipFile(wheel, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for path, data in sorted(files.items()):
        info = zipfile.ZipInfo(path, timestamp)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        archive.writestr(info, data)
PY

# Equivalent CLI form: python3 agent-sdk/scripts/verify-artifact-manifest.py create
"$PYTHON_BIN" agent-sdk/scripts/verify-artifact-manifest.py create \
  --artifact-dir "$OUTPUT" \
  --target-triple "$TARGET" \
  --sdk-version "$SDK_VERSION" \
  --schema-version "$SCHEMA_VERSION" \
  --binding-version "$BINDING_VERSION" \
  --license-inventory-file "$OUTPUT/license-inventory.json" \
  --artifact "native-library=native/$NATIVE_NAME" \
  --artifact "python-wheel=$WHEEL_NAME" \
  --artifact "c-header=include/notemeld_agent.h" \
  --artifact "abi-contract=abi-v1.json" \
  --artifact "license-inventory=license-inventory.json"

"$PYTHON_BIN" agent-sdk/scripts/verify-artifact-manifest.py verify \
  --artifact-root "$OUTPUT" \
  --sdk-version "$SDK_VERSION" \
  --schema-version "$SCHEMA_VERSION" \
  --binding-version "$BINDING_VERSION" \
  --expected-target "$TARGET"
