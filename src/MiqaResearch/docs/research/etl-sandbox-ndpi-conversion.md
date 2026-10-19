# Research: can the ETL sandbox run NDPI conversion?

Resolves #305 (part of #303). Findings only; no spec decisions locked.

Legend: **[V]** verified by reading code/docs at commit 708d386 (path cited). **[U]** unverified: inference, or not run/measured. Nothing here was executed; no sandbox run, no benchmark rerun.

Sources read: `documentation/manuals/technical/src/etl.md`, `.../ndpi-conversion.md`, `GLOSSARY.md` (ETL terms, ADR table), `MiqaResearch/etl_sandbox/*`, `etl_shim/*`, `tasks/etl_orchestrator/*`, `etl_datatypes/*`, `etl_native_scripts/*`, `tasks/dicom_handling/ndpi_conversion.py`, `etl_sandbox.Dockerfile`, `pyproject.toml`, `settings.py`. ADR files are not in the repo; ADR 0025/0030/0032/0034 are only summarised in etl.md/GLOSSARY.md.

## Answer

**No, not as the contract stands. Yes only for small slides, and with luck.** Three hard blockers, two soft ones:

1. **Scripts cannot return files [V].** The only output read back is `output/result.jsonl` + `output/log.txt` (`_staging.read_output_from_tar`); `runner._finalize` loads only the JSONL. Anything else a Script writes to `output/` is discarded. The DICOM files would be lost.
2. **Output cap 1 GiB [V].** `MIRES_SANDBOX_MAX_OUTPUT_BYTES` default 1 GiB, no Binding override (`limits.resolve_limits`). Conversion output is about input size (+2.4% on the benchmark). Any NDPI over ~1 GiB overflows. Compose `_retrieve_output` and K8s `_exec_read` then return `None` for the whole output, so even `result.jsonl` is dropped and the Job fails ("exit 0 but wrote no result.jsonl", `runner._load_result`).
3. **Whole input in worker RAM [V].** `runner.run_job` calls `EtlBucketSource.read` = `get_object(...)["Body"].read()` per input (full `bytes`), keeps them all in `input_files`, then `build_sandbox_archive` builds a `BytesIO` tar and `getvalue()` (another copy). So at least 2 to 3 copies of the NDPI sit in the Celery worker at once [U on exact multiple; V that they are whole-file in-memory]. Cap is 15 GiB input (`MIRES_SANDBOX_MAX_INPUT_BYTES`), but the worker's real RAM is the limit, long before that. K8s then writes it through pod-exec in chunks from that same in-memory buffer (`_exec_write`).
4. (soft) **Timeout/CPU/memory defaults are tight [V limits, U fit].**
   - Timeout 600 s, CPU 1000 m, memory 1024 MB; a Binding can only lower these (`limits._clamp`).
   - The conversion doc's benchmark is CMU-1: 198 MB, 7.7 s wall, 11.4 s CPU, 570 MB peak (`ndpi-conversion.md`). That is **about 39 s/GB wall** on 18 cores (the doc's own per-GB column), not "about 8 s/GB". The issue's 8 s/GB looks like the 7.7 s figure misread as per-GB. [V doc, check with author].
   - On the 1-CPU default, CPU time is the floor: 11.4 CPU-s / 0.198 GB is about 58 s/GB [U: assumes the work is CPU-bound and does not scale below 1 core]. 600 s then covers roughly 10 GB, not 15. A raised ceiling needs a platform-wide env change (`MIRES_SANDBOX_DEFAULT_*`); no per-Binding raise exists.
   - 570 MB peak plus the shim's own Django import baseline must fit in 1024 MB [U: baseline not measured]. Raise CPU/memory only via platform ceilings.
5. (soft) **Disk [V code, U ops].**
   - K8s: one PVC per run sized `ceil((max_input + max_output)/GiB)` = 16 Gi by default (`kubernetes_backend._pvc_size_gi`). Input (N) plus converted output (about N) must fit; for a 15 GiB NDPI that is 30 GiB, over the 16 Gi PVC.
   - Compose: files go in the container's writable layer via `put_archive`; no disk limit is set [V]. An unbounded layer is a host-disk risk for big slides.

Things that do work [V]:
- The sandbox image has the library: `wsidicomizer>=0.30.0` is in `[project].dependencies` (pyproject), and the Dockerfile does `uv sync --frozen --no-dev` and copies the whole app, so `MiqaResearch.tasks.dicom_handling.ndpi_conversion` is importable. No network needed.
- `ctx.input_dir` is a real directory of real files, so `convert_ndpi_to_dicom(path, out_dir)` can be called.
- Native Script convention is stdlib-only (etl.md "Native Scripts") because a Customized copy must stay standalone; a conversion script would break that (it would import app code). Minor.

## Why "rows only" is deliberate

