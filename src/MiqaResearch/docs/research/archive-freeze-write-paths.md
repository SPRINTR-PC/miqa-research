# Research: write paths an Archived Project freeze must cover

Resolves #426 (parent map #425). Findings only; no spec decisions locked. Source = this repo's code at `main` de7c128 (paths relative to `src/MiqaResearch/MiqaResearch/`). Not exhaustive on tests/migrations.

Legend: **[B]** blocks inside the freeze; **[X]** deliberately NOT frozen (candidates); **[?]** open decision.

## TL;DR
- No single choke point exists today. Project is resolved 4 different ways (see Seams). No `ResearchProject.archived_*` field yet.
- Best central seam = RAPID **actions** layer: one `require_project_writable(project)` raising a `ProjectArchived` (a `ViewerActionError`-like / `EtlActionError`-like domain error) at the top of every project-scoped action, plus a **loader/runner** guard for the ETL Job path (which bypasses most actions).
- Paths that bypass actions entirely (must be guarded separately): ETL poll/run/loader tasks, native consent upsert API, `etl_datatypes/*` loaders, management commands, Django admin, the `.NET` SFTP uploader + DicomReceiver (out-of-process, land in buckets), OCR task, signals.
- Archive itself must deactivate ETL Bindings (settled in map); that alone does NOT stop already queued/running Jobs, retries, or the raw-bucket mover.

## Inventory

### 1. Dashboard HTTP views (HTMX, session, `interfaces/http/views/dashboard/`)
All resolve project via `get_user_project_or_404` / `get_user_etl_project_or_404` (`project.py`), then role check, then call an action. All POST except tab GETs.

| Path (url name) | Action called | Frozen? |
|---|---|---|
| etl_scripts_create / _edit / _archive / _delete / _customize | `actions/etl/scripts.py` (create_custom_script, create_script_version, update_custom_script, archive_custom_script, delete_archived_script, customize_native_script) | [B] project scripts. `delete_archived_script` is superuser, no project arg: [?] allow (Deletion is explicit, Custodian/Superuser per map) |
| etl_bindings_create / _edit | `create_pipeline_binding`, `update_pipeline_binding` (also calls `rehome_backlog_after_grouping_change`) | [B] |
| etl_defaults_update | `actions/etl/settings.py update_etl_project_settings` | [B] |
| etl_job_retry | `actions/etl/jobs.py retry_failed_job` (creates EtlJob + enqueues run) | [B] |
| etl_source_locations_create / _edit / _delete; etl_location_grants_create / _edit / _delete | `actions/etl/sources.py` | [B] |
| etl_storage_browse | `browse_storage` (read-only listing, writes AuditLog) | [X] read |
| api_client_issue / update / rotate / revoke | `actions/client_bindings.py` (creates OAuth Application+ClientBinding, rotates secret, deletes AccessTokens) | [B] issue/update/rotate. [?] revoke should stay allowed (security: must be able to cut access on a frozen project) |
| consent-statistics, goals, etl-pipelines GET tabs, job detail, datatype-schema | readers only | [X] |

Goals: only a read-only tab (`tabs.py goals`, renders consent counts); **no goal write path exists today**. Future Goals map must route through the same check.

### 2. Ninja API (`interfaces/http/api/`)
Default auth = `ClientCredentialsAuth(["read"])` (Bearer); several routers override with `SessionAuth`.

