$ErrorActionPreference = "Stop"

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")).Path

& (Join-Path $RootDir "scripts\desktop\packaging\scripts\build-backend-windows.ps1")

Push-Location (Join-Path $RootDir "desktop")
try {
  if (-not $env:TAURI_SIGNING_PRIVATE_KEY -and -not $env:TAURI_SIGNING_PRIVATE_KEY_PATH) {
    $DefaultUpdaterKey = Join-Path $HOME ".tauri\notemeld-updater.key"
    if (Test-Path $DefaultUpdaterKey) {
      $env:TAURI_SIGNING_PRIVATE_KEY_PATH = $DefaultUpdaterKey
    }
  }

  $UpdaterConfig = '{"bundle":{"createUpdaterArtifacts":false}}'
  if ($env:TAURI_SIGNING_PRIVATE_KEY -or $env:TAURI_SIGNING_PRIVATE_KEY_PATH) {
    $UpdaterConfig = '{"bundle":{"createUpdaterArtifacts":true}}'
    Write-Host "[notemeld] updater-signing=enabled"
  } else {
    Write-Host "[notemeld] updater-signing=disabled"
  }

  npx tauri build --no-bundle --config $UpdaterConfig
  npx tauri bundle --bundles msi --config $UpdaterConfig
} finally {
  Pop-Location
}
