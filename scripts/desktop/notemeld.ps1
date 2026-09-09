param(
  [Parameter(Position = 0)]
  [string]$Command = "start"
)

$ErrorActionPreference = "Stop"

$NotemeldHome = if ($env:NOTEMELD_HOME) { $env:NOTEMELD_HOME } else { Join-Path $env:USERPROFILE ".notemeld" }
$AppDir = if ($env:NOTEMELD_APP_DIR) { $env:NOTEMELD_APP_DIR } else { Join-Path $NotemeldHome "app" }
$DataRoot = Join-Path $AppDir "desktop\data"
$LogDir = Join-Path $AppDir "desktop\logs"
$ModelDir = Join-Path $DataRoot "models"
$RunDir = Join-Path $DataRoot "run"

$BackendPort = if ($env:NOTEMELD_BACKEND_PORT) { [int]$env:NOTEMELD_BACKEND_PORT } else { 8483 }
$FrontendPort = if ($env:NOTEMELD_FRONTEND_PORT) { [int]$env:NOTEMELD_FRONTEND_PORT } else { 3015 }

$BackendLog = Join-Path $LogDir "backend.log"
$BackendErrLog = Join-Path $LogDir "backend.err.log"
$FrontendLog = Join-Path $LogDir "frontend.log"
$FrontendErrLog = Join-Path $LogDir "frontend.err.log"
$BackendPidFile = Join-Path $RunDir "backend.pid"
$FrontendPidFile = Join-Path $RunDir "frontend.pid"
$BackendRunner = Join-Path $RunDir "backend.ps1"
$FrontendRunner = Join-Path $RunDir "frontend.ps1"

function Log {
  param([string]$Message)
  Write-Host "[NoteMeld] $Message"
}

function Warn {
  param([string]$Message)
  Write-Warning "[NoteMeld] $Message"
}

function Fail {
  param([string]$Message)
  Write-Error "[NoteMeld] ERROR: $Message"
  exit 1
}

function Require-Command {
  param([string]$Name)
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    Fail "Missing required command: $Name"
  }
}

function Quote-PsString {
  param([string]$Value)
  return "'" + ($Value -replace "'", "''") + "'"
}

function Test-PortInUse {
  param([int]$Port)

  $client = New-Object System.Net.Sockets.TcpClient
  try {
    $async = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
    if (-not $async.AsyncWaitHandle.WaitOne(250)) {
      return $false
    }
    $client.EndConnect($async)
    return $true
  } catch {
    return $false
  } finally {
    $client.Close()
  }
}

function Wait-ForUrl {
  param([string]$Url, [int]$Retries = 60, [int]$SleepSeconds = 2)

  for ($i = 1; $i -le $Retries; $i++) {
    try {
      Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3 | Out-Null
      return $true
    } catch {
      Start-Sleep -Seconds $SleepSeconds
    }
  }

  return $false
}

function Open-Browser {
  param([string]$Url)
  try {
    Start-Process $Url | Out-Null
  } catch {
    Warn "Open $Url manually."
  }
}

function Invoke-CheckedCommand {
  param(
    [string]$FilePath,
    [string[]]$Arguments,
    [string]$FailureMessage
  )

  & $FilePath @Arguments
  if ($LASTEXITCODE -ne 0) {
    Fail "$FailureMessage (exit code: $LASTEXITCODE)"
  }
}

function Repair-FrontendDependencies {
  param([string]$FrontendDir)

  Push-Location $FrontendDir
  try {
    Invoke-CheckedCommand "corepack" @("pnpm", "approve-builds", "esbuild", "core-js") "Failed to approve required pnpm build scripts"
    Invoke-CheckedCommand "corepack" @("pnpm", "install", "--registry", "https://registry.npmjs.org") "Failed to install frontend dependencies"
    Invoke-CheckedCommand "corepack" @("pnpm", "rebuild", "esbuild", "core-js") "Failed to rebuild required frontend packages"
  } finally {
    Pop-Location
  }
}

function Prepare-Dirs {
  New-Item -ItemType Directory -Force -Path `
    $LogDir, `
    $RunDir, `
    (Join-Path $DataRoot "note_results"), `
    (Join-Path $DataRoot "chroma"), `
    (Join-Path $DataRoot "config"), `
    (Join-Path $DataRoot "uploads"), `
    (Join-Path $DataRoot "static\screenshots"), `
    (Join-Path $DataRoot "tmp"), `
    (Join-Path $DataRoot "data\output_frames"), `
    $ModelDir | Out-Null
}

function Get-RuntimeEnvScript {
  $lines = @(
    "`$env:NOTEMELD_DATA_DIR = $(Quote-PsString $DataRoot)",
    "`$env:NOTEMELD_LOG_DIR = $(Quote-PsString $LogDir)"
  )
  return ($lines -join [Environment]::NewLine)
}

