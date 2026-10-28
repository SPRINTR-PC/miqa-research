# Manual per-OS release checklist

The automated tests (unit, UI, and the opt-in Container and Scale categories) run on one development machine. Everything they cannot prove is checked by hand before each release. Run this on a release candidate built by `publish.sh` / `publish.ps1`, tick every box, and write what you saw next to the item or in the release notes. A failed item blocks the release unless a ticket records why it does not.

Targets: `win-x64`, `linux-x64`, `linux-arm64`, `osx-arm64`. The eleven numbered items are the ones fixed in spec #329; items 1 to 11 keep that numbering. Each says **Do**, **Expect**, and **Never verified** where no implementer could run it on a real machine, in which case the first run is research: record the result and fix the doc or the code.

Preparation, once per machine:

- Unpack the package for the target (`MiresSftpUploader-<version>-<rid>.zip` or `.tar.gz`) into a fresh folder and run from there, not from the build tree.
- Have an SFTP server you can write to (the Container tests' OpenSSH image works: see [testing.md](testing.md)) and a throw-away Source folder with a few files.

---

## 1. SQLite loads from the untrimmed single file, pragmas, `BEGIN IMMEDIATE`, 1,000,000 rows

Targets: all four.

- [ ] **Do:** with the packaged single-file executable run `--init-data-dir`, then `--headless --dry-run`, then a real `--headless` Run of a small Source.
- **Expect:** `state.db` is created and used. No `DllNotFoundException`, `EntryPointNotFoundException` or "unable to load native library" in the log. This proves `IncludeNativeLibrariesForSelfExtract` (ADR 0002) with the native SQLite the package carries (`SQLitePCLRaw.lib.e_sqlite3` 2.1.14, see item 12).
- [ ] **Do:** while a Run is going, read the database from another process (`sqlite3 state.db 'PRAGMA journal_mode; PRAGMA busy_timeout; PRAGMA synchronous;'`).
- **Expect:** `wal`, and the app's settings (`busy_timeout=30000`, `synchronous=NORMAL`) apply to every pooled connection, not only the first: check also a second Run in the same process (two Runs one after another from the UI).
- [ ] **Do:** trace the SQL (for example `sqlite3_trace_v2` in a debug build, or `strace -e trace=write` on the db) and note the text Microsoft.Data.Sqlite emits to start a write transaction.
- **Expect:** `BEGIN IMMEDIATE`. If it emits plain `BEGIN`, record it: the writer assumes the write lock is taken up front.
- [ ] **Do (load):** fill the Upload State with 1,000,000 file rows (a Source of that many tiny files, or insert into `Files`), then run the next Run and open Run History.
- **Expect:** the Run starts without a long stall, memory stays near the figure in [testing.md](testing.md#what-the-scale-tests-found) (about 670 MB for the Source's state at 1,000,000 files), and Run History opens.

## 2. Windows: a second account, and `AttachConsole`

Target: `win-x64`.

- [ ] **Do:** as an elevated administrator run `MiresSftpUploader --init-data-dir`. As account A run a Run so `state.db`, `state.db-wal` and `state.db-shm` exist. Then from a different non-administrator account B (`runas` or a second session) run `--headless --dry-run`, `--list-runs`, and a real Run while A's window is open.
- **Expect:** B reads and writes the Upload State through `-wal` and `-shm` with no "unable to open database file" or "attempt to write a readonly database". The ACL set by `--init-data-dir` is inheritable, so files A created later (`-wal`, `-shm`, Reports, the lock) are usable by B: `icacls` on `state.db-wal` and `state.db-shm` shows `BUILTIN\Users` with Modify inherited (`(I)`). **Never verified on Windows.**
- [ ] **Do:** with B's Run going, open the History page as A and request Cancel.
- **Expect:** A sees B's Run as in progress and B's Run stops within the cancel poll interval (cross-user cancel).
- [ ] **Do (`AttachConsole`, cmd.exe):** from `cmd.exe` and PowerShell run `MiresSftpUploader.exe --version`, `--help`, `--headless --dry-run`, `--validate-config`, and `MiresSftpUploader.exe --version > out.txt`.
- **Expect:** output appears in the console, the prompt returns at once (the executable is a `WinExe` and attaches to the parent console in `Program.cs`), the redirect fills `out.txt`, and `echo %ERRORLEVEL%` shows the exit code.
- [ ] **Do (`AttachConsole`, Task Scheduler):** import `scheduler/task.xml` (item 10), run it, read **Last Run Result**.
- **Expect:** the Run's exit code (0, 1, 3 or 4), no hung task, no flashing window, and the log and Report written even though there is no parent console. **Never verified.** If `AttachConsole` misbehaves here, build the console shim (a console-subsystem launcher) instead.

## 3. macOS: `/Users/Shared` group behaviour and Gatekeeper

Target: `osx-arm64`.

- [ ] **Do:** `sudo MiresSftpUploader --init-data-dir`, then `ls -leO@ /Users/Shared/MiresSftpUploader`. Add a second user to `staff` (the default `State:AccessGroup` on macOS) and run a Run as each user in turn.
- **Expect:** group `staff`, mode `2770` (setgid) on the directory, `0660` on files, and entries created by either user (`state.db`, `-wal`, `-shm`, Reports) keep group `staff`. If macOS does not inherit the group on `/Users/Shared`, record which entries ended up with which group and whether the second user still works. **Never verified.**
- [ ] **Do:** download the package through a browser (so it is quarantined), unpack it and start the executable by double-click and from Terminal.
- **Expect:** the documented unsigned behaviour (README, "Unsigned builds"): Gatekeeper blocks the first start, and `xattr -d com.apple.quarantine MiresSftpUploader` lets it run. Correct the README if what you see differs.

## 4. Logging, and a real single-file publish on the four targets

Targets: all four.

- [ ] **Do:** run on two consecutive days (or advance the clock one day between Runs) and list the log folder.
- **Expect:** the older log carries a date suffix and files older than `Logging:RetainDays` are removed. Note the suffix NLog actually produced. Logging is configured in code (`Logging/AppLogging.cs`), not from a JSON NLog config, so the `${var:}` and JSON `minLevel` cases from the research only matter if that changes.
- [ ] **Do:** set `MIRES_Logging__Level=Debug` (and again with `--log-level Debug`), start a Run.
- **Expect:** the level changes. Check on Windows (case-insensitive variable names) and Linux (case-sensitive): the key casing the app accepts matches the docs.
- [ ] **Do:** on each OS run the publish script (`publish.sh`, `publish.ps1`) for all four targets, from a foreign host as well (for example `win-x64` from macOS). **Never verified:** `publish.ps1`, and every publish of a RID other than the host's, have not been run.
- **Expect:** all four packages build, each unpacked package runs on its own OS, and the script's smoke test (`--version`, `--validate-config`) passes for the host RID. Record any RID that cannot be published from another host.

## 5. S3 checksum behaviour against MinIO and one other server

Target: any one OS.

- [ ] **Do:** configure an S3 Source against MinIO and run a Run, then repeat against one other third-party S3-compatible server (for example Ceph RGW, Wasabi, Backblaze B2 or Cloudflare R2). The Container tests cover MinIO only. **Never verified against a second server.**
- **Expect:** listing and reading work, the ETag change token is stable between Runs (an unchanged object is Skipped), and there are no `x-amz-checksum`, `x-amz-content-sha256` or signature errors: the SDK's request checksum is `WHEN_REQUIRED`, so a server that rejects the newer default checksum headers still accepts the requests. Record the server and its version.

## 6. Encrypted ed25519 private keys

Target: any one OS (the SSH.NET code is the same everywhere).

- [ ] **Do:** `ssh-keygen -t ed25519` with a passphrase, install the public key, set `Sftp:PrivateKeyPath` and `MIRES_SFTP_KEY_PASSPHRASE`, run `--validate-config --check-connection`. Repeat with an RSA key and an unencrypted key.
- **Expect:** exit 0 and the host key matches. A wrong or missing passphrase gives a clear configuration or authentication error (exit 2 or 3), not a stack trace.

## 7. Golden-file zip: byte-identical Archives on every OS

Targets: all four. Today the golden zip has been checked on macOS only.

- [ ] **Do:** on each OS run `dotnet test MiqaResearch.slnx --filter "FullyQualifiedName~ArchiveTests"` (the golden-file test), and build an Archive from the same fixed members on each OS, then compare `sha256sum` of the zip across machines.
- **Expect:** the golden test passes and the hashes are equal on `win-x64`, `linux-x64`, `linux-arm64` and `osx-arm64`. A difference (line endings, time zone, attribute bits, extra fields) means the deterministic writer has an OS dependency to fix.

## 8. Write-only SFTP account (mode `0300` directory)

Target: any one OS.

- [ ] **Do:** against an account that can create and rename in its directory but not read or list it (container user with a `0300` directory), run a Run with Verification at `Size`, `Hash` and `ReadBack`, and a second Run.
- **Expect:** the behaviour the test plan assumes: upload and rename succeed; a Verification level the server cannot answer is reported as documented, not as a silent pass; the In-progress Marker is placed only if the account can delete; a Manifest that cannot be replaced is written run-stamped with `supersedes` in the next one. Record where your server differs.

## 9. Markdown viewer, light-mode contrast, logos and icon

Targets: all four (look at least on one Windows and one Mac).

- [ ] **Do:** open Help (README, scheduling guide) in the dark and the light theme.
- **Expect:** `Markdown.Avalonia.Tight` renders headings, tables, code blocks and links in both themes; text and code backgrounds use the app's theme colours (known open point: the viewer's own theme colours may not follow the app theme, so check contrast of body text, code blocks, links and table borders in light and dark). If it fails on Avalonia 12, switch to the minimal renderer.
- [ ] **Do:** look at the primary button in light mode.
- **Expect:** its label and background have acceptable contrast (check against WCAG AA, 4.5:1).
- [ ] **Do:** look at the MIRES logo in the sidebar and the window title bar and task bar icon.
- **Expect:** the logo renders. **Known open point:** the window icon is still the template `Assets/avalonia-logo.ico` (`Views/MainWindow.axaml`); replace it with the MIRES icon before a public release, or record that the release ships with it.

## 10. Scheduler samples import and lint

Targets: the OS each sample is for.

- [ ] **Windows:** `schtasks /Create /XML scheduler\task.xml /TN "MIRES SFTP Uploader" /RU DOMAIN\svc-mires /RP *`, then `schtasks /Run /TN "MIRES SFTP Uploader"`. Run `scheduler\run-with-dpapi.ps1` once as the service account. **Expect:** the XML imports without an error, and **Last Run Result** shows the Run's exit code. **Never verified.**
- [ ] **Linux, systemd:** edit the paths, then `systemd-analyze verify scheduler/mires-sftp-uploader.service scheduler/mires-sftp-uploader.timer`, install both, `systemctl start`, read `journalctl -u`. **Expect:** no warnings beyond paths you have not created. **Never verified.**
- [ ] **Linux, cron:** install `scheduler/crontab.example` with `crontab -e` as the service account. **Expect:** it saves without a syntax error, `flock -n` skips an overlapping start, and the next start writes a Report.
- [ ] **Wrapper scripts:** unpack the `.tar.gz` and the `.zip` and list `scheduler/*.sh`. **Expect:** the `.tar.gz` keeps the executable bit; if the package you ship does not, `scheduling.md` must say `chmod +x scheduler/*.sh`. `run-from-env-file.sh` refuses an env file whose mode is not `0600`. **Never verified:** `chmod +x` on the wrappers.
- [ ] **macOS:** `plutil -lint scheduler/eu.mires.sftp-uploader.plist`, then `launchctl bootstrap` it and `launchctl kickstart`; `run-with-keychain.sh` reads the Secret as the service user. **Expect:** `OK` from `plutil`, and a Report after the kickstart.
- **Expect (all):** the scheduled start runs `--headless`, takes the lock (exit 4 when one is held), writes the Report, and the scheduler sees the exit code.

## 11. The published binary starts and the UI opens

Targets: all four.

- [ ] **Do:** from the unpacked package run `--version`, then `--validate-config` against the shipped `appsettings.json`, then start it without arguments.
- **Expect:** `--version` prints the package version with its `+<commit>` suffix. `--validate-config` fails only on the documented required fields (`Sftp:Host`, `Sftp:HostKeyFingerprint`, at least one Source). The window opens, says no Sources are configured, and every page renders (Upload, History, Settings, Help, log pane).

## 12. Dependency check (every release, any OS)

- [ ] **Do:** `dotnet build MiqaResearch.slnx` and `dotnet list src/dotnet/MiresSftpUploader.Core package --vulnerable --include-transitive`.
- **Expect:** no `NU1902` or `NU1903`. `Microsoft.Data.Sqlite 10.0.0` brings `SQLitePCLRaw.lib.e_sqlite3 2.1.11`, flagged by GHSA-2m69-gcr7-jv3q (`<= 2.1.11`), so `MiresSftpUploader.Core.csproj` references `2.1.14` directly. When Microsoft.Data.Sqlite brings a patched native library itself, drop the direct reference; until then re-run item 1 on every target after any change here.

## 13. Optional: a 4 GiB file

- [ ] **Do:** `MIRES_TEST_4GIB=1 dotnet test MiqaResearch.slnx --filter "TestCategory=Container&FullyQualifiedName~SftpHashProof"`, or upload one 4 GiB file to an SFTP server by hand and compare its `sha256sum` with the Manifest.
- **Expect:** equal hashes and flat memory during the transfer. The automated hash proof covers 64 MiB only. There is no resume: a restarted Run uploads the file again.

## 14. Settings TUI (`--configure`)

Targets: as listed per item. Modal dialogs (Unlock confirmation, unsaved changes, per-Source Archive Rules) CAN be driven headlessly by injecting keys from a timer while the modal runs (see `SettingsTuiConfirmDialogTests`), so the automated tests cover their keys; the items below stay manual to check how they look and behave in a real terminal.

- [ ] **Windows console under the `WinExe` build** (win-x64). **Never verified.** **Do:** run `MiresSftpUploader --configure` from cmd, PowerShell, Windows Terminal and an SSH session into Windows. **Expect:** the Settings TUI opens and takes keys, or it fails cleanly. Record the result; if it does nothing, try `AttachConsole` plus `CONIN$`/`CONOUT$`, `SetStdHandle` and Terminal.Gui's `ansi` driver, or build the console shim from item 2. Until verified, `--configure` is documented as supported on Linux and macOS, with Windows unverified.
- [ ] **SSH session** (linux-x64, linux-arm64, osx-arm64). **Do:** `ssh host` and run `--configure`, edit a field, save with Ctrl+S, quit with Ctrl+Q. **Expect:** it renders, the keys work, the terminal is restored on exit.
- [ ] **Throttled SSH session.** **Do:** the same over a slow link (for example `tc qdisc add dev eth0 root netem delay 200ms`, or a mobile hotspot). **Expect:** usable, no garbled screen, no hang.
- [ ] **Resize while running.** **Do:** shrink the terminal below 80x24, then enlarge it. **Expect:** an overlay says the terminal is too small instead of a broken screen, and the form returns when it is large enough.
- [ ] **`TERM=dumb`.** **Do:** `TERM=dumb MiresSftpUploader --configure`. **Expect:** exit code 2, one line on stderr, nothing on stdout.
- [ ] **A 256-colour terminal.** **Do:** `TERM=xterm-256color` in a terminal without truecolor. **Expect:** the colours round to the nearest ones and keep their meaning (cyan navigation, green changed, red error, amber locked or warning), and the symbols carry it too.
- [ ] **Emoji and Unicode rendering** of the lock, the changed mark and the error mark in Windows Terminal, PuTTY and macOS Terminal. **Expect:** no overlapping or clipped cells; record the font.
- [ ] **Dialogs** (Unlock the Host Key Fingerprint, unsaved changes on quit, per-Source Archive Rules). **Do:** open each in a real terminal. **Expect:** Cancel is the default of the Unlock confirmation, Esc cancels, Save is absent from the unsaved-changes dialog while errors exist, and the Archive Rules dialog edits and closes.
- [ ] **SIGHUP and SIGTERM.** **Do:** change a field without saving, then `kill -HUP <pid>` (and again with `-TERM`). **Expect:** exit code 130, the terminal is restored, and nothing was written to the User Overrides.
- [ ] **The published binary starts the Settings TUI** on linux-x64, linux-arm64 and osx-arm64. **Do:** from the unpacked package run `--configure`. **Expect:** the TUI opens from the untrimmed single file with no missing native or driver error.
- [ ] **Check connection (F5) against a real SFTP server.** **Do:** in `--configure` with a saved, valid Destination and the password set (environment or Secret Store), press F5; then repeat with a wrong password and with a wrong Host Key Fingerprint. **Expect:** a dialog says connected; then an authentication failure; then a host key mismatch. No secret value appears in any of them, and nothing is uploaded.

## 15. Whole-app TUI (`--tui`)

Targets: linux-x64, linux-arm64, osx-arm64 unless stated. Modal dialogs can be driven headlessly (see section 14). Covers the shell and the Upload, History, Settings and Help pages.

- [ ] **F9-F12 on real terminals.** **Do:** press F9-F12 in gnome-terminal (F10 menu, F11 fullscreen), macOS Terminal and iTerm without the Fn key, and Guake/Yakuake (F12). **Expect:** the pages switch; where the terminal swallows a key, note it. **Unverified.**
- [ ] **Windows console under the `WinExe` build** (win-x64). **Never verified.** **Do:** as section 14 with `--tui`.
- [ ] **Redirected streams and `TERM=dumb`.** **Do:** `MiresSftpUploader --tui </dev/null` and `TERM=dumb MiresSftpUploader --tui`. **Expect:** exit code 2, one line on stderr naming `--tui`, nothing on stdout.
- [ ] **Resize.** **Do:** shrink the terminal below 80x24, press keys, enlarge it. **Expect:** an overlay, keys do nothing, the page and its focus return.
- [ ] **Mouse** in PuTTY and Windows Terminal. **Do:** click the tab labels. **Expect:** the page switches; the keyboard works without the mouse.
- [ ] **Unsaved quit.** **Do:** change a field, press Ctrl+Q (and Ctrl+C). **Expect:** Save, Discard or Cancel; Discard writes nothing.
- [ ] **SIGHUP and SIGTERM.** **Do:** change a field without saving, `kill -HUP <pid>`, then `-TERM`. **Expect:** exit code 130, the terminal is restored, nothing was written.
- [ ] **Glyphs and colours.** **Do:** check `● ✗ !` per terminal, on 16-colour and 256-colour terminals. **Expect:** no overlap; colour never carries meaning alone.
- [ ] **100,000-file Run over a throttled SSH session.** **Do:** start a Run on a Source with 100,000 files over a throttled SSH link. **Expect:** a steady draw rate, no flicker, Cancel (X) takes effect within about 10 s.
- [ ] **Resize during a Run.** **Do:** resize the terminal while a Run is active, also below 80x24 and back. **Expect:** the page redraws, the Run is unaffected, keys do nothing only while the too-small overlay shows.
- [ ] **Real SIGHUP and SIGTERM mid-Run.** **Do:** start a Run, `kill -HUP <pid>` (then again with `-TERM`). **Expect:** the Run is cancelled, exit code 130, the terminal is restored, History shows the Run as cancelled.
- [ ] **Glyphs** `▶ ✓ ✗ ⊘ … ●` per terminal. **Expect:** each renders one cell wide with no overlap; the text beside it carries the meaning.
- [ ] **Two operators.** **Do:** one operator starts a Run, a second opens History (F10) on the same Data Directory. **Expect:** the second sees the Run live and, after the first finishes, its outcome; Request cancel works for the other user's Run.
- [ ] **The published binary starts the TUI** on linux-x64, linux-arm64 and osx-arm64. **Do:** from the unpacked package run `--tui`. **Expect:** the shell opens from the untrimmed single-file executable.

---

## Sign-off

| Target | Machine and OS version | Package | Date | By | Result |
|---|---|---|---|---|---|
| win-x64 | | | | | |
| linux-x64 | | | | | |
| linux-arm64 | | | | | |
| osx-arm64 | | | | | |
