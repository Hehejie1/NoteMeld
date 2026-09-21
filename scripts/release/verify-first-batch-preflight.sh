#!/usr/bin/env bash
set -euo pipefail

# Automated compatibility preflight for the legacy first-batch release path.
# The authoritative Cloud / macOS x64 / Android release scope is the 56-gate
# ledger checked below; this script never turns live evidence into approval.
# This intentionally does not claim the production and physical-device gates:
# those require the four-role topology documented in the release ledger.

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
sdk_root="${NOTEMELD_AGENT_SDK_DIR:-$repo_root/../packages/notemeld-agent-sdk}"
require_clean=0

usage() {
  cat <<'EOF'
Usage: scripts/release/verify-first-batch-preflight.sh [--rc]

  --rc  Require a clean NoteMeld commit before running the release preflight.

Set NOTEMELD_AGENT_SDK_DIR to override the sibling Agent SDK checkout.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --rc)
      require_clean=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "first-batch-preflight: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

cd "$repo_root"

if [[ "$require_clean" -eq 1 ]] && [[ -n "$(git status --porcelain)" ]]; then
  echo "first-batch-preflight: RC mode requires a clean NoteMeld worktree" >&2
  exit 2
fi

python_bin="$repo_root/.venv/bin/python"
if [[ ! -x "$python_bin" ]] || ! "$python_bin" -m pytest --version >/dev/null 2>&1; then
  python_bin="python3"
fi

if [[ ! -f "$sdk_root/Cargo.toml" ]]; then
  echo "first-batch-preflight: Agent SDK checkout not found at $sdk_root" >&2
  exit 2
fi

sdk_aar="$sdk_root/target/notemeld-agent-sdk-0.1.0.aar"
sdk_aar_sha256="e4f8acd6a2217b8fce683c26de2823b4407ebb8b5d9fa58c804c6142cc7fc2c0"
if [[ ! -f "$sdk_aar" ]]; then
  echo "first-batch-preflight: pinned Agent SDK AAR not found at $sdk_aar" >&2
  exit 2
fi
if [[ "$(shasum -a 256 "$sdk_aar" | awk '{print $1}')" != "$sdk_aar_sha256" ]]; then
  echo "first-batch-preflight: pinned Agent SDK AAR hash mismatch" >&2
  exit 2
fi

run_step() {
  local label="$1"
  shift
  echo
  echo "==> $label"
  "$@"
}

run_step "Product documentation registry" \
  python3 scripts/cloud/validate_product_docs.py

run_step "Desktop backend tests" \
  env PYTHONPATH=desktop/backend "$python_bin" -m pytest desktop/backend/tests -q

run_step "Desktop frontend TypeScript contracts" \
  bash -c 'cd "$1" && corepack pnpm test:contracts' _ "$repo_root/desktop/frontend"

run_step "Desktop frontend Node contracts" \
  bash -c 'cd "$1" && node --test tests/*.test.mjs' _ "$repo_root/desktop/frontend"

run_step "Desktop frontend production build" \
  bash -c 'cd "$1" && corepack pnpm build' _ "$repo_root/desktop/frontend"

run_step "Android tests and debug build" \
  env NOTEMELD_AGENT_SDK_AAR="$sdk_aar" NOTEMELD_AGENT_SDK_AAR_SHA256="$sdk_aar_sha256" \
  bash -c 'cd "$1" && ./gradlew test assembleDebug --no-daemon' _ "$repo_root/android"

run_step "Agent SDK formatting" \
  bash -c 'cd "$1" && cargo fmt --all --check' _ "$sdk_root"

run_step "Agent SDK workspace tests" \
  bash -c 'cd "$1" && cargo test --workspace --locked' _ "$sdk_root"

run_step "Cloud/macOS x64/Android 56-gate ledger report" \
  "$python_bin" scripts/acceptance/verify-release-ledger.py \
  docs/superpowers/tests/2026-09-13-cloud-macos-x64-android-agent-release-ledger.json --report

echo
echo "first-batch-preflight: automated checks passed"
echo "first-batch-preflight: release is NOT approved until all 56 Cloud/macOS x64/Android P0 checks are PASS"
echo "first-batch-preflight: legacy 19-gate Windows evidence is not valid macOS release evidence"
