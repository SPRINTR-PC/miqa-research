# Builds the release publishes of MiresSftpUploader for all four targets, smoke-tests the one matching this
# machine, and packages each as artifacts/packages/MiresSftpUploader-<version>-<rid>.{zip,tar.gz}.
#
# Usage: ./publish.ps1 [-Version x.y.z] [-Rid win-x64,linux-x64,...]   (default: all four RIDs, version from the csproj)
# Signing is off unless SignWindows / SignMac are set; see docs/signing.md.
[CmdletBinding()]
param(
    [string]$Version,
    [string[]]$Rid = @('win-x64', 'linux-x64', 'linux-arm64', 'osx-arm64')
)
$ErrorActionPreference = 'Stop'

$here = $PSScriptRoot
$root = (Resolve-Path (Join-Path $here '../../..')).Path
$project = Join-Path $here 'MiresSftpUploader.csproj'
$out = Join-Path $root 'artifacts'

$props = @()
if ($Version) {
    $props += "-p:Version=$Version"
} else {
    $Version = (dotnet msbuild $project -getProperty:Version).Trim()
}

$arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
$hostRid = $null
if ($IsWindows -or $env:OS -eq 'Windows_NT') { if ($arch -eq 'X64') { $hostRid = 'win-x64' } }
elseif ($IsLinux) { $hostRid = if ($arch -eq 'Arm64') { 'linux-arm64' } elseif ($arch -eq 'X64') { 'linux-x64' } }
elseif ($IsMacOS) { if ($arch -eq 'Arm64') { $hostRid = 'osx-arm64' } }

function Test-Published([string]$Dir, [string]$ExeName) {
    $exe = Join-Path $Dir $ExeName
    Write-Host "Smoke test: $exe"
    $actual = (& $exe --version).Trim()
    if ($LASTEXITCODE -ne 0) { throw '--version failed' }
    if ($actual -ne $Version) { throw "--version printed '$actual', expected '$Version'" }

    # The shipped appsettings.json has no host, username, host key or Sources, so --validate-config is expected to
    # report exactly those four required fields and nothing else.
    $errorLines = @(& $exe --validate-config 2>&1 | ForEach-Object { "$_" })
    $rc = $LASTEXITCODE
    if ($rc -eq 0) { return }
    if ($rc -ne 2) { throw "--validate-config exited ${rc}: $($errorLines -join "`n")" }
    $expected = '^  (Sftp:Host|Sftp:Username|Sftp:HostKeyFingerprint): is required|^  Sources: at least one enabled Source is required'
    $unexpected = @($errorLines | Where-Object { $_ -match '^  ' -and $_ -notmatch $expected })
    if ($unexpected.Count -gt 0) { throw "--validate-config reported unexpected errors:`n$($unexpected -join "`n")" }
}

New-Item -ItemType Directory -Force (Join-Path $out 'packages') | Out-Null
foreach ($r in $Rid) {
    Write-Host "=== $r"
    $dir = Join-Path $out "publish/$r"
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
    dotnet publish $project "-p:PublishProfile=$r" @props
    if ($LASTEXITCODE -ne 0) { throw "dotnet publish failed for $r" }

    $isWin = $r.StartsWith('win-')
    $exeName = if ($isWin) { 'MiresSftpUploader.exe' } else { 'MiresSftpUploader' }
    foreach ($required in @($exeName, 'appsettings.json', 'README.md')) {
        if (-not (Test-Path (Join-Path $dir $required))) { throw "Missing $required in publish output for $r" }
    }

    if ($r -eq $hostRid) { Test-Published $dir $exeName }
    else { Write-Host "Skipping smoke test for $r (host is $(if ($hostRid) { $hostRid } else { 'unsupported' }))" }

    $name = "MiresSftpUploader-$Version-$r"
    $packages = Join-Path $out 'packages'
    Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $packages "$name.zip"), (Join-Path $packages "$name.tar.gz")
    if ($isWin) {
        Compress-Archive -Path (Join-Path $dir '*') -DestinationPath (Join-Path $packages "$name.zip")
    } else {
        tar -czf (Join-Path $packages "$name.tar.gz") -C $dir .
        if ($LASTEXITCODE -ne 0) { throw "tar failed for $r" }
    }
    Write-Host "Packaged $name"
}
