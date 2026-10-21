# Scheduling Headless Runs

The MIRES SFTP Uploader has no scheduler of its own. The operating system's scheduler starts a **Headless Run**: `MiresSftpUploader --headless` scans the Sources, uploads what is new or changed, writes a Report, prints one summary line and exits. Samples for every scheduler are in the `scheduler/` folder next to the executable.

A Headless Run uses the same configuration, logging and exit codes as a Run started from the window.

## First-setup checklist

Do these in order, on the machine that will run the schedule.

1. **Create the Data Directory.** As an administrator (Windows: elevated prompt, Linux/macOS: `sudo`): `MiresSftpUploader --init-data-dir`. It is safe to repeat. It prints the group it uses.
2. **Add the service account to the access group** that step 1 reported (`State:AccessGroup`, default `mires-uploader` on Linux and `staff` on macOS; the group must exist, `--init-data-dir` does not create it). On Windows the command grants `BUILTIN\Users` Modify access, so any local account already has it.
3. **Edit the Machine Config**, `appsettings.json` next to the executable: set `Sftp:Host`, `Sftp:Username`, `Sftp:HostKeyFingerprint` and at least one Source.
4. **Set the Secrets for the service account** (see [Secrets](#secrets-in-scheduled-runs)).
5. **Check the configuration as that account:** `MiresSftpUploader --validate-config --check-connection`. Exit 0 means the configuration is valid, the server answered and the host key matches the pinned Host Key Fingerprint.
6. **Try a Dry Run as that account:** `MiresSftpUploader --headless --dry-run`. It plans and reports but uploads and records nothing.
7. **Create the scheduled task** with one of the samples below.

## Secrets in scheduled Runs

A Secret (password, key passphrase, S3 access key, S3 secret key) comes from an environment variable (`MIRES_SFTP_PASSWORD`, `MIRES_SFTP_KEY_PASSPHRASE`, `MIRES_S3_<SOURCE>_ACCESS_KEY` and `MIRES_S3_<SOURCE>_SECRET_KEY`), which wins, or else from the service account's **Secret Store**. There is no option to read them from a configuration file.

**The Secret Store** is an encrypted SQLite file in the account's own application-data folder (`secrets.db`, next to the logs). Log on as the service account and run, once per Secret:

```
MiresSftpUploader --set-secret sftp-password
MiresSftpUploader --set-secret sftp-key-passphrase
MiresSftpUploader --set-secret s3-access-key:<Source>
MiresSftpUploader --set-secret s3-secret-key:<Source>
```

Each prompts without echo, or reads one line from stdin (`printf '%s\n' "$VALUE" | MiresSftpUploader --set-secret sftp-password`). The value is never accepted as an argument. `--list-secrets` shows names and state (`stored`, `unreadable`), never values; `--clear-secret <name>` removes one.

The key is derived from the machine identifier and the account name, so the store is readable only by the same account on the same machine. It protects against a copied, backed-up or leaked file. It does **not** protect against another process running as the same account, who can derive the same key. If you need that, use the DPAPI, Keychain or `0600` env-file patterns below. If the machine is cloned or reinstalled, or the account is renamed, the stored Secrets read as `unreadable` and a Run fails with a clear message until you set them again. A machine with no stable machine identifier (some containers) cannot use the Secret Store and says so.

**Never put a Secret in a task definition**, a crontab, a unit file or a plist: they are readable by other accounts or end up in backups and logs. Use one of these patterns instead.

| System | Pattern |
|---|---|
| Windows | Run as a dedicated service account. Either set the variables in that account's user environment, or use a wrapper that reads a DPAPI-protected file (`scheduler/run-with-dpapi.ps1`). The file can be decrypted only by the same account on the same machine. |
| Linux, systemd | `EnvironmentFile=/etc/mires-sftp-uploader.env` at mode `0600`, owned by the service account. |
| Linux, cron | A wrapper that sources a file at mode `0600` (`scheduler/run-from-env-file.sh`, which refuses a file with another mode). |
| macOS | A wrapper that reads the Keychain with `security find-generic-password` (`scheduler/run-with-keychain.sh`). |

## Windows Task Scheduler

Sample: `scheduler/task.xml` (daily at 02:00, a wrapper script, the Secrets in a DPAPI file).

1. Create a dedicated service account, for example `svc-mires`, (an ordinary account is enough; `--init-data-dir` grants `BUILTIN\Users` access to the Data Directory). Give it read access to every Source and the install folder.
2. Log on as that account once and create the DPAPI file as described at the top of `scheduler/run-with-dpapi.ps1`.
3. Edit `task.xml` (the account in `UserId`, the paths, the start time) and import it: `schtasks /Create /XML task.xml /TN "MIRES SFTP Uploader" /RU DOMAIN\svc-mires /RP *`.
4. Start it once by hand: `schtasks /Run /TN "MIRES SFTP Uploader"`, then read **Last Run Result** in Task Scheduler. It shows the exit code.

Settings in the sample that matter:

- **Run whether the user is logged on or not**, as the service account, with the working directory set to the install folder.
- **Do not start a new instance** (`MultipleInstancesPolicy` `IgnoreNew`). If a Run still holds the lock, a second start exits 4 on its own anyway.
- **Run as soon as possible after a missed start** (`StartWhenAvailable`). The tool does not catch up on missed Runs.
- No execution time limit: a large first Run can take many hours.

Without the wrapper, you can run the executable directly (`Program: C:\Program Files\MiresSftpUploader\MiresSftpUploader.exe`, `Arguments: --headless`) when the Secrets are user-scope environment variables of the service account.

## cron

Sample: `scheduler/crontab.example` with the wrapper `scheduler/run-from-env-file.sh`. cron is the baseline on any Linux or Unix; install the line as the service account with `crontab -e`.

- `flock -n` skips a start while the previous Run is still going.
- cron does not run a start that was missed because the machine was off. On a systemd distribution prefer the timer below.
- stdout carries only the summary line; send stderr (the log) to a file, as the sample does.

## systemd

Preferred on systemd distributions. Samples: `scheduler/mires-sftp-uploader.service` and `scheduler/mires-sftp-uploader.timer`.

1. `install -m 0600 -o svc-mires /dev/null /etc/mires-sftp-uploader.env`, then add `MIRES_SFTP_PASSWORD=...` (one `NAME=value` per line, no quotes).
2. Copy both units to `/etc/systemd/system/`, edit the account and paths, then `systemctl daemon-reload` and `systemctl enable --now mires-sftp-uploader.timer`.
3. Test: `systemctl start mires-sftp-uploader.service`, then `journalctl -u mires-sftp-uploader.service`.

`Persistent=true` in the timer runs a start that was missed while the machine was off. The service treats exit 4 (another Run holds the lock) as success, so an overlap is not reported as a failed unit.

## launchd

Sample: `scheduler/eu.mires.sftp-uploader.plist` with the wrapper `scheduler/run-with-keychain.sh`. It is a LaunchAgent of the service account, so the job can read that account's Keychain.

1. As the service account, store each Secret: `security add-generic-password -s mires-sftp-uploader -a MIRES_SFTP_PASSWORD -w` (it prompts for the value).
2. Copy the plist to `~/Library/LaunchAgents/` and load it: `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/eu.mires.sftp-uploader.plist`.
3. Test: `launchctl kickstart gui/$(id -u)/eu.mires.sftp-uploader`.

launchd runs a start missed while the Mac slept when it wakes; it does not run one missed while the Mac was off. The binary is unsigned: remove the quarantine flag first (`xattr -d com.apple.quarantine MiresSftpUploader`).

## Overlapping Runs

Only one Run can use the Upload State at a time, whether it was started by the scheduler or by a person in the window. A second Headless Run that finds the lock held writes a warning and exits 4 at once. Treat exit 4 as "skipped" wherever the scheduler lets you.

## When a scheduled Run fails

A Headless Run prints exactly one line on stdout, for example `succeeded=12 skipped=340 failed=0 exit=0 report=/var/lib/mires-sftp-uploader/reports/run-<id>.json`. The log goes to stderr and to the log file. The tool sends no notifications; watch the scheduler's last result or the exit code.

| Exit code | Meaning | What to check |
|---|---|---|
| 0 | OK, or every file skipped as unchanged | Nothing. |
| 1 | Some files failed | The Report (`--report`, or `Report:Directory`; by default `reports/` inside the Data Directory) lists each failed file with its reason. The next Run retries them. |
| 2 | Configuration or environment error | Run `MiresSftpUploader --validate-config` as the service account. Common causes: a missing Secret, a Data Directory the account cannot write (run `--init-data-dir`, check the group), an unknown `--source`. |
| 3 | Could not connect or authenticate, including a host key mismatch | Run `--validate-config --check-connection` as the service account. Check the network, the credentials and `Sftp:HostKeyFingerprint`. A changed fingerprint means the server key changed: verify it before updating the setting. |
| 4 | Another Run holds the lock | Normal when a previous Run is still going. If it never clears, look for a stuck process; a stopped one is recovered as an Abandoned Run. |
| 130 | Cancelled | The Run was stopped (Ctrl+C, a termination signal, or Cancel in the window). Unfinished files are retried. |

Where things are:

- **Report:** `--report <path>` writes one for this Run. Without it, the Report goes to `Report:Directory`, or to `reports/` inside the Data Directory. Past Runs: `MiresSftpUploader --list-runs`, and `--export-run <id>` prints or saves a Report.
- **Log:** `Logging:Directory`, by default the `logs` folder in the service account's own application-data folder (Windows `%APPDATA%\MiresSftpUploader`, macOS `~/Library/Application Support/MiresSftpUploader`, Linux `~/.config/mires-sftp-uploader`). The default level is `Info`; use `--log-level Debug` for more. Secrets are never written to the log.
- **Data Directory:** Windows `%ProgramData%\MiresSftpUploader`, macOS `/Users/Shared/MiresSftpUploader`, Linux `/var/lib/mires-sftp-uploader`; change it with `MIRES_DATA_DIR` or `--data-dir`. A scheduled Run never falls back to another folder: if the account cannot use it, the Run exits 2 and says which path, which account and which command to run.