| Endpoint | Auth | Writes | Frozen? |
|---|---|---|---|
| POST `/v1/consent/` (`upload_data/upload_consent.py`) | Bearer scope `upsert_consent` | `actions/consents/participant_consents.create_participant_consents`: creates ParticipantConsentType/Clinic/ParticipantConsent. **No project argument**: types looked up by `label` globally; new types go to the default project `TASK_CONSENT_RESEARCH_PROJECT_NAME` (get_or_create) | [B] but the project is implicit via consent type; needs resolving the type's project (and `aget(label=)` may be ambiguous across projects since #226) |
| POST `/v1/viewer/objects` (`viewer/objects.py save_object`) | Session | `actions/annotations.save_viewer_object`: stores SR/SEG DicomFile + DerivedObjectProvenance + AuditLog. Project from `study.participant_key.project` | [B] Annotations and Segmentations |
| POST `/v1/viewer/objects/{id}/retire` | Session | `annotations.retire_object` | [B] |
| PUT `/v1/viewer/projects/{id}/blinded-annotation` (`viewer/blinding.py`) | Session | `actions/blinding.set_blinded_annotation` mutates ResearchProject | [B] |
| POST `/v1/viewer/participants/{id}/blinding-reveal` | Session | session-only (`remember_reveal`) + AuditLog | [?] no project data written; reading aid; likely [X] |
| POST `/v1/participant-keys/keys/{id}/link`, `/repoint`, `/unlink` | Session | `actions/participant_key_admin.py` mutates ParticipantKey + may fill StudyParticipant demographics | [B] |
| POST `/v1/viewer/first-render` (`viewer/telemetry.py`) | Session | log line only | [X] |
| GET `/v1/dicom/*` WADO (machine Bearer + session) | both | reads; writes AuditLog rows (`image_access_audit.py`) | [X] reads stay; audit writes must stay |
| GET monitor, ETL scripts table, participant search | | read | [X] |
| `upload_prom_data.py`, `views/views.py` | | empty files | none |

Machine clients: tokens are issued per project (`ClientBinding`). WADO is read-only, so frozen-project tokens still work for reads (audit-logged). The only machine **write** is the consent upsert (above). Freeze should decide whether bound clients stay valid (reads) or are revoked [?].

### 3. Non-API views
- `UploadDataView` (`views/upload_data/index.py`): stub, POST returns 201, writes nothing, hard-coded projects. [X] today; guard if wired.
- Viewer page / unlinked viewer page: read + AuditLog (`image_access_audit`). [X]
- Login/EID: user rows, not project data. [X]

### 4. Background jobs (`tasks/`, `celery.py`; `django.tasks.@task` unless noted)
Beat schedule (`celery.py`): fan-out polls 60s-ish (`ETL_POLL_INTERVAL_SECONDS`), recover-stuck 60s, prune-logs daily 02:00, retry-source-cleanup 60s, sweep-sandboxes 300s, dicom orphan sweep daily 03:00.

| Task | What it writes | Project check today | Frozen? |
|---|---|---|---|
| `fan_out_etl_polls` | enqueues poll per **every** PipelineBinding (`PipelineBinding.objects.values_list`) | none | [B] skip bindings of Archived Projects (map: archive deactivates bindings, so a binding `active` flag filter here is the primary mechanism) |
| `poll_pipeline_binding` -> `polling.poll_binding` | EtlProcessedFile rows, EtlPendingGroup, EtlJob + EtlJobInput | none | [B] defense in depth |
| `run_etl_job` -> `runner.run_job` | status, runs sandbox, then `_finalize` -> `load_jsonl` (all datatype loads) | none; only `job.status == pending` guard | [B] **critical bypass**: a Job queued before archive still runs and loads |
| `move_etl_job_inputs_to_raw_bucket`, `retry_etl_source_cleanup` | moves/deletes source objects in buckets, mutates EtlJobInput | none | [?] cleanup of an already-succeeded job; deleting under "delete" retention is the safety-critical step. Recommend: finish in-flight cleanup, do not start new |
| `recover_stuck_etl_jobs` -> `retry.retry_infra_failure` | fails job, creates auto-retry EtlJob + enqueues | none | [B] retry creation; marking stuck as failed [X] |
| `prune_etl_job_logs`, `sweep_orphaned_sandboxes` | log pruning / sandbox removal | none | [X] housekeeping |
| `sweep_dicom_orphans` | deletes orphan DICOM blobs | none | [?] housekeeping; but it deletes stored data, confirm it never touches Archived Project data (also mgmt cmd `sweep_dicom_orphans`) |
| `backfill_frame_indexes`, `resanitize_dicom_metadata` | `DicomFile.update(...)` across all files, no project filter | none | [?] platform maintenance mutating frozen data; decide exempt vs per-project skip |
| `fetch_participant_consent` | **no DB write**; writes CSV export to the consent upload bucket (`TASK_CONSENT_UPLOAD_BUCKET`), a Binding then loads it | none, takes `form_id` not project | [B] via binding deactivation / loader guard (bucket is shared, not project-scoped) |
| `rebuild_consent_daily_active_summary(project_id)` | deletes+rebuilds ConsentDailyActiveSummary; fired from `post_save/post_delete` on ParticipantConsent (`data/signals.py`) | none | [X] derived data; only fires after a consent write, which is blocked |
| `run_ocr_on_prom_data` (Celery `app.task`, `tasks/ocr/__init__.py`) | creates ParsedPromForm for a PromData | none | [B]; it is the only PROM write path in the app code |
| NDPI conversion (`ndpi_conversion.convert_ndpi_to_dicom`) | helper used by the ETL script, not a task | n/a | n/a |

