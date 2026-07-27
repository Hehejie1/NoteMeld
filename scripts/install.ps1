param()

$ErrorActionPreference = "Stop"

$RepoUrl = if ($env:NOTEMELD_REPO_URL) { $env:NOTEMELD_REPO_URL } else { "https://github.com/Hehejie1/NoteMeld.git" }
$RepoBranch = if ($env:NOTEMELD_REPO_BRANCH) { $env:NOTEMELD_REPO_BRANCH } else { "main" }

$InstallRoot = if ($env:NOTEMELD_HOME) { $env:NOTEMELD_HOME } else { Join-Path $env:USERPROFILE ".notemeld" }
$AppDir = Join-Path $InstallRoot "app"
$DataDir = Join-Path $InstallRoot "data"
$LogDir = Join-Path $InstallRoot "logs"
$ModelDir = Join-Path $InstallRoot "models"
$ConfigDir = Join-Path $InstallRoot "config"
$BinDir = if ($env:NOTEMELD_BIN_DIR) { $env:NOTEMELD_BIN_DIR } else { Join-Path $env:LOCALAPPDATA "Programs\NoteMeld\bin" }

$script:PythonCommand = ""
$script:PythonBaseArgs = @()
$script:GitCommand = ""
$script:NodeCommand = ""
$script:NpmCommand = ""
$script:CorepackCommand = ""

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

function Test-Command {
  param([string]$Name)
  return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Refresh-SessionPath {
  $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
  $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
  $parts = @($machinePath, $userPath) | Where-Object { $_ }
  if ($parts.Count -gt 0) {
    $env:Path = ($parts -join ";")
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

function Resolve-GitFromKnownLocations {
  $candidates = @(
    "C:\Program Files\Git\cmd\git.exe",
    "C:\Program Files\Git\bin\git.exe"
  )

  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) {
      $script:GitCommand = $candidate
      return $true
    }
  }

  return $false
}

function Try-Resolve-Git {
  $git = Get-Command git -ErrorAction SilentlyContinue
  if ($git) {
    $script:GitCommand = $git.Source
    return $true
  }

  return (Resolve-GitFromKnownLocations)
}

function Install-Git-WithWinget {
  if (-not (Test-Command "winget")) {
    return $false
  }

  Log "git not found. Trying to install it with winget"
  try {
    & winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) {
      Warn "winget failed to install git (exit code: $LASTEXITCODE)"
      return $false
    }
    Refresh-SessionPath
    return (Try-Resolve-Git)
  } catch {
    Warn "winget failed to install git: $($_.Exception.Message)"
    return $false
  }
}

function Install-Git-WithScoop {
  if (-not (Test-Command "scoop")) {
    return $false
  }

  Log "git not found. Trying to install it with scoop"
  try {
    & scoop install git
    if ($LASTEXITCODE -ne 0) {
      Warn "scoop failed to install git (exit code: $LASTEXITCODE)"
      return $false
    }
    Refresh-SessionPath
    return (Try-Resolve-Git)
  } catch {
    Warn "scoop failed to install git: $($_.Exception.Message)"
    return $false
  }
}

function Install-Git-WithChoco {
  if (-not (Test-Command "choco")) {
    return $false
  }

  Log "git not found. Trying to install it with Chocolatey"
  try {
    & choco install git -y
    if ($LASTEXITCODE -ne 0) {
      Warn "Chocolatey failed to install git (exit code: $LASTEXITCODE)"
      return $false
    }
    Refresh-SessionPath
    return (Try-Resolve-Git)
  } catch {
    Warn "Chocolatey failed to install git: $($_.Exception.Message)"
    return $false
  }
}

function Ensure-Git {
  if (Try-Resolve-Git) {
    return
  }

  foreach ($installer in @(
    { Install-Git-WithWinget },
    { Install-Git-WithScoop },
    { Install-Git-WithChoco }
  )) {
    if (& $installer) {
      Log "git is available"
      return
    }
  }

  Fail @"
Missing required command: git

Automatic installation failed. Install git manually, then rerun:
  winget install --id Git.Git -e

If you do not have winget, install one of these package managers first:
  - winget
  - scoop
  - choco
"@
}

