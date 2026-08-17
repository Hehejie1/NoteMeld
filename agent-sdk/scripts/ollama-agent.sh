#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$ROOT/bindings/python${PYTHONPATH:+:$PYTHONPATH}"
if [[ -z "${NOTEMELD_AGENT_SDK_LIBRARY:-}" ]]; then
  for candidate in "$ROOT/target/release/libnotemeld_agent.dylib" "$ROOT/target/debug/libnotemeld_agent.dylib" "$ROOT/target/release/libnotemeld_agent.so" "$ROOT/target/debug/libnotemeld_agent.so"; do
    if [[ -f "$candidate" ]]; then export NOTEMELD_AGENT_SDK_LIBRARY="$candidate"; break; fi
  done
fi
exec "${PYTHON:-python3}" -m notemeld_agent_sdk.ollama_cli "$@"
