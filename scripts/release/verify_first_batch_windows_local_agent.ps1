param(
    [Parameter(Mandatory = $true)][string]$InstalledExe,
    [Parameter(Mandatory = $true)][string]$ExpectedInstaller,
    [Parameter(Mandatory = $true)][string]$ExpectedVersion,
    [Parameter(Mandatory = $true)][ValidatePattern("^[0-9a-fA-F]{40}$")][string]$ExpectedCommit,
    [Parameter(Mandatory = $true)][string]$ExpectedModel,
    [Parameter(Mandatory = $true)][string]$RuntimeEvidence,
    [int]$TimeoutSeconds = 180
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

function Assert-PassEvidence {
    param([string]$Path, [string[]]$CheckPrefixes)
    $evidence = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    foreach ($prefix in $CheckPrefixes) {
        $matched = $false
        foreach ($property in $evidence.release_checks.PSObject.Properties) {
            $normalized = $property.Name.ToUpperInvariant() -replace "[^A-Z0-9]+", "-"
            if (($normalized -eq $prefix -or $normalized.StartsWith("$prefix-")) -and $property.Value -eq "PASS") { $matched = $true }
        }
        if (-not $matched) { throw "Evidence does not prove $prefix" }
    }
    return $evidence
}

function Find-ElementExact {
    param([System.Windows.Automation.AutomationElement]$Root, [string]$Name, [int]$Timeout = 30)
    $condition = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, $Name)
    $deadline = [DateTime]::UtcNow.AddSeconds($Timeout)
    do {
        $element = $Root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
        if ($null -ne $element) { return $element }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Timed out waiting for UI Automation element $Name"
}

function Find-ElementsByPrefix {
    param([System.Windows.Automation.AutomationElement]$Root, [string]$Prefix)
    $all = $Root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
    return @($all | Where-Object { $_.Current.Name.StartsWith($Prefix, [StringComparison]::Ordinal) })
}

function Find-ElementByPrefix {
    param([System.Windows.Automation.AutomationElement]$Root, [string]$Prefix, [int]$Timeout = 30)
    $deadline = [DateTime]::UtcNow.AddSeconds($Timeout)
    do {
        $elements = @(Find-ElementsByPrefix $Root $Prefix)
        if ($elements.Count -gt 0) { return $elements[0] }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Timed out waiting for UI Automation element prefix $Prefix"
}

function Invoke-Element {
    param([System.Windows.Automation.AutomationElement]$Element)
    $pattern = $Element.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
    ([System.Windows.Automation.InvokePattern]$pattern).Invoke()
}

function Get-StringSha256 {
    param([string]$Value)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value)))).Replace('-', '').ToLowerInvariant() } finally { $sha.Dispose() }
}

if (-not [Environment]::Is64BitOperatingSystem) { throw "X-02 requires Windows x64" }
if ([string]::IsNullOrWhiteSpace($ExpectedModel) -or $ExpectedModel.StartsWith("deterministic-", [StringComparison]::Ordinal)) { throw "X-02 requires an explicit real model" }
$InstalledExe = (Resolve-Path -LiteralPath $InstalledExe).Path
$ExpectedInstaller = (Resolve-Path -LiteralPath $ExpectedInstaller).Path
$RuntimeEvidence = (Resolve-Path -LiteralPath $RuntimeEvidence).Path
$runtime = Assert-PassEvidence $RuntimeEvidence @("WINDOWS-LOCAL-AGENT-RUNTIME")
$ExpectedCommit = $ExpectedCommit.ToLowerInvariant()
if ($runtime.model -ne $ExpectedModel -or $null -eq $runtime.installed_package) { throw "Runtime evidence does not match the expected model or installed executable" }
$runtimeVersion = [string]$runtime.installed_package.version
if ($runtimeVersion -ne $ExpectedVersion -and -not $runtimeVersion.StartsWith("$ExpectedVersion.", [StringComparison]::Ordinal)) { throw "Runtime evidence version does not match the expected RC" }

