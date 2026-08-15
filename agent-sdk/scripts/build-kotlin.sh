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
GRADLE_BIN="${GRADLE_BIN:-gradle}"
NATIVE_ROOT="$CARGO_TARGET_DIR/android-jni"

command -v "$GRADLE_BIN" >/dev/null
command -v cargo-ndk >/dev/null
rm -rf "$NATIVE_ROOT"
mkdir -p "$NATIVE_ROOT"

# cargo ndk compiles the same FFI crate for every Android ABI.
"${CARGO_COMMAND[@]}" ndk \
  -t armeabi-v7a \
  -t arm64-v8a \
  -t x86 \
  -t x86_64 \
  -o "$NATIVE_ROOT" \
  build --manifest-path agent-sdk/Cargo.toml --locked -p agent-ffi --release

NOTEMELD_AGENT_LIBRARY_DIR="$NATIVE_ROOT" \
  "$GRADLE_BIN" -p agent-sdk/bindings/kotlin --no-daemon clean assembleRelease
NOTEMELD_AGENT_LIBRARY_DIR="$NATIVE_ROOT" \
  "$GRADLE_BIN" -p agent-sdk/examples/android-harness --no-daemon assembleDebug assembleAndroidTest

LICENSE_METADATA="$CARGO_TARGET_DIR/cargo-metadata.json"
LICENSE_INVENTORY="$CARGO_TARGET_DIR/license-inventory.json"
# cargo metadata is the source of the shipped dependency license inventory.
"${CARGO_COMMAND[@]}" metadata --manifest-path agent-sdk/Cargo.toml \
  --locked --format-version 1 > "$LICENSE_METADATA"
"$PYTHON_BIN" agent-sdk/scripts/verify-artifact-manifest.py licenses \
  --cargo-metadata "$LICENSE_METADATA" --output "$LICENSE_INVENTORY"

AAR_SOURCE="$(find agent-sdk/bindings/kotlin/build/outputs/aar -name '*-release.aar' -type f -print -quit)"
if [[ -z "$AAR_SOURCE" || ! -f "$AAR_SOURCE" ]]; then
  echo "Gradle assembleRelease did not produce an AAR" >&2
  exit 3
fi
AAR_STAGING="$CARGO_TARGET_DIR/notemeld-agent-sdk-${SDK_VERSION}.aar"

# Gradle packages the JNI bridge. Repack it with the four real Rust ABI
# libraries, sorted entries, and a fixed timestamp for a stable archive hash.
"$PYTHON_BIN" - "$AAR_SOURCE" "$AAR_STAGING" "$NATIVE_ROOT" "$SOURCE_DATE_EPOCH" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import sys
import zipfile

source = Path(sys.argv[1])
output = Path(sys.argv[2])
native_root = Path(sys.argv[3])
epoch = max(315532800, int(sys.argv[4]))
stamp = list(datetime.fromtimestamp(epoch, timezone.utc).timetuple()[:6])
stamp[5] -= stamp[5] % 2
timestamp = tuple(stamp)
abis = ("armeabi-v7a", "arm64-v8a", "x86", "x86_64")
files = {}
with zipfile.ZipFile(source) as archive:
    for info in archive.infolist():
        if info.is_dir():
            continue
        if info.filename in files:
            raise SystemExit(f"duplicate Gradle AAR entry: {info.filename}")
        files[info.filename] = archive.read(info)
for abi in abis:
    library = native_root / abi / "libnotemeld_agent.so"
    if not library.is_file():
        raise SystemExit(f"missing cargo-ndk output: {library}")
    files[f"jni/{abi}/libnotemeld_agent.so"] = library.read_bytes()
with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for name, data in sorted(files.items()):
        info = zipfile.ZipInfo(name, timestamp)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        archive.writestr(info, data)
PY

declare -A TARGET_TO_ABI=(
  [aarch64-linux-android]=arm64-v8a
  [armv7-linux-androideabi]=armeabi-v7a
  [i686-linux-android]=x86
  [x86_64-linux-android]=x86_64
)

for target in "${!TARGET_TO_ABI[@]}"; do
  abi="${TARGET_TO_ABI[$target]}"
  output="$DIST_ROOT/$target"
  rm -rf "$output"
  mkdir -p "$output/native/$abi"
  cp "$NATIVE_ROOT/$abi/libnotemeld_agent.so" "$output/native/$abi/"
  cp "$AAR_STAGING" "$output/notemeld-agent-sdk-${SDK_VERSION}.aar"
  cp agent-sdk/bindings/abi-v1.json "$output/"
  cp "$LICENSE_INVENTORY" "$output/"

  "$PYTHON_BIN" agent-sdk/scripts/verify-artifact-manifest.py create \
    --artifact-dir "$output" \
    --target-triple "$target" \
    --sdk-version "$SDK_VERSION" \
    --schema-version "$SCHEMA_VERSION" \
    --binding-version "$BINDING_VERSION" \
    --license-inventory-file "$output/license-inventory.json" \
    --artifact "native-library=native/$abi/libnotemeld_agent.so" \
    --artifact "kotlin-aar=notemeld-agent-sdk-${SDK_VERSION}.aar" \
    --artifact "abi-contract=abi-v1.json" \
    --artifact "license-inventory=license-inventory.json"
  "$PYTHON_BIN" agent-sdk/scripts/verify-artifact-manifest.py verify \
    --artifact-root "$output" \
    --sdk-version "$SDK_VERSION" \
    --schema-version "$SCHEMA_VERSION" \
    --binding-version "$BINDING_VERSION" \
    --expected-target "$target"
done
