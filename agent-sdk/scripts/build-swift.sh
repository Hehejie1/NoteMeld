#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-1577836800}"

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
PYTHON_BIN="${PYTHON_BIN:-python3}"
DEVICE_TARGET="aarch64-apple-ios"
SIMULATOR_TARGET="aarch64-apple-ios-sim"
BUILD_ROOT="$CARGO_TARGET_DIR/swift-artifacts"

command -v xcodebuild >/dev/null
command -v swift >/dev/null
rustup target add "$DEVICE_TARGET" "$SIMULATOR_TARGET"

for target in "$DEVICE_TARGET" "$SIMULATOR_TARGET"; do
  # cargo rustc is used so the FFI crate emits a linkable static iOS slice.
  "${CARGO_COMMAND[@]}" rustc --manifest-path agent-sdk/Cargo.toml --locked \
    -p agent-ffi --release --target "$target" -- --crate-type staticlib
  library="$CARGO_TARGET_DIR/$target/release/deps/libnotemeld_agent.a"
  if [[ ! -f "$library" ]]; then
    echo "cargo rustc did not produce $library" >&2
    exit 3
  fi
done

# Compile the typed Swift layer on the build host before packaging target slices.
swift build --package-path agent-sdk/bindings/swift

rm -rf "$BUILD_ROOT"
mkdir -p "$BUILD_ROOT"
LICENSE_METADATA="$BUILD_ROOT/cargo-metadata.json"
LICENSE_INVENTORY="$BUILD_ROOT/license-inventory.json"
# cargo metadata is the source of the shipped dependency license inventory.
"${CARGO_COMMAND[@]}" metadata --manifest-path agent-sdk/Cargo.toml \
  --locked --format-version 1 > "$LICENSE_METADATA"
"$PYTHON_BIN" agent-sdk/scripts/verify-artifact-manifest.py licenses \
  --cargo-metadata "$LICENSE_METADATA" --output "$LICENSE_INVENTORY"
xcodebuild -create-xcframework \
  -library "$CARGO_TARGET_DIR/$DEVICE_TARGET/release/deps/libnotemeld_agent.a" \
  -headers agent-sdk/include \
  -library "$CARGO_TARGET_DIR/$SIMULATOR_TARGET/release/deps/libnotemeld_agent.a" \
  -headers agent-sdk/include \
  -output "$BUILD_ROOT/NoteMeldAgentSDK.xcframework"

create_deterministic_zip() {
  "$PYTHON_BIN" - "$@" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import sys
import zipfile

output = Path(sys.argv[1])
root = Path(sys.argv[2])
members = [root / member for member in sys.argv[3:-1]]
epoch = max(315532800, int(sys.argv[-1]))
stamp = list(datetime.fromtimestamp(epoch, timezone.utc).timetuple()[:6])
stamp[5] -= stamp[5] % 2
timestamp = tuple(stamp)
files = []
for member in members:
    if not member.exists():
        raise SystemExit(f"archive member does not exist: {member}")
    files.extend([member] if member.is_file() else member.rglob("*"))
with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for path in sorted(candidate for candidate in files if candidate.is_file()):
        info = zipfile.ZipInfo(path.relative_to(root).as_posix(), timestamp)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        archive.writestr(info, path.read_bytes())
PY
}

create_deterministic_zip \
  "$BUILD_ROOT/NoteMeldAgentSDK.xcframework.zip" \
  "$BUILD_ROOT" NoteMeldAgentSDK.xcframework "$SOURCE_DATE_EPOCH"
create_deterministic_zip \
  "$BUILD_ROOT/NoteMeldAgentSwiftPackage.zip" \
  agent-sdk/bindings/swift Package.swift Sources "$SOURCE_DATE_EPOCH"

for target in "$DEVICE_TARGET" "$SIMULATOR_TARGET"; do
  output="$DIST_ROOT/$target"
  rm -rf "$output"
  mkdir -p "$output/native"
  cp "$CARGO_TARGET_DIR/$target/release/deps/libnotemeld_agent.a" "$output/native/"
  cp "$BUILD_ROOT/NoteMeldAgentSDK.xcframework.zip" "$output/"
  cp "$BUILD_ROOT/NoteMeldAgentSwiftPackage.zip" "$output/"
  cp agent-sdk/bindings/abi-v1.json "$output/"
  cp "$LICENSE_INVENTORY" "$output/"

  "$PYTHON_BIN" agent-sdk/scripts/verify-artifact-manifest.py create \
    --artifact-dir "$output" \
    --target-triple "$target" \
    --sdk-version "$SDK_VERSION" \
    --schema-version "$SCHEMA_VERSION" \
    --binding-version "$BINDING_VERSION" \
    --license-inventory-file "$output/license-inventory.json" \
    --artifact "static-library=native/libnotemeld_agent.a" \
    --artifact "swift-xcframework=NoteMeldAgentSDK.xcframework.zip" \
    --artifact "swift-package=NoteMeldAgentSwiftPackage.zip" \
    --artifact "abi-contract=abi-v1.json" \
    --artifact "license-inventory=license-inventory.json"
  "$PYTHON_BIN" agent-sdk/scripts/verify-artifact-manifest.py verify \
    --artifact-root "$output" \
    --sdk-version "$SDK_VERSION" \
    --schema-version "$SCHEMA_VERSION" \
    --binding-version "$BINDING_VERSION" \
    --expected-target "$target"
done
