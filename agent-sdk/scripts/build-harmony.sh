#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-1577836800}"

TARGET="aarch64-unknown-linux-ohos"
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
OHPM_BIN="${OHPM_BIN:-ohpm}"
HVIGOR_BIN="${HVIGOR_BIN:-hvigorw}"
OHOS_SDK_NATIVE="${OHOS_SDK_NATIVE:?set OHOS_SDK_NATIVE to the unpacked OpenHarmony native SDK directory}"

command -v "$OHPM_BIN" >/dev/null
command -v "$HVIGOR_BIN" >/dev/null
CLANG="$OHOS_SDK_NATIVE/llvm/bin/clang"
AR="$OHOS_SDK_NATIVE/llvm/bin/llvm-ar"
if [[ ! -x "$CLANG" || ! -x "$AR" ]]; then
  echo "OpenHarmony native LLVM toolchain is incomplete: $OHOS_SDK_NATIVE" >&2
  exit 2
fi

LINKER_WRAPPER="$CARGO_TARGET_DIR/aarch64-unknown-linux-ohos-clang.sh"
mkdir -p "$CARGO_TARGET_DIR"
"$PYTHON_BIN" - "$LINKER_WRAPPER" "$CLANG" <<'PY'
from pathlib import Path
import shlex
import sys

wrapper = Path(sys.argv[1])
clang = shlex.quote(sys.argv[2])
wrapper.write_text(f"#!/usr/bin/env bash\nexec {clang} --target=aarch64-linux-ohos \"$@\"\n")
wrapper.chmod(0o755)
PY
export CARGO_TARGET_AARCH64_UNKNOWN_LINUX_OHOS_LINKER="$LINKER_WRAPPER"
export CARGO_TARGET_AARCH64_UNKNOWN_LINUX_OHOS_AR="$AR"
export CC_aarch64_unknown_linux_ohos="$CLANG --target=aarch64-linux-ohos"
export AR_aarch64_unknown_linux_ohos="$AR"
export CFLAGS_aarch64_unknown_linux_ohos="--target=aarch64-linux-ohos -fPIC -D__MUSL__=1"

rustup target add "$TARGET"
# This cargo build uses the OpenHarmony SDK clang linker configured above.
"${CARGO_COMMAND[@]}" build --manifest-path agent-sdk/Cargo.toml --locked \
  -p agent-ffi --release --target "$TARGET"

LICENSE_METADATA="$CARGO_TARGET_DIR/cargo-metadata.json"
LICENSE_INVENTORY="$CARGO_TARGET_DIR/license-inventory.json"
# cargo metadata is the source of the shipped dependency license inventory.
"${CARGO_COMMAND[@]}" metadata --manifest-path agent-sdk/Cargo.toml \
  --locked --format-version 1 > "$LICENSE_METADATA"
"$PYTHON_BIN" agent-sdk/scripts/verify-artifact-manifest.py licenses \
  --cargo-metadata "$LICENSE_METADATA" --output "$LICENSE_INVENTORY"

NATIVE_LIBRARY="$CARGO_TARGET_DIR/$TARGET/release/libnotemeld_agent.so"
if [[ ! -f "$NATIVE_LIBRARY" ]]; then
  echo "cargo build did not produce $NATIVE_LIBRARY" >&2
  exit 3
fi

PROJECT="$CARGO_TARGET_DIR/harmony-har-project"
MODULE="$PROJECT/notemeld-agent"
rm -rf "$PROJECT"
mkdir -p "$PROJECT/hvigor" "$MODULE/src/main/cpp" "$MODULE/src/main/ets" "$MODULE/libs/arm64-v8a"
cp agent-sdk/bindings/harmony/src/main/cpp/napi_init.cpp "$MODULE/src/main/cpp/"
cp agent-sdk/bindings/harmony/src/main/ets/index.ets "$MODULE/src/main/ets/Index.ets"
cp agent-sdk/include/notemeld_agent.h "$MODULE/src/main/cpp/"
cp "$NATIVE_LIBRARY" "$MODULE/libs/arm64-v8a/"

"$PYTHON_BIN" - "$PROJECT" "$SDK_VERSION" <<'PY'
from pathlib import Path
import sys

