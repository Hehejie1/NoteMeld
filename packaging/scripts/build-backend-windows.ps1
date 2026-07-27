$ErrorActionPreference = "Stop"

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$PythonBin = Join-Path $RootDir ".venv\Scripts\python.exe"
$DistBin = Join-Path $RootDir "dist\notemeld-backend.exe"
$BackendStageDir = Join-Path $RootDir "desktop\src-tauri\bin\backend"
$BackendStageBin = Join-Path $BackendStageDir "notemeld-backend.exe"
$BackendUnixStageBin = Join-Path $BackendStageDir "notemeld-backend"
$FfmpegStageDir = Join-Path $RootDir "desktop\src-tauri\resources\ffmpeg"
$FfmpegArchive = Join-Path $FfmpegStageDir "ffmpeg-runtime-windows.zip"

if (-not (Test-Path $PythonBin)) {
  $PythonBin = (Get-Command python).Source
}

$ffmpegSourceDir = $env:FFMPEG_BIN_PATH
if (-not $ffmpegSourceDir) {
  $ffmpegCommand = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
  if ($ffmpegCommand) {
    $ffmpegSourceDir = Split-Path $ffmpegCommand.Source -Parent
  }
}

if (
  -not $ffmpegSourceDir -or
  -not (Test-Path (Join-Path $ffmpegSourceDir "ffmpeg.exe")) -or
  -not (Test-Path (Join-Path $ffmpegSourceDir "ffprobe.exe"))
) {
  throw "expected ffmpeg.exe and ffprobe.exe in FFMPEG_BIN_PATH or PATH before desktop packaging"
}

Push-Location $RootDir
try {
  $env:NOTEMELD_ROOT_DIR = $RootDir
  & $PythonBin -m PyInstaller packaging/backend/pyinstaller/backend.spec
} finally {
  Pop-Location
}

if (-not (Test-Path $DistBin)) {
  throw "expected backend binary not found at $DistBin"
}

New-Item -ItemType Directory -Force -Path $BackendStageDir | Out-Null
Remove-Item $BackendStageBin, $BackendUnixStageBin -Force -ErrorAction SilentlyContinue
Copy-Item $DistBin $BackendStageBin -Force
Copy-Item $DistBin $BackendUnixStageBin -Force

New-Item -ItemType Directory -Force -Path $FfmpegStageDir | Out-Null
Remove-Item `
  $FfmpegArchive `
  -Force -ErrorAction SilentlyContinue
$TempFfmpegDir = Join-Path ([System.IO.Path]::GetTempPath()) ("notemeld-ffmpeg-" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $TempFfmpegDir | Out-Null
Copy-Item (Join-Path $ffmpegSourceDir "ffmpeg.exe") (Join-Path $TempFfmpegDir "ffmpeg.exe") -Force
Copy-Item (Join-Path $ffmpegSourceDir "ffprobe.exe") (Join-Path $TempFfmpegDir "ffprobe.exe") -Force
Compress-Archive -Path (Join-Path $TempFfmpegDir "*") -DestinationPath $FfmpegArchive -Force
Remove-Item $TempFfmpegDir -Recurse -Force

Write-Host "staged backend sidecar at $BackendStageBin"
Write-Host "staged ffmpeg runtime archive at $FfmpegArchive"
