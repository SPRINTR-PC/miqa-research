#!/usr/bin/env bash
# Wrapper for cron: exports the Secrets from a file only the service account can read, then starts a Headless Run.
# Create the file once:   install -m 0600 /dev/null ~/.config/mires-sftp-uploader.env
# Content, one per line, no quotes:   MIRES_SFTP_PASSWORD=...
set -euo pipefail
env_file="${MIRES_ENV_FILE:-$HOME/.config/mires-sftp-uploader.env}"
mode="$(stat -c '%a' "$env_file" 2>/dev/null || stat -f '%Lp' "$env_file")"
[ "$mode" = "600" ] || { echo "$env_file must have mode 0600, has $mode" >&2; exit 2; }
set -a
# shellcheck disable=SC1090
. "$env_file"
set +a
exec "$(dirname "$0")/../MiresSftpUploader" --headless