function Ensure-Installed {
  if (-not (Test-Path $AppDir)) { Fail "NoteMeld app not found at $AppDir. Run the installer first." }
  if (-not (Test-Path (Join-Path $AppDir "desktop\backend"))) { Fail "Backend directory not found at $AppDir\desktop\backend." }
  if (-not (Test-Path (Join-Path $AppDir "desktop\frontend"))) { Fail "Frontend directory not found at $AppDir\desktop\frontend." }
  if (-not (Test-Path (Join-Path $AppDir ".venv\Scripts\python.exe"))) { Fail "Python virtualenv not found. Run: notemeld doctor" }
}

function Test-PidRunning {
  param([string]$PidFile)

  if (-not (Test-Path $PidFile)) { return $false }
  $rawPid = Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $rawPid) { return $false }

  try {
    Get-Process -Id ([int]$rawPid) -ErrorAction Stop | Out-Null
    return $true
  } catch {
    return $false
  }
}

function Start-Backend {
  if (Test-PidRunning $BackendPidFile) {
    Log "Backend is already running with PID $(Get-Content $BackendPidFile)"
    return
  }

  if (Test-PortInUse $BackendPort) {
    Warn "Backend port $BackendPort is already in use. Skipping backend start."
    return
  }

  $pythonPath = Join-Path $AppDir ".venv\Scripts\python.exe"
  $backendDir = Join-Path $AppDir "desktop\backend"
  $runner = @"
`$ErrorActionPreference = "Stop"
$(Get-RuntimeEnvScript)
Set-Location $(Quote-PsString $backendDir)
& $(Quote-PsString $pythonPath) main.py
"@
  $runner | Set-Content -Path $BackendRunner -Encoding UTF8

  Log "Starting backend on http://127.0.0.1:$BackendPort"
  $process = Start-Process powershell `
    -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $BackendRunner) `
    -RedirectStandardOutput $BackendLog `
    -RedirectStandardError $BackendErrLog `
    -PassThru `
    -WindowStyle Hidden
  $process.Id | Set-Content -Path $BackendPidFile -Encoding ASCII

  if (-not (Wait-ForUrl "http://127.0.0.1:$BackendPort/api/sys_check" 90 2)) {
    if (Test-Path $BackendLog) { Get-Content $BackendLog -Tail 80 -ErrorAction SilentlyContinue }
    if (Test-Path $BackendErrLog) { Get-Content $BackendErrLog -Tail 80 -ErrorAction SilentlyContinue }
    Fail "Backend failed to start. See $BackendLog and $BackendErrLog"
  }
}

function Start-Frontend {
  if (Test-PidRunning $FrontendPidFile) {
    Log "Frontend is already running with PID $(Get-Content $FrontendPidFile)"
    return
  }

  if (Test-PortInUse $FrontendPort) {
    Warn "Frontend port $FrontendPort is already in use. Skipping frontend start."
    return
  }

  $frontendDir = Join-Path $AppDir "desktop\frontend"
  $runner = @"
`$ErrorActionPreference = "Stop"
Set-Location $(Quote-PsString $frontendDir)
`$env:VITE_API_BASE_URL = $(Quote-PsString "http://127.0.0.1:$BackendPort/api")
`$env:VITE_SCREENSHOT_BASE_URL = $(Quote-PsString "http://127.0.0.1:$BackendPort/static/screenshots")
corepack pnpm dev --host 127.0.0.1 --port $FrontendPort
"@
  $runner | Set-Content -Path $FrontendRunner -Encoding UTF8

  Log "Starting frontend on http://127.0.0.1:$FrontendPort"
  $process = Start-Process powershell `
    -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $FrontendRunner) `
    -RedirectStandardOutput $FrontendLog `
    -RedirectStandardError $FrontendErrLog `
    -PassThru `
    -WindowStyle Hidden
  $process.Id | Set-Content -Path $FrontendPidFile -Encoding ASCII

  if (-not (Wait-ForUrl "http://127.0.0.1:$FrontendPort" 90 2)) {
    if (Test-Path $FrontendLog) { Get-Content $FrontendLog -Tail 80 -ErrorAction SilentlyContinue }
    if (Test-Path $FrontendErrLog) { Get-Content $FrontendErrLog -Tail 80 -ErrorAction SilentlyContinue }
    Fail "Frontend failed to start. See $FrontendLog and $FrontendErrLog"
  }
}

