# Task 7 Report

Status: **DONE_WITH_CONCERNS**

Implementation checkpoint commit: `76afddaf866b6addb75ebd80e88d426b0ff03fcc` (`ci(agent-sdk): build and verify platform artifacts`). The final commit after attaching this ignored SDD report is reported to the parent task because a file cannot contain its own final Git object hash.

## AGENTS.md preflight

1. 影响模块：只新增独立 Agent SDK workflow、四个平台构建脚本、artifact manifest/license 校验器及其契约测试；不修改 Task 6 FFI/binding 生产代码，也不触碰 Host、DB、API、UI、CLI、desktop 或 MCP。
2. 既有类似能力：现有 `.github/workflows/release.yml` 构建桌面产物；Task 6 已有 ABI、四种 binding 与 harness，但没有 SDK artifact matrix、完整 target ledger 或跨 job manifest gate。
3. 产品规则：不冲突；本 Task 只分发同一 Rust Agent SDK 的平台包装，不创建第二套 Agent loop，也不访问知识库事实源。
4. 数据模型：不改 SQLite、文件事实源、状态流转或 API 语义。
5. Known pitfalls：保留现有 release workflow；所有脚本 fail closed，不伪造空产物，不记录 secret/payload；交叉编译不会被误报为 target runtime execution。
6. 数据/线上影响：本地只生成可删除的临时构建产物；新 workflow 尚未在 GitHub hosted runner 上执行，不发布 Release，也不写用户数据。
7. 最小改动：一个独立 workflow、四个 binding-specific build entry、一个 create/verify/license CLI、一个静态与行为契约文件。
8. 回归测试：workflow DAG/target/tooling、shell 失败策略、真实 manifest positive/negative、Cargo license inventory、重复 target/path、路径逃逸、checksum/version/target/expected coverage、现有 Python ABI oracle。

## Scope delivered

- `contracts` job first: focused artifact contracts plus locked Rust workspace build/test.
- Platform jobs second: five native host targets, two iOS targets, complete four-ABI Android set, and OpenHarmony ARM64.
- `verify-manifests` last: downloads every artifact and verifies the exact twelve-target set.
- Each manifest artifact entry carries `sdk_version`, `schema_version`, `target_triple`, `sha256`, and `binding_version`.
- Each target bundle includes a deterministic Cargo-derived SPDX license inventory. A dependency with no declared license fails packaging.
- Python wheel, XCFramework/package ZIP, AAR, and unsigned HAR containers use sorted entries and fixed `SOURCE_DATE_EPOCH` timestamps. Cargo/Gradle/Hvigor inputs and tool versions are locked or pinned by the workflow.
- The validator rejects missing fields/manifests/targets, unexpected or duplicate target manifests, duplicate artifact paths, path escape/symlink escape, absent/non-regular files, malformed or mismatched checksums, SDK/schema/binding mismatch, mixed targets, and license inventory mismatch.

## TDD evidence

The production files did not exist when the first test was run.

1. Initial behavior RED:

   `PYTHONPATH=backend python3 -m pytest backend/tests/test_agent_sdk_workflow_contracts.py -q`

   Result: **14 failed**. Failures named the missing workflow, all four build scripts, validator, target matrix, DAG, manifest fields, duplicate/path/checksum/version/coverage rejection.

2. Initial GREEN: the same focused command produced **14 passed**.
3. License inventory review RED: after adding license contracts first, **4 failed, 10 passed** because all build scripts lacked Cargo-derived inventory; implementation returned the suite to GREEN.
4. Reproducibility review RED: fixed timestamp/deterministic repack contracts produced **7 failed, 12 passed**; adding `SOURCE_DATE_EPOCH` and deterministic ZIP writers returned GREEN.
5. Real `cargo rustc` probe exposed a genuine packaging defect: compilation succeeded, but `release/libnotemeld_agent.a` did not exist; Cargo emitted the added staticlib at `release/deps/libnotemeld_agent.a`. A focused contract failed first, then the Swift packager was corrected and the real iOS device archive was confirmed non-empty.
6. OpenHarmony archive-permission review RED: the workflow lacked permission restoration for executables extracted from ZIP. The focused contract failed first; the workflow now finds then `chmod +x` checksummed clang/ar/ohpm/hvigor tools.
7. Final focused GREEN: **20 passed in 1.10s**.

