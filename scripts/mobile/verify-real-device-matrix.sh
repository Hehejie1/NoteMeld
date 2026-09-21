#!/usr/bin/env bash
set -euo pipefail

# Fail-closed acceptance gate for the physical-device portion of M01/M02.
# This script intentionally rejects Android/iOS simulators and OpenHarmony
# targets are required to be supplied by hdc. It does not change registry
# status by itself; the resulting logs must be reviewed with the relay matrix.

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
apk_path="${NOTEMELD_ANDROID_APK:-$repo_root/android/app/build/outputs/apk/debug/app-debug.apk}"
ios_app="${NOTEMELD_IOS_APP:-$repo_root/ios/build/physical/Build/Products/Debug-iphoneos/NoteMeldMobile.app}"
hap_path="${NOTEMELD_HAP:-$repo_root/harmony/entry/build/default/outputs/default/entry-default-signed.hap}"
package_name="com.notemeld.mobile"

die() {
  echo "real-device-matrix: $*" >&2
  exit 2
}

require_file() {
  [[ -f "$1" || -d "$1" ]] || die "missing artifact: $1 (set the corresponding NOTEMELD_* variable)"
}

find_android_device() {
  command -v adb >/dev/null 2>&1 || die "adb is not installed"
  local serial qemu
  while read -r serial _; do
    [[ -n "${serial:-}" && "$serial" != "List" && "$serial" != "*" ]] || continue
    [[ "$serial" != emulator-* ]] || continue
    qemu="$(adb -s "$serial" shell getprop ro.kernel.qemu 2>/dev/null | tr -d '\r')"
    [[ "$qemu" != "1" ]] || continue
    printf '%s\n' "$serial"
    return 0
  done < <(adb devices 2>/dev/null)
  die "no physical Android device found; simulators/emulators are intentionally rejected"
}

find_ios_device() {
  command -v xcrun >/dev/null 2>&1 || die "xcrun is not installed"
  local udid="${NOTEMELD_IOS_DEVICE_UDID:-}"
  [[ -n "$udid" ]] || die "set NOTEMELD_IOS_DEVICE_UDID to a trusted physical iOS device UDID"
  xcrun devicectl list devices 2>/dev/null | grep -F "$udid" | grep -Eiq 'connected|available' \
    || die "iOS device $udid is not connected/available through devicectl"
  printf '%s\n' "$udid"
}

find_harmony_device() {
  local hdc="${HDC_BIN:-hdc}"
  command -v "$hdc" >/dev/null 2>&1 || die "hdc is not installed (set HDC_BIN to the OpenHarmony SDK tool)"
  local target
  target="$("$hdc" list targets 2>/dev/null | awk 'NF && $0 !~ /^\[Empty\]$/ {print $1; exit}')"
  [[ -n "$target" ]] || die "no physical OpenHarmony device found through hdc"
  printf '%s\n' "$target"
}

android_smoke() {
  local serial="$1" log_file
  require_file "$apk_path"
  log_file="$(mktemp -t notemeld-android-real.XXXXXX.log)"
  trap 'rm -f "$log_file"' RETURN
  adb -s "$serial" install -r "$apk_path"
  adb -s "$serial" shell am force-stop "$package_name"
  adb -s "$serial" logcat -c
  adb -s "$serial" shell am start -n "$package_name/.MainActivity"
  sleep 5
  adb -s "$serial" logcat -d -t 1200 >"$log_file"
  if grep -Eqi 'FATAL EXCEPTION|AndroidRuntime.*(crash|fatal)' "$log_file"; then
    cat "$log_file" >&2
    die "Android physical-device launch reported a fatal runtime error"
  fi
  adb -s "$serial" shell dumpsys activity activities | grep -q "$package_name/.MainActivity" \
    || die "Android physical-device MainActivity is not foreground"
  echo "Android physical device $serial: install/launch passed"
}

ios_smoke() {
  local udid="$1"
  require_file "$ios_app"
  xcrun devicectl device install app --device "$udid" "$ios_app"
  xcrun devicectl device process launch --device "$udid" "$package_name"
  echo "iOS physical device $udid: install/launch command passed"
}

harmony_smoke() {
  local target="$1" hdc="${HDC_BIN:-hdc}"
  require_file "$hap_path"
  "$hdc" -t "$target" install -r "$hap_path"
  "$hdc" -t "$target" shell aa start -a EntryAbility -b "$package_name"
  echo "Harmony physical device $target: install/launch command passed"
}

android_device="$(find_android_device)"
ios_device="$(find_ios_device)"
harmony_device="$(find_harmony_device)"

android_smoke "$android_device"
ios_smoke "$ios_device"
harmony_smoke "$harmony_device"
echo "real-device-matrix: install/launch gate passed for all three physical platforms"