PROMs: model `PromData` (`data/models/prom_data.py`, FK `PROTECT` to project), `PromFormTemplate`; **no HTTP write view in this app** (`upload_prom_data.py` empty). Submission is presumably through the `kpforms` package and the OCR task; check `kpforms` for its own views (not in this repo) [?].

### 5. ETL loaders and DICOM ingestion (the biggest bypass)
`runner._finalize` -> `etl_datatypes/loader.load_jsonl(project=..., etl_job=...)` -> registered loader per Datatype. Writes by loader:
- `etl_datatypes/participant_consent.py`: ParticipantConsentType, Clinic, ParticipantConsent, StudyParticipant
- `etl_datatypes/measurement.py`, `visit_occurrence.py`: Measurement, VisitOccurrence
- `etl_datatypes/participant_key_link.py` -> `actions/participant_keys.py` (ParticipantKey create/link, demographics)
- `etl_datatypes/dicom_instance.py` -> `actions/dicom_ingest/load.py load_dicom_instances` (DicomStudy/Series/File rows, blobs, frame index, key linking, `_link_referencing_derived_objects`) and `records.py`, `storage.py`, `pseudonymize.py` (lazily generates `ResearchProject.dicom_hashuid_salt_key`: a write to the project row)
- `actions/dicom_ingest/local.py ingest_local_folder` (dev/CLI): creates StudyParticipant, EtlScript, PipelineBinding, EtlJob, then `load_jsonl`. Not an HTTP path; used by tests/dev.

`load_jsonl` already asserts `etl_job.binding.project_id == project.id` (`EtlJobProjectMismatch`): the natural hook for a **loader-level freeze guard** (one line, covers every Datatype, ingest, and local ingest). It already runs in `transaction.atomic()`.

### 6. SFTP-driven loads
No SFTP code in Django. `src/dotnet/MiresSftpUploader*` (SSH.NET client) pushes archives to a remote; arrival in an ETL bucket is then picked up by Binding polling. `Miqa.Service.DicomReceiver` (C-STORE SCP) has no Django/HTTP/S3 reference in its sources. So SFTP/DICOM-receive cannot be blocked at Django; **effect is blocked only when the Binding is deactivated and the loader guard rejects**. Files will keep arriving in the bucket and accumulate un-ingested (operational note for Archive: tell the sender/Custodian). Also: because ledger diffing (`EtlProcessedFile`) records new files only when polled, unarchive later picks up the backlog.

### 7. Other write surfaces
- Django admin (`data/admin/*.py`: ResearchProject, roles, role maps, ETL models, consents): superuser can edit anything incl. Archived Project. Needs `has_change_permission`/`has_add_permission`/`has_delete_permission` overrides or a documented superuser exemption [?].
- Management commands (`data/management/commands/`): `import_prom_form_template`, `adopt_legacy_consent_participants`, `sync_*`, `seed_*`, `loaddata`, `purge_old_audit_logs`, `evaluate_prom_ocr`. Operator-level; exempt or guard case-by-case. `adopt_legacy_consent_participants` writes participants.
- `ResearchProjectUserRoleMap` edits (Users & Roles map): role changes on an archived project [?] (needs at least custodian/PI visibility changes allowed or explicitly refused).
- `data/signals.py`: AuditLog on login; consent-summary rebuild. AuditLog writes must NEVER be frozen (archive/unarchive and access audits are required evidence).
- Archive/unarchive themselves, and Custodian/Deletion actions on the project: must bypass the check (they are the thaw/delete paths).

## Where a central check could sit