function Stop-PidFile {
  param([string]$PidFile, [string]$Label)

  if (-not (Test-Path $PidFile)) { return }
  $rawPid = Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1

  if ($rawPid) {
    try {
      Stop-Process -Id ([int]$rawPid) -Force -ErrorAction Stop
      Log "Stopped $Label process $rawPid"
    } catch {
      Warn "$Label process $rawPid was not running."
    }
  }

  Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

function Cmd-Start {
  Ensure-Installed
  Require-Command corepack

  Prepare-Dirs
  Start-Backend
  Start-Frontend

  Log "NoteMeld is running"
  Log "Frontend: http://127.0.0.1:$FrontendPort"
  Log "Backend:  http://127.0.0.1:$BackendPort"
  Log "Logs:     $LogDir"

  Open-Browser "http://127.0.0.1:$FrontendPort"
}

function Cmd-Stop {
  Stop-PidFile $FrontendPidFile "frontend"
  Stop-PidFile $BackendPidFile "backend"
}

function Cmd-Restart {
  Cmd-Stop
  Cmd-Start
}

function Cmd-Logs {
  New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
  foreach ($path in @($BackendLog, $BackendErrLog, $FrontendLog, $FrontendErrLog)) {
    if (-not (Test-Path $path)) { New-Item -ItemType File -Force -Path $path | Out-Null }
  }
  Get-Content $BackendLog, $BackendErrLog, $FrontendLog, $FrontendErrLog -Wait
}

function Cmd-Doctor {
  Log "Checking NoteMeld environment"

  Require-Command git
  Require-Command node
  Require-Command corepack
  Require-Command ffmpeg

  if (-not (Test-Path $AppDir)) { Fail "Missing app directory: $AppDir" }
  if (-not (Test-Path (Join-Path $AppDir ".git"))) { Warn "$AppDir is not a git repository" }
  if (-not (Test-Path (Join-Path $AppDir ".venv\Scripts\python.exe"))) { Fail "Missing Python virtualenv: $AppDir\.venv" }
  if (-not (Test-Path (Join-Path $AppDir "desktop\frontend\node_modules"))) { Fail "Missing frontend dependencies: $AppDir\desktop\frontend\node_modules" }

  Log "Doctor passed"
}

function Cmd-Update {
  Ensure-Installed
  if (-not (Test-Path (Join-Path $AppDir ".git"))) { Fail "Cannot update because $AppDir is not a git repository." }

  Log "Updating NoteMeld"
  Push-Location $AppDir
  try {
    Invoke-CheckedCommand "git" @("pull", "--ff-only") "Failed to update NoteMeld repository"
    Invoke-CheckedCommand (Join-Path $AppDir ".venv\Scripts\python.exe") @("-m", "pip", "install", "-r", "desktop\backend\requirements.txt") "Failed to install backend requirements"
    Repair-FrontendDependencies (Join-Path $AppDir "desktop\frontend")
  } finally {
    Pop-Location
  }

  Log "Update complete"
}

function Cmd-Uninstall {
  Cmd-Stop

  $binDir = if ($env:NOTEMELD_BIN_DIR) { $env:NOTEMELD_BIN_DIR } else { Join-Path $env:LOCALAPPDATA "Programs\NoteMeld\bin" }
  Remove-Item (Join-Path $binDir "notemeld.cmd") -Force -ErrorAction SilentlyContinue
  Remove-Item (Join-Path $binDir "notemeld.ps1") -Force -ErrorAction SilentlyContinue

  Log "Removed CLI from $binDir"
  Log "User data is kept at: $NotemeldHome"
  Log "To remove everything manually, delete: $NotemeldHome"
}

function Cmd-Help {
  Write-Host @"
NoteMeld CLI

Usage:
  notemeld              Start NoteMeld
  notemeld start        Start NoteMeld
  notemeld stop         Stop NoteMeld
  notemeld restart      Restart NoteMeld
  notemeld logs         Follow backend and frontend logs
  notemeld doctor       Check local dependencies and installation
  notemeld update       Pull latest code and refresh dependencies
  notemeld uninstall    Remove CLI only, keep user data
  notemeld help         Show this help

Environment:
  NOTEMELD_HOME         Default: %USERPROFILE%\.notemeld
  NOTEMELD_BACKEND_PORT Default: 8483
  NOTEMELD_FRONTEND_PORT Default: 3015
"@
}

switch ($Command) {
  "start" { Cmd-Start }
  "stop" { Cmd-Stop }
  "restart" { Cmd-Restart }
  "logs" { Cmd-Logs }
  "doctor" { Cmd-Doctor }
  "update" { Cmd-Update }
  "uninstall" { Cmd-Uninstall }
  { $_ -in @("help", "--help", "-h") } { Cmd-Help }
  default { Fail "Unknown command: $Command" }
}
