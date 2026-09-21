param(
    [Parameter(Mandatory = $true)][string]$InstalledExe,
    [Parameter(Mandatory = $true)][string]$ExpectedVersion,
    [Parameter(Mandatory = $true)][ValidatePattern("^[0-9a-fA-F]{40}$")][string]$ExpectedCommit,
    [Parameter(Mandatory = $true)][string]$CloudEvidence,
    [Parameter(Mandatory = $true)][string]$RemoteHostEvidence,
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

function Get-ExactProcess {
    param([string]$Path, [switch]$RequireWindow)
    return Get-Process -ErrorAction SilentlyContinue | Where-Object {
        try { $_.Path -eq $Path -and (-not $RequireWindow -or $_.MainWindowHandle -ne 0) } catch { $false }
    } | Select-Object -First 1
}

function Get-HostMarker {
    param([System.Diagnostics.Process]$Process)
    $root = [System.Windows.Automation.AutomationElement]::FromHandle($Process.MainWindowHandle)
    $all = $root.FindAll(
        [System.Windows.Automation.TreeScope]::Descendants,
        [System.Windows.Automation.Condition]::TrueCondition
    )
    foreach ($element in $all) {
        $name = $element.Current.Name
        if ($name -match '^notemeld-cloud-host:running:([^:]+):([0-9a-f]{64})$') {
            return @{ device_id = $Matches[1]; public_key_sha256 = $Matches[2] }
        }
    }
    return $null
}

function Wait-HostMarker {
    param([string]$Path, [int]$Timeout)
    $deadline = [DateTime]::UtcNow.AddSeconds($Timeout)
    do {
        $process = Get-ExactProcess $Path -RequireWindow
        if ($null -ne $process) {
            $marker = Get-HostMarker $process
            if ($null -ne $marker) { return @{ process = $process; marker = $marker } }
        }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Timed out waiting for the app-scoped Cloud Host marker"
}

function Assert-BuildCommit {
    param([System.Diagnostics.Process]$Process, [string]$ExpectedCommit)
    $root = [System.Windows.Automation.AutomationElement]::FromHandle($Process.MainWindowHandle)
    $condition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty,
        "notemeld-build-commit:$ExpectedCommit"
    )
    if ($null -eq $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)) {
        throw "Running app build commit does not match the expected RC"
    }
}

function Invoke-CloudGet {
    param([string]$BaseUrl, [string]$Path, [string]$Token)
    $headers = @{ Authorization = "Bearer $Token" }
    $response = Invoke-RestMethod -Method Get -Uri "$($BaseUrl.TrimEnd('/'))$Path" -Headers $headers -TimeoutSec 30
    if ($response.code -ne 0) { throw "Cloud returned a failed response envelope" }
    return $response.data
}

function Get-CloudHost {
    param([string]$BaseUrl, [string]$Token, [string]$DeviceId)
    $devices = @(Invoke-CloudGet $BaseUrl "/v1/devices" $Token)
    $device = $devices | Where-Object { $_.id -eq $DeviceId } | Select-Object -First 1
    if ($null -eq $device) { throw "Cloud does not list the restarted Host device" }
    if (-not $device.public_key) { throw "Cloud Host device has no public key" }
    $encoded = ([string]$device.public_key).Replace('-', '+').Replace('_', '/')
    while ($encoded.Length % 4 -ne 0) { $encoded += '=' }
    $bytes = [Convert]::FromBase64String($encoded)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $fingerprint = ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant() } finally { $sha.Dispose() }
    return @{ online = [bool]$device.online; last_seen_at = [double]$device.last_seen_at; public_key_sha256 = $fingerprint }
}