### Option A (recommended): actions-layer guard + one loader guard
- Add `readers/research_project_reader.py` (or new `readers/project_state.py`): `is_project_writable(project)`; and `actions/project_guard.py`: `require_project_writable(project)` raising `ProjectArchived`. Fits RAPID: readers decide, actions enforce, interfaces map the error to 409/403 (existing `ViewerActionError` -> `http_error` in `interfaces/http/api/views/viewer/errors.py`; ETL views already use `_attempt(action)` in `dashboard/etl.py` to turn action exceptions into form errors).
- Call it first in every project-scoped action listed above (about 25 functions). Where an action has only an object (e.g. `retire_object`, `revoke_client`, `update_client`), resolve project from the object, as they already do for permission checks.
- Add the same call in `etl_datatypes/loader.load_jsonl` beside the existing project-mismatch check (covers all Datatype loads including DICOM ingestion), and in `runner.run_job` before the status flip (so queued Jobs of a just-archived project fail fast with a clear log line rather than running the sandbox), and in `polling.poll_binding` / `retry.retry_infra_failure`.
- Pros: matches existing seams; no middleware magic; each action stays independently testable. Cons: opt-in per action: a new action that forgets the call silently bypasses (mitigate with a test that enumerates action modules, or an AST/grep lint like the repo's existing contract tests).

### Option B: model-level (`ResearchProject`-scoped base manager / `save()` hook)
Too many models are project-scoped only through 2-3 FK hops (DicomFile -> series -> study -> participant_key -> project; ParticipantConsent -> consent_type -> project; Measurement). A `pre_save` signal would have to traverse FKs on every write, and bulk operations (`bulk_create`, `.update()`, `_raw_delete` used in `update_consent_summary`, `DicomFile.objects.filter().update` in backfills) skip signals. Not recommended as the sole mechanism; at most a tripwire in tests.

### Option C: HTTP middleware/decorator
Both dashboard views and Ninja routers carry `project_id` in path, but the viewer objects/keys/blinding endpoints identify the project via object ids, the consent API has no project, and Celery has no HTTP. Covers only a subset; good for UX (disable buttons, return 409 early) but not enforcement. Recommend a shared template flag (`project.is_archived`) for UI and the action guard for enforcement.

### Binding deactivation as a first line
Map-settled: archive deactivates Bindings. Add `PipelineBinding.active` (or reuse state) and filter in `fan_out_etl_polls`; this stops new work cheaply but is not the freeze (see bypass list).

## Paths that bypass the Option A guard (need explicit handling)
1. Jobs already queued/running at archive time (`run_etl_job`, `_finalize`, `move_etl_job_inputs_to_raw_bucket`): covered only by the runner/loader guards above.
2. `fetch_participant_consent` and the shared consent upload bucket: not project-scoped; blocked only via binding/loader guard.
3. Native consent upsert API (`create_participant_consents`): no project arg; project is inferred from `ParticipantConsentType`; also `aget(label=...)` is global, not per project (#226 made types per project): pre-existing ambiguity the guard cannot fix.
4. Platform maintenance tasks (`backfill_frame_indexes`, `resanitize_dicom_metadata`, `sweep_dicom_orphans`): no project filter, mutate files across projects.
5. Django admin and management commands.
6. Bulk/raw SQL writes (`update_consent_summary` `_raw_delete` + INSERT; DicomFile `.update`): bypass any model-level hook.
7. OCR task `run_ocr_on_prom_data` (Celery `app.task`, not `django.tasks`): own decorator, own entry point.
8. Out-of-process .NET tools (SFTP uploader, DicomReceiver): cannot be blocked by Django.
9. `ResearchProject` row itself: `dicom_hashuid_salt_key` is lazily written on first DICOM use (`dicom_ingest/pseudonymize.py`); `set_blinded_annotation` writes the row; Archive fields live on it. The guard must exempt the Archive/Unarchive actions.
10. Read endpoints that write AuditLog (WADO, viewer open, storage browse, key table open with reveal): must remain allowed.

## Suggested follow-up decisions (for #427+)
- Exempt list: AuditLog, Archive/Unarchive/Custodian/Deletion actions, `revoke_client`, in-flight raw-bucket cleanup, derived summaries, platform maintenance.
- Failure UX per layer: HTMX action -> form error via `_attempt`; Ninja -> 409 `ProjectArchived` via `http_error`; Celery -> log+no-op (not raise, to avoid retry storms).
- Whether bound API Clients keep read access (WADO) on a frozen project.
- Enumeration test: every action module that mutates a project-scoped model calls the guard (lint/AST test).
- Admin: read-only mixin for project-scoped models when parent project is archived.
