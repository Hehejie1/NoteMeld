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
HEADERS="$BUILD_ROOT/headers"
PUBLISHED_PACKAGE="$BUILD_ROOT/swift-package"
mkdir -p "$HEADERS" "$PUBLISHED_PACKAGE/Sources/NoteMeldAgentSDK"
cp agent-sdk/include/notemeld_agent.h "$HEADERS/"
cat > "$HEADERS/module.modulemap" <<'EOF'
module CNotemeldAgent {
  header "notemeld_agent.h"
  export *
}
EOF
LICENSE_METADATA="$BUILD_ROOT/cargo-metadata.json"
LICENSE_INVENTORY="$BUILD_ROOT/license-inventory.json"
# cargo metadata is the source of the shipped dependency license inventory.
"${CARGO_COMMAND[@]}" metadata --manifest-path agent-sdk/Cargo.toml \
  --locked --format-version 1 > "$LICENSE_METADATA"
"$PYTHON_BIN" agent-sdk/scripts/verify-artifact-manifest.py licenses \
  --cargo-metadata "$LICENSE_METADATA" \
  --cargo-lock agent-sdk/Cargo.lock \
  --root-package agent-ffi \
  --output "$LICENSE_INVENTORY"
xcodebuild -create-xcframework \
  -library "$CARGO_TARGET_DIR/$DEVICE_TARGET/release/deps/libnotemeld_agent.a" \
  -headers "$HEADERS" \
  -library "$CARGO_TARGET_DIR/$SIMULATOR_TARGET/release/deps/libnotemeld_agent.a" \
  -headers "$HEADERS" \
  -output "$PUBLISHED_PACKAGE/NoteMeldAgentNative.xcframework"

cp agent-sdk/bindings/swift/Sources/NoteMeldAgentSDK/Runtime.swift \
  "$PUBLISHED_PACKAGE/Sources/NoteMeldAgentSDK/"
cp agent-sdk/bindings/abi-v1.json "$PUBLISHED_PACKAGE/abi-v1.json"
cp agent-sdk/bindings/abi-v1.json \
  "$PUBLISHED_PACKAGE/NoteMeldAgentNative.xcframework/abi-v1.json"
cat > "$PUBLISHED_PACKAGE/Package.swift" <<'EOF'
// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "NoteMeldAgentSDK",
    platforms: [.iOS(.v15)],
    products: [.library(name: "NoteMeldAgentSDK", targets: ["NoteMeldAgentSDK"])],
    targets: [
        .binaryTarget(
            name: "CNotemeldAgent",
            path: "NoteMeldAgentNative.xcframework"
        ),
        .target(
            name: "NoteMeldAgentSDK",
            dependencies: ["CNotemeldAgent"],
            path: "Sources/NoteMeldAgentSDK"
        )
    ]
)
EOF
"$PYTHON_BIN" - "$PUBLISHED_PACKAGE" "$SDK_VERSION" "$SCHEMA_VERSION" \
  "$BINDING_VERSION" "$DEVICE_TARGET" "$SIMULATOR_TARGET" <<'PY'
from pathlib import Path
import json
import sys

package = Path(sys.argv[1])
sdk, schema, binding, device, simulator = sys.argv[2:]
marker = json.dumps({
    "sdk_version": sdk,
    "schema_version": schema,
    "binding_version": binding,
    "target_triples": [device, simulator],
}, indent=2, sort_keys=True) + "\n"
(package / "notemeld-agent-sdk.json").write_text(marker)
(package / "NoteMeldAgentNative.xcframework" / "notemeld-agent-sdk.json").write_text(marker)
PY

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
  "$BUILD_ROOT/NoteMeldAgentNative.xcframework.zip" \
  "$PUBLISHED_PACKAGE" NoteMeldAgentNative.xcframework notemeld-agent-sdk.json \
  abi-v1.json \
  "$SOURCE_DATE_EPOCH"
