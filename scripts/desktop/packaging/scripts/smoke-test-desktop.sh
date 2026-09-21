#!/usr/bin/env bash
set -euo pipefail

BACKEND_URL="${1:-http://127.0.0.1:8483}"

curl -fsS "${BACKEND_URL}/api/sys_check"