Datatype = schema + loader that persists rows; Scripts never write to DB or storage (GLOSSARY "ETL Datatype"; `shim.run_script` validates rows only). Making files a second output channel changes `SandboxRunResult`, both backends, the tar/size-cap logic and the loader. And `SandboxBackend.run()` is blocking inside one `QUEUE_ETL_RUN` task (ADR 0025), so a long conversion occupies a worker slot for its whole duration.

## Option space

| Option | What | Verdict |
|---|---|---|
| A. Sandbox as-is | Script calls the converter, emits no files | Dead: output discarded |
| B. Sandbox + output-artifact channel | Backends return a file set; orchestrator uploads to S3 | Large change (both backends, streaming, ADR 0025-adjacent); still inherits in-memory input read and caps; a security-surface increase for a trusted-code job |
| C. Native Script + "request" Datatype whose loader enqueues a conversion task | Reuses polling and Job | Loses Raw Retention safety (see below) and still reads the NDPI into RAM first |
| **D. New Job executor: platform task instead of a sandbox run** | Binding points at a registered Native "executor" (not a Script Version); Job runs a Celery task | Recommended direction [U: not prototyped] |

### Option D sketch (separate Celery task triggered by a Job)

- Reuse polling, `EtlJob`/`EtlJobInput`, per-Binding single active Job, retry, stuck detection, Raw Retention. Only `runner.run_job` changes: branch on executor kind. Add a queue for conversion so it does not starve `QUEUE_ETL_RUN` [U on queue shape].
- Task streams the object S3 to local temp disk (`download_file`, hashing as it goes to fill `EtlJobInput.sha256/size_bytes`; fixes blocker 3), runs `convert_ndpi_to_dicom`, uploads the DICOM files to a bucket/prefix that DICOM ingestion reads (`ingest_dicom_source(research_project_id, "s3://bucket/prefix")`, `tasks/dicom_handling/tasks.py`), then enqueues ingestion or leaves it to a Binding. Marks the Job `succeeded` only after upload.
- No row Datatype involved; "loading" is the upload. All-or-nothing: on any failure delete partial uploads and fail the Job.
- Not sandboxed: it parses untrusted NDPI/TIFF in worker code. DICOM ingestion already parses untrusted files in a worker, so this is the same trust class [V that ingestion does so; U on risk acceptance]. It runs platform code, not user code, so the sandbox's job (isolating user scripts) does not apply; a hardened K8s Job runner is the upgrade path if wanted.
- Limits: needs its own timeout/memory/CPU (the stuck-job rule uses the Binding's sandbox timeout + grace via `is_stuck`; it would need the executor's timeout). Disk: needs about 2x slide on scratch.

## Interaction with grouping mode and Raw Retention

**Grouping mode (per file) [V].** `polling._poll_per_file` queues the oldest unassigned file, one Job per file; one active Job per Binding (partial unique constraint). Per-file is the right mode: one NDPI to one Job to one DICOM series. Folder mode would put several slides in one Job (more RAM and runtime, one failure fails all). Conversion is serialised per Binding, so throughput is one slide at a time per Binding: fine at ~40 to 60 s/GB [U], but a backlog of many large slides is slow.

**Raw Retention [V].** `_finalize` enqueues `move_etl_job_inputs_to_raw_bucket` immediately when the Job is `succeeded`; under `move` the source is copied (verify SHA-256) then deleted; under `delete` (ADR 0032, Admin-only) it is just deleted, "no copy kept anywhere". Consequences:

- Option C is unsafe: Job "succeeds" when the request row loads, source is moved/deleted, then an async conversion fails and the NDPI is gone (under `delete`) or sits in the raw bucket needing manual recovery (under `move`). The retry (`Manual Retry`) reuses the Job's inputs, which no longer exist at the source.
- Option D is safe: `succeeded` means converted and uploaded, so the existing move/delete is correct as-is. A failed Job leaves the source in place (glossary rule), so retries work.
- Under `delete`, the NDPI is destroyed after conversion: only checksums remain. Whether researchers may lose the original slide is a product decision; default `move` keeps it in the Raw Bucket (about 2x storage: raw NDPI + DICOM). Flag for the spec.
- The mover reads checksums recorded on `EtlJobInput`, so Option D must fill them (streamed hash) or the verify step fails.

## Open items for the spec (all [U])

- Real per-GB cost on target hardware at the platform's CPU ceiling (rerun the benchmark constrained to 1 core; resolve 8 vs 39 s/GB).
- Scratch-disk sizing and where the converted files land (which bucket/prefix, who owns ingestion trigger).
- Whether DICOM output should be ingested automatically (chain `ingest_dicom_source`) or via a second Binding.
- Output file naming/idempotence on re-run (Raw keys nest by Job id; DICOM SOP UIDs from wsidicomizer are generated per run, so a re-run may duplicate studies) [U: check wsidicomizer UID behaviour].