create_deterministic_zip \
  "$BUILD_ROOT/NoteMeldAgentSwiftPackage.zip" \
  "$PUBLISHED_PACKAGE" Package.swift Sources NoteMeldAgentNative.xcframework \
  notemeld-agent-sdk.json abi-v1.json "$SOURCE_DATE_EPOCH"

CONSUMER_ROOT="$BUILD_ROOT/swift-release-consumer"
PUBLISHED_EXTRACTED="$CONSUMER_ROOT/published"
mkdir -p "$PUBLISHED_EXTRACTED" "$CONSUMER_ROOT/Sources/NoteMeldAgentIOSHarness"
unzip -q "$BUILD_ROOT/NoteMeldAgentSwiftPackage.zip" -d "$PUBLISHED_EXTRACTED"
cp agent-sdk/examples/ios-harness/Sources/NoteMeldAgentIOSHarness/main.swift \
  "$CONSUMER_ROOT/Sources/NoteMeldAgentIOSHarness/"
cat > "$CONSUMER_ROOT/Package.swift" <<'EOF'
// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "NoteMeldAgentIOSHarness",
    platforms: [.iOS(.v15)],
    dependencies: [.package(path: "published")],
    targets: [.executableTarget(
        name: "NoteMeldAgentIOSHarness",
        dependencies: [.product(name: "NoteMeldAgentSDK", package: "published")]
    )]
)
EOF
(cd "$CONSUMER_ROOT" && xcodebuild \
  -scheme NoteMeldAgentIOSHarness \
  -destination 'generic/platform=iOS' \
  -derivedDataPath "$BUILD_ROOT/derived-device" \
  CODE_SIGNING_ALLOWED=NO build)
(cd "$CONSUMER_ROOT" && xcodebuild \
  -scheme NoteMeldAgentIOSHarness \
  -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath "$BUILD_ROOT/derived-simulator" \
  ARCHS=arm64 ONLY_ACTIVE_ARCH=YES CODE_SIGNING_ALLOWED=NO build)

for target in "$DEVICE_TARGET" "$SIMULATOR_TARGET"; do
  output="$DIST_ROOT/$target"
  rm -rf "$output"
  mkdir -p "$output/native"
  cp "$CARGO_TARGET_DIR/$target/release/deps/libnotemeld_agent.a" "$output/native/"
  cp "$BUILD_ROOT/NoteMeldAgentNative.xcframework.zip" "$output/"
  cp "$BUILD_ROOT/NoteMeldAgentSwiftPackage.zip" "$output/"
  cp agent-sdk/bindings/abi-v1.json "$output/"
  cp "$LICENSE_INVENTORY" "$output/"
  cp agent-sdk/Cargo.lock "$output/"

  "$PYTHON_BIN" agent-sdk/scripts/verify-artifact-manifest.py create \
    --artifact-dir "$output" \
    --target-triple "$target" \
    --sdk-version "$SDK_VERSION" \
    --schema-version "$SCHEMA_VERSION" \
    --binding-version "$BINDING_VERSION" \
    --license-inventory-file "$output/license-inventory.json" \
    --cargo-lock-file "$output/Cargo.lock" \
    --artifact "static-library=native/libnotemeld_agent.a" \
    --artifact "swift-xcframework=NoteMeldAgentNative.xcframework.zip" \
    --artifact "swift-package=NoteMeldAgentSwiftPackage.zip" \
    --artifact "abi-contract=abi-v1.json" \
    --artifact "license-inventory=license-inventory.json" \
    --artifact "cargo-lock=Cargo.lock"
  "$PYTHON_BIN" agent-sdk/scripts/verify-artifact-manifest.py verify \
    --artifact-root "$output" \
    --sdk-version "$SDK_VERSION" \
    --schema-version "$SCHEMA_VERSION" \
    --binding-version "$BINDING_VERSION" \
    --expected-cargo-metadata "$LICENSE_METADATA" \
    --expected-cargo-lock agent-sdk/Cargo.lock \
    --root-package agent-ffi \
    --expected-target "$target"
done
