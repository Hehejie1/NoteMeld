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
OHOS_SDK_ROOT="${OHOS_SDK_ROOT:?set OHOS_SDK_ROOT to the complete unpacked OpenHarmony SDK root}"
OHOS_SDK_NATIVE="${OHOS_SDK_NATIVE:?set OHOS_SDK_NATIVE to the unpacked OpenHarmony native SDK directory}"
SYSROOT="$OHOS_SDK_NATIVE/sysroot"
export OHOS_SDK_ROOT DEVECO_SDK_HOME="$OHOS_SDK_ROOT" HOS_SDK_HOME="$OHOS_SDK_ROOT"

command -v "$OHPM_BIN" >/dev/null
command -v "$HVIGOR_BIN" >/dev/null
if [[ ! -d "$OHOS_SDK_ROOT" || ! -d "$OHOS_SDK_NATIVE" ]]; then
  echo "OpenHarmony SDK root/native directories do not exist" >&2
  exit 2
fi
for sdk_component in ets native toolchains; do
  if [[ ! -d "$OHOS_SDK_ROOT/$sdk_component" ]]; then
    echo "OpenHarmony SDK is missing $OHOS_SDK_ROOT/$sdk_component" >&2
    exit 2
  fi
done
SDK_DESCRIPTOR="$OHOS_SDK_ROOT/toolchains/oh-uni-package.json"
if [[ ! -f "$SDK_DESCRIPTOR" ]]; then
  echo "OpenHarmony SDK is missing $SDK_DESCRIPTOR" >&2
  exit 2
fi
OHOS_API_VERSION="$("$PYTHON_BIN" - "$SDK_DESCRIPTOR" <<'PY'
import json
from pathlib import Path
import sys

document = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
api_version = document.get("apiVersion")
if isinstance(api_version, int):
    value = str(api_version)
elif isinstance(api_version, str) and api_version.isdigit():
    value = api_version
else:
    raise SystemExit("OpenHarmony toolchains descriptor has invalid apiVersion")
print(value)
PY
)"
export OHOS_API_VERSION
CLANG="$OHOS_SDK_NATIVE/llvm/bin/clang"
AR="$OHOS_SDK_NATIVE/llvm/bin/llvm-ar"
if [[ ! -x "$CLANG" || ! -x "$AR" || ! -d "$SYSROOT" ]]; then
  echo "OpenHarmony native LLVM toolchain is incomplete: $OHOS_SDK_NATIVE" >&2
  exit 2