function Install-WithWinget {
  if (-not (Test-Command "winget")) {
    return $false
  }

  Log "ffmpeg not found. Trying to install it with winget"
  try {
    & winget install --id Gyan.FFmpeg.Essentials -e --accept-source-agreements --accept-package-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) {
      Warn "winget failed to install ffmpeg (exit code: $LASTEXITCODE)"
      return $false
    }
    Refresh-SessionPath
    return (Test-Command "ffmpeg")
  } catch {
    Warn "winget failed to install ffmpeg: $($_.Exception.Message)"
    return $false
  }
}

function Install-WithScoop {
  if (-not (Test-Command "scoop")) {
    return $false
  }

  Log "ffmpeg not found. Trying to install it with scoop"
  try {
    & scoop install ffmpeg
    if ($LASTEXITCODE -ne 0) {
      Warn "scoop failed to install ffmpeg (exit code: $LASTEXITCODE)"
      return $false
    }
    Refresh-SessionPath
    return (Test-Command "ffmpeg")
  } catch {
    Warn "scoop failed to install ffmpeg: $($_.Exception.Message)"
    return $false
  }
}

function Install-WithChoco {
  if (-not (Test-Command "choco")) {
    return $false
  }

  Log "ffmpeg not found. Trying to install it with Chocolatey"
  try {
    & choco install ffmpeg -y
    if ($LASTEXITCODE -ne 0) {
      Warn "Chocolatey failed to install ffmpeg (exit code: $LASTEXITCODE)"
      return $false
    }
    Refresh-SessionPath
    return (Test-Command "ffmpeg")
  } catch {
    Warn "Chocolatey failed to install ffmpeg: $($_.Exception.Message)"
    return $false
  }
}

function Ensure-FFmpeg {
  if (Test-Command "ffmpeg") {
    return
  }

  foreach ($installer in @(
    { Install-WithWinget },
    { Install-WithScoop },
    { Install-WithChoco }
  )) {
    if (& $installer) {
      Log "ffmpeg is available"
      return
    }
  }

  Fail @"
Missing required command: ffmpeg

Automatic installation failed. Install ffmpeg manually, then rerun:
  winget install --id Gyan.FFmpeg.Essentials -e

If you do not have winget, install one of these package managers first:
  - winget
  - scoop
  - choco
"@
}

function Test-Python311 {
  param([string]$Command, [string[]]$BaseArgs)

  try {
    $versionText = & $Command @BaseArgs --version 2>&1
    return ($versionText -match "Python 3\.11")
  } catch {
    return $false
  }
}

function Test-Node20Plus {
  param([string]$Command)

  try {
    $versionText = & $Command --version 2>&1
    if ($versionText -match "v(\d+)") {
      return ([int]$Matches[1] -ge 20)
    }
    return $false
  } catch {
    return $false
  }
}

function Resolve-Node20PlusFromKnownLocations {
  $nodeCandidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\nodejs\node.exe"),
    "C:\Program Files\nodejs\node.exe"
  )

  foreach ($candidate in $nodeCandidates) {
    if ((Test-Path $candidate) -and (Test-Node20Plus $candidate)) {
      $script:NodeCommand = $candidate
      $nodeDir = Split-Path $candidate -Parent
      $npmCandidate = Join-Path $nodeDir "npm.cmd"
      if (Test-Path $npmCandidate) {
        $script:NpmCommand = $npmCandidate
      }
      return $true
    }
  }

  return $false
}

function Try-Resolve-Node20Plus {
  $node = Get-Command node -ErrorAction SilentlyContinue
  if ($node -and (Test-Node20Plus $node.Source)) {
    $script:NodeCommand = $node.Source
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if ($npm) {
      $script:NpmCommand = $npm.Source
    }
    return $true
  }

  return (Resolve-Node20PlusFromKnownLocations)
}

