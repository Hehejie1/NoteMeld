---
name: "notemeld-dmg-packaging"
description: "Use when packaging, uploading, or verifying NoteMeld macOS DMG releases for both Apple Silicon and Intel Macs."
---

# NoteMeld DMG Packaging

## Core Rule
Every NoteMeld DMG release means **both** macOS architectures:
- Apple Silicon / M series: `aarch64`
- Intel Mac: `x64`

Never upload a DMG after only `hdiutil verify`. A valid DMG can still contain a broken `NoteMeld.app`.

## Fixed Paths
- Repo: `/Users/bytedance/ai/NoteMeld`
- Build script: `/Users/bytedance/ai/NoteMeld/packaging/scripts/build-desktop-macos.sh`
- Apple Silicon DMG: `/Users/bytedance/ai/NoteMeld/desktop/src-tauri/target/aarch64-apple-darwin/release/bundle/dmg/NoteMeld_<version>_aarch64.dmg`
- Intel DMG: `/Users/bytedance/ai/NoteMeld/desktop/src-tauri/target/x86_64-apple-darwin/release/bundle/dmg/NoteMeld_<version>_x64.dmg`
- Intel Python: `/Users/bytedance/ai/NoteMeld/.venv-x64-003/bin/python`
- Server config: `/Users/bytedance/ai/cloud.txt`
- Remote release dir: `/srv/filebox/releases/notemeld/stable`
- Public base URL: `https://notemeld.wiki/releases/notemeld/stable`

## Required Gate
Before reporting success, every generated or downloaded DMG must pass:
- `hdiutil verify <dmg>`
- Mount DMG and run `codesign --verify --deep --strict <mount>/NoteMeld.app`
- Mount DMG and confirm `Applications -> /Applications` exists
- Confirm package architecture:
  - `aarch64` DMG contains `Mach-O thin (arm64)`
  - `x64` DMG contains `Mach-O thin (x86_64)`
- Public download must match local SHA256 and pass `hdiutil verify`

`spctl rejected` is allowed only for local ad-hoc test builds. It is never allowed for a server release.

## Intel Build Rule
Intel DMGs may be cross-built on Apple Silicon only if every x64 component is verified. Do not assume "built on M" means "works on Intel".

Required x64 checks:
- Main Tauri binary and backend sidecar are `x86_64`.
- Bundled FFmpeg/FFprobe are `x86_64`, executable, and pass `ffmpeg -version` / `ffprobe -version`.
- `otool -L` for bundled FFmpeg/FFprobe must not contain `/usr/local/Cellar`, `/usr/local/opt`, or `/opt/homebrew`.
- Use portable/self-contained FFmpeg runtime, not Homebrew-linked binaries.
- If an Intel Mac is available, final release acceptance must include install + first launch + deployment monitor check on that Intel Mac.

## Release Command
Use this for packages uploaded to the server:

```bash
NOTEMELD_CODESIGN_IDENTITY="Developer ID Application: <Name> (<TEAMID>)" \
NOTEMELD_NOTARY_PROFILE="notemeld-notary" \
/Users/bytedance/ai/NoteMeld/.trae/skills/notemeld-dmg-packaging/scripts/package-notemeld-dmg.sh --release --upload --public-verify
```

Release mode requires:
- Developer ID Application certificate in the macOS keychain
- notarytool keychain profile created with `xcrun notarytool store-credentials`
- `xcrun notarytool submit --wait`
- `xcrun stapler staple`
- `spctl -a -vv --type execute <mount>/NoteMeld.app` accepted
- `spctl -a -vv --type open <dmg>` accepted

## Local Test Command
Only use this for local verification, not for server releases:

```bash
/Users/bytedance/ai/NoteMeld/.trae/skills/notemeld-dmg-packaging/scripts/package-notemeld-dmg.sh
```

## What The Script Does
- Builds Apple Silicon DMG with `packaging/scripts/build-desktop-macos.sh`
- Builds Intel DMG with `NOTEMELD_TARGET_ARCH=x86_64` and the fixed x64 Python path
- Verifies both local DMGs with `hdiutil`
- Mounts both DMGs and verifies `NoteMeld.app` signatures
- In release mode, notarizes and staples both DMGs before upload
- Optionally uploads both DMGs atomically to the server
- Optionally downloads both public URLs and verifies full-file SHA256 + `hdiutil`

## Failure That Must Not Recur
The previous broken release had this pattern:

```text
hdiutil verify: VALID
codesign: code has no resources but signature indicates they must be present
macOS: "NoteMeld" 已损坏，无法打开
```

This skill prevents that by treating `codesign --verify --deep --strict` as a blocking release gate.

## If Gatekeeper Blocks
If a server release is blocked by Gatekeeper, treat it as a release failure. Do not tell users to work around it.

Allowed only for local ad-hoc test builds:

```bash
xattr -dr com.apple.quarantine /Applications/NoteMeld.app
```
