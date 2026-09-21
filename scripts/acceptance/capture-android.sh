#!/usr/bin/env bash
set -euo pipefail

SERIAL=""
OUTPUT=""
REFERENCE=""
RC=""
COMMIT=""
CASE_ID=""
PAGE=""
ROUTE=""
REQUIREMENT_IDS=""
FEATURE_IDS=""
REQUIRED_LOCATORS=""
LOCATOR_CONTRACT="$(cd "$(dirname "$0")/../.." && pwd)/tests/visual/locator-contract.json"
for arg in "$@"; do
  case "$arg" in
    --serial=*) SERIAL="${arg#*=}" ;;
    --output=*) OUTPUT="${arg#*=}" ;;
    --reference=*) REFERENCE="${arg#*=}" ;;
    --rc=*) RC="${arg#*=}" ;;
    --commit=*) COMMIT="${arg#*=}" ;;
    --case=*) CASE_ID="${arg#*=}" ;;
    --page=*) PAGE="${arg#*=}" ;;
    --route=*) ROUTE="${arg#*=}" ;;
    --requirement-ids=*) REQUIREMENT_IDS="${arg#*=}" ;;
    --feature-ids=*) FEATURE_IDS="${arg#*=}" ;;
    --required-locators=*) REQUIRED_LOCATORS="${arg#*=}" ;;
    --locator-contract=*) LOCATOR_CONTRACT="${arg#*=}" ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done
for value in SERIAL OUTPUT REFERENCE RC COMMIT CASE_ID PAGE ROUTE REQUIREMENT_IDS FEATURE_IDS; do
  [[ -n "${!value}" ]] || { echo "--${value,,} is required" >&2; exit 2; }
done
command -v adb >/dev/null || { echo "adb is required" >&2; exit 2; }
[[ -f "$REFERENCE" ]] || { echo "reference image is required: $REFERENCE" >&2; exit 2; }
adb -s "$SERIAL" get-state >/dev/null 2>&1 || { echo "Android device is not online: $SERIAL" >&2; exit 2; }
if [[ -z "$REQUIRED_LOCATORS" ]]; then
  [[ -f "$LOCATOR_CONTRACT" ]] || { echo "Android locator contract is required: $LOCATOR_CONTRACT" >&2; exit 2; }
  REQUIRED_LOCATORS="$(python3 - "$LOCATOR_CONTRACT" "$PAGE" "$CASE_ID" <<'PY'
import json
import sys

path, page, case = sys.argv[1:]
with open(path, encoding="utf-8") as stream:
    data = json.load(stream)
locators = data.get("android_cases", {}).get(f"{page}/{case}")
if not isinstance(locators, list) or not locators or any(not isinstance(item, str) or not item for item in locators):
    raise SystemExit(f"no Android locator contract for {page}/{case}")
print(",".join(locators))
PY
)" || { echo "Android locator contract has no case mapping for ${PAGE}/${CASE_ID}" >&2; exit 2; }
fi
if adb -s "$SERIAL" reverse --list 2>/dev/null | grep -q .; then
  echo "adb reverse is forbidden for Android acceptance capture" >&2
  exit 3
fi
mkdir -p "$(dirname "$OUTPUT")"
adb -s "$SERIAL" exec-out screencap -p > "$OUTPUT"
[[ -s "$OUTPUT" ]] || { echo "screencap produced no bytes" >&2; exit 4; }
if [[ -n "$REQUIRED_LOCATORS" ]]; then
  UI_DUMP_REMOTE="/sdcard/notemeld-acceptance-ui.xml"
  UI_DUMP_LOCAL="${OUTPUT}.ui.xml"
  adb -s "$SERIAL" shell rm -f "$UI_DUMP_REMOTE"
  adb -s "$SERIAL" shell uiautomator dump "$UI_DUMP_REMOTE" >/dev/null
  adb -s "$SERIAL" exec-out cat "$UI_DUMP_REMOTE" > "$UI_DUMP_LOCAL"
  [[ -s "$UI_DUMP_LOCAL" ]] || { echo "uiautomator dump produced no bytes" >&2; exit 5; }
  IFS=',' read -r -a LOCATORS <<< "$REQUIRED_LOCATORS"
  for locator in "${LOCATORS[@]}"; do
    [[ -n "$locator" ]] || continue
    if ! grep -Fq -- "$locator" "$UI_DUMP_LOCAL"; then
      echo "required Android locator is missing: $locator" >&2
      exit 6
    fi
  done
fi
node "$(dirname "$0")/write-visual-manifest.mjs" \
  --output "$OUTPUT" --reference "$REFERENCE" --rc "$RC" --commit "$COMMIT" \
  --case "$CASE_ID" --page "$PAGE" --route "$ROUTE" --platform android \
  --requirement-ids "$REQUIREMENT_IDS" --feature-ids "$FEATURE_IDS" \
  --device "$SERIAL" --os android
