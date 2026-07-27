#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]] || ! "$PYTHON_BIN" -m pytest --version >/dev/null 2>&1; then
  PYTHON_BIN="python3"
fi

PYTHONPATH=backend "$PYTHON_BIN" -m pytest \
  backend/tests/test_core_runtime_contracts.py \
  backend/tests/test_core_migration_contracts.py \
  backend/tests/test_core_migration_api_contracts.py -q
node frontend/tests/chatStreamApiBaseUrl.test.mjs
node frontend/tests/runtimeContracts.test.mjs
node frontend/tests/backendInitProviderContracts.test.mjs
node frontend/tests/noteTaskPendingUi.test.mjs
node frontend/tests/dataMigrationRouteContracts.test.mjs
node frontend/tests/dataMigrationServiceContracts.test.mjs
node frontend/tests/dataMigrationPageContracts.test.mjs
