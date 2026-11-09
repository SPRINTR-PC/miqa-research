(heading-etl)=
# ETL Pipelines

The ETL (extract, transform, load) subsystem turns files dropped into an S3-compatible bucket
into rows in the research database. For each project, a Data Manager or Admin connects a source
bucket to an **ETL Script** through a **Pipeline Binding**. From then on the platform polls the
bucket, runs the Script over each new file (or folder) in an isolated **Sandbox Runner**, checks
the rows the Script returns against the chosen **ETL Datatype**, loads them in a single
all-or-nothing transaction, and moves the source files to a **Raw Bucket**, or deletes them
under the Binding's "delete" **Raw Retention**.

The end-to-end flow:

```{mermaid}
flowchart LR
    SRC[(Source bucket)] -->|poll + diff| ORCH[Orchestrator]
    ORCH -->|queue| JOB[ETL Job]
    JOB -->|SandboxRunSpec| SB[Sandbox Runner]
    SB -->|result.jsonl| LOAD[Datatype loader]
    LOAD -->|one transaction| DB[(Database)]
    LOAD -->|on success| MOVE[Raw bucket move]
    MOVE --> RAW[(Raw bucket)]
```

The code is split across these packages:

| Package | Responsibility |
|---|---|
| `MiqaResearch/etl_datatypes/` | The ETL Datatype registry and the JSONL loader. |
| `MiqaResearch/data/models/etl_*.py` | Scripts, Script Versions, Pipeline Bindings, Jobs and the orchestrator's bookkeeping tables. |
| `MiqaResearch/tasks/etl_orchestrator/` | Celery tasks for polling, running Jobs, retries, stuck-job recovery, log pruning and the raw-bucket move. |
| `MiqaResearch/etl_sandbox/` | The `SandboxBackend` interface, its Compose and Kubernetes implementations, the image allowlist and resource limits. |
| `MiqaResearch/etl_shim/` | The script contract and the Python and R shims baked into the sandbox images. |
| `MiqaResearch/actions/etl/`, `readers/etl_*.py` | Management writes (audited) and reads for the ETL Pipelines project tab, and the permission policy. |

(heading-etl-datatypes)=
## ETL Datatype registry

An **ETL Datatype** is a kind of incoming data that is registered in code. Each one has a name,
a row schema (a Django Ninja / Pydantic `Schema`) and a loader function that persists validated
rows. Users choose among the registered Datatypes but can never define one. Scripts only return
rows, and they never write to the database themselves.

A Datatype is registered with a decorator. `etl_datatypes/__init__.py` imports each module so
that registration happens at import time:

```python
@register_datatype("measurement", MeasurementRowSchema)
def load_measurement_rows(*, project, etl_job, rows) -> LoadResult:
    ...
```

Registering the same name twice raises `DatatypeAlreadyRegistered`.

Three Datatypes are shipped. The first two target OMOP CDM v5.4 tables:

| Datatype | Target model | Natural key (upsert) |
|---|---|---|
| `measurement` | `Measurement` | person, `measurement_concept_id`, `measurement_date`, `measurement_source_value` |
| `visit_occurrence` | `VisitOccurrence` | person, `visit_concept_id`, `visit_start_date`, `visit_source_value` |
| `participant_consent` | `ParticipantConsent` | participant, consent type, `consent_signed_date` |

Rows are upserted on these natural keys, so re-running the same batch updates rows in place
instead of creating duplicates. Every loaded row records the `EtlJob` that wrote it
(`etl_job` foreign key).

### Participant consent