if (-not [Environment]::Is64BitOperatingSystem) { throw "X-03 requires Windows x64" }
$InstalledExe = (Resolve-Path -LiteralPath $InstalledExe).Path
if ([IO.Path]::GetExtension($InstalledExe) -ne ".exe") { throw "Installed executable must be an EXE" }
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
$hostEvidence = Assert-PassEvidence $RemoteHostEvidence @("C-04", "X-06")
$ExpectedCommit = $ExpectedCommit.ToLowerInvariant()
if ($cloud.rc_version -ne $ExpectedVersion -or $hostEvidence.rc_version -ne $ExpectedVersion -or $cloud.rc_commit -ne $ExpectedCommit -or $hostEvidence.rc_commit -ne $ExpectedCommit) {
    throw "Cloud and Host evidence must be bound to the same expected RC"
}
if ($cloud.base_url.TrimEnd('/') -ne $hostEvidence.base_url.TrimEnd('/')) { throw "Cloud and Host evidence target different deployments" }
if ($cloud.build_commit -ne $ExpectedCommit -or $hostEvidence.build_commit -ne $ExpectedCommit -or $cloud.cloud_image_digest -notmatch '^sha256:[0-9a-f]{64}$' -or $hostEvidence.cloud_image_digest -ne $cloud.cloud_image_digest) {
    throw "Cloud and Host evidence target different Cloud build identities"
}
if ($hostEvidence.host_platform -ne "desktop") { throw "Remote Host evidence is not for a desktop Host" }
if ($hostEvidence.cloud_persisted_commands -ne 0 -or $hostEvidence.cloud_persisted_events -ne 0) { throw "Remote Host evidence is not release-safe" }
$accountToken = [Environment]::GetEnvironmentVariable("NOTEMELD_CLOUD_ACCOUNT_TOKEN")
if ([string]::IsNullOrWhiteSpace($accountToken)) { throw "NOTEMELD_CLOUD_ACCOUNT_TOKEN is required" }

$before = Wait-HostMarker $InstalledExe $TimeoutSeconds
Assert-BuildCommit $before.process $ExpectedCommit
if ($before.marker.device_id -ne $hostEvidence.host_device_id) { throw "Running app Host does not match bound Host evidence" }
$cloudBefore = Get-CloudHost $cloud.base_url $accountToken $before.marker.device_id
if (-not $cloudBefore.online -or $cloudBefore.public_key_sha256 -ne $before.marker.public_key_sha256) {
    throw "Cloud Host identity does not match the running app"
}

Start-Sleep -Seconds 2
$null = $before.process.CloseMainWindow()
if (-not $before.process.WaitForExit(10000)) {
    Stop-Process -Id $before.process.Id -Force
    $before.process.WaitForExit()
}
$remaining = Get-ExactProcess $InstalledExe
if ($null -ne $remaining) { throw "Installed app did not fully stop before restart" }
$null = Start-Process -FilePath $InstalledExe -PassThru

$after = Wait-HostMarker $InstalledExe $TimeoutSeconds
Assert-BuildCommit $after.process $ExpectedCommit
if ($after.marker.device_id -ne $before.marker.device_id -or $after.marker.public_key_sha256 -ne $before.marker.public_key_sha256) {
    throw "Windows restart changed the Credential Manager Host identity"
}
$cloudAfter = Get-CloudHost $cloud.base_url $accountToken $after.marker.device_id
if (-not $cloudAfter.online -or $cloudAfter.last_seen_at -le $cloudBefore.last_seen_at) {
    throw "Cloud heartbeat did not advance after the Windows Host restart"
}
if ($cloudAfter.public_key_sha256 -ne $after.marker.public_key_sha256) { throw "Cloud public key changed after restart" }

$result = [ordered]@{
    release_checks = @{ x_03 = "PASS" }
    version = $ExpectedVersion
    rc_version = $ExpectedVersion
    rc_commit = $ExpectedCommit
    platform = "windows-x86_64"
    executable_sha256 = (Get-FileHash -LiteralPath $InstalledExe -Algorithm SHA256).Hash.ToLowerInvariant()
    signer_thumbprint = $signature.SignerCertificate.Thumbprint.ToLowerInvariant()
    cloud_base_url = $cloud.base_url
    build_commit = $cloud.build_commit
    cloud_image_digest = $cloud.cloud_image_digest
    pre_restart_remote_evidence_sha256 = (Get-FileHash -LiteralPath $RemoteHostEvidence -Algorithm SHA256).Hash.ToLowerInvariant()
    host_device_sha256 = (Get-FileHash -InputStream ([IO.MemoryStream]::new([Text.Encoding]::UTF8.GetBytes($after.marker.device_id))) -Algorithm SHA256).Hash.ToLowerInvariant()
    public_key_sha256 = $after.marker.public_key_sha256
    last_seen_before = $cloudBefore.last_seen_at
    last_seen_after = $cloudAfter.last_seen_at
    identity_stable_after_restart = $true
    cloud_heartbeat_advanced = $true
}
$result | ConvertTo-Json -Depth 5 -Compress