function Install-Node20Plus-WithWinget {
  if (-not (Test-Command "winget")) {
    return $false
  }

  Log "Node.js 20+ not found. Trying to install it with winget"
  try {
    & winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) {
      Warn "winget failed to install Node.js LTS (exit code: $LASTEXITCODE)"
      return $false
    }
    Refresh-SessionPath
    return (Try-Resolve-Node20Plus)
  } catch {
    Warn "winget failed to install Node.js LTS: $($_.Exception.Message)"
    return $false
  }
}

function Install-Node20Plus-WithScoop {
  if (-not (Test-Command "scoop")) {
    return $false
  }

  Log "Node.js 20+ not found. Trying to install it with scoop"
  try {
    & scoop install nodejs-lts
    if ($LASTEXITCODE -ne 0) {
      Warn "scoop failed to install Node.js LTS (exit code: $LASTEXITCODE)"
      return $false
    }
    Refresh-SessionPath
    return (Try-Resolve-Node20Plus)
  } catch {
    Warn "scoop failed to install Node.js LTS: $($_.Exception.Message)"
    return $false
  }
}

function Install-Node20Plus-WithChoco {
  if (-not (Test-Command "choco")) {
    return $false
  }

  Log "Node.js 20+ not found. Trying to install it with Chocolatey"
  try {
    & choco install nodejs-lts -y
    if ($LASTEXITCODE -ne 0) {
      Warn "Chocolatey failed to install Node.js LTS (exit code: $LASTEXITCODE)"
      return $false
    }
    Refresh-SessionPath
    return (Try-Resolve-Node20Plus)
  } catch {
    Warn "Chocolatey failed to install Node.js LTS: $($_.Exception.Message)"
    return $false
  }
}

function Ensure-Node20Plus {
  if (Try-Resolve-Node20Plus) {
    return
  }

  foreach ($installer in @(
    { Install-Node20Plus-WithWinget },
    { Install-Node20Plus-WithScoop },
    { Install-Node20Plus-WithChoco }
  )) {
    if (& $installer) {
      Log "Node.js 20+ is available"
      return
    }
  }

  Fail @"
Missing required command: node (20+)

Automatic installation failed. Install Node.js LTS manually, then rerun:
  winget install --id OpenJS.NodeJS.LTS -e

If you do not have winget, install one of these package managers first:
  - winget
  - scoop
  - choco
"@
}

function Resolve-CorepackFromKnownLocations {
  $candidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\nodejs\corepack.cmd"),
    "C:\Program Files\nodejs\corepack.cmd"
  )

  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) {
      $script:CorepackCommand = $candidate
      return $true
    }
  }

  return $false
}

function Try-Resolve-Corepack {
  $corepack = Get-Command corepack -ErrorAction SilentlyContinue
  if ($corepack) {
    $script:CorepackCommand = $corepack.Source
    return $true
  }

  return (Resolve-CorepackFromKnownLocations)
}

function Install-Corepack-WithNpm {
  if (-not $script:NpmCommand) {
    return $false
  }

  Log "corepack not found. Trying to install it with npm"
  try {
    & $script:NpmCommand install -g corepack
    if ($LASTEXITCODE -ne 0) {
      Warn "npm failed to install corepack (exit code: $LASTEXITCODE)"
      return $false
    }
    Refresh-SessionPath
    return (Try-Resolve-Corepack)
  } catch {
    Warn "npm failed to install corepack: $($_.Exception.Message)"
    return $false
  }
}

function Ensure-Corepack {
  if (Try-Resolve-Corepack) {
    return
  }

  if (Install-Corepack-WithNpm) {
    Log "corepack is available"
    return
  }

  Fail @"
Missing required command: corepack

Automatic installation failed. Reopen PowerShell after Node.js installation and rerun.
If it still fails, run manually:
  npm install -g corepack
"@
}