$stream = [IO.File]::OpenRead($InstalledExe)
try {
    $reader = [IO.BinaryReader]::new($stream)
    if ([Text.Encoding]::ASCII.GetString($reader.ReadBytes(2)) -ne "MZ") { throw "Installed executable is not a PE image" }
    $stream.Position = 0x3c
    $peOffset = $reader.ReadInt32()
    $stream.Position = $peOffset
    if ([Text.Encoding]::ASCII.GetString($reader.ReadBytes(4)) -ne "PE`0`0" -or $reader.ReadUInt16() -ne 0x8664) { throw "Installed executable is not x86_64" }
} finally { $stream.Dispose() }
$signature = Get-AuthenticodeSignature -LiteralPath $InstalledExe
if ($signature.Status -ne "Valid" -or $null -eq $signature.SignerCertificate) { throw "Installed executable is not Authenticode-valid" }
$productVersion = [Diagnostics.FileVersionInfo]::GetVersionInfo($InstalledExe).ProductVersion
if ($productVersion -ne $ExpectedVersion -and -not $productVersion.StartsWith("$ExpectedVersion.", [StringComparison]::Ordinal)) { throw "Installed executable version does not match the RC" }
$exeSha256 = (Get-FileHash -LiteralPath $InstalledExe -Algorithm SHA256).Hash.ToLowerInvariant()
if ($runtime.installed_package.sha256 -ne $exeSha256) { throw "Runtime evidence was collected from a different executable" }
$installerExtension = [IO.Path]::GetExtension($ExpectedInstaller).ToLowerInvariant()
if ($installerExtension -notin @(".msi", ".exe")) { throw "Expected installer must be an MSI or EXE" }
if (-not [IO.Path]::GetFileName($ExpectedInstaller).Contains($ExpectedVersion)) { throw "Expected installer filename does not contain the RC version" }
$installerSignature = Get-AuthenticodeSignature -LiteralPath $ExpectedInstaller
if ($installerSignature.Status -ne "Valid" -or $null -eq $installerSignature.SignerCertificate) { throw "Expected installer is not Authenticode-valid" }
if ($installerSignature.SignerCertificate.Thumbprint -ne $signature.SignerCertificate.Thumbprint) { throw "Installer and running executable use different Authenticode signers" }
$installerSha256 = (Get-FileHash -LiteralPath $ExpectedInstaller -Algorithm SHA256).Hash.ToLowerInvariant()

$process = Get-Process -ErrorAction SilentlyContinue | Where-Object {
    try { $_.Path -eq $InstalledExe -and $_.MainWindowHandle -ne 0 } catch { $false }
} | Select-Object -First 1
if ($null -eq $process) { throw "Installed NoteMeld window is not running" }
$root = [System.Windows.Automation.AutomationElement]::FromHandle($process.MainWindowHandle)
$null = Find-ElementExact $root "notemeld-build-commit:$ExpectedCommit"

$modelSelector = Find-ElementByPrefix $root "notemeld-local-agent-model:"
if ($modelSelector.Current.Name -ne "notemeld-local-agent-model:$ExpectedModel") {
    Invoke-Element $modelSelector
    $modelOption = Find-ElementExact $root "notemeld-local-agent-model-option:$ExpectedModel"
    Invoke-Element $modelOption
    $null = Find-ElementExact $root "notemeld-local-agent-model:$ExpectedModel"
}

$input = Find-ElementExact $root "notemeld-local-agent-input"
$challenge = "NMWINDOWSLOCAL$([Guid]::NewGuid().ToString('N').ToUpperInvariant())"
$valuePattern = $input.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
([System.Windows.Automation.ValuePattern]$valuePattern).SetValue("Reply exactly $challenge")
$send = Find-ElementExact $root "notemeld-local-agent-send-idle"
Invoke-Element $send

$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
$answer = ""
$answerPrefix = "notemeld-local-agent-assistant:turn.succeeded:1:"
$terminalFound = $false
do {
    Start-Sleep -Milliseconds 500
    $answerMatches = @((Find-ElementsByPrefix $root $answerPrefix) | Where-Object { $_.Current.Name.Contains($challenge) })
    if ($answerMatches.Count -gt 1) { throw "Windows UI rendered the verification answer more than once" }
    if ($answerMatches.Count -eq 1) {
        $answerElement = $answerMatches[0]
        $answer = $answerElement.Current.Name.Substring($answerPrefix.Length)
        $terminalFound = $true
    }
    $idle = @(Find-ElementsByPrefix $root "notemeld-local-agent-send-idle").Count -gt 0
    if ($answer.Contains($challenge) -and $idle -and $terminalFound) { break }
} while ([DateTime]::UtcNow -lt $deadline)

if (-not $answer.Contains($challenge)) { throw "Windows UI Agent answer did not contain the unique challenge" }
if (-not $terminalFound) { throw "Windows UI Agent did not expose exactly one successful terminal event" }
if ($process.HasExited) { throw "NoteMeld exited during local Agent UI verification" }

$result = [ordered]@{
    release_checks = @{ x_01 = "PASS"; x_02 = "PASS" }
    version = $ExpectedVersion
    rc_version = $ExpectedVersion
    rc_commit = $ExpectedCommit
    platform = "windows-x86_64"
    model = $ExpectedModel
    executable_sha256 = $exeSha256
    windows_installer_sha256 = $installerSha256
    signer_thumbprint = $signature.SignerCertificate.Thumbprint.ToLowerInvariant()
    runtime_evidence_sha256 = (Get-FileHash -LiteralPath $RuntimeEvidence -Algorithm SHA256).Hash.ToLowerInvariant()
    challenge_sha256 = Get-StringSha256 $challenge
    answer_sha256 = Get-StringSha256 $answer
    terminal_event = "turn.succeeded"
    terminal_event_count = 1
    ui_driven = $true
}
$result | ConvertTo-Json -Depth 5 -Compress
