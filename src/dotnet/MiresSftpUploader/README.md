# MIRES SFTP Uploader

Scans Sources, hashes their files, optionally packs some into Archives, and uploads them to a MIRES-owned SFTP server together with a Manifest that lets consumers validate what arrived.

This folder contains the executable, `appsettings.json` (the Machine Config; edit it for this machine), `manifest.schema.json` (the Manifest JSON Schema), `scheduling.md` (how to schedule Headless Runs) and `scheduler/` (sample definitions for Task Scheduler, cron, systemd and launchd).

## First setup

1. Create the shared Data Directory once, as an administrator: `MiresSftpUploader --init-data-dir`, then add the accounts that run the tool to the group it reports (Linux and macOS; on Windows every local account is granted access).
2. Edit `appsettings.json`: set `Sftp:Host`, `Sftp:Username`, `Sftp:HostKeyFingerprint` and add at least one Source.
3. Provide Secrets through environment variables only (`MIRES_SFTP_PASSWORD`, `MIRES_SFTP_KEY_PASSPHRASE`, `MIRES_S3_<SOURCE>_ACCESS_KEY` and `_SECRET_KEY`). They are never read from files.
4. Check: `MiresSftpUploader --validate-config --check-connection`, then `MiresSftpUploader --headless --dry-run`.
5. Schedule `MiresSftpUploader --headless` with the operating system's scheduler, using the samples in `scheduler/`; `scheduling.md` has the steps for each system, how to keep Secrets out of the task, and what each exit code means.

## Scheduler one-liners

After the checks pass, register the sample for your system (edit the account and paths in it first):

- Windows: `schtasks /Create /XML scheduler\task.xml /TN "MIRES SFTP Uploader" /RU DOMAIN\svc-mires /RP *`
- Linux, cron: `crontab -e`, then paste the line from `scheduler/crontab.example`
- Linux, systemd: `cp scheduler/mires-sftp-uploader.* /etc/systemd/system/ && systemctl enable --now mires-sftp-uploader.timer`
- macOS: `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/eu.mires.sftp-uploader.plist` (after copying `scheduler/eu.mires.sftp-uploader.plist` there)

A Headless Run exits 0 (OK), 1 (some files failed), 2 (configuration or environment error), 3 (connect or authentication failed), 4 (another Run holds the lock) or 130 (cancelled); see `scheduling.md` for what to check.

`MiresSftpUploader --help` lists every option; `--version` prints the version.

## Unsigned builds

Release builds are not signed. On macOS, Gatekeeper blocks the first start: remove the quarantine flag with `xattr -d com.apple.quarantine MiresSftpUploader`. On Windows, SmartScreen may warn on first start.
