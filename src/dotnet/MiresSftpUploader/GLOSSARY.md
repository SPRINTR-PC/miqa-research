# MiresSftpUploader

A cross-platform tool (desktop UI and headless mode) that scans Sources, hashes their files, optionally packs some of them into Archives, and uploads the result to a MIRES-owned SFTP server together with a Manifest that lets consumers validate what arrived.

## Language

### What is uploaded

**Source**:
A named place files are read from: either a local directory or a prefix in an S3-compatible bucket. A Run covers one or more Sources.
_Avoid_: Location, input folder, bucket (as a generic term)

**Remote Path**:
The server directory a Source is uploaded into, including the Source's own directory. Defaults to the configured remote root plus the Source name; can be set per Source.
_Avoid_: Destination, target folder

**Ignore Rule**:
An entry that excludes files from a Run: either an exact relative path or a regular expression matched against the relative path. The Upload State and a small set of built-in junk patterns (such as `.DS_Store`, which can be switched off) are always ignored.
_Avoid_: Exclude, filter, blacklist

**Archive Rule**:
A regular expression that selects files to be packed into an Archive instead of being uploaded individually.
_Avoid_: Zip rule, compression rule

**Archive**:
A zip file built from the files an Archive Rule selected, uploaded in place of those files. Built deterministically so the same members always give the same bytes.
_Avoid_: Zip, bundle, package

**Staging Area**:
The local folder where an Archive is built before upload, one subfolder per Run, removed when the Run ends.
_Avoid_: Temp folder, cache

### Running

**Run**:
One execution of scan, hash, plan, upload and Manifest upload over the selected Sources, started from the UI or as a Headless Run. Ends with a result per file and an exit code.
_Avoid_: Job, batch, session

**Headless Run**:
A Run started from the command line without opening a window, intended to be launched by the operating system's scheduler.
_Avoid_: Scheduled task, service mode, daemon

**Dry Run**:
A Run that performs discovery, Ignore Rules and Archive planning, reports the plan, and uploads, archives and records nothing.
_Avoid_: Preview, simulation

**File Outcome**:
The status of one file in a Run: Pending, Hashing, Uploading, Verifying, Succeeded, Failed, Skipped or Ignored. A Skipped file carries a reason, such as unchanged or Too Recent.
_Avoid_: Result, state (of a file)

**Too Recent**:
The reason a file is Skipped because it was modified more recently than the configured minimum age, or after the configured cutoff. It is picked up by a later Run, and an Archive with any Too Recent member is deferred as a whole.
_Avoid_: Locked file, in-use file

**Post-upload Move**:
An opt-in step that moves a Source's files out of the Source once their final outcome is known: to one location after success and another after failure, so a recurring Run finds only new data. Never overwrites, and never removes a file before its copy is checked.
_Avoid_: Cleanup, archive-after-upload, delete after upload

**Moved Away**:
The Upload State's record that a file left its Source through a Post-upload Move. It is not Missing and stays in the Manifest.
_Avoid_: Deleted

**Verification**:
An optional check, at one of the levels Size, Hash or ReadBack, that a file on the server matches what was uploaded. Done on the temporary upload before the rename, and for unchanged files that would otherwise be skipped.
_Avoid_: Validation (that is what consumers do with the Manifest)

**Destination**:
The SFTP server (host and port) together with a Remote Path. Upload State is keyed by Destination, so pointing a Source at a different server counts as new.
_Avoid_: Target, endpoint

**Upload State**:
The durable, machine-wide record shared by all users of a machine: the latest known state of every uploaded file and Archive, plus the history of every Run. Used to skip unchanged files and retry failed ones; losing it costs a full re-upload, not correctness.
_Avoid_: Cache, checkpoint

**Data Directory**:
The machine-wide folder holding the Upload State, Staging Areas, logs, Reports and the lock. Created once by an administrator, who grants access to a shared group of accounts; everything inside is readable and writable by that group only.
_Avoid_: Working folder, app data

**Run History**:
The part of the Upload State that records each Run (who started it, mode, outcome, exit code) and the outcome of every file in it. Pruned after a retention period.
_Avoid_: Log, audit log

**Abandoned Run**:
A Run whose process stopped without finishing, recognised by a stale heartbeat. Its in-flight files are cleaned up and retried.
_Avoid_: Crashed run, zombie run

**Report**:
An exported summary of one Run (summary plus per-file outcomes) in JSON or CSV, written on request or at the end of a Headless Run. It is not uploaded.
_Avoid_: Export, log file

### Validation

**Manifest**:
The uploaded hash file for a Source: a tree in which each uploaded item has its SHA-256 and each Archive additionally lists its original member files with their own hashes. Always uploaded at the end of a Run and always truthful: it states whether the Run was complete and lists the files that failed.
_Avoid_: Hash file, checksum file, index

**Flat Manifest**:
The optional companion to the Manifest in `sha256sum -c` format, listing only the objects physically present on the server (plain files and Archives).
_Avoid_: Checksum list

**In-progress Marker**:
A small file on the server that exists while a Run is uploading a Source, so consumers know the Manifest may be stale. Removed at the end of the Run; skipped when the account cannot delete.
_Avoid_: Lock file, flag file

**Write-only Access**:
A Destination where the account can upload but not read, list, delete or overwrite. The Run then trusts the Upload State instead of the server and skips every check that reads from it.
_Avoid_: Blind mode, restricted mode

### Configuration

**Machine Config**:
The `appsettings.json` next to the executable: the settings (Sources, Destination, rules) that all users of a machine share, managed by an administrator. When its folder is not writable, the UI shows them as Locked Settings.
_Avoid_: Global config, shared settings

**User Overrides**:
Settings changed in the UI and saved per user, layered above Machine Config and below environment variables. Secrets are never part of them.
_Avoid_: User config, preferences

**Locked Setting**:
A setting currently supplied by an environment variable, or by Machine Config the user cannot write, shown in the UI but not editable.
_Avoid_: Read-only setting

**Secret**:
A setting that grants access (password, key passphrase, S3 secret key). Supplied only by environment variables, never displayed, never saved.
_Avoid_: Credential setting

**Host Key Fingerprint**:
The pinned identity of the SFTP server. A connection to a server presenting a different one is refused.
_Avoid_: Server key, known host