function Resolve-Python311FromKnownLocations {
  $candidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"),
    "C:\Program Files\Python311\python.exe",
    "C:\Python311\python.exe"
  )

  foreach ($candidate in $candidates) {
    if ((Test-Path $candidate) -and (Test-Python311 $candidate @())) {
      $script:PythonCommand = $candidate
      $script:PythonBaseArgs = @()
      return $true
    }
  }

  return $false
}

function Try-Resolve-Python311 {
  if ((Get-Command py -ErrorAction SilentlyContinue) -and (Test-Python311 "py" @("-3.11"))) {
    $script:PythonCommand = "py"
    $script:PythonBaseArgs = @("-3.11")
    return $true
  }

  if ((Get-Command python -ErrorAction SilentlyContinue) -and (Test-Python311 "python" @())) {
    $script:PythonCommand = "python"
    $script:PythonBaseArgs = @()
    return $true
  }

  return (Resolve-Python311FromKnownLocations)
}

function Install-Python311-WithWinget {
  if (-not (Test-Command "winget")) {
    return $false
  }

  Log "Python 3.11 not found. Trying to install it with winget"
  try {
    & winget install --id Python.Python.3.11 -e --accept-source-agreements --accept-package-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) {
      Warn "winget failed to install Python 3.11 (exit code: $LASTEXITCODE)"
      return $false
    }
    Refresh-SessionPath
    return (Try-Resolve-Python311)
  } catch {
    Warn "winget failed to install Python 3.11: $($_.Exception.Message)"
    return $false
  }
}

function Install-Python311-WithChoco {
  if (-not (Test-Command "choco")) {
    return $false
  }

  Log "Python 3.11 not found. Trying to install it with Chocolatey"
  try {
    & choco install python --version=3.11 -y
    if ($LASTEXITCODE -ne 0) {
      Warn "Chocolatey failed to install Python 3.11 (exit code: $LASTEXITCODE)"
      return $false
    }
    Refresh-SessionPath
    return (Try-Resolve-Python311)
  } catch {
    Warn "Chocolatey failed to install Python 3.11: $($_.Exception.Message)"
    return $false
  }
}

function Ensure-Python311 {
  if (Try-Resolve-Python311) {
    return
  }

  foreach ($installer in @(
    { Install-Python311-WithWinget },
    { Install-Python311-WithChoco }
  )) {
    if (& $installer) {
      Log "Python 3.11 is available"
      return
    }
  }

  Fail @"
Missing Python 3.11

Automatic installation failed. Install Python 3.11 manually, then rerun:
  winget install --id Python.Python.3.11 -e

If winget is unavailable, install Python 3.11 from:
  https://www.python.org/downloads/windows/
"@
}

function Resolve-Python311 {
  if (-not (Try-Resolve-Python311)) {
    Fail "Missing Python 3.11"
  }
}

function Invoke-Python {
  param([string[]]$Arguments)
  & $script:PythonCommand @($script:PythonBaseArgs + $Arguments)
}

function Ensure-Path {
  New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

  $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
  $pathItems = @()
  if ($userPath) {
    $pathItems = $userPath -split ";" | Where-Object { $_ }
  }

  if ($pathItems -notcontains $BinDir) {
    $newPath = if ($userPath) { "$userPath;$BinDir" } else { $BinDir }
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Warn "$BinDir was added to your user PATH. Restart PowerShell if 'notemeld' is not found."
  }

  if (($env:Path -split ";") -notcontains $BinDir) {
    $env:Path = "$env:Path;$BinDir"
  }
}

