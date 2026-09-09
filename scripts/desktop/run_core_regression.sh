#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]] || ! "$PYTHON_BIN" -m pytest --version >/dev/null 2>&1; then
  PYTHON_BIN="python3"
fi

PYTHONPATH=desktop/backend "$PYTHON_BIN" -m pytest \
  desktop/backend/tests/test_core_runtime_contracts.py \
  desktop/backend/tests/test_core_migration_contracts.py \
  desktop/backend/tests/test_core_migration_api_contracts.py -q
node desktop/frontend/tests/chatStreamApiBaseUrl.test.mjs
node desktop/frontend/tests/runtimeContracts.test.mjs
node desktop/frontend/tests/backendInitProviderContracts.test.mjs
node desktop/frontend/tests/noteTaskPendingUi.test.mjs
node desktop/frontend/tests/dataMigrationRouteContracts.test.mjs
node desktop/frontend/tests/dataMigrationServiceContracts.test.mjs
node desktop/frontend/tests/dataMigrationPageContracts.test.mjs
