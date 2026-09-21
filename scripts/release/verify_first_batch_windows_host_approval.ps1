param(
    [Parameter(Mandatory = $true)][string]$InstalledExe,
    [Parameter(Mandatory = $true)][ValidateSet("deny", "expired")][string]$Mode,
    [Parameter(Mandatory = $true)][string]$ExpectedVersion,
    [Parameter(Mandatory = $true)][ValidatePattern("^[0-9a-fA-F]{40}$")][string]$ExpectedCommit,
    [Parameter(Mandatory = $true)][string]$CloudEvidence,
    [Parameter(Mandatory = $true)][string]$RemoteHostEvidence,
    [int]$TimeoutSeconds = 420
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

function Find-ElementsByPrefix {
    param([System.Windows.Automation.AutomationElement]$Root, [string]$Prefix)
    $all = $Root.FindAll(
        [System.Windows.Automation.TreeScope]::Descendants,
        [System.Windows.Automation.Condition]::TrueCondition
    )
    return @($all | Where-Object { $_.Current.Name.StartsWith($Prefix, [StringComparison]::Ordinal) })
}

function Find-ElementByPrefix {
    param([System.Windows.Automation.AutomationElement]$Root, [string]$Prefix, [int]$Timeout)
    $deadline = [DateTime]::UtcNow.AddSeconds($Timeout)
    do {
        $matches = @(Find-ElementsByPrefix $Root $Prefix)
        if ($matches.Count -eq 1) { return $matches[0] }
        if ($matches.Count -gt 1) { throw "Multiple UI elements matched $Prefix" }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Timed out waiting for UI Automation element prefix $Prefix"
}

function Invoke-Element {
    param([System.Windows.Automation.AutomationElement]$Element)
    $pattern = $Element.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
    ([System.Windows.Automation.InvokePattern]$pattern).Invoke()
}

function Get-Sha256Text {
    param([string]$Value)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value)))).Replace('-', '').ToLowerInvariant()
    } finally { $sha.Dispose() }
}

if (-not [Environment]::Is64BitOperatingSystem) { throw "E-02 Host approval gate requires Windows x64" }
$InstalledExe = (Resolve-Path -LiteralPath $InstalledExe).Path
$stream = [IO.File]::OpenRead($InstalledExe)
try {
    $reader = [IO.BinaryReader]::new($stream)
    if ([Text.Encoding]::ASCII.GetString($reader.ReadBytes(2)) -ne "MZ") { throw "Installed executable is not a PE image" }
    $stream.Position = 0x3c
    $peOffset = $reader.ReadInt32()
    $stream.Position = $peOffset
    if ([Text.Encoding]::ASCII.GetString($reader.ReadBytes(4)) -ne "PE`0`0" -or $reader.ReadUInt16() -ne 0x8664) {
        throw "Installed executable is not x86_64"
    }
} finally { $stream.Dispose() }
$signature = Get-AuthenticodeSignature -LiteralPath $InstalledExe
if ($signature.Status -ne "Valid" -or $null -eq $signature.SignerCertificate) { throw "Installed executable is not Authenticode-valid" }
$productVersion = [Diagnostics.FileVersionInfo]::GetVersionInfo($InstalledExe).ProductVersion
if ($productVersion -ne $ExpectedVersion -and -not $productVersion.StartsWith("$ExpectedVersion.", [StringComparison]::Ordinal)) {
    throw "Installed executable version does not match the expected RC"
}

$cloud = Assert-PassEvidence $CloudEvidence @("C-01", "C-02")
$host = Assert-PassEvidence $RemoteHostEvidence @("C-04", "X-06")
$ExpectedCommit = $ExpectedCommit.ToLowerInvariant()
if ($cloud.rc_version -ne $ExpectedVersion -or $host.rc_version -ne $ExpectedVersion -or $cloud.rc_commit -ne $ExpectedCommit -or $host.rc_commit -ne $ExpectedCommit) {
    throw "Cloud and Host evidence must be bound to the same expected RC"
}
if ($cloud.base_url.TrimEnd('/') -ne $host.base_url.TrimEnd('/')) { throw "Cloud and Host evidence target different deployments" }
if ($cloud.build_commit -ne $ExpectedCommit -or $host.build_commit -ne $ExpectedCommit -or $cloud.cloud_image_digest -notmatch '^sha256:[0-9a-f]{64}$' -or $host.cloud_image_digest -ne $cloud.cloud_image_digest) {
    throw "Cloud and Host evidence target different Cloud build identities"
}
if ($host.host_platform -ne "desktop") { throw "Remote Host evidence is not for a desktop Host" }