project = Path(sys.argv[1])
version = sys.argv[2]
module = project / "notemeld-agent"
(project / "oh-package.json5").write_text("""{
  modelVersion: '5.0.0',
  devDependencies: {
    '@ohos/hvigor': '5.0.2',
    '@ohos/hvigor-ohos-plugin': '5.0.2'
  }
}\n""")
(project / "build-profile.json5").write_text("""{
  app: { products: [{ name: 'default' }] },
  modules: [{ name: 'notemeld-agent', srcPath: './notemeld-agent' }]
}\n""")
(project / "hvigorfile.ts").write_text("""import { appTasks } from '@ohos/hvigor-ohos-plugin';
export default { system: appTasks, plugins: [] };
""")
(project / "hvigor" / "hvigor-config.json5").write_text("""{
  modelVersion: '5.0.0', dependencies: {}
}\n""")
(module / "oh-package.json5").write_text(f"""{{
  name: '@notemeld/agent-sdk', version: '{version}', type: 'module',
  main: 'Index.ets', description: 'NoteMeld Agent SDK OpenHarmony binding'
}}\n""")
(module / "build-profile.json5").write_text("""{
  apiType: 'stageMode',
  buildOption: { externalNativeOptions: { path: './src/main/cpp/CMakeLists.txt' } },
  targets: [{ name: 'default' }]
}\n""")
(module / "hvigorfile.ts").write_text("""import { harTasks } from '@ohos/hvigor-ohos-plugin';
export default { system: harTasks, plugins: [] };
""")
(module / "src" / "main" / "module.json5").write_text("""{
  module: { name: 'notemeld_agent', type: 'har', deviceTypes: ['default'] }
}\n""")
(module / "src" / "main" / "cpp" / "CMakeLists.txt").write_text("""cmake_minimum_required(VERSION 3.5)
project(notemeld_agent_napi)
add_library(notemeld_agent SHARED IMPORTED)
set_target_properties(notemeld_agent PROPERTIES IMPORTED_LOCATION
  ${CMAKE_CURRENT_SOURCE_DIR}/../../../libs/arm64-v8a/libnotemeld_agent.so)
add_library(notemeld_agent_napi SHARED napi_init.cpp)
target_include_directories(notemeld_agent_napi PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(notemeld_agent_napi PUBLIC libace_napi.z.so notemeld_agent)
""")
PY

(cd "$PROJECT" && "$OHPM_BIN" install)
(cd "$PROJECT" && "$HVIGOR_BIN" --mode module \
  -p module=notemeld-agent@default -p product=default assembleHar --no-daemon)

HAR_SOURCE="$(find "$MODULE/build" -name '*.har' -type f -print -quit)"
if [[ -z "$HAR_SOURCE" || ! -f "$HAR_SOURCE" ]]; then
  echo "hvigor assembleHar did not produce a HAR" >&2
  exit 4
fi

HAR_STAGING="$CARGO_TARGET_DIR/notemeld-agent-sdk-${SDK_VERSION}.har"
# Normalize the unsigned HAR container so identical inputs have an identical hash.
"$PYTHON_BIN" - "$HAR_SOURCE" "$HAR_STAGING" "$SOURCE_DATE_EPOCH" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import sys
import zipfile

source = Path(sys.argv[1])
output = Path(sys.argv[2])
epoch = max(315532800, int(sys.argv[3]))
stamp = list(datetime.fromtimestamp(epoch, timezone.utc).timetuple()[:6])
stamp[5] -= stamp[5] % 2
timestamp = tuple(stamp)
files = {}
with zipfile.ZipFile(source) as archive:
    for info in archive.infolist():
        if info.is_dir():
            continue
        if info.filename in files:
            raise SystemExit(f"duplicate Hvigor HAR entry: {info.filename}")
        files[info.filename] = archive.read(info)
with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for name, data in sorted(files.items()):
        info = zipfile.ZipInfo(name, timestamp)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        archive.writestr(info, data)
PY

OUTPUT="$DIST_ROOT/$TARGET"
rm -rf "$OUTPUT"
mkdir -p "$OUTPUT/native"
cp "$NATIVE_LIBRARY" "$OUTPUT/native/"
cp "$HAR_STAGING" "$OUTPUT/notemeld-agent-sdk-${SDK_VERSION}.har"
cp agent-sdk/bindings/abi-v1.json "$OUTPUT/"
cp "$LICENSE_INVENTORY" "$OUTPUT/"

"$PYTHON_BIN" agent-sdk/scripts/verify-artifact-manifest.py create \
  --artifact-dir "$OUTPUT" \
  --target-triple "$TARGET" \
  --sdk-version "$SDK_VERSION" \
  --schema-version "$SCHEMA_VERSION" \
  --binding-version "$BINDING_VERSION" \
  --license-inventory-file "$OUTPUT/license-inventory.json" \
  --artifact "native-library=native/libnotemeld_agent.so" \
  --artifact "openharmony-har=notemeld-agent-sdk-${SDK_VERSION}.har" \
  --artifact "abi-contract=abi-v1.json" \
  --artifact "license-inventory=license-inventory.json"

"$PYTHON_BIN" agent-sdk/scripts/verify-artifact-manifest.py verify \
  --artifact-root "$OUTPUT" \
  --sdk-version "$SDK_VERSION" \
  --schema-version "$SCHEMA_VERSION" \
  --binding-version "$BINDING_VERSION" \
  --expected-target "$TARGET"
