# Wrapper for Task Scheduler: loads the Secrets from a DPAPI-protected file, then starts a Headless Run.
# The file is readable only by the account that created it, on this machine. No Secrets are stored in the task.
#
# Create the file once, logged on as the service account:
#   New-Item -ItemType Directory -Force "$env:APPDATA\MiresSftpUploader" | Out-Null
#   Read-Host -AsSecureString 'SFTP password' | ConvertFrom-SecureString | Set-Content "$env:APPDATA\MiresSftpUploader\sftp-password.dpapi"
# Do the same for the key passphrase or S3 keys if you use them, and add one line per Secret below.
$ErrorActionPreference = 'Stop'
$dir = Join-Path $env:APPDATA 'MiresSftpUploader'

function Read-Secret([string]$file) {
    $secure = Get-Content -LiteralPath (Join-Path $dir $file) | ConvertTo-SecureString
    [System.Net.NetworkCredential]::new('', $secure).Password
}

$env:MIRES_SFTP_PASSWORD = Read-Secret 'sftp-password.dpapi'
# $env:MIRES_SFTP_KEY_PASSPHRASE = Read-Secret 'sftp-key-passphrase.dpapi'

$exe = Join-Path (Split-Path -Parent $PSScriptRoot) 'MiresSftpUploader.exe'
& $exe --headless
exit $LASTEXITCODE
