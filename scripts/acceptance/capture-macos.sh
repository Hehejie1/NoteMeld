#!/usr/bin/env bash
set -euo pipefail

OUTPUT=""
REFERENCE=""
RECT=""
WINDOW_ID=""
RC=""
COMMIT=""
CASE_ID=""
PAGE=""
ROUTE=""
REQUIREMENT_IDS=""
FEATURE_IDS=""
for arg in "$@"; do
  case "$arg" in
    --output=*) OUTPUT="${arg#*=}" ;;
    --reference=*) REFERENCE="${arg#*=}" ;;
    --rect=*) RECT="${arg#*=}" ;;
    --window-id=*) WINDOW_ID="${arg#*=}" ;;
    --rc=*) RC="${arg#*=}" ;;
    --commit=*) COMMIT="${arg#*=}" ;;
    --case=*) CASE_ID="${arg#*=}" ;;
    --page=*) PAGE="${arg#*=}" ;;
    --route=*) ROUTE="${arg#*=}" ;;
    --requirement-ids=*) REQUIREMENT_IDS="${arg#*=}" ;;
    --feature-ids=*) FEATURE_IDS="${arg#*=}" ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done
for value in OUTPUT REFERENCE RC COMMIT CASE_ID PAGE ROUTE REQUIREMENT_IDS FEATURE_IDS; do
  [[ -n "${!value}" ]] || { echo "--${value,,} is required" >&2; exit 2; }
done
command -v screencapture >/dev/null || { echo "screencapture is required" >&2; exit 2; }
[[ -f "$REFERENCE" ]] || { echo "reference image is required: $REFERENCE" >&2; exit 2; }
if [[ -n "$RECT" && -n "$WINDOW_ID" ]]; then
  echo "choose only one of --rect=x,y,w,h or --window-id=id" >&2
  exit 2
fi
[[ -n "$RECT" || -n "$WINDOW_ID" ]] || { echo "a fixed --rect or --window-id is required" >&2; exit 2; }
mkdir -p "$(dirname "$OUTPUT")"
if [[ -n "$WINDOW_ID" ]]; then
  screencapture -x -l "$WINDOW_ID" "$OUTPUT"
else
  screencapture -x -R "$RECT" "$OUTPUT"
fi
[[ -s "$OUTPUT" ]] || { echo "screencapture produced no bytes" >&2; exit 4; }
node "$(dirname "$0")/write-visual-manifest.mjs" \
  --output "$OUTPUT" --reference "$REFERENCE" --rc "$RC" --commit "$COMMIT" \
  --case "$CASE_ID" --page "$PAGE" --route "$ROUTE" --platform macos \
  --requirement-ids "$REQUIREMENT_IDS" --feature-ids "$FEATURE_IDS" \
  --device "${WINDOW_ID:-$RECT}" --os macos
