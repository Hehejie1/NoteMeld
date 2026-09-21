# Physical mobile device gate

`verify-real-device-matrix.sh` is the fail-closed preflight for the final M01/M02 acceptance. It deliberately refuses Android emulators and iOS Simulators, then installs and launches the Android APK, iOS `.app`, and Harmony `.hap` on connected physical targets.

Example on a Mac with all three devices trusted and connected:

```bash
export NOTEMELD_IOS_DEVICE_UDID="<physical iOS UDID>"
export HDC_BIN="/path/to/OpenHarmony/sdk/toolchains/hdc"
export NOTEMELD_ANDROID_APK="/path/to/app-debug.apk"
export NOTEMELD_IOS_APP="/path/to/NoteMeldMobile.app"
export NOTEMELD_HAP="/path/to/entry-default-signed.hap"
scripts/mobile/verify-real-device-matrix.sh
```

The command exits with status `2` when a required physical target is absent. A passing install/launch check is necessary but not sufficient to change `M01.home` or `M02.session` to `implemented`; the same device set must then complete the LAN-first, Relay fallback, E2EE receipt, offline/reconnect, and cursor-continuity matrix against the configured Cloud environment.
