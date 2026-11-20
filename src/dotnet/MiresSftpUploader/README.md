# MIRES SFTP Uploader

Scans Sources, hashes their files, optionally packs some into Archives, and uploads them to a MIRES-owned SFTP server together with a Manifest that lets consumers validate what arrived.

This folder contains the executable, `appsettings.json` (the Machine Config; edit it for this machine), `manifest.schema.json` (the Manifest JSON Schema), `scheduling.md` (how to schedule Headless Runs) and `scheduler/` (sample definitions for Task Scheduler, cron, systemd and launchd).

## First setup

1. Create the shared Data Directory once, as an administrator: `MiresSftpUploader --init-data-dir`, then add the accounts that run the tool to the group it reports (Linux and macOS; on Windows every local account is granted access).
2. Edit `appsettings.json`: set `Sftp:Host`, `Sftp:Username`, `Sftp:HostKeyFingerprint` and add at least one Source. `Sftp:RemoteRoot` and a Source's `RemotePath` may contain `{date}` (yyyyMMdd), `{time}` (HHmmss), `{year}`, `{month}` and `{day}`, replaced by the start of the Run in UTC: `/incoming/{date}` uploads into a new directory each day. Each Run works the path out once; a retry of an earlier Run uses the path of that Run. Because the Upload State is kept per directory, a new directory starts empty and every file is uploaded into it.
3. Provide Secrets either as environment variables (`MIRES_SFTP_PASSWORD`, `MIRES_SFTP_KEY_PASSPHRASE`, `MIRES_S3_<SOURCE>_ACCESS_KEY` and `_SECRET_KEY`), which win, or in the account's Secret Store: type them in the Settings page, or run `MiresSftpUploader --set-secret sftp-password` (the value is read from a prompt or stdin, never from the command line). They are never read from the configuration files. The Secret Store is encrypted for this account on this machine; it protects a copied or leaked file, not someone already running as that account (see `docs/adr/0003-secret-store-per-account-machine-derived-key.md`).
   To keep a recurring Run from seeing the same files again, a Source can move its files after upload: `Sources:<n>:AfterUpload:OnSuccess` and `:OnFailure`, each with `Action: Move` and a `Path` (or, for S3, a `Bucket` and `Prefix`), so successful and failed files can go to different places. Both are also in the Settings page (Avalonia and TUI) under the Source.
4. Check: `MiresSftpUploader --validate-config --check-connection`, then `MiresSftpUploader --headless --dry-run`.
5. Schedule `MiresSftpUploader --headless` with the operating system's scheduler, using the samples in `scheduler/`; `scheduling.md` has the steps for each system, how to keep Secrets out of the task, and what each exit code means.

## TUI

`MiresSftpUploader --tui` opens the **TUI**, the whole application in a full-screen terminal for machines reached over SSH. It has four pages behind a tab bar: Upload, History, Settings and Help, switched with F9, F10, F11 and F12 or a mouse click. A `●` on the Settings tab marks unsaved changes; unsaved edits survive a tab switch. One status line and one key bar at the bottom are shared by all pages. Ctrl+Q or Ctrl+C quits (with unsaved Settings changes it asks Save, Discard or Cancel); SIGHUP or SIGTERM exits with code 130 and saves nothing. `--tui` has the same terminal rules as `--configure` (exit code 2 and one stderr line when stdin or stdout is redirected, `TERM` is `dumb` or unset, or the terminal is below 80x24), honours only `--data-dir` and `--log-level`, and cannot be combined with `--configure` or `--headless`. With an invalid configuration it opens on Settings.

Key bindings, besides F9-F12 and Ctrl+Q. Tab moves between the parts of a page and Enter activates the focused item; the mouse works where the terminal supports it and is never required.

- **Upload:** R Run, D Dry run, S Scan, X Cancel the Run, T Retry failed files; 1-4 filter the file table (succeeded, failed, skipped, pending); Space includes or excludes the selected Source; L shows or hides the Log pane; End follows the active file again (moving the cursor stops following). Quitting during a Run asks whether to cancel the Run and quit, or go back.
- **History:** 1-3 filter the Runs (All, Attention, Live); F shows failed outcomes only; R retries the failed files of the selected Run (opens Upload); X cancels the selected Run (a request to cancel for another user's Run); J or C exports a Report as JSON or CSV; F5 refreshes.
- **Settings:** the keys of the Settings TUI below.
- **Help:** Up/Down choose a topic or scroll; PageUp, PageDown, Home and End scroll; Tab switches between the topic list and the text. The Keys topic repeats this list.

## Upload progress

While a Run uploads, the Engine publishes an `UploadProgress` snapshot about 4 times a second: for every file or Archive uploading now its source, path, bytes sent, total and **Upload Speed**, plus the total Upload Speed; a last snapshot with no files clears the total. Bytes sent are the bytes the server has acknowledged, not the bytes read from the file. Upload Speed is smoothed over a 3 s sliding window and absent until 2 samples exist; a retry starts the file again at 0. Scans and Dry Runs emit no snapshots. The Avalonia UI, the TUI and the Headless Run are consumers of these snapshots.

A Headless Run shows and logs progress without touching stdout, which stays exactly the one summary line. When stderr is an interactive terminal (not redirected, `TERM` not `dumb`, `CI` not set) it draws one status line that is rewritten in place and cut to the window width, without ANSI escapes: `↑ 9.2 MiB/s · 3 uploading · 412 of 1,280 files done` (the speed and the uploading count are left out when nothing uploads; a file is done when Succeeded, Failed or Skipped). Log lines on stderr go through the same writer, so the status line is never left in front of one; it is cleared before the summary and on Ctrl+C. Dry Runs and Scans draw no status line. Every Headless Run also writes one line every 10 s while files upload, for example `progress: 412 of 1,280 files done, 3 uploading, 9.2 MiB/s`, to the log file only (logger name `MiresSftpUploader.Progress`, at Information level, so a configured level above Information hides it); it is not a setting. With your own `NLog` section the logger name is yours to route.

## Settings TUI

On a machine without a display (for example over SSH) run `MiresSftpUploader --configure` to open the **Settings TUI** (the TUI on its Settings page), a full-screen terminal editor with the same pages, Locked Settings, validation and save rules as the Settings page. `--configure` is supported on Linux and macOS; Windows is unverified (the Windows build is a `WinExe` and an interactive console session from it has not been tested). It needs an interactive terminal of at least 80x24 and refuses with exit code 2 and one line on stderr when stdin or stdout is redirected, when `TERM` is `dumb` or unset (Unix), or when the terminal is too small. Only `--data-dir` and `--log-level` are honoured with it.

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
