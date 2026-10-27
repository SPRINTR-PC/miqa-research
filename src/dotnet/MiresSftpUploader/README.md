# MIRES SFTP Uploader

Scans Sources, hashes their files, optionally packs some into Archives, and uploads them to a MIRES-owned SFTP server together with a Manifest that lets consumers validate what arrived.

This folder contains the executable, `appsettings.json` (the Machine Config; edit it for this machine), `manifest.schema.json` (the Manifest JSON Schema), `scheduling.md` (how to schedule Headless Runs) and `scheduler/` (sample definitions for Task Scheduler, cron, systemd and launchd).

## First setup

1. Create the shared Data Directory once, as an administrator: `MiresSftpUploader --init-data-dir`, then add the accounts that run the tool to the group it reports (Linux and macOS; on Windows every local account is granted access).
2. Edit `appsettings.json`: set `Sftp:Host`, `Sftp:Username`, `Sftp:HostKeyFingerprint` and add at least one Source.
3. Provide Secrets either as environment variables (`MIRES_SFTP_PASSWORD`, `MIRES_SFTP_KEY_PASSPHRASE`, `MIRES_S3_<SOURCE>_ACCESS_KEY` and `_SECRET_KEY`), which win, or in the account's Secret Store: type them in the Settings page, or run `MiresSftpUploader --set-secret sftp-password` (the value is read from a prompt or stdin, never from the command line). They are never read from the configuration files. The Secret Store is encrypted for this account on this machine; it protects a copied or leaked file, not someone already running as that account (see `docs/adr/0003-secret-store-per-account-machine-derived-key.md`).
4. Check: `MiresSftpUploader --validate-config --check-connection`, then `MiresSftpUploader --headless --dry-run`.
5. Schedule `MiresSftpUploader --headless` with the operating system's scheduler, using the samples in `scheduler/`; `scheduling.md` has the steps for each system, how to keep Secrets out of the task, and what each exit code means.

## Settings TUI

On a machine without a display (for example over SSH) run `MiresSftpUploader --configure` to open the **Settings TUI**, a full-screen terminal editor with the same pages, Locked Settings, validation and save rules as the Settings page. `--configure` is supported on Linux and macOS; Windows is unverified (the Windows build is a `WinExe` and an interactive console session from it has not been tested). It needs an interactive terminal of at least 80x24 and refuses with exit code 2 and one line on stderr when stdin or stdout is redirected, when `TERM` is `dumb` or unset (Unix), or when the terminal is too small. Only `--data-dir` and `--log-level` are honoured with it.

Key bindings:

- Tab / Shift+Tab (or Down / Up) move between fields; Enter or Right enters a page's form or list; Esc goes back one level.
- Ctrl+S saves, Ctrl+R reverts, Ctrl+PageUp / Ctrl+PageDown change page, F4 lists every problem and warning, Ctrl+Q quits (with unsaved changes it asks Save, Discard or Cancel).
- F5 runs Check connection for the saved configuration (one session, host key and credentials, no upload); with unsaved changes it asks you to save first.
- Path fields have Tab completion: a unique match completes, several complete the common prefix and list the candidates, and Tab moves on only when there is nothing to complete.

Secrets are set and cleared with their own Save and Clear buttons, saved to the Secret Store at once and never shown.

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