$process = Get-Process -ErrorAction SilentlyContinue | Where-Object {
    try { $_.Path -eq $InstalledExe -and $_.MainWindowHandle -ne 0 } catch { $false }
} | Select-Object -First 1
if ($null -eq $process) { throw "Installed NoteMeld window is not running" }
$root = [System.Windows.Automation.AutomationElement]::FromHandle($process.MainWindowHandle)
$buildMarker = Find-ElementByPrefix $root "notemeld-build-commit:" 30
if ($buildMarker.Current.Name -ne "notemeld-build-commit:$ExpectedCommit") { throw "Running app build commit does not match the expected RC" }

$existing = @(Find-ElementsByPrefix $root "notemeld-host-approval:")
if ($existing.Count -ne 0) { throw "Host has a stale or unrelated pending approval before the field gate" }
$notice = Find-ElementByPrefix $root "通知，" 30
Invoke-Element $notice
$initialCount = Find-ElementByPrefix $root "notemeld-host-approval-count:" 10
if ($initialCount.Current.Name -ne "notemeld-host-approval-count:0") {
    throw "Host has a stale or unrelated pending approval before the field gate"
}

$item = Find-ElementByPrefix $root "notemeld-host-approval:" $TimeoutSeconds
$approvalId = $item.Current.Name.Substring("notemeld-host-approval:".Length)
if ([string]::IsNullOrWhiteSpace($approvalId)) { throw "Host approval item has no identifier" }
$approvalHash = Get-Sha256Text $approvalId
$observedAt = [DateTime]::UtcNow

if ($Mode -eq "deny") {
    $deny = Find-ElementByPrefix $root "notemeld-host-approval-deny:$approvalId" 30
    Invoke-Element $deny
}

$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
do {
    Start-Sleep -Milliseconds 250
    $remaining = @(Find-ElementsByPrefix $root "notemeld-host-approval:$approvalId")
    if ($remaining.Count -eq 0) { break }
} while ([DateTime]::UtcNow -lt $deadline)
if ($remaining.Count -ne 0) { throw "Host approval did not disappear after $Mode resolution" }
if ($process.HasExited) { throw "NoteMeld exited during Host approval verification" }

$resolvedAt = [DateTime]::UtcNow
$checkName = if ($Mode -eq "deny") { "host_approval_deny_ui" } else { "host_approval_timeout_ui" }
$releaseChecks = [ordered]@{}
$releaseChecks[$checkName] = "PASS"
$result = [ordered]@{
    release_checks = $releaseChecks
    rc_version = $ExpectedVersion
    rc_commit = $ExpectedCommit
    platform = "windows-x86_64"
    cloud_base_url = $cloud.base_url
    build_commit = $cloud.build_commit
    cloud_image_digest = $cloud.cloud_image_digest
    host_device_sha256 = (Get-Sha256Text ([string]$host.host_device_id))
    executable_sha256 = (Get-FileHash -LiteralPath $InstalledExe -Algorithm SHA256).Hash.ToLowerInvariant()
    signer_thumbprint = $signature.SignerCertificate.Thumbprint.ToLowerInvariant()
    decision = $Mode
    approval_id_sha256 = $approvalHash
    observed_at = $observedAt.ToString("o")
    resolved_at = $resolvedAt.ToString("o")
    visible_duration_ms = [int]($resolvedAt - $observedAt).TotalMilliseconds
    approval_removed = $true
}
$result | ConvertTo-Json -Depth 5 -Compress