`participant_consent` differs from the other Datatypes in three ways
([ADR 0031](#heading-etl-adr-0031)):

- **Unknown participants are created.** A row must carry `person_source_value`. If no Study
  Participant in the project matches it, one is created in the Binding's project, with the
  row's `name` and a generated `alias1`. This happens inside the Job's single transaction, so
  a bad row rolls the new participants back too.
- **Consent types are per project.** `consent_type` is a label that is looked up, and created
  if missing, within the Binding's project. `ParticipantConsentType` is unique on
  `(research_project, label)` (migration 0023).
- **Clinics** are looked up by `clinic_code` and created if missing.

The other row fields are `consent_signed_date`, `status`, `consent_revoked_date`,
`participant_information_version` and `source`. A re-imported row updates the existing consent
in place, so a revocation in a later export is recorded.

(heading-etl-adr-0031)=
:::{note}
**ADR 0031.** Consent is how a person enters a study, so for this Datatype an unknown
personnummer is expected rather than an error. Participants created earlier by the legacy
SamtyckenUmu task have no project and are not matched until
`adopt_legacy_consent_participants` adopts them (see
[SamtyckenUmu consent task](#heading-etl-samtycken-task)).
:::

### Participant references and concepts

Every row carries exactly one Participant Reference, either `person_source_value` or `alias1`.
It is resolved only against **this project's** Study Participants. A `person_source_value` is
matched in the shared format (trimmed, dashes removed), so `19121212-1212` and `191212121212`
are the same person, as in consent loads and DICOM ingestion.

- A reference that matches no participant raises `UnresolvableParticipantReference`.
- A reference that matches more than one raises `AmbiguousParticipantReference`. The loader
  never silently picks one: `person_source_value` is not guaranteed to be unique, while
  `alias1` is.

Concept fields hold `Concept.concept_id` UUIDs. Mapping a source system's own codes to Concepts
is the Script's job. Any UUID that does not match a Concept fails the whole batch before
anything is written.

### Loading

`load_jsonl(datatype_name=..., project=..., etl_job=..., jsonl_text=...)` validates every line
against the Datatype's schema. It then passes the rows to the loader inside one
`transaction.atomic()` block. A single malformed or unresolvable row raises `EtlRowError` and
rolls back the entire batch. There are never partial writes. `load_jsonl` also refuses an
`EtlJob` whose Binding belongs to a different project (`EtlJobProjectMismatch`).

(heading-etl-data-model)=
## Data model

```{mermaid}
erDiagram
    ResearchProject ||--o{ EtlScript : "owns (custom)"
    EtlScript ||--o{ EtlScriptVersion : versions
    ResearchProject ||--o{ PipelineBinding : has
    EtlScriptVersion ||--o{ PipelineBinding : "pinned by"
    PipelineBinding ||--o{ EtlJob : queues
    EtlScriptVersion ||--o{ EtlJob : "ran"
    EtlJob ||--o{ EtlJobInput : inputs
    PipelineBinding ||--o{ EtlProcessedFile : "seen files"
    PipelineBinding ||--o{ EtlPendingGroup : "folders awaiting quiescence"
    ResearchProject ||--o{ EtlLocationGrant : "bucket grants"
    EtlStorage ||--o{ EtlLocationGrant : "granted on"
    EtlStorage ||--o{ PipelineBinding : "reads via"
    ResearchProject ||--o{ EtlSourceLocation : "named sources"
    EtlSourceLocation ||--o{ PipelineBinding : "source of"
    ResearchProject ||--o| EtlProjectSettings : overrides
```

`EtlScript` (ETL Script)
: A named program with an `origin` of `native` or `custom`.
  - **Native** scripts are global (`project` is null) and read-only. See
    [Native Scripts](#heading-etl-native-scripts).
  - **Custom** scripts belong to one Research Project.
  - `datatype_name` names the ETL Datatype that the Script's rows conform to. It is chosen,
    from the registry, when the Script is created, and it can't be changed afterwards. A Script
    left without one (created before #223) can have it set once through **Edit**.
  - Scripts are archive-only: `archived_at` is set instead of deleting the row. Both
    `delete()` and a bulk queryset delete raise `ValidationError`.

`EtlScriptVersion` (Script Version)
: An immutable snapshot of a Script's source.
  - Holds `version` (1, 2, …), `source` (a file), `sha256` of the source bytes, and
    `image_key`, which is the sandbox image the source is written for (see
    [Sandbox images](#heading-etl-sandbox-images)).
  - `config_schema` is an optional JSON Schema (Draft 2020-12) that a Binding's config must
    satisfy (see [Config schemas](#heading-etl-config-schema)). Null keeps config free-form.
  - Once created, a version can never be updated. `save()` on an existing row and a bulk
    queryset `update()` both raise.
  - Source files are stored locally, or in S3 when `MIRES_ETL_SCRIPT_STORAGE_BACKEND=s3`.
  - The source size is capped per project (see
    [Configuration reference](#heading-etl-configuration)).

`PipelineBinding` (Pipeline Binding)
: Connects a project's source location to a Script Version.
  - The source location is `source_bucket` plus `source_prefix`, which must be unique across
    all Bindings. The Binding also holds `raw_bucket` and `raw_prefix`.
  - `script_version` is pinned. Editing the Script later creates a new version and never
    changes an existing Binding. A manager can re-pin the Binding through **Edit**.
  - Everything except the source location can be edited on the tab
    (`actions/etl/bindings.update_pipeline_binding`), with the same grant, usable-version and
    lower-only rules as creation. An edit never affects a Job that is already queued: the runner
    uses the Job's own `script_version` and `config_snapshot`.
  - Changing `grouping_mode` re-derives the pending folder groups
    (`polling.rehome_backlog_after_grouping_change`). A switch to folder starts fresh quiescence
    windows for files that were seen but not yet queued. A switch to per-file drops the groups.
  - `grouping_mode` is `file` or `folder`, with a `quiescence_seconds` window for folders.
  - `config` is a JSON object passed to the Script as `ctx.config`. When the pinned Version has
    a `config_schema`, config is validated against it on create, edit and re-pin.
  - Optional overrides for sandbox timeout, memory and CPU can only **lower** the platform
    defaults.

`EtlJob` (ETL Job)
: One run of one Script Version over one group of inputs.
  - Records the `script_version` that actually ran, `status` (`pending`, `running`,
    `succeeded` or `failed`), `attempt`, `retry_of` (auto-retries only), `config_snapshot`,
    `log` (capped at 64 KB, keeping the tail), `started_at` and `finished_at`.
  - A partial unique constraint (`mires_etl_job_one_active_per_binding`) allows **at most
    one pending or running Job per Binding**.

`EtlJobInput`
: One input file of a Job. Holds `bucket`, `key`, and the `sha256` and `size_bytes` stamped
  when the runner fetches the file. It also tracks the raw-bucket move: `raw_bucket_key`,
  `source_status`, `cleanup_attempts` and `cleanup_next_attempt_at`.

`EtlProcessedFile`
: The orchestrator's ledger of every object it has seen under a Binding, unique per
  (binding, bucket, key). Diffing a bucket listing against this table is how the poller finds
  new files.

`EtlPendingGroup`
: Used only by folder-grouped Bindings. It has one row per child folder that holds files not
  yet assigned to a Job. `last_seen_at` is bumped whenever a new file appears in that folder.

`EtlLocationGrant`
: Grants a project a `bucket` plus optional `prefix`; an empty prefix grants the whole bucket.
  This is how per-project bucket isolation is enforced (see
  [Permissions and audit](#heading-etl-permissions)).

`EtlSourceLocation` (Source Location)
: A named `bucket` plus `prefix` inside one of the project's grants (#268), unique per project
  by name and by bucket/prefix. The Binding wizard offers these instead of a typed bucket. A
  Binding copies the location's bucket/prefix into `source_bucket`/`source_prefix` (what the
  poller reads) and keeps `source_location` (`PROTECT`, null for older Bindings). Bucket and
  prefix never change after creation; only `name` does.

`EtlProjectSettings`
: Per-project overrides for log retention and the maximum Script source size. A null value
  falls back to the global setting.

(heading-etl-orchestrator)=
## Orchestrator

The orchestrator is a set of Celery tasks in `tasks/etl_orchestrator/tasks.py`, split over two
queues: `QUEUE_ETL_POLL` for polling and housekeeping, and `QUEUE_ETL_RUN` for sandbox runs.
The `app.conf.beat_schedule` in `MiqaResearch/celery.py` seeds these beat entries:

| Task | Schedule | Purpose |
|---|---|---|
| `fan_out_etl_polls` | every `MIRES_ETL_POLL_INTERVAL_SECONDS` | Enqueues one `poll_pipeline_binding` per Binding. |
| `recover_stuck_etl_jobs` | every 60 s | Stuck-job recovery (below). |
| `retry_etl_source_cleanup` | every 60 s | Retries raw-bucket moves whose backoff is due. |
| `prune_etl_job_logs` | daily 02:00 | Clears Job logs past their retention window. |
| `sweep_orphaned_sandboxes` | every 300 s | Removes sandboxes left behind by crashed workers (below). |

### Polling

Each poll lists the Binding's whole source bucket/prefix. It then diffs the listing against
`EtlProcessedFile`, so no bucket event notifications are needed. Zero-byte "directory marker"
objects are skipped. A file stays a candidate until its key appears in an `EtlJobInput` of that
Binding. Once a file is assigned to a Job, what happens to it depends on that Job, and later
polls ignore it.

- **Per-file** (`grouping_mode = file`): each poll queues a Job for the **oldest** unassigned
  file.
- **Folder** (`grouping_mode = folder`): the *group key* of a file is the name of the first
  folder under `source_prefix`. Files directly under the prefix get an empty group key.
  - A new file bumps its group's `EtlPendingGroup.last_seen_at`.
  - Once a group has seen no new file for `quiescence_seconds`, all its unassigned files are
    queued as **one** Job and the pending-group row is deleted.
  - A later file dropped into the same folder starts a fresh quiescence window.

Because only one Job per Binding may be active, queueing onto a busy Binding hits the partial
unique constraint. The poller treats that as "nothing queued this poll", not as an error: the
file or folder is still a candidate and is picked up by a later poll. Each Binding is polled in
its own task, so a bucket that cannot be listed (`EtlBucketSourceError`) affects only that
Binding.

### Running a Job

`run_etl_job` (`runner.run_job`):

1. Ignores the call unless the Job is `pending`, so duplicate dispatches are safe. It then marks
   the Job `running`.
2. Reads every input from the source bucket and records its real SHA-256 and size on the
   `EtlJobInput`.
3. Builds a `SandboxRunSpec` from:
   - the Job id;
   - the Script Version's `image_key` and source;
   - the manifest `{"datatype": <script.datatype_name>, "config": <job.config_snapshot>}`;
   - the Binding's resolved limits;
   - the input bytes, keyed by path relative to `source_prefix`.
4. Calls `get_sandbox_backend().run(spec)`, which blocks this Celery task for the whole run
   ([ADR 0025](#heading-etl-adr-0025)).
5. On exit code 0, removes the result's header line and passes the rows to `load_jsonl`. If the
   load succeeds, the Job becomes `succeeded` and `move_etl_job_inputs_to_raw_bucket` is
   enqueued. If the loader rejects the batch, the Job is `failed` and the loader's error is
   appended to the log.
6. Any other exit code fails the Job.

### Failure classes and retries

| Class | Examples | Outcome |
|---|---|---|
| Script | Exit 1 (script error), 2 (contract violation), 3 (timeout or killed); loader rejected the rows | `failed`; needs a Manual Retry. |
| Config | `UnknownSandboxImage`, `SandboxInputTooLarge` raised by `run()` before any container starts | `failed` permanently; retrying cannot help. |
| Infra | Any other exception from `run()` (backend unreachable); a stuck Job | `failed`, and an automatic retry is queued. |

An infra-class auto-retry is a new `EtlJob` with `attempt + 1`, `retry_of` set, and the same
Script Version, config snapshot and inputs. No further retries are queued once `attempt`
reaches `MIRES_ETL_JOB_MAX_AUTO_RETRIES`.

### Stuck-job recovery

There is no heartbeat. A Job counts as **stuck** when it is still `running` after its Binding's
resolved sandbox timeout plus `MIRES_ETL_JOB_STUCK_GRACE_SECONDS`. `recover_stuck_etl_jobs`
fails such Jobs and sends them through the infra-class retry path above. The Jobs panel uses
the same `is_stuck()` rule to show "Stuck" before the sweep has run. "Stuck" is computed for
display only and is never stored as a status.

### Orphaned sandbox cleanup

Stuck-job recovery fails the Job, but the dead worker's sandbox (a container, or a Kubernetes
Job with its pods and PVC) is still there. `sweep_orphaned_sandboxes`
(`tasks/etl_orchestrator/sandbox_sweep.py`) calls `SandboxBackend.sweep()`, which removes every
labelled sandbox whose run id doesn't belong to a `pending` or `running` Job.

- A stuck Job's sandbox is kept until stuck recovery has failed the Job, and removed on the next
  pass after that.
- The backend lists its sandboxes **before** asking which runs are live. A run that starts
  between the two steps is therefore never mistaken for an orphan.
- Only resources with a `mires.etl.run_id` label are swept. The Kubernetes egress probe pod has
  no run id and is left to `_ensure_healthy`.

### Manual Retry

An Admin or Data Manager can retry a `failed` Job from the Jobs panel
(`actions/etl/jobs.retry_failed_job`). The retry is a fresh Job:

- `attempt` is 1 and `retry_of` is not set.
- It reuses the failed Job's inputs and config snapshot.
- It runs the **failed Job's own Script Version**, not the Binding's current one.

The retry is refused while the Binding has an active Job. Each Manual Retry is audited.

### Log retention

The runner caps each Job's `log` at 64 KB and keeps the tail. `prune_etl_job_logs` clears a
log once the Job's `finished_at` (or `created_at`) is older than the project's retention window:
`EtlProjectSettings.log_retention_days`, or `MIRES_ETL_LOG_RETENTION_DAYS` if that is not set.

(heading-etl-adr-0025)=
:::{note}
**ADR 0025.** `SandboxBackend.run()` stays synchronous and blocking inside its own
`QUEUE_ETL_RUN` task. The number of concurrent sandbox runs is therefore set by that queue's
worker concurrency. A run whose worker dies is recovered by the stuck-job sweep, not by a
heartbeat. Splitting the call into an asynchronous start and poll would change the
`SandboxBackend` interface itself.
:::

(heading-etl-sandbox)=
## Sandbox Runner

Custom Scripts run in a **Sandbox Runner**: a throwaway container that has no network access,
runs as a non-root user (65534:65534) with every Linux capability dropped, has limited
resources, and holds no credentials. Its only input is the staged sandbox directory.

### The `SandboxBackend` interface

`etl_sandbox/backend.py` defines the interface that the orchestrator is written against:

```python
class SandboxBackend(abc.ABC):
    def run(self, spec: SandboxRunSpec) -> SandboxRunResult: ...
    def cancel(self, run_id: str) -> None: ...
    def sweep(self, *, live_run_ids: Callable[[], set[str]]) -> None: ...
```

- **`run()`** returns `SandboxRunResult(exit_code, result_jsonl, log, killed)`. A Script's own
  failure is reported through `exit_code`. `run()` raises only for runner-level problems, where
  no container was ever started.
- **`cancel()`** removes a single run.
- **`sweep()`** removes sandboxes left behind by a crashed worker. It finds them by the
  `mires.etl.sandbox=1` label and keeps any whose `mires.etl.run_id` is in `live_run_ids()`. See
  [Orphaned sandbox cleanup](#heading-etl-orchestrator).

`MIRES_SANDBOX_BACKEND` selects the implementation (`compose` or `kubernetes`).

Both backends share `etl_sandbox/_staging.py`, so they enforce the same gates and use the same
layout:

1. `resolve_sandbox_image(image_key)` must succeed before anything else. It raises
   `UnknownSandboxImage` if the key is missing from the allowlist.
2. The script source plus all input files must fit within `max_input_bytes`, or
   `SandboxInputTooLarge` is raised.
3. The sandbox directory is packed as a tar archive and unpacked at `/sandbox` (see
   [Script contract](#heading-etl-contract)).
4. The `output/` directory is read back. Output larger than `max_output_bytes` is discarded.

### Resource limits

`resolve_limits(binding)` starts from the platform defaults. A Binding's override replaces a
default only when it is lower:

| Limit | Default | Binding override |
|---|---|---|
| Timeout | 600 s | lower only |
| Memory | 1024 MB | lower only |
| CPU | 1000 millicores | lower only |
| PIDs | 128 | none |
| Staged input | 15 GiB | none |
| Output | 1 GiB | none |

### Compose backend

`ComposeSandboxBackend` talks to a Docker API at `MIRES_SANDBOX_DOCKER_HOST`. In production this
should be a docker-socket-proxy on each worker host. A worker never mounts the raw Docker socket.

A run goes through these steps:

1. Create the container stopped, with `network_mode="none"`, a non-root user,
   `cap_drop=["ALL"]`, `no-new-privileges`, and the memory, CPU and PID limits.
2. Stage `/sandbox` with `put_archive`.
3. Start the container and wait up to the timeout.
4. Read `/sandbox/output` with `get_archive`.
5. Always remove the container.

A timeout or an OOM kill is reported as exit code 3 with `killed=True`. Input and output go
only through the archive API and never through bind mounts, because the worker and the Docker
daemon are not assumed to share a filesystem.

### Kubernetes backend

`KubernetesSandboxBackend` runs each sandbox run as one `batch/v1` Job in the dedicated
`MIRES_SANDBOX_K8S_NAMESPACE`.

Every pod in that namespace falls under a namespace-wide `default-deny-egress` NetworkPolicy.
A PersistentVolumeClaim is created for each run. Short-lived, trusted "transfer" pods (running
`MIRES_SANDBOX_K8S_STAGER_IMAGE`) write the input onto the volume and read the output back by
streaming `tar` over pod exec. The Script's pod only mounts the already-staged volume.

The Job's pod runs:

- with `runAsNonRoot`, all capabilities dropped and no privilege escalation;
- with the `RuntimeDefault` seccomp profile;
- with no service-account token;
- with `activeDeadlineSeconds` set to the timeout.

`DeadlineExceeded` and `OOMKilled` are both mapped to exit code 3.

:::{warning}
Some CNIs silently ignore NetworkPolicy. kind's default `kindnet` is one of them. Before
scheduling any run, the backend therefore launches a probe pod under the deny policy that tries
to connect to `MIRES_SANDBOX_K8S_EGRESS_PROBE_HOST:PORT`. If that connection succeeds, the
backend raises `SandboxBackendUnhealthy` and refuses to run anything. A passing result is cached
for `MIRES_SANDBOX_K8S_SELF_TEST_TTL_SECONDS`.
:::

(heading-etl-sandbox-images)=
### Sandbox images

A Script Version never names a raw image. Its `image_key` names a language, a runtime and a
release (for example `python-etl-v1` or `r-etl-v1`). The key is resolved through the
operator-managed `MIRES_SANDBOX_IMAGE_ALLOWLIST`, a JSON object that maps each key to an image
reference. In production each reference should be pinned by digest
(`registry/…@sha256:…`).

When a Script or Version is uploaded, its `image_key` is chosen from the file extension through
`MIRES_ETL_SCRIPT_IMAGE_KEYS` (default `{".py": "python-etl-v1", ".r": "r-etl-v1"}`). An
unsupported extension is rejected as a form error.

| Image | Dockerfile | Key |
|---|---|---|
| Python | `etl_sandbox.Dockerfile` (Python 3.14 slim, bookworm) | `python-etl-v1` |
| R | `etl_sandbox_r.Dockerfile`: `FROM` the Python image, plus `r-base-core` 4.2 and `r-cran-jsonlite` | `r-etl-v1` |

Both images use `python -m MiqaResearch.etl_shim /sandbox` as their entrypoint. The R image
sets `MIRES_ETL_SHIM_LANGUAGE=r`. Build them with:

```console
docker compose --profile etl-sandbox-build build mires_etl_sandbox_python mires_etl_sandbox_r
```

The integration tests that run the real images carry the `long_running` pytest marker. They
skip when no container daemon or image is available.

(heading-etl-contract)=
## Script contract

Every language shim implements the same file layout and exit codes, defined in
`etl_shim/contract.py`. All paths are relative to the sandbox root (`/sandbox`).

| Path | Written by | Contents |
|---|---|---|
| `manifest.json` | runner | `{"datatype": "<registered name>", "config": {…}}` |
| `script.py` or `script.R` | runner | The pinned Script Version's source. The filename comes from the image key's language prefix. |
| `input/` | runner | The Job's input files, with paths relative to the Binding's `source_prefix`. |
| `output/result.jsonl` | shim | Only on success: a header line `{"datatype": "<name>"}`, then one validated row per line. |
| `output/log.txt` | shim | The Script's captured stdout and stderr. Written whatever the outcome. |

`result.jsonl` is written to a temporary file and renamed only after **every** row has been
validated. On any failure no result file exists, so the loader can never read a partial batch.

| Exit code | Name | Meaning |
|---|---|---|
| 0 | `EXIT_SUCCESS` | The Script completed and every row validated. |
| 1 | `EXIT_SCRIPT_ERROR` | The Script's own code raised, including at import time. |
| 2 | `EXIT_CONTRACT_VIOLATION` | Bad or missing manifest, unknown Datatype, invalid source, no `main`, or a row that fails the Datatype schema. |
| 3 | `EXIT_TIMEOUT_OR_KILLED` | Set by the backend, never by a shim: the run timed out or was OOM-killed. |

### Python Scripts

A Python Script defines `main(ctx)` and yields dictionaries. `ctx` is a `ScriptContext` with
`input_dir` (a `Path`), `datatype` and `config`:

```python
import csv

def main(ctx):
    for path in sorted(ctx.input_dir.glob("*.csv")):
        with path.open() as f:
            for rec in csv.DictReader(f):
                yield {
                    "alias1": rec["subject"],
                    "measurement_concept_id": ctx.config["concept_id"],
                    "measurement_type_concept_id": ctx.config["type_concept_id"],
                    "measurement_date": rec["date"],
                    "measurement_source_value": rec["code"],
                    "value_as_number": float(rec["value"]),
                }
```

### R Scripts

An R Script defines `main <- function(ctx)` and calls `emit(row)` once per row. `row` is a named
list or a one-row data.frame. `ctx` is a list with `input_dir`, `datatype` and `config`.

The R shim has two halves:

1. `shim.R` runs the Script in an `Rscript` child process and writes each emitted row as a raw
   JSON line.
2. `r_shim.run_r_sandbox` (Python) feeds those rows through the same `run_script` function that
   Python Scripts use.

R rows are therefore validated against the same Datatype schemas, with the same all-or-nothing
`result.jsonl` rule. No schema is duplicated in R.

(heading-etl-raw-bucket)=
## Raw bucket move

When a Job succeeds, `move_etl_job_inputs_to_raw_bucket` is queued only after the Job's
`succeeded` status is saved, and the mover leaves alone any Job that isn't `succeeded`. It moves each input to the Binding's
**Raw Bucket** at `<raw_prefix><job id>/<path relative to source_prefix>`. Keys include the Job
id, so re-runs never overwrite earlier copies. Each input is moved independently, so one failing
file does not block the others in a folder Job.

### Raw Retention

`PipelineBinding.raw_retention` is `move` (the default) or `delete` (ADR 0032, #246). Polling,
auto-retries and manual retries copy it onto `EtlJob.raw_retention` when a Job is queued, so
changing a Binding never affects Jobs already queued. Under `delete`:

- only the source key needs grant coverage, and no copy is made;
- the source is deleted and `source_status` becomes `deleted`. `source_handled_at` records when, and
  `raw_bucket_key` stays empty. The `EtlJobInput` key, SHA-256 and size are the only
  provenance left;
- failed deletes go through the same capped backoff and escalation as moves (below). The
  `etl_source_cleanup_stuck` event records the `raw_retention`.

The Binding's `raw_bucket` and `raw_prefix` are blank under `delete`. Only an Admin may switch a
Binding to `delete`, and doing so requires a confirmation checkbox. Either manager role may switch
it back to `move`. Both `etl_binding_created` and `etl_binding_updated` record
`raw_retention`, and an update also records `raw_retention_previous`. Switching to `delete`
doesn't purge raw copies that earlier Jobs already stored.

Each input goes through these steps:

1. **Grant check.** Both the source key and the raw key must be covered by one of the project's
   `EtlLocationGrant` rows. If either is not, the move is skipped and is not retried.
2. **Copy and verify.** Copy the object, read the copy back, and compare its size and SHA-256
   against the values recorded on the `EtlJobInput`. The ETag is never trusted on its own. A
   copy that does not match is deleted, and the attempt counts as a failure. After a verified
   copy, `raw_bucket_key` is recorded, so a retry skips straight to deleting the source.
3. **Delete the source.** On success, `source_status` becomes `moved`.

Under `delete` Raw Retention, step 1 checks only the source key, and step 2 is skipped.

If the copy, verification or delete fails, the input becomes `source_cleanup_pending`, with
capped exponential backoff: `BASE × 2^(attempt−1)`, capped at `MAX`.
`retry_etl_source_cleanup` retries inputs whose next attempt is due. After
`MIRES_ETL_SOURCE_CLEANUP_MAX_ATTEMPTS` failures the input becomes `source_cleanup_stuck`. The
source file is then left in place for manual handling, and the platform, once only:

- emails staff users and the project's Admins and Data Managers;
- records an `etl_source_cleanup_stuck` audit event.

(heading-etl-permissions)=
## Permissions and audit

`readers/etl_permissions.py` is the single policy for the ETL Pipelines tab:

| Role | Access |
|---|---|
| Superuser, Admin | Everything, including admin-only actions: archiving a Script, editing the project's ETL overrides under Defaults, and switching a Binding to `delete` Raw Retention. |
| Data Manager | Create and edit custom Scripts, upload Versions, create and edit Bindings (not into `delete` Raw Retention), retry failed Jobs. |
| PI, Investigator | Read-only: every section is listed, but no manage controls are rendered or accepted. |
| Staff (`is_staff`) | Read-only on every section, plus the Sources section: grants and Source Locations. |
| Any other role | No access. The tab returns 404. |

The **Sources** section (#268) is shown only to Admins, staff and superusers; for anyone else
the section and its endpoints return 404. Admins create, rename and delete Source Locations
inside existing grants. Only staff and superusers create or delete `EtlLocationGrant`s (403 for
an Admin). Staff and superusers still need project membership (any role) to open the tab.

Views first resolve the project with `get_user_etl_project_or_404`. A view that performs a
manage action then checks the relevant permission itself and responds 403 if it is missing.

(heading-etl-connected-storages)=
### Connected Storages

A Connected Storage (`EtlStorage`) is an S3-compatible store: a unique name, endpoint URL, region and
the *names* of the env vars holding its access key id and secret (`access_key_id_env`,
`secret_access_key_env`). No secret value is stored, logged or rendered. A storage whose env vars are
unset shows as "credentials not configured" and fails to browse or poll with that message.

Every `EtlLocationGrant`, `EtlSourceLocation` and `PipelineBinding` belongs to one storage (a location
and Binding take it from their grant). Unique keys include the storage, so the same bucket and prefix in
two storages are two places. Every S3 call for a Binding or Job (polling, source fetch, raw-bucket move
and cleanup) builds its client from that Binding's storage (`s3.build_storage_client`), and a grant
only authorises its own storage.

- **Default**: created by migration and attached to all pre-existing rows. It is the platform-wide
  `MIRES_ETL_S3_*` settings read *live* (endpoint, region and credentials), so an existing deployment
  behaves as before. It is read-only in the admin and can't be deleted.
- **Settings**: `MIRES_ETL_STORAGES` is a JSON list of `{name, kind, endpoint_url, region,
  access_key_id_env, secret_access_key_env}`, synced after every `migrate` and by
  `manage.py sync_etl_storages` (`actions/etl/storages.py`). These are read-only in the admin. One
  removed from settings is deleted if nothing references it, otherwise kept and flagged "no longer in
  settings". A declared name that clashes with an admin-created storage is skipped and logged.
- **Admin**: staff and superusers create, edit and delete the rest (env-var names only).
- **Browsing**: in the Location Grant form, staff and superusers pick a storage, then a bucket
  (`ListBuckets`; type it instead if the credential can't list), then drill into folders one level at a
  time, with up to 50 object names per folder for orientation, never contents (`readers/etl_storage_browser.py`,
  `GET .../etl-pipelines/storages/<id>/browse/`). Choosing a folder fills in the grant's prefix. Errors
  show inline and typing stays possible. Each browse writes an `etl_storage_browsed` audit event with the
  storage id and bucket (none for the bucket list), never a prefix or object name.

Per-project isolation is enforced in application code through `EtlLocationGrant`:

- A Source Location can only be created inside a grant, and the wizard re-checks the chosen
  one and the raw location against the grants.
- The raw-bucket mover checks both keys again before copying.
- Grants are managed by staff and superusers in the Sources section, or in the Django admin
  (`/<MIRES_ADMIN_URL>/`). Both go through `actions/etl/sources.py`: adds and deletes are
  audited, and a grant can't be deleted while a Source Location, or a Binding's source or raw
  location, that it covers would fall outside the remaining grants. In the admin an existing
  grant's project, bucket and prefix are read-only and there is no bulk delete. Source
  Locations are read-only in the admin.
- Creating a Source Location and deleting a grant both lock the project's grant rows
  (`select_for_update`), so they can't interleave.

A Binding may only pin a Version of a native Script or of one of the project's own
non-archived custom Scripts. Its source bucket and prefix must not already be bound elsewhere.

Every management action writes an `AuditLog` entry. The metadata holds identifiers only, never
names, descriptions or bucket paths:

| Event type | Recorded when |
|---|---|
| `etl_script_created` | A custom Script (and its version 1) is created, including by Customizing a Native Script (then with `customized_from`). |
| `etl_script_updated` | A Script's name or description is edited. |
| `etl_script_version_created` | A new Version is uploaded. |
| `etl_script_archived` | A Script is archived. |
| `etl_binding_created` | A Pipeline Binding is created. |
| `etl_binding_updated` | A Pipeline Binding is edited. |
| `etl_settings_updated` | The project's ETL overrides are changed. |
| `etl_job_manual_retry` | A failed Job is manually retried. |
| `etl_source_cleanup_stuck` | A raw-bucket source delete gave up (system event, no user). |
| `etl_source_location_created` / `_renamed` / `_deleted` | A Source Location is created, renamed or deleted. |
| `etl_location_grant_created` / `_deleted` | A location grant is created or deleted in the Sources section. |

(heading-etl-native-scripts)=
## Native Scripts

Native Scripts ship with the codebase in `MiqaResearch/etl_native_scripts/`
([ADR 0030](#heading-etl-adr-0030)). `NATIVE_SCRIPTS` lists each one's name, Datatype,
description and source file. The sources are self-contained (standard library only), because
they run in the sandbox as `script.py` and a Customized copy has to keep working on its own.

**Sync.** `sync_native_etl_scripts` runs after every `migrate`, through `post_migrate`, and can
also be run on demand with `manage.py sync_native_etl_scripts`. It mirrors the list into
`EtlScript` rows (origin `native`, no project, keyed by name):

- A new immutable Version is published only when a source's SHA-256 or its config schema
  changes. The schema is a `<stem>.schema.json` sidecar next to the source
  (`csv_participant_consent.schema.json`). A malformed sidecar is logged and that Script gets
  no new Version until it's fixed, so it can't block a `migrate`; a test checks every shipped
  sidecar so CI catches it first. Bindings keep the
  Version they pinned until a manager re-pins them.
- A Native Script that is removed from the list is archived, never deleted.
- `MIRES_ETL_SYNC_NATIVE_SCRIPTS_ON_MIGRATE=False` turns off the automatic sync. Tests do this.

**Customize.** Native Scripts are available to every project, with no per-project toggle.
Admins and Data Managers can **Customize** one (`actions/etl/scripts.customize_native_script`).
This creates a project-owned custom Script with the same name, description and Datatype, whose
version 1 is a copy of the Native Script's latest Version, config schema included. The copy
does not follow later upgrades of the Native Script.

(heading-etl-adr-0030)=
:::{note}
**ADR 0030.** Keeping Native Scripts in code keeps them reviewed and versioned with the
platform. Syncing them into immutable Versions keeps every Job reproducible. Customizing by
copying means one project's change never reaches another project's pipelines.
:::

### CSV → participant consent

The first Native Script (`csv_participant_consent.py`) produces `participant_consent` rows. By
default it reads the SamtyckenUmu consent export:

- **Fixed columns:** `Personnummer`, `Namn`, `Status`, `Signerat`, `Återtaget`, `klinik` and
  `participant_information_version`. `Senast Uppdaterad` and `Kommentar` are ignored.
- **Consent columns:** every other column is a consent type, and a cell of `Ja` means the
  consent was given.
- **Dates** are local times in `Europe/Stockholm`, as `YYYY-MM-DD HH:MM[:SS]`.
- **Personnummer** has its dashes removed. Every ETL Datatype applies the same format (trimmed,
  dashes removed) to `person_source_value`, and so does DICOM ingestion to PatientID, so all
  match the same Study Participant. Migration 0026 reformatted identifiers stored earlier.
  It aborts without changes, naming the alias1s, if two participants of one project would
  collide.

A Binding's config can override any of these:

```json
{
  "delimiter": ";",
  "encoding": "utf-8-sig",
  "timezone": "Europe/Stockholm",
  "consented_values": ["yes"],
  "source": "Lab export",
  "columns": {
    "person_source_value": "ssn", "name": "full_name", "status": "state",
    "signed": "signed_at", "revoked": "revoked_at", "clinic": "site",
    "participant_information_version": "info_version", "ignore": ["notes"]
  }
}
```

A CSV missing a required column (person, signed date or clinic) fails the Job with exit 1 and
a message naming the missing column. Its config schema allows only these keys (and only these
`columns` keys), so a misspelt key is rejected when the Binding is saved.

(heading-etl-samtycken-task)=
### SamtyckenUmu consent task

The `fetch_participant_consent` task (#241) only fetches. It writes each SamtyckenUmu export,
unchanged, to `<MIRES_TASK_CONSENT_UPLOAD_PREFIX><form_id>/<UTC timestamp>.csv` in
`MIRES_TASK_CONSENT_UPLOAD_BUCKET` (for example `samtycken/1234/20261006T073015Z.csv`), using
the platform ETL credential (`MIRES_ETL_S3_*`). It fails before fetching if no bucket is set.
A failed fetch uploads nothing. The task never creates Bindings. The **Consent Project** is the
Research Project named by `MIRES_TASK_CONSENT_RESEARCH_PROJECT_NAME`. An operator sets up
loading once:

1. Run `manage.py adopt_legacy_consent_participants --dry-run`, then without `--dry-run`.
   It adopts each **Legacy Consent Participant** into the Consent Project: a participant the
   legacy task created without a project, that has a consent of a Consent Project consent
   type. Other participants are left alone. It is idempotent. Skipping it makes the first ETL
   import duplicate those participants. A Legacy Consent Participant whose person is already in
   the Consent Project (for example because a Binding ran first) is skipped and printed with
   both alias1s, `--dry-run` included. Merge those by hand: adopting them would make every later
   consent Job fail with an ambiguous participant reference.
2. Grant the bucket and prefix to the Consent Project, and add a Source Location for it
   (Sources section).
3. In the Consent Project, create a per-file Binding on that Source Location running the native
   **CSV → participant consent** Script. Set its Raw Retention to **delete**: the exports
   carry personnummer and names (ADR 0032). Put any non-default columns, and the former
   `MIRES_TASK_CONSENT_SOURCE` value as `source`, in the Binding's config.

Legacy consent types already belong to the Consent Project, so they match as they are.

An export fetched without `from_date`/`to_date` is a full export, so every Job re-upserts all
consents and records revocations. A non-comma `separator` needs a matching `delimiter` in the
Binding's config.

(heading-etl-adr-0033)=
:::{note}
**ADR 0033.** Loading through a Binding gives consents per-project matching, Job history and
recorded revocations, which the legacy task's own load path lacked. That path is removed,
with no transition flag. The consent upload API keeps `create_participant_consents`.
:::

(heading-etl-config-schema)=
## Config schemas

A Script Version can carry a config schema (#238): a JSON Schema, Draft 2020-12, stored as
`EtlScriptVersion.config_schema`. A custom Script's version gets one from the optional
**Config schema** upload on **New script** and **Edit script** (saved as a new Version when it, the code or the language changed). A Native Script gets one from
its sidecar file. The upload must be a JSON object that passes `check_schema`
(`MiqaResearch/etl_config_schema.py`); otherwise it is a form error.

```json
{
  "type": "object",
  "properties": {
    "delimiter": {"type": "string", "maxLength": 1, "title": "Delimiter", "description": "Default: \",\""},
    "skip_rows": {"type": "integer", "minimum": 0},
    "strict": {"type": "boolean"},
    "encoding": {"enum": ["utf-8", "latin-1"]},
    "columns": {"type": "object"}
  },
  "required": ["delimiter"],
  "additionalProperties": false
}
```

**Validation.** The Binding wizard and **Edit** form validate the assembled config against the
selected Version's schema (`EtlBindingEditForm`). Each error names the key path and is shown
beside its field, so a create, edit or re-pin with config that doesn't fit is rejected; a
rejected Edit re-opens with the input kept. `create_pipeline_binding` and
`update_pipeline_binding` re-check it and raise `EtlBindingConfigInvalid`. Config isn't
re-checked when a Job runs; a Binding saved before its Version had a schema keeps its config
until it is next edited.

**Generated fields.** With a schema, the form shows one field per top-level `properties`
entry, named `config__<key>`, labelled by `title` (or the key) with `description` as help text:

| Property | Field |
|---|---|
| `enum` | Select of the enum values |
| `"type": "boolean"` | Select: unset, Yes, No |
| `"type": "string"` | Text |
| `"type": "integer"` / `"number"` | Number |
| anything else (array, object, union) | JSON textarea |

Keys in `required` make their field required. An empty field leaves the key out, so the
Script's own default applies; in a JSON textarea, `null` sets the key to null. Unless the schema
sets `"additionalProperties": false`, an **Additional config** JSON box keeps the keys that
aren't listed as properties. The box also appears, even then, for a value no field can show (an
empty string, a value outside an enum, a wrong type), so a saved value is never silently lost.

Changing **Script & version** sends the whole form (minus the CSRF token) to
`dashboard_tab_etl_binding_config_fields` (HTMX). The fragment's hidden `config_fields_for`
names the Version its fields were rendered for; the endpoint reads the typed config under that
Version (`EtlBindingEditForm.entered_config`) and renders the new Version's fields filled in
with it.

(heading-etl-configuration)=
## Configuration reference

All settings are environment variables. See [Configuration](#heading-configuration) for how
they are loaded.

| Variable | Default | Description |
|---|---|---|
| `MIRES_ETL_S3_ENDPOINT_URL` | *(none)* | S3-compatible endpoint for source and raw buckets. |
| `MIRES_ETL_S3_REGION_NAME` | `us-east-1` | Region for that endpoint. |
| `MIRES_ETL_S3_VAULT_PATH` | `mires/etl-s3` | With `MIRES_USE_VAULT`, the Vault KV path holding `AccessKeyId` and `SecretAccessKey` for the Default storage. Used only when the two `MIRES_ETL_S3_*` credential vars are unset. |
| `MIRES_ETL_S3_ACCESS_KEY_ID` / `MIRES_ETL_S3_SECRET_ACCESS_KEY` | *(none)* | The credential of the built-in `Default` Connected Storage (these `MIRES_ETL_S3_*` settings are read live). |
| `MIRES_ETL_STORAGES` | `[]` | JSON list of additional Connected Storages (`name`, `kind`, `endpoint_url`, `region`, `access_key_id_env`, `secret_access_key_env`), synced after every `migrate`. See [Connected Storages](#heading-etl-connected-storages). |
| `MIRES_ETL_POLL_INTERVAL_SECONDS` | `30` | How often every Binding is polled. |
| `MIRES_ETL_JOB_MAX_AUTO_RETRIES` | `3` | Maximum number of attempts for infra-class failures. |
| `MIRES_ETL_JOB_STUCK_GRACE_SECONDS` | `300` | Grace period on top of the sandbox timeout before a running Job counts as stuck. |
| `MIRES_ETL_LOG_RETENTION_DAYS` | `30` | Default Job log retention (per-project override under Defaults). |
| `MIRES_ETL_SOURCE_CLEANUP_MAX_ATTEMPTS` | `5` | Raw-bucket move attempts before escalation. |
| `MIRES_ETL_SOURCE_CLEANUP_BACKOFF_BASE_SECONDS` | `60` | First backoff delay. |
| `MIRES_ETL_SOURCE_CLEANUP_BACKOFF_MAX_SECONDS` | `3600` | Backoff cap. |
| `MIRES_ETL_SCRIPT_STORAGE_BACKEND` | `local` | `local` or `s3`: where Script Version sources are stored. |
| `MIRES_ETL_SCRIPT_S3_BUCKET`, `_ENDPOINT_URL`, `_REGION_NAME`, `_ACCESS_KEY_ID`, `_SECRET_ACCESS_KEY` | *(none)*, region `us-east-1` | S3 settings for Script source storage when the backend is `s3`. |
| `MIRES_ETL_SCRIPT_MAX_SOURCE_BYTES` | `262144` (256 KiB) | Default maximum Script source size (per-project override under Defaults). |
| `MIRES_ETL_SCRIPT_IMAGE_KEYS` | `{".py": "python-etl-v1", ".r": "r-etl-v1"}` | Maps a file extension to a sandbox image key. |
| `MIRES_TASK_CONSENT_UPLOAD_BUCKET` / `_PREFIX` | *(none)* / `""` | Where the SamtyckenUmu consent task writes each export. See [SamtyckenUmu consent task](#heading-etl-samtycken-task). |
| `MIRES_ETL_SYNC_NATIVE_SCRIPTS_ON_MIGRATE` | `True` | Sync Native Scripts from the codebase after every `migrate`. |
| `MIRES_SANDBOX_BACKEND` | `compose` | `compose` or `kubernetes`. |
| `MIRES_SANDBOX_IMAGE_ALLOWLIST` | `{}` | JSON object mapping an image key to an image reference. Must list every key in use. |
| `MIRES_SANDBOX_DOCKER_HOST` | `unix:///var/run/docker.sock` | Docker API for the Compose backend. Use a socket proxy in production. |
| `MIRES_SANDBOX_DEFAULT_TIMEOUT_SECONDS` | `600` | Platform timeout ceiling. |
| `MIRES_SANDBOX_DEFAULT_MEMORY_MB` | `1024` | Platform memory ceiling. |
| `MIRES_SANDBOX_DEFAULT_CPU_MILLICORES` | `1000` | Platform CPU ceiling. |
| `MIRES_SANDBOX_DEFAULT_PIDS_LIMIT` | `128` | Process limit for each run. |
| `MIRES_SANDBOX_MAX_INPUT_BYTES` | 15 GiB | Maximum staged input per run. |
| `MIRES_SANDBOX_MAX_OUTPUT_BYTES` | 1 GiB | Maximum output archive per run. |
| `MIRES_SANDBOX_K8S_NAMESPACE` | `mires-etl-sandbox` | Namespace for sandbox Jobs (Kubernetes backend). |
| `MIRES_SANDBOX_K8S_STAGER_IMAGE` | `busybox:1.36` | Trusted image for the transfer and probe pods. |
| `MIRES_SANDBOX_K8S_SELF_TEST_TTL_SECONDS` | `300` | How long a passing egress probe is cached. |
| `MIRES_SANDBOX_K8S_EGRESS_PROBE_HOST` / `_PORT` | `1.1.1.1` / `443` | The target the egress probe must fail to reach. |

(heading-etl-limitations)=
## Current limitations

Project Admins can't create grants, only Source Locations inside them. This is intended: grants
are the isolation boundary for the one platform-wide credential (ADR 0034).