function Install-Repo {
  New-Item -ItemType Directory -Force -Path $InstallRoot, $DataDir, $LogDir, $ModelDir, $ConfigDir | Out-Null

  if (Test-Path (Join-Path $AppDir ".git")) {
    Log "Updating existing NoteMeld repository"
    Invoke-CheckedCommand $script:GitCommand @("-C", $AppDir, "fetch", "origin", $RepoBranch) "Failed to fetch NoteMeld repository"
    Invoke-CheckedCommand $script:GitCommand @("-C", $AppDir, "checkout", $RepoBranch) "Failed to checkout NoteMeld repository branch"
    Invoke-CheckedCommand $script:GitCommand @("-C", $AppDir, "pull", "--ff-only", "origin", $RepoBranch) "Failed to update NoteMeld repository"
    return
  }

  if (Test-Path $AppDir) {
    Fail "$AppDir exists but is not a git repository. Move it away and retry."
  }

  Log "Cloning NoteMeld from $RepoUrl"
  Invoke-CheckedCommand $script:GitCommand @("clone", "--branch", $RepoBranch, $RepoUrl, $AppDir) "Failed to clone NoteMeld repository"
}

function Install-Backend {
  Log "Installing backend dependencies"
  Push-Location $AppDir
  try {
    if (-not (Test-Path ".venv")) {
      Invoke-Python @("-m", "venv", ".venv")
      if ($LASTEXITCODE -ne 0) {
        Fail "Failed to create Python virtualenv (exit code: $LASTEXITCODE)"
      }
    }

    $venvPython = Join-Path $AppDir ".venv\Scripts\python.exe"
    Invoke-CheckedCommand $venvPython @("-m", "pip", "install", "--upgrade", "pip") "Failed to upgrade pip"
    Invoke-CheckedCommand $venvPython @("-m", "pip", "install", "-r", "backend\requirements.txt") "Failed to install backend requirements"
  } finally {
    Pop-Location
  }
}

function Install-Frontend {
  Log "Installing frontend dependencies"
  Push-Location (Join-Path $AppDir "frontend")
  try {
    Invoke-CheckedCommand $script:CorepackCommand @("pnpm", "approve-builds", "esbuild", "core-js") "Failed to approve required pnpm build scripts"
    Invoke-CheckedCommand $script:CorepackCommand @("pnpm", "install", "--registry", "https://registry.npmjs.org") "Failed to install frontend dependencies"
    Invoke-CheckedCommand $script:CorepackCommand @("pnpm", "rebuild", "esbuild", "core-js") "Failed to rebuild required frontend packages"
  } finally {
    Pop-Location
  }
}

function Init-Env {
  $envPath = Join-Path $AppDir ".env"
  $envExamplePath = Join-Path $AppDir ".env.example"

  if ((-not (Test-Path $envPath)) -and (Test-Path $envExamplePath)) {
    Copy-Item $envExamplePath $envPath
    Log "Created $envPath from .env.example"
  }
}

function Install-Cli {
  New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

  $cmdPath = Join-Path $BinDir "notemeld.cmd"
  $ps1Path = Join-Path $BinDir "notemeld.ps1"

  @"
@echo off
set "NM_HOME=%NOTEMELD_HOME%"
if "%NM_HOME%"=="" set "NM_HOME=%USERPROFILE%\.notemeld"
powershell -NoProfile -ExecutionPolicy Bypass -File "%NM_HOME%\app\scripts\notemeld.ps1" %*
"@ | Set-Content -Path $cmdPath -Encoding ASCII

  @"
`$ErrorActionPreference = "Stop"
`$HomeRoot = if (`$env:NOTEMELD_HOME) { `$env:NOTEMELD_HOME } else { Join-Path `$env:USERPROFILE ".notemeld" }
& (Join-Path `$HomeRoot "app\scripts\notemeld.ps1") @args
"@ | Set-Content -Path $ps1Path -Encoding ASCII

  Log "Installed CLI at $cmdPath"
}

function Main {
  Log "Installing NoteMeld"

  Ensure-Path
  Ensure-Git
  Ensure-Node20Plus
  Ensure-Corepack
  Ensure-Python311
  Ensure-FFmpeg
  Install-Repo
  Install-Backend
  Install-Frontend
  Init-Env
  Install-Cli

  Log "Install complete."
  Log "Run: notemeld"
}

Main
