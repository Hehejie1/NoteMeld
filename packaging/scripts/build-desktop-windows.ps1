$ErrorActionPreference = "Stop"

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

& (Join-Path $RootDir "packaging\scripts\build-backend-windows.ps1")

Push-Location (Join-Path $RootDir "desktop")
try {
  if (-not $env:TAURI_SIGNING_PRIVATE_KEY -and -not $env:TAURI_SIGNING_PRIVATE_KEY_PATH) {
    $DefaultUpdaterKey = Join-Path $HOME ".tauri\notemeld-updater.key"
    if (Test-Path $DefaultUpdaterKey) {
      $env:TAURI_SIGNING_PRIVATE_KEY_PATH = $DefaultUpdaterKey
    }
  }

  npx tauri build --no-bundle
  npx tauri bundle --bundles msi
} finally {
  Pop-Location
}
