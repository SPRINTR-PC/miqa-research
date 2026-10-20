#!/usr/bin/env bash
# Wrapper for launchd: reads the Secrets from the macOS Keychain, then starts a Headless Run.
# Store a Secret once, as the service account:
#   security add-generic-password -s mires-sftp-uploader -a MIRES_SFTP_PASSWORD -w
# (-w as the last option prompts for the value, so it never appears in shell history or a process list.)
set -euo pipefail
MIRES_SFTP_PASSWORD="$(security find-generic-password -s mires-sftp-uploader -a MIRES_SFTP_PASSWORD -w)"
export MIRES_SFTP_PASSWORD
# MIRES_SFTP_KEY_PASSPHRASE="$(security find-generic-password -s mires-sftp-uploader -a MIRES_SFTP_KEY_PASSPHRASE -w)"; export MIRES_SFTP_KEY_PASSPHRASE
exec "$(dirname "$0")/../MiresSftpUploader" --headless