fi
case "$(cd "$OHOS_SDK_NATIVE" && pwd -P)" in
  "$(cd "$OHOS_SDK_ROOT" && pwd -P)"/*) ;;
  *) echo "OHOS_SDK_NATIVE must be inside OHOS_SDK_ROOT" >&2; exit 2 ;;
esac

LINKER_WRAPPER="$CARGO_TARGET_DIR/aarch64-unknown-linux-ohos-clang.sh"
mkdir -p "$CARGO_TARGET_DIR"
"$PYTHON_BIN" - "$LINKER_WRAPPER" "$CLANG" "$SYSROOT" <<'PY'
from pathlib import Path
import shlex
import sys

wrapper = Path(sys.argv[1])
clang = shlex.quote(sys.argv[2])
sysroot = shlex.quote(sys.argv[3])
wrapper.write_text(
    f"#!/usr/bin/env bash\nexec {clang} --target=aarch64-linux-ohos "
    f"--sysroot={sysroot} -D__MUSL__=1 \"$@\"\n"
)
wrapper.chmod(0o755)
PY
export CARGO_TARGET_AARCH64_UNKNOWN_LINUX_OHOS_LINKER="$LINKER_WRAPPER"
export CARGO_TARGET_AARCH64_UNKNOWN_LINUX_OHOS_AR="$AR"
export CC_aarch64_unknown_linux_ohos="$CLANG --target=aarch64-linux-ohos --sysroot=$SYSROOT -D__MUSL__=1"
export AR_aarch64_unknown_linux_ohos="$AR"
export CFLAGS_aarch64_unknown_linux_ohos="--target=aarch64-linux-ohos --sysroot=$SYSROOT -fPIC -D__MUSL__=1"

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
  --cargo-metadata "$LICENSE_METADATA" \
  --cargo-lock agent-sdk/Cargo.lock \
  --root-package agent-ffi \
  --output "$LICENSE_INVENTORY"

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

"$PYTHON_BIN" - "$PROJECT" "$SDK_VERSION" "$OHOS_SDK_ROOT" \
  "$OHOS_API_VERSION" <<'PY'
from pathlib import Path
import sys

project = Path(sys.argv[1])
version = sys.argv[2]
sdk_root = Path(sys.argv[3])
api_version = int(sys.argv[4])
module = project / "notemeld-agent"
(project / "local.properties").write_text(
    f"sdk.dir={sdk_root.as_posix()}\nhwsdk.dir={sdk_root.as_posix()}\n"
)
(project / "oh-package.json5").write_text("""{
  modelVersion: '5.0.0',
  devDependencies: {
    '@ohos/hvigor': '5.0.2',
    '@ohos/hvigor-ohos-plugin': '5.0.2'
  }
}\n""")
(project / "build-profile.json5").write_text(f"""{{
  app: {{ products: [{{
    name: 'default', compileSdkVersion: {api_version},
    compatibleSdkVersion: {api_version}, runtimeOS: 'OpenHarmony'
  }}] }},
  modules: [{{
    name: 'notemeld-agent', srcPath: './notemeld-agent',
    targets: [{{ name: 'default', applyToProducts: ['default'] }}]
  }}]
}}\n""")
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
"$PYTHON_BIN" - "$HAR_SOURCE" "$HAR_STAGING" "$SOURCE_DATE_EPOCH" \
  "$SDK_VERSION" "$SCHEMA_VERSION" "$BINDING_VERSION" "$TARGET" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import json
import sys
import zipfile

source = Path(sys.argv[1])
output = Path(sys.argv[2])
epoch = max(315532800, int(sys.argv[3]))
sdk, schema, binding, target = sys.argv[4:]
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
for required in ("libnotemeld_agent.so", "libnotemeld_agent_napi.so"):
    if not any(name.endswith(required) for name in files):
        raise SystemExit(f"Hvigor HAR is missing native library: {required}")
if not any(name.endswith("Index.ets") or name.endswith("index.ets") for name in files):
    raise SystemExit("Hvigor HAR is missing ArkTS binding")
files["notemeld-agent-sdk.json"] = json.dumps({
    "sdk_version": sdk,
    "schema_version": schema,
    "binding_version": binding,
    "target_triples": [target],
}, sort_keys=True).encode()
files["notemeld-agent-abi.json"] = Path(
    "agent-sdk/bindings/abi-v1.json"
).read_bytes()
with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for name, data in sorted(files.items()):
        info = zipfile.ZipInfo(name, timestamp)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        archive.writestr(info, data)
PY

CONSUMER_PROJECT="$CARGO_TARGET_DIR/harmony-har-consumer"
CONSUMER_MODULE="$CONSUMER_PROJECT/consumer"
rm -rf "$CONSUMER_PROJECT"
mkdir -p "$CONSUMER_PROJECT/hvigor" "$CONSUMER_MODULE/src/main/ets"
"$PYTHON_BIN" - "$CONSUMER_PROJECT" "$HAR_STAGING" "$OHOS_SDK_ROOT" \
  "$OHOS_API_VERSION" <<'PY'
from pathlib import Path
import sys

project = Path(sys.argv[1])
har = Path(sys.argv[2])
sdk_root = Path(sys.argv[3])
api_version = int(sys.argv[4])
module = project / "consumer"
(project / "local.properties").write_text(
    f"sdk.dir={sdk_root.as_posix()}\nhwsdk.dir={sdk_root.as_posix()}\n"
)
(project / "oh-package.json5").write_text("""{
  modelVersion: '5.0.0',
  devDependencies: {
    '@ohos/hvigor': '5.0.2',
    '@ohos/hvigor-ohos-plugin': '5.0.2'
  }
}\n""")
(project / "build-profile.json5").write_text(f"""{{
  app: {{ products: [{{
    name: 'default', compileSdkVersion: {api_version},
    compatibleSdkVersion: {api_version}, runtimeOS: 'OpenHarmony'
  }}] }},
  modules: [{{
    name: 'consumer', srcPath: './consumer',
    targets: [{{ name: 'default', applyToProducts: ['default'] }}]
  }}]
}}\n""")
(project / "hvigorfile.ts").write_text("""import { appTasks } from '@ohos/hvigor-ohos-plugin';
export default { system: appTasks, plugins: [] };
""")
(project / "hvigor" / "hvigor-config.json5").write_text("{ modelVersion: '5.0.0', dependencies: {} }\n")
(module / "oh-package.json5").write_text(f"""{{
  name: 'notemeld-agent-harmony-harness', version: '0.1.0', type: 'module',
  main: 'Index.ets', dependencies: {{ '@notemeld/agent-sdk': 'file:{har.as_posix()}' }}
}}\n""")
(module / "build-profile.json5").write_text("""{
  apiType: 'stageMode', targets: [{ name: 'default' }]
}\n""")
(module / "hvigorfile.ts").write_text("""import { harTasks } from '@ohos/hvigor-ohos-plugin';
export default { system: harTasks, plugins: [] };
""")
(module / "src" / "main" / "module.json5").write_text("""{
  module: { name: 'notemeld_agent_consumer', type: 'har', deviceTypes: ['default'] }
}\n""")
(module / "src" / "main" / "ets" / "Index.ets").write_text("""import { SDK_VERSION, SCHEMA_VERSION } from '@notemeld/agent-sdk';
export const consumedVersions: string = `${SDK_VERSION}/${SCHEMA_VERSION}`;
""")
PY
(cd "$CONSUMER_PROJECT" && "$OHPM_BIN" install)
(cd "$CONSUMER_PROJECT" && "$HVIGOR_BIN" --mode module \
  -p module=consumer@default -p product=default assembleHar --no-daemon)
CONSUMER_HAR="$(find "$CONSUMER_MODULE/build" -name '*.har' -type f -print -quit)"
if [[ -z "$CONSUMER_HAR" || ! -f "$CONSUMER_HAR" ]]; then
  echo "OpenHarmony HAR consumer build did not produce a HAR" >&2
  exit 5
fi

OUTPUT="$DIST_ROOT/$TARGET"
rm -rf "$OUTPUT"
mkdir -p "$OUTPUT/native"
cp "$NATIVE_LIBRARY" "$OUTPUT/native/"
cp "$HAR_STAGING" "$OUTPUT/notemeld-agent-sdk-${SDK_VERSION}.har"
cp agent-sdk/bindings/abi-v1.json "$OUTPUT/"
cp "$LICENSE_INVENTORY" "$OUTPUT/"
cp agent-sdk/Cargo.lock "$OUTPUT/"

"$PYTHON_BIN" agent-sdk/scripts/verify-artifact-manifest.py create \
  --artifact-dir "$OUTPUT" \
  --target-triple "$TARGET" \
  --sdk-version "$SDK_VERSION" \
  --schema-version "$SCHEMA_VERSION" \
  --binding-version "$BINDING_VERSION" \
  --license-inventory-file "$OUTPUT/license-inventory.json" \
  --cargo-lock-file "$OUTPUT/Cargo.lock" \
  --artifact "native-library=native/libnotemeld_agent.so" \
  --artifact "openharmony-har=notemeld-agent-sdk-${SDK_VERSION}.har" \
  --artifact "abi-contract=abi-v1.json" \
  --artifact "license-inventory=license-inventory.json" \
  --artifact "cargo-lock=Cargo.lock"

"$PYTHON_BIN" agent-sdk/scripts/verify-artifact-manifest.py verify \
  --artifact-root "$OUTPUT" \
  --sdk-version "$SDK_VERSION" \
  --schema-version "$SCHEMA_VERSION" \
  --binding-version "$BINDING_VERSION" \
  --expected-cargo-metadata "$LICENSE_METADATA" \
  --expected-cargo-lock agent-sdk/Cargo.lock \
  --root-package agent-ffi \
  --expected-target "$TARGET"
