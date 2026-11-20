# Running the tests

All commands run from the repository root. CI is out of scope; these are run by hand.

| Command | What runs |
|---|---|
| `dotnet test MiqaResearch.slnx --filter "TestCategory!=Container&TestCategory!=Scale"` | The everyday run: unit tests and the Avalonia headless UI tests. No Docker, a few seconds. |
| `dotnet test MiqaResearch.slnx --filter "TestCategory=Container"` | The container integration tests (below). |
| `dotnet test MiqaResearch.slnx --filter "TestCategory=Scale"` | The Scale tests (below). |

The Engine tests give an upload a duration with a fake clock: `FakeRemote.OnUpload` runs at the start of every upload and advances the `FakeTimeProvider` (see `UploadTimeTests`). The Upload State schema migration is tested by turning a database back to version 3 and opening it again.

Per-OS checks that no test can do are in [release-checklist.md](release-checklist.md).

## Container category

These tests run the same contract tests against the real adapters: an OpenSSH SFTP server (`atmoz/sftp`, pinned by digest) for `SshNetRemote`, and MinIO for `S3Source`. They use Testcontainers, so they need a reachable Docker-compatible engine (Docker Desktop, or podman with its Docker API socket). Without one each test ends **Inconclusive** with "Docker is not reachable", not failed.

- The first run pulls the images; later runs reuse them.
- With podman, start its Docker-compatible API socket and point `DOCKER_HOST` at it.
- `MIRES_TEST_4GIB=1` also enables the 4 GiB hash proof (`SftpHashProofTests`); without it that test ends Inconclusive.
- They include the upload progress contract: the reported acknowledged bytes are monotonic and the last one equals the size of the object.
- They cover the `.part`-rename hash proof (the server's SHA-256 equals the Manifest), faults and a write-only account, and S3 listing and change detection.

## Upload progress (Unit)

`UploadProgressTests` drive the Engine with a `FakeTimeProvider` and a `FakeRemote` that reports acknowledged bytes as it consumes its stream in `UploadChunkSize` chunks. `FakeRemote.OnUploadChunk` is the throttle: a test awaits in it after each chunk, advances the clock by 250 ms (one meter tick) and reads the `UploadProgress` snapshots. They cover bytes, total and speeds, the 2-sample rule, the window, out-of-order reports, retries, the final clearing snapshot, Archives and Dry Runs.

## Upload progress view models (Unit, Ui)

`UploadPageViewModelTests` feed `UploadProgress` snapshots and Succeeded events (with bytes sent and Upload Time) to `UploadPageViewModel` through `FakeRunEngine.Script`, and through a small engine that hands out its progress sink to report events while the Run goes. They cover the active-uploads list and the total, no bar before an Upload Speed exists, the hidden card, Archives without a row, the `12.4 MiB in 3 s` text, stale snapshots, and that a snapshot over a 20,000-row list raises nothing on the list or its rows. `TransferFormat` (sizes, speeds, durations) is tested there too. `MainWindowSmokeTests` checks that the Avalonia "Uploading now" card shows and hides. There is no screenshot test: the headless platform does not render frames.

## Upload progress in the TUI (Unit)

`TuiStatusCellTests` build rows through the real `UploadPageViewModel` (held `FakeRunEngine` with snapshots and Succeeded events) and assert the Status cell text: bar, percent and speed, 0% and 100%, no bar before an Upload Speed exists, the bar dropped first at narrow widths (22, 21, 5 characters), `Succeeded 12.4 MiB in 3 s`, and unchanged text for other rows. `UploadTuiPageTests` (real `Application.Run` loop) show the cell and `↑ 9.2 MiB/s total` on screen, their disappearance after the clearing snapshot, the bar dropped at 80 columns with a long path, and that one snapshot of 8 files causes at most 2 redraws.

## Headless progress (Unit)

`HeadlessProgressTests` feed `RunEvent`s to `HeadlessProgress` with a `FakeTimeProvider` (the 10 s log line needs no waiting) and a `StatusLineWriter` over a `StringWriter`; a small terminal emulation (carriage return, overwrite) turns what was written into the screen, so a test can assert that a status line is never left in front of a log line, that it is cut to the width and that nothing of a longer line remains. `StatusLineWriter.IsInteractive` is a pure function of redirection, `TERM` and `CI`. `HeadlessRunnerTests` check that stdout is exactly the summary line with a status writer, `AppLoggingTests` that the progress logger name goes to the file target only (a first Final rule). The process-level path (real `Console.IsErrorRedirected`, `Console.SetError`, Windows console) is covered only by the release checklist.

## Scale category

Opt-in volume tests in `tests/dotnet/MiresSftpUploader.Test.Unit/ScaleTests.cs`. They are not part of the everyday run and take a few seconds. They drive the Engine and run one at a time, because they measure the process heap and the number of Upload State commits (the commit count is the one internal hook, `UploadStateStore.CommitCount`: no public behaviour tells how many transactions were used).

| Test | Asserts |
|---|---|
| 20,000 tiny files, batched writes | Every file Succeeds, the Manifest lists all 20,000 and is `complete`, and the Upload State used fewer than one commit per 10 files. |
| 20,000 tiny files, bounded memory | Live heap growth during the Run stays under 100 MB (measured about 30 MB). |
| A large Manifest | A Run over 100,000 files writes and uploads a 36 MB Manifest while the live heap grows by under 20 MB (measured about 7 MB), so the Manifest is streamed, not built in memory. The test's remote swallows the Manifest and watches the heap from the Manifest connection until the Manifest is in place. |
| Incremental Run cost | A second Run over 100,000 unchanged files skips them all and holds under 3,000 bytes per file (measured about 1,400): the Upload State dictionary, the plan and the outcomes. |

The 64 MiB hash proof is in the Container category; the 4 GiB one is item 13 of the release checklist.

## What the Scale tests found

Memory use is linear in the number of files of a Run, not constant. Measured numbers:

- **The Manifest is streamed.** `ManifestWriter` and `UploadStateStore.EnumerateDelivered` read rows one at a time and write through a `Utf8JsonWriter` flushed every 1,000 nodes, so the Manifest of any size costs a constant amount of memory. The Manifest is written to a temporary file and uploaded from there.
- **State writes are batched.** The writer thread commits up to 200 queued writes in one transaction, so 20,000 files give fewer than 2,000 commits (the test limit), not 20,000.
- **A Run holds one entry per file.** The Run's per-file outcomes (for the Report and the progress events), the plan (`FileWork` per file) and the work queue are all in memory: about 1.5 KB per file, roughly 30 MB for 20,000 files and about 1.5 GB for 1,000,000 files. The Source's listing is not streamed into the plan, so the whole listing is in memory before the first upload starts.
- **`LoadSource` loads the Source's whole Upload State into a dictionary** (path to status, size, mtime and hash) to decide what is unchanged: about 670 bytes per file, so about 670 MB at 1,000,000 files, in addition to the point above.

Together a Source of 1,000,000 files needs about 2 GB of memory for one Run. Up to 100,000 files per Source (about 200 MB) is comfortable. Nothing breaks below that, and Archives reduce the count because their members are listed once. Fixing it for good means streaming the listing against a sorted read of the Upload State, which is a larger change than this ticket; it is recorded here instead.
