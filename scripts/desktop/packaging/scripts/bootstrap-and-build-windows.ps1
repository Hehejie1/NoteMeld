# NoteMeld Windows 一键打包脚本
#
# 目标: 在一台干净的 Windows (10/11, x64 或 ARM64) 上, clone 完源码后
#       只跑这一个脚本就能产出 desktop\src-tauri\target\release\bundle\msi\*.msi
#
# 用法 (PowerShell):
#   cd <repo_root>
#   .\scripts\packaging\scripts\bootstrap-and-build-windows.ps1
#
# 可选参数:
#   -SkipDepsInstall   : 跳过 pip / pnpm 依赖安装阶段 (你确定环境已就绪时使用)
#   -ReinstallVenv     : 删除现有 .venv 并重建
#   -FfmpegBinPath <x> : 显式指定 ffmpeg.exe 所在目录 (否则从 PATH 自动找)

[CmdletBinding()]
param(
    [switch]$SkipDepsInstall,
    [switch]$ReinstallVenv,
    [string]$FfmpegBinPath
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# ---------- 工具函数 ----------

function Write-Step([string]$msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

function Write-Ok([string]$msg) {
    Write-Host "  [OK] $msg" -ForegroundColor Green
}

function Write-WarnLine([string]$msg) {
    Write-Host "  [!]  $msg" -ForegroundColor Yellow
}

function Fail([string]$msg, [string]$hint = "") {
    Write-Host ""
    Write-Host "[FATAL] $msg" -ForegroundColor Red
    if ($hint) {
        Write-Host ""
        Write-Host "下一步建议:" -ForegroundColor Yellow
        Write-Host $hint
    }
    exit 1
}

function Test-Cmd([string]$name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Get-CmdVersion([string]$cmd, [string]$args) {
    try {
        $output = & $cmd $args.Split(" ") 2>&1 | Select-Object -First 1
        return $output
    } catch {
        return "<unknown>"
    }
}

# ---------- 路径 ----------

$RootDir       = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")).Path
$VenvDir       = Join-Path $RootDir ".venv"
$VenvPython    = Join-Path $VenvDir "Scripts\python.exe"
$BackendReq    = Join-Path $RootDir "desktop\backend\requirements.txt"
$FrontendDir   = Join-Path $RootDir "desktop\frontend"
$DesktopDir    = Join-Path $RootDir "desktop"
$BuildScript   = Join-Path $RootDir "scripts\desktop\packaging\scripts\build-desktop-windows.ps1"
$MsiOutputGlob = Join-Path $RootDir "desktop\src-tauri\target\release\bundle\msi\*.msi"

Write-Host ""
Write-Host "NoteMeld Windows 一键打包" -ForegroundColor Magenta
Write-Host "Repo: $RootDir"
Write-Host ""

# ---------- 1. 环境检查 ----------

Write-Step "Step 1/5  环境检查"

# Python
if (-not (Test-Cmd "python")) {
    Fail "未检测到 python" @"
请安装 Python 3.11 (建议 64 位):
    winget install --id Python.Python.3.11
安装后重新打开 PowerShell 再跑本脚本。
"@
}
$pyVer = & python --version 2>&1
Write-Ok "python: $pyVer"

# Node.js
if (-not (Test-Cmd "node")) {
    Fail "未检测到 node" @"
请安装 Node.js LTS:
    winget install --id OpenJS.NodeJS.LTS
"@
}
$nodeVer = & node --version 2>&1
Write-Ok "node:   $nodeVer"

# pnpm (允许通过 corepack 启用)
if (-not (Test-Cmd "pnpm")) {
    Write-WarnLine "未检测到 pnpm, 尝试通过 corepack 启用 ..."
    try {
        & corepack enable 2>&1 | Out-Null
        & corepack prepare pnpm@9 --activate 2>&1 | Out-Null
    } catch {
        # ignore
    }
}
if (-not (Test-Cmd "pnpm")) {
    Fail "未检测到 pnpm" @"
请安装 pnpm:
    npm install -g pnpm@9
或启用 corepack:
    corepack enable
    corepack prepare pnpm@9 --activate
"@
}
$pnpmVer = & pnpm --version 2>&1
Write-Ok "pnpm:   $pnpmVer"

# Rust / cargo
if (-not (Test-Cmd "cargo")) {
    Fail "未检测到 cargo (Rust 工具链)" @"
请安装 rustup, 并选择 MSVC 工具链:
    winget install --id Rustlang.Rustup
    rustup default stable-msvc
"@
}
$cargoVer = & cargo --version 2>&1
Write-Ok "cargo:  $cargoVer"

# ffmpeg
$ffmpegDir = $FfmpegBinPath
if (-not $ffmpegDir) { $ffmpegDir = $env:FFMPEG_BIN_PATH }
if (-not $ffmpegDir) {
    $cmd = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
    if ($cmd) { $ffmpegDir = Split-Path $cmd.Source -Parent }
}
if (
    -not $ffmpegDir -or
    -not (Test-Path (Join-Path $ffmpegDir "ffmpeg.exe")) -or
    -not (Test-Path (Join-Path $ffmpegDir "ffprobe.exe"))
) {
    Fail "未找到 ffmpeg.exe / ffprobe.exe" @"
方式1 (推荐) 通过 winget 安装:
    winget install --id Gyan.FFmpeg
方式2 手动下载 ffmpeg-release-essentials, 解压并把 bin 加到 PATH
然后重开 PowerShell, 或显式传 -FfmpegBinPath C:\path\to\ffmpeg\bin
"@
}
Write-Ok "ffmpeg: $ffmpegDir"
$env:FFMPEG_BIN_PATH = $ffmpegDir

# MSVC 工具链 (cl.exe 不一定在 PATH, 但 cargo 编译时需要 link.exe)
# 这里只做温和提示, 不强制中断
if (-not (Test-Cmd "link")) {
    Write-WarnLine "未检测到 MSVC link.exe (可能尚未在 'x64 Native Tools Command Prompt' 中)"
    Write-WarnLine '如后续 cargo build 报 linker link.exe not found, 请安装:'
    Write-WarnLine '  winget install --id Microsoft.VisualStudio.2022.BuildTools --override "--add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"'
}

# ---------- 2. Python venv + 依赖 ----------

Write-Step "Step 2/5  准备 Python 虚拟环境"

if ($ReinstallVenv -and (Test-Path $VenvDir)) {
    Write-WarnLine "ReinstallVenv 已开启, 删除现有 .venv ..."
    Remove-Item $VenvDir -Recurse -Force
}

if (-not (Test-Path $VenvPython)) {
    & python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { Fail "python -m venv 失败" }
    Write-Ok "已创建 .venv"
} else {
    Write-Ok ".venv 已存在, 复用"
}

if (-not $SkipDepsInstall) {
    Write-Step "Step 3/5  安装 backend Python 依赖 (耗时较长, 首次约 5-15 分钟)"
    & $VenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { Fail "pip 升级失败" }

    & $VenvPython -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) { Fail "pyinstaller 安装失败" }

    & $VenvPython -m pip install -r $BackendReq
    if ($LASTEXITCODE -ne 0) {
        Fail "backend 依赖安装失败" @"
常见原因:
  1) 某个包要求 C 编译器 -> 装 VS Build Tools (见上一步提示)
  2) 网络问题 -> 配置国内镜像:
     `$env:PIP_INDEX_URL = 'https://pypi.tuna.tsinghua.edu.cn/simple'
"@
    }
    Write-Ok "backend 依赖完成"
} else {
    Write-Step "Step 3/5  跳过 pip 依赖安装 (-SkipDepsInstall)"
}

# ---------- 3. 前端 / desktop 依赖 ----------

if (-not $SkipDepsInstall) {
    Write-Step "Step 4/5  安装 frontend / desktop 依赖"

    Push-Location $FrontendDir
    try {
        & pnpm install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) {
            Write-WarnLine "frozen-lockfile 失败, 回退到普通 install ..."
            & pnpm install
            if ($LASTEXITCODE -ne 0) { Fail "frontend pnpm install 失败" }
        }
        Write-Ok "frontend 依赖完成"
    } finally { Pop-Location }

    Push-Location $DesktopDir
    try {
        & pnpm install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) {
            Write-WarnLine "frozen-lockfile 失败, 回退到普通 install ..."
            & pnpm install
            if ($LASTEXITCODE -ne 0) { Fail "desktop pnpm install 失败" }
        }
        Write-Ok "desktop 依赖完成"
    } finally { Pop-Location }
} else {
    Write-Step "Step 4/5  跳过 pnpm 依赖安装 (-SkipDepsInstall)"
}

# ---------- 4. 调用既有打包脚本 ----------

Write-Step "Step 5/5  打包桌面端 (PyInstaller -> Tauri MSI)"

if (-not (Test-Path $BuildScript)) {
    Fail "未找到既有打包脚本: $BuildScript"
}

& $BuildScript
if ($LASTEXITCODE -ne 0) {
    Fail "打包脚本执行失败" @"
排查思路 (按出现顺序):
  1) PyInstaller 失败 -> 看错误中的 'ModuleNotFoundError', 在
     scripts\desktop\packaging\backend\pyinstaller\backend.spec 的 hiddenimports 里补包名
  2) cargo build 失败 -> 一般是 MSVC 工具链没装好 (见 Step 1 的提示)
  3) tauri bundle msi 失败 -> Tauri CLI 第一次会下载 WiX, 需联网;
     如果在公司网络下被墙, 设置代理:
     `$env:HTTPS_PROXY = 'http://127.0.0.1:7890'
"@
}

# ---------- 5. 收尾 ----------

Write-Host ""
Write-Host "==============================" -ForegroundColor Green
Write-Host " 打包成功 " -ForegroundColor Green
Write-Host "==============================" -ForegroundColor Green
Get-ChildItem $MsiOutputGlob -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host ("  -> " + $_.FullName) -ForegroundColor Green
}
Write-Host ""
