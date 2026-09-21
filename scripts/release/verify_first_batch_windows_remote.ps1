param(
    [Parameter(Mandatory = $true)][ValidateSet("lan", "relay")][string]$ExpectedTransport,
    [Parameter(Mandatory = $true)][string]$HostDeviceId,
    [Parameter(Mandatory = $true)][string]$InstalledExe,
    [Parameter(Mandatory = $true)][string]$ExpectedVersion,
    [Parameter(Mandatory = $true)][ValidatePattern("^[0-9a-fA-F]{40}$")][string]$ExpectedCommit,
    [Parameter(Mandatory = $true)][string]$CloudEvidence,
    [Parameter(Mandatory = $true)][string]$RemoteHostEvidence,
    [string]$ProcessName = "NoteMeld",
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
            if (($normalized -eq $prefix -or $normalized.StartsWith("$prefix-")) -and $property.Value -eq "PASS") {
                $matched = $true
            }
        }
        if (-not $matched) { throw "Evidence does not prove $prefix" }
    }
    return $evidence
}

function Find-ElementExact {
    param(
        [System.Windows.Automation.AutomationElement]$Root,
        [string]$Name,
        [int]$Timeout = 30
    )
    $condition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty,
        $Name
    )
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
    $all = $Root.FindAll(
        [System.Windows.Automation.TreeScope]::Descendants,
        [System.Windows.Automation.Condition]::TrueCondition
    )
    return @($all | Where-Object { $_.Current.Name.StartsWith($Prefix, [StringComparison]::Ordinal) })
}

function Find-ElementByPrefix {
    param(
        [System.Windows.Automation.AutomationElement]$Root,
        [string]$Prefix,
        [int]$Timeout = 30
    )
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

if (-not [Environment]::Is64BitOperatingSystem) { throw "X-04/X-05 require Windows x64" }
$InstalledExe = (Resolve-Path -LiteralPath $InstalledExe).Path
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
$cloud = Assert-PassEvidence $CloudEvidence @("C-01", "C-02")
$host = Assert-PassEvidence $RemoteHostEvidence @("C-04", "X-06")
$ExpectedCommit = $ExpectedCommit.ToLowerInvariant()
if ($cloud.rc_version -ne $ExpectedVersion -or $host.rc_version -ne $ExpectedVersion -or $cloud.rc_commit -ne $ExpectedCommit -or $host.rc_commit -ne $ExpectedCommit) {
    throw "Cloud and Host evidence must be bound to the same expected RC version and commit"
}
if ($cloud.base_url.TrimEnd('/') -ne $host.base_url.TrimEnd('/')) {
    throw "Cloud and Host evidence target different deployments"
}
if ($cloud.build_commit -ne $ExpectedCommit -or $host.build_commit -ne $ExpectedCommit -or $cloud.cloud_image_digest -notmatch '^sha256:[0-9a-f]{64}$' -or $host.cloud_image_digest -ne $cloud.cloud_image_digest) {
    throw "Cloud and Host evidence target different Cloud build identities"
}
if ($host.host_device_id -ne $HostDeviceId -or $host.host_platform -ne "desktop") {
    throw "Remote Host evidence does not match the selected desktop Host"
}
if ($host.cloud_persisted_commands -ne 0 -or $host.cloud_persisted_events -ne 0) {
    throw "Remote Host evidence is not release-safe"
}

$process = Get-Process -Name $ProcessName | Where-Object {
    try { $_.Path -eq $InstalledExe -and $_.MainWindowHandle -ne 0 } catch { $false }
} | Select-Object -First 1
if ($null -eq $process) { throw "Installed NoteMeld window is not running" }
$productVersion = $process.MainModule.FileVersionInfo.ProductVersion
if ($productVersion -ne $ExpectedVersion -and -not $productVersion.StartsWith("$ExpectedVersion.", [StringComparison]::Ordinal)) {
    throw "Installed NoteMeld version does not match the expected RC"
}
$root = [System.Windows.Automation.AutomationElement]::FromHandle($process.MainWindowHandle)
$null = Find-ElementExact $root "notemeld-build-commit:$ExpectedCommit"

$hostSelector = Find-ElementByPrefix $root "notemeld-remote-host:"
if ($hostSelector.Current.Name -ne "notemeld-remote-host:$HostDeviceId") {
    $expandPattern = $hostSelector.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern)
    ([System.Windows.Automation.ExpandCollapsePattern]$expandPattern).Expand()
    $hostOption = Find-ElementExact $root "notemeld-remote-host-option:$HostDeviceId"
    $selectionPattern = $hostOption.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
    ([System.Windows.Automation.SelectionItemPattern]$selectionPattern).Select()
    $hostSelector = Find-ElementExact $root "notemeld-remote-host:$HostDeviceId"
}
$connect = Find-ElementExact $root "notemeld-remote-connect"
Invoke-Element $connect
$null = Find-ElementExact $root "notemeld-remote-transport-$ExpectedTransport" 60
$input = Find-ElementExact $root "notemeld-remote-input"
$challenge = "NMWINDOWSREMOTE$([Guid]::NewGuid().ToString('N').ToUpperInvariant())"
$valuePattern = $input.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
([System.Windows.Automation.ValuePattern]$valuePattern).SetValue("Reply exactly $challenge")
$send = Find-ElementExact $root "notemeld-remote-send-idle"
Invoke-Element $send

