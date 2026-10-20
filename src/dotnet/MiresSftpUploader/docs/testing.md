# Running the tests

All commands run from the repository root. CI is out of scope; these are run by hand.

| Command | What runs |
|---|---|
| `dotnet test MiqaResearch.slnx --filter "TestCategory!=Container&TestCategory!=Scale"` | The everyday run: unit tests and the Avalonia headless UI tests. No Docker, a few seconds. |
| `dotnet test MiqaResearch.slnx --filter "TestCategory=Container"` | The container integration tests (below). |
| `dotnet test MiqaResearch.slnx --filter "TestCategory=Scale"` | The Scale tests (below). |

Per-OS checks that no test can do are in [release-checklist.md](release-checklist.md).

## Container category

These tests run the same contract tests against the real adapters: an OpenSSH SFTP server (`atmoz/sftp`, pinned by digest) for `SshNetRemote`, and MinIO for `S3Source`. They use Testcontainers, so they need a reachable Docker-compatible engine (Docker Desktop, or podman with its Docker API socket). Without one each test ends **Inconclusive** with "Docker is not reachable", not failed.

- The first run pulls the images; later runs reuse them.
- With podman, start its Docker-compatible API socket and point `DOCKER_HOST` at it.
- `MIRES_TEST_4GIB=1` also enables the 4 GiB hash proof (`SftpHashProofTests`); without it that test ends Inconclusive.
- They cover the `.part`-rename hash proof (the server's SHA-256 equals the Manifest), faults and a write-only account, and S3 listing and change detection.

## Scale category

Opt-in volume tests in `tests/dotnet/MiresSftpUploader.Test.Unit/ScaleTests.cs`. They are not part of the everyday run and take a few seconds. They run one at a time, because they measure the process heap and the number of Upload State commits.

| Test | Asserts |
|---|---|
| 20,000 tiny files, batched writes | Every file Succeeds, the Manifest lists all 20,000 and is `complete`, and the Upload State used fewer than one commit per 10 files. |
| 20,000 tiny files, bounded memory | Live heap growth during the Run stays under 100 MB (measured about 30 MB). |
| A million-node Manifest | `ManifestWriter` writes 366 MB of JSON for 1,000,000 nodes while the live heap grows by under 20 MB (measured under 1 MB), so the Manifest is streamed, not built in memory. |
| Upload State load cost | `LoadSource` holds under 800 bytes per file (measured about 670). |

The 64 MiB hash proof is in the Container category; the 4 GiB one is item 13 of the release checklist.

## What the Scale tests found

Memory use is linear in the number of files of a Run, not constant. Measured numbers:

- **The Manifest is streamed.** `ManifestWriter` and `UploadStateStore.EnumerateDelivered` read rows one at a time and write through a `Utf8JsonWriter` flushed every 1,000 nodes, so the Manifest of any size costs a constant amount of memory. The Manifest is written to a temporary file and uploaded from there.
- **State writes are batched.** The writer thread commits up to 200 queued writes in one transaction, so 20,000 files give fewer than 2,000 commits (the test limit), not 20,000.
- **A Run holds one entry per file.** The Run's per-file outcomes (for the Report and the progress events), the plan (`FileWork` per file) and the work queue are all in memory: about 1.5 KB per file, roughly 30 MB for 20,000 files and about 1.5 GB for 1,000,000 files. The Source's listing is not streamed into the plan, so the whole listing is in memory before the first upload starts.
- **`LoadSource` loads the Source's whole Upload State into a dictionary** (path to status, size, mtime and hash) to decide what is unchanged: about 670 bytes per file, so about 670 MB at 1,000,000 files, in addition to the point above.

Together a Source of 1,000,000 files needs about 2 GB of memory for one Run. Up to 100,000 files per Source (about 200 MB) is comfortable. Nothing breaks below that, and Archives reduce the count because their members are listed once. Fixing it for good means streaming the listing against a sorted read of the Upload State, which is a larger change than this ticket; it is recorded here instead.