## Platform evidence ledger

| Target(s) | Build/package gate | Runtime evidence in this task |
|---|---|---|
| macOS x64/arm64 | real locked Cargo build + Python wheel/native bundle | host-matching matrix job runs Python fake-turn; cross slice logs build-only accurately |
| Windows x64 | real locked Cargo build + Python wheel/native bundle | Windows hosted matrix job runs Python fake-turn |
| Linux x64/arm64 | real locked Cargo build; ARM uses `gcc-aarch64-linux-gnu` | x64 hosted job runs fake-turn; ARM cross job is build-only |
| iOS device/simulator ARM64 | real `cargo rustc` static slices + `xcodebuild -create-xcframework` + Swift package build | build/package only; no simulator/device process is claimed |
| Android armv7/arm64/x86/x86_64 | pinned JDK/Gradle/SDK/build-tools/CMake/NDK + `cargo-ndk` + AAR | x86_64 hosted emulator runs `connectedAndroidTest`; the other ABIs are real build evidence, not runtime evidence |
| OpenHarmony ARM64 | checksummed official SDK/tools + Rust OHOS target + `ohpm install` + `hvigor assembleHar` | build/package only; no hosted OpenHarmony device runtime is claimed |

Local real probes:

- Isolated official Cargo cache, locked/offline `cargo rustc` for `x86_64-apple-darwin`: succeeded; static archive observed under `release/deps`.
- The same command for `aarch64-apple-ios`: succeeded; `file` reported `current ar archive` for the non-empty staticlib.
- `swift build --package-path agent-sdk/bindings/swift`: succeeded earlier in this task; the generated `.build` directory was removed and not committed.
- No GitHub Actions run is claimed. Android SDK/emulator and OpenHarmony `ohpm`/`hvigor` were unavailable locally.

## Verification

- `PYTHONPATH=backend python3 -m pytest backend/tests/test_agent_sdk_workflow_contracts.py -q` → **20 passed**.
- PyYAML `BaseLoader` parse plus exact job/`needs` assertions → `workflow YAML parse: OK`.
- `bash -n` over all four build scripts → passed.
- `python3 -m py_compile` over validator/test → passed; generated caches removed.
- Manual manifest `create` and positive `verify` → 1 manifest / 2 artifacts / expected Linux target.
- Manual checksum corruption → rejected with `checksum mismatch for abi-v1.json`.
- Existing `test_abi_contract.py` oracle → **2 passed**.
- `git diff --cached --check` → passed; executable modes are `100755` for all scripts and validator.

## Security, self-review, and limitations

- No raw prompt, provider credential, token, callback payload, or local absolute developer path is placed in workflow artifacts or logs.
- Downloads for OpenHarmony are fail-closed and SHA-256 checked before extraction. The workflow requires repository variables `OPENHARMONY_SDK_URL`, `OPENHARMONY_COMMANDLINE_TOOLS_URL`, `OPENHARMONY_SDK_SHA256`, and `OPENHARMONY_COMMANDLINE_TOOLS_SHA256`; until maintainers set them to pinned official archives, that job will intentionally fail rather than silently use an untrusted/latest toolchain.
- The local user Cargo hierarchy replaces crates.io with an unavailable Tuna mirror. It was not edited. Real probes used the pre-existing isolated official cache from `/tmp`; CI uses a clean runner.
- Android runtime coverage is x86_64 instrumentation only. OpenHarmony and iOS jobs provide real target builds/packages but not device execution. These are explicit remaining platform-evidence limits, not passing runtime claims.
- No Task 6 production file, Task 8+ file, current release workflow, or concurrent whiteboard file was staged. `git status --short` was clean after the implementation commit.
- System documentation synchronization remains the approved plan's Task 19; this Task establishes the executable evidence gate only.

Rollback is to disable/remove the new standalone `agent-sdk.yml` and its new scripts/tests. No schema, stored conversation, note, or existing release artifact needs migration or recovery.