$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
$answer = ""
$terminalNames = @()
do {
    Start-Sleep -Milliseconds 500
    $answer = ((Find-ElementsByPrefix $root "notemeld-remote-assistant:") | ForEach-Object {
        $_.Current.Name.Substring("notemeld-remote-assistant:".Length)
    }) -join ""
    $terminalNames = @((Find-ElementsByPrefix $root "notemeld-remote-terminal-") | ForEach-Object { $_.Current.Name })
    $idle = @(Find-ElementsByPrefix $root "notemeld-remote-send-idle").Count -gt 0
    if ($answer.Contains($challenge) -and $idle -and $terminalNames.Count -gt 0) { break }
} while ([DateTime]::UtcNow -lt $deadline)

if (-not $answer.Contains($challenge)) { throw "Remote Agent answer did not contain the unique challenge" }
if ($terminalNames.Count -ne 1 -or $terminalNames[0] -ne "notemeld-remote-terminal-turn.succeeded") {
    throw "Remote Agent did not emit exactly one successful terminal event"
}
if ($process.HasExited) { throw "NoteMeld exited during remote Agent verification" }

$releaseId = if ($ExpectedTransport -eq "lan") { "x_04" } else { "x_05" }
$releaseChecks = [ordered]@{}
$releaseChecks[$releaseId] = "PASS"
$result = [ordered]@{
    release_checks = $releaseChecks
    version = $ExpectedVersion
    rc_version = $ExpectedVersion
    rc_commit = $ExpectedCommit
    platform = "windows-x86_64"
    executable_sha256 = (Get-FileHash -LiteralPath $InstalledExe -Algorithm SHA256).Hash.ToLowerInvariant()
    signer_thumbprint = $signature.SignerCertificate.Thumbprint.ToLowerInvariant()
    transport = $ExpectedTransport
    cloud_base_url = $cloud.base_url
    build_commit = $cloud.build_commit
    cloud_image_digest = $cloud.cloud_image_digest
    host_device_sha256 = (Get-FileHash -InputStream ([IO.MemoryStream]::new([Text.Encoding]::UTF8.GetBytes($HostDeviceId))) -Algorithm SHA256).Hash.ToLowerInvariant()
    challenge_sha256 = (Get-FileHash -InputStream ([IO.MemoryStream]::new([Text.Encoding]::UTF8.GetBytes($challenge))) -Algorithm SHA256).Hash.ToLowerInvariant()
    answer_sha256 = (Get-FileHash -InputStream ([IO.MemoryStream]::new([Text.Encoding]::UTF8.GetBytes($answer))) -Algorithm SHA256).Hash.ToLowerInvariant()
    terminal_event = "turn.succeeded"
}
$result | ConvertTo-Json -Depth 5 -Compress
