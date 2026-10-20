# MIRES SFTP Uploader

Scans Sources, hashes their files, optionally packs some into Archives, and uploads them to a MIRES-owned SFTP server together with a Manifest that lets consumers validate what arrived.

This folder contains the executable, `appsettings.json` (the Machine Config; edit it for this machine), `manifest.schema.json` (the Manifest JSON Schema) and `scheduler/` (sample definitions for Task Scheduler, cron, systemd and launchd).

## First setup

1. Create the shared Data Directory once, as an administrator: `MiresSftpUploader --init-data-dir`, then add the accounts that run the tool to the group it reports.
2. Edit `appsettings.json`: set `Sftp:Host`, `Sftp:Username`, `Sftp:HostKeyFingerprint` and add at least one Source.
3. Provide Secrets through environment variables only (`MIRES_SFTP_PASSWORD`, `MIRES_SFTP_KEY_PASSPHRASE`, `MIRES_S3_<SOURCE>_ACCESS_KEY` and `_SECRET_KEY`). They are never read from files.
4. Check: `MiresSftpUploader --validate-config --check-connection`, then `MiresSftpUploader --headless --dry-run`.
5. Schedule `MiresSftpUploader --headless` with the operating system's scheduler, using the samples in `scheduler/`.

`MiresSftpUploader --help` lists every option; `--version` prints the version.

## Unsigned builds

Release builds are not signed. On macOS, Gatekeeper blocks the first start: remove the quarantine flag with `xattr -d com.apple.quarantine MiresSftpUploader`. On Windows, SmartScreen may warn on first start.
