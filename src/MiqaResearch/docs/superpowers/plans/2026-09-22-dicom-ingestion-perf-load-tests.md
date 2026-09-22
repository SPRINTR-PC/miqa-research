# DICOM Ingestion: Performance/Load Test Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `long_running`-marked performance/load test suite for DICOM ingestion (issue #126): many-small-files throughput, one-very-large-file/S3, and real-task-dispatch concurrency — each against an explicit acceptance threshold, all excluded from the default test run.

**Architecture:** Two of the three scenarios (throughput, large-file) call `run_ingestion` directly with `pytest-benchmark`'s `pedantic` mode, exactly like every other DICOM ingestion test — matching #116's Testing Decisions ("only the concurrency-focused performance test... goes through task dispatch"). The concurrency scenario needs a real `django.tasks`/Celery wrapper around `run_ingestion` that doesn't exist yet (deferred by `pipeline.py`'s own docstring: "the django.tasks/Celery wrapper is a later ticket" — decided in advance in ticket #103, closed). This plan introduces that wrapper (new dedicated queue, custom longer time limit via `task_annotations`) purely so the concurrency test has something real to dispatch onto, then adds a `mires_worker_dicom` docker-compose service so the test's dispatched tasks are actually consumed in CI.

**Tech Stack:** pytest-benchmark (already a declared, unused dev dependency), django.tasks (`@task`), django_tasks_celery.CeleryBackend, existing `tests/dicom_fixtures.py` synthetic DICOM builders, existing real-RustFS long_running pattern from `tests/test_dicom_storage_backend.py`.

## Global Constraints

- `long_running` marker already exists (`pyproject.toml`, added by closed ticket #104) and is already excluded by default (`addopts = "--reuse-db -m 'not vlm and not long_running and not ocr'"`) — reuse it verbatim, do not invent a new marker.
- Do not run `ocr`-marked tests as part of this work (AGENTS.md) — irrelevant code, not touched.
- Every new/changed synthetic DICOM fixture must use fully numeric UID components (`1.2.9999.<digits>...`) — `tests/dicom_fixtures.py`'s existing UIDs already do; a prior scratch run confirmed non-numeric UID segments (e.g. `"...perf.1"` — wait, digits only, no letters) trigger `pydicom` VR warnings, so all new UIDs here follow the `1.2.9999.<digits>.<digits>...` shape used by existing builders.
- No new synthetic-fixture-builder machinery needed: `build_ct_image` (small, cheap — good for the throughput scenario) and `build_wsi` (parametrizable tile/frame size — good for the large-file scenario, at `tile_rows=512, tile_columns=512, number_of_frames=32, samples_per_pixel=3` ≈ 25MB of `PixelData`, comfortably past boto3's 8MB multipart threshold) already cover both shapes.
- The concurrency test is the *only* test in this feature that dispatches through task infrastructure — every other assertion in this plan calls `run_ingestion` directly (per #116 Testing Decisions).
- Queue/task naming follows ticket #103's resolution exactly: `QUEUE_DICOM_INGESTION = "dicomIngestion"`, routing key `"analysis.dicom.#"`, `@task(queue_name=QUEUE_DICOM_INGESTION)` from `django.tasks` (not raw Celery `@app.task`), custom time limit via `app.conf.task_annotations` in `MiqaResearch/celery.py` (the decorator itself has no time-limit kwarg).

---

## Task 1: New `dicomIngestion` Celery queue

**Files:**
- Modify: `contract/constants/celery.py`
- Modify: `MiqaResearch/celery.py`
- Modify: `MiqaResearch/settings.py:6-10` (import), `MiqaResearch/settings.py:479-484` (`TASKS["default"]["QUEUES"]`)

**Interfaces:**
- Produces: `QUEUE_DICOM_INGESTION` constant (`contract/constants/celery.py`), importable by Task 2's task module and by settings/celery config.

No test for this task (pure config/constants, no behavior to assert beyond "the app boots" — implicitly verified by the full suite run at the end and by Task 2's test importing the task module).

- [ ] **Step 1: Add the queue constant**

`contract/constants/celery.py` — add one line:

```python
QUEUE_OCR = "ocr"
QUEUE_EMAIL = "email"
QUEUE_GET_CONSENTS = "getConsents"
QUEUE_CALCULATE_CONSENT_STATISTICS = "calculateConsentStatistics"
QUEUE_DICOM_INGESTION = "dicomIngestion"
```

- [ ] **Step 2: Register the queue and its time limit in `celery.py`**

`MiqaResearch/celery.py` — full new contents:

```python
import os

from celery import Celery
from kombu import Queue

from contract.constants.celery import (
    QUEUE_CALCULATE_CONSENT_STATISTICS,
    QUEUE_DICOM_INGESTION,
    QUEUE_EMAIL,
    QUEUE_GET_CONSENTS,
    QUEUE_OCR,
)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MiqaResearch.settings')

app = Celery('MiqaResearch')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.conf.task_default_queue = 'mires'
app.conf.task_default_queue_type="quorum"
app.conf.task_default_exchange_type = 'topic'
app.conf.task_queues = (
    Queue(QUEUE_EMAIL, queue_arguments={"x-queue-type": "quorum"}, routing_key="notification.email.#"),
    Queue(QUEUE_CALCULATE_CONSENT_STATISTICS, queue_arguments={"x-queue-type": "quorum"},
          routing_key="data.calculate.consent_statistics.#"),
    Queue(QUEUE_GET_CONSENTS, queue_arguments={"x-queue-type": "quorum"}, routing_key="data.get.consent.#"),
    Queue(QUEUE_OCR, queue_arguments={"x-queue-type": "quorum"}, routing_key="analysis.ocr.#"),
    Queue(QUEUE_DICOM_INGESTION, queue_arguments={"x-queue-type": "quorum"}, routing_key="analysis.dicom.#"),
)
app.conf.broker_transport_options = {'confirm_publish': True}
# Ingestion runs over large folders/S3 prefixes are far more variable in
# duration than this codebase's other tasks. django.tasks' `@task()`
# decorator has no time-limit kwarg (unlike raw Celery `@app.task`, which
# tasks/ocr/__init__.py uses instead) -- so the limit is set here, per-task,
# via Celery's own task_annotations, keyed by the task's dotted Python path.
# Comfortably larger than the 30min MIRES_CELERY_TASK_TIME_LIMIT global default (#103).
DICOM_INGESTION_TASK_SOFT_TIME_LIMIT = 55 * 60
DICOM_INGESTION_TASK_TIME_LIMIT = 60 * 60
app.conf.task_annotations = {
    "MiqaResearch.tasks.dicom_handling.tasks.ingest_dicom_source": {
        "time_limit": DICOM_INGESTION_TASK_TIME_LIMIT,
        "soft_time_limit": DICOM_INGESTION_TASK_SOFT_TIME_LIMIT,
    },
}
app.autodiscover_tasks([
    "MiqaResearch.tasks"
])
```

- [ ] **Step 3: Add the queue to `settings.py`'s task backend config**

`MiqaResearch/settings.py:6-10` — add `QUEUE_DICOM_INGESTION` to the existing import:

```python
from contract.constants.celery import (
    QUEUE_CALCULATE_CONSENT_STATISTICS,
    QUEUE_DICOM_INGESTION,
    QUEUE_EMAIL,
    QUEUE_GET_CONSENTS,
    QUEUE_OCR,
)
```

`MiqaResearch/settings.py:479-484` — add it to `QUEUES`:

```python
TASKS = {
    "default": {
        "BACKEND": "django_tasks_celery.CeleryBackend", # See: https://github.com/oliverhaas/django-tasks-celery
        "QUEUES": ["default", QUEUE_OCR, QUEUE_EMAIL, QUEUE_GET_CONSENTS, QUEUE_CALCULATE_CONSENT_STATISTICS, QUEUE_DICOM_INGESTION],
    }
}
```

- [ ] **Step 4: Commit**

```bash
git add contract/constants/celery.py MiqaResearch/celery.py MiqaResearch/settings.py
git commit -m "DICOM ingestion: register dicomIngestion Celery queue (#126)"
```

---

## Task 2: `ingest_dicom_source` task wrapper

**Files:**
- Create: `MiqaResearch/tasks/dicom_handling/tasks.py`
- Test: `tests/test_dicom_ingestion_task.py`

**Interfaces:**
- Consumes: `MiqaResearch.tasks.dicom_handling.pipeline.run_ingestion(research_project, source, overwrite_existing=None, delete_originals_after_storage=None) -> IngestionReport` (existing; `IngestionReport.counts -> dict[str, int]`).
- Produces: `ingest_dicom_source` — a `django.tasks.Task` (from `@task(queue_name=QUEUE_DICOM_INGESTION)`), callable two ways: `ingest_dicom_source.func(research_project_id: str, source: str) -> dict[str, int]` (direct call, used by this task's own unit test) and `ingest_dicom_source.enqueue(research_project_id, source) -> TaskResult` (real dispatch, used only by Task 5's concurrency test).

- [ ] **Step 1: Write the failing test**

`tests/test_dicom_ingestion_task.py` (new file):

```python
"""Unit test for the Celery task wrapper around DICOM ingestion (#126).

Calls the task's underlying function directly (`.func(...)`), bypassing
dispatch -- this thin wrapper's only job is id-resolution and counts
extraction, so a plain unit test is enough here; real dispatch is exercised
only by the concurrency scenario in test_dicom_ingestion_performance.py, per
#116's Testing Decisions.
"""
import pytest

from MiqaResearch.data.models import DicomFile, ResearchProject
from MiqaResearch.tasks.dicom_handling.tasks import ingest_dicom_source
from tests.dicom_fixtures import build_ct_image, write_dicom


@pytest.fixture(autouse=True)
def encryption_keys(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="


@pytest.fixture(autouse=True)
def allow_tmp_sources(settings, tmp_path):
    settings.DICOM_ALLOWED_SOURCE_ROOTS = [tmp_path]


@pytest.fixture
def research_project(db):
    return ResearchProject.objects.create(name="Task wrapper project", description="Project for #126 tests")


def test_ingest_dicom_source_ingests_the_file_and_returns_counts(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    src = write_dicom(build_ct_image(), tmp_path / "ct1.dcm")

    counts = ingest_dicom_source.func(str(research_project.id), str(src))

    assert counts == {"ingested": 1, "skipped_duplicate": 0, "duplicate_conflict": 0, "error": 0}
    assert DicomFile.objects.count() == 1


def test_ingest_dicom_source_raises_for_unknown_research_project(db):
    with pytest.raises(ResearchProject.DoesNotExist):
        ingest_dicom_source.func("00000000-0000-0000-0000-000000000000", "s3://irrelevant/prefix")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/test_dicom_ingestion_task.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'MiqaResearch.tasks.dicom_handling.tasks'`

- [ ] **Step 3: Write minimal implementation**

`MiqaResearch/tasks/dicom_handling/tasks.py` (new file):

```python
"""Celery task wrapper around the DICOM ingestion pipeline (#103, #126).

Per #116's Testing Decisions, only the concurrency-focused performance test
(tests/test_dicom_ingestion_performance.py) dispatches this as a real task
onto the actual queue; every other ingestion test calls
`pipeline.run_ingestion` directly. A thin wrapper: id-resolution in, the
run's summary counts out -- the full per-file report never needs to survive
a Celery result round-trip.
"""
from django.tasks import task

from contract.constants.celery import QUEUE_DICOM_INGESTION
from MiqaResearch.data.models import ResearchProject

from .pipeline import run_ingestion


@task(queue_name=QUEUE_DICOM_INGESTION)
def ingest_dicom_source(research_project_id: str, source: str) -> dict[str, int]:
    research_project = ResearchProject.objects.get(pk=research_project_id)
    report = run_ingestion(research_project, source)
    return report.counts
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-sync pytest tests/test_dicom_ingestion_task.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add MiqaResearch/tasks/dicom_handling/tasks.py tests/test_dicom_ingestion_task.py
git commit -m "DICOM ingestion: add ingest_dicom_source task wrapper (#126)"
```

---

## Task 3: `mires_worker_dicom` docker-compose service + shared scratch paths

**Files:**
- Modify: `docker-compose.dev-test.yml`

**Interfaces:**
- Produces: a running Celery worker consuming `dicomIngestion`, and two env-configured absolute paths (`MIRES_DICOM_ALLOWED_SOURCE_ROOTS`, `MIRES_MEDIA_ROOT`) that Task 5's concurrency test must use identically, since that test's dispatched tasks execute inside this container, not inside `mires_testrunner` — a `settings.py`-fixture override in the test process has no effect on this separate process.

No test for this task (infrastructure-only; verified functionally by Task 5's concurrency test, which fails/hangs without a live consumer on `dicomIngestion`).

- [ ] **Step 1: Add the worker service**

`docker-compose.dev-test.yml` — insert a new service after `mires_worker_ocr` (same shape as the other `mires_worker_*` services), and add two env vars scratch-pathing the concurrency test's shared local source/media directories (see Task 5 — `Path(settings.BASE_DIR) / ".dev-data" / "dicom_perf_concurrency"`, which resolves to `/app/.dev-data/dicom_perf_concurrency` inside every container, since all services bind-mount the repo at `/app`):

```yaml
  mires_worker_dicom:
    build:
      context: .
      dockerfile: dev.Dockerfile
    command: sh -c "/tools/celery/start_worker.sh dicomIngestion"
    environment:
      - MIRES_DEBUG=1
      - MIRES_SITE_URL=http://mires_web:8000
      - MIRES_DATABASE_URL=psql://postgres:postgres@mires_db:5432/miqaresearch
      - MIRES_CELERY_BROKER_URL=amqp://miresRabmin:miresRabmin@miresrabbit:5672//
      - MIRES_AUTH_TOKEN=2ac83c66b6affe116e16efc51ef752f583b37c52
      - SET_CELERY_PYTHON_PATH=1
      - MIRES_VAULT_URL=http://mires_vault:8200
      - MIRES_VAULT_TOKEN=AVeryUnsecretSecret
      # Shared with mires_testrunner's dicom concurrency perf test (#126) --
      # both processes must agree on these paths, since the task this worker
      # runs executes in *this* container, not the test process.
      - MIRES_DICOM_ALLOWED_SOURCE_ROOTS=/app/.dev-data/dicom_perf_concurrency
      - MIRES_MEDIA_ROOT=/app/.dev-data/dicom_perf_concurrency/media
    depends_on:
      - mires_web
      - mires_db
      - mires_rabbit
      - mires_vault
    volumes:
      - ./:/app
    networks:
      - mires
    restart: unless-stopped
```

- [ ] **Step 2: Add matching env vars to `mires_testrunner` and make it depend on the new worker**

`docker-compose.dev-test.yml`'s `mires_testrunner` service — add the same two env vars (so the test process's own path construction via `settings.BASE_DIR` lines up byte-for-byte with the worker's) and add `mires_worker_dicom` to `depends_on`:

```yaml
  mires_testrunner:
    build:
      context: .
      dockerfile: dev.Dockerfile
    container_name: mires_testrunner
    environment:
      - MIRES_DEBUG=1
      - MIRES_SECRET_KEY=pf*3@8!@!8dtx%p)51_*sl*-5+fk)8ei^pq)j1$tcr$qm(j#q!
      - MIRES_DATABASE_URL=psql://postgres:postgres@mires_db:5432/miqaresearch
      - MIRES_ALLOWED_HOSTS=*
      - MIRES_CELERY_BROKER_URL=amqp://miresRabmin:miresRabmin@miresrabbit:5672//
      - MIRES_USE_VAULT=1
      - MIRES_VAULT_URL=http://mires_vault:8200
      - MIRES_VAULT_TOKEN=AVeryUnsecretSecret
      - MIRES_DICOM_ALLOWED_SOURCE_ROOTS=/app/.dev-data/dicom_perf_concurrency
      - MIRES_MEDIA_ROOT=/app/.dev-data/dicom_perf_concurrency/media
    command: sh -c "pytest --plus-profile=ci"
    networks:
      - mires
    depends_on:
      - mires_rabbit
      - mires_db
      - mires_fs
      - mires_vault
      - mires_worker_dicom
    volumes:
      - ./:/app
```

- [ ] **Step 3: Commit**

```bash
git add docker-compose.dev-test.yml
git commit -m "DICOM ingestion: add mires_worker_dicom service for real task dispatch (#126)"
```

---

## Task 4: Throughput benchmark — many small files (AC #1)

**Files:**
- Create: `tests/test_dicom_ingestion_performance.py`

**Interfaces:**
- Consumes: `run_ingestion` (Task-agnostic, existing), `build_ct_image`/`write_dicom` (existing, `tests/dicom_fixtures.py`).

A measured local baseline (Postgres via `docker-compose.dev-test.yml`'s `mires_db`, 200 files, single run) came in at **40.6 files/sec** (24.65ms/file). The threshold below asks for **≥15 files/sec** — roughly 2.7x headroom under that baseline, to absorb slower CI hardware without becoming flaky, while still catching a real regression (e.g. an accidental per-file N+1 query).

- [ ] **Step 1: Write the failing test**

`tests/test_dicom_ingestion_performance.py` (new file — this step's content; Tasks 5 and 6 append to it):

```python
"""Performance/load test suite for DICOM ingestion (#126).

Three scenarios, each long_running and excluded from the default test run
(pyproject.toml's `-m 'not ... and not long_running ...'`, added by #104):
many small files (throughput), one very large file/series (S3 backend), and
concurrent runs (real task dispatch, #116's one deliberate exception to
"call run_ingestion directly"). All against fully synthetic data.
"""
import itertools
import os

import boto3
import pytest

from MiqaResearch.data.models import DicomFile, ResearchProject
from MiqaResearch.tasks.dicom_handling.pipeline import run_ingestion
from tests.dicom_fixtures import build_ct_image, build_wsi, write_dicom


@pytest.fixture(autouse=True)
def encryption_keys(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="


@pytest.mark.long_running
def test_throughput_many_small_files_meets_acceptance_threshold(benchmark, settings, tmp_path, db):
    """AC #1: many small synthetic files, explicit throughput threshold."""
    settings.DICOM_ALLOWED_SOURCE_ROOTS = [tmp_path]
    settings.MEDIA_ROOT = tmp_path / "media"
    files_per_round = 200
    acceptance_files_per_second = 15  # see plan doc: measured baseline 40.6/sec, ~2.7x headroom

    project_counter = itertools.count()

    def setup():
        n = next(project_counter)
        project = ResearchProject.objects.create(name=f"Throughput perf project {n}", description="Project for #126 throughput test")
        folder = tmp_path / f"batch-{n}"
        for i in range(files_per_round):
            write_dicom(
                build_ct_image(
                    patient_id=f"P-PERF-{n}-{i}",
                    study_instance_uid=f"1.2.9999.126.1.{n}.{i}.1",
                    series_instance_uid=f"1.2.9999.126.1.{n}.{i}.2",
                    sop_instance_uid=f"1.2.9999.126.1.{n}.{i}.3",
                ),
                folder / f"file-{i}.dcm",
            )
        return (project, folder), {}

    def run(project, folder):
        return run_ingestion(project, folder)

    report = benchmark.pedantic(run, setup=setup, rounds=3, iterations=1)

    assert report.counts["ingested"] == files_per_round
    mean_seconds_per_round = benchmark.stats.stats.mean
    assert mean_seconds_per_round > 0
    files_per_second = files_per_round / mean_seconds_per_round
    assert files_per_second >= acceptance_files_per_second, (
        f"throughput {files_per_second:.1f} files/sec below the {acceptance_files_per_second}/sec threshold"
    )
```

- [ ] **Step 2: Run test to verify it fails for the right reason**

Run: `uv run --no-sync pytest tests/test_dicom_ingestion_performance.py -v -m long_running`
Expected: at this point the test should actually PASS (nothing new is required of production code — `run_ingestion` and the fixture builders already exist). Confirm this by running it and reading the printed throughput; if it fails, the failure must be the *threshold* assertion (a real regression signal), never an import/attribute error. This is the TDD "red" step in spirit — since no new production code is introduced by this task, "red" here means confirming the test can genuinely fail (temporarily lower `acceptance_files_per_second` to something unreachable, e.g. `100000`, rerun to see it fail, then restore `15`).

- [ ] **Step 3: Run test to verify it passes at the real threshold**

Run: `uv run --no-sync pytest tests/test_dicom_ingestion_performance.py -v -m long_running`
Expected: PASS (1 passed)

- [ ] **Step 4: Commit**

```bash
git add tests/test_dicom_ingestion_performance.py
git commit -m "DICOM ingestion: throughput benchmark for many small files (#126)"
```

---

## Task 5: Large-file/S3 benchmark (AC #2)

**Files:**
- Modify: `tests/test_dicom_ingestion_performance.py` (append)

**Interfaces:**
- Consumes: `run_ingestion`, `build_wsi`/`write_dicom` (existing), same real-RustFS settings pattern as `tests/test_dicom_storage_backend.py::test_real_multipart_upload_round_trip_against_rustfs`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_dicom_ingestion_performance.py`:

```python
@pytest.mark.long_running
def test_large_series_via_s3_backend_meets_acceptance_threshold(benchmark, settings, tmp_path, db):
    """AC #2: one very large synthetic file/series, ingested through the real
    S3-compatible backend (RustFS, docker-compose.dev-test.yml's mires_fs --
    same real-backend precedent as test_dicom_storage_backend.py's
    long_running multipart test), explicit acceptance threshold.
    """
    settings.DICOM_ALLOWED_SOURCE_ROOTS = [tmp_path]
    settings.DICOM_STORAGE_BACKEND = "s3"
    settings.DICOM_S3_BUCKET = "dicom-perf-large-file-test"
    settings.DICOM_S3_ENDPOINT_URL = os.environ.get("MIRES_TEST_DICOM_S3_ENDPOINT_URL", "http://mires_fs:9000")
    settings.DICOM_S3_REGION_NAME = "us-east-1"
    settings.DICOM_S3_ACCESS_KEY_ID = "MiresAccessKey"
    settings.DICOM_S3_SECRET_ACCESS_KEY = "MiresSecretKey"

    client = boto3.client(
        "s3",
        endpoint_url=settings.DICOM_S3_ENDPOINT_URL,
        region_name=settings.DICOM_S3_REGION_NAME,
        aws_access_key_id=settings.DICOM_S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.DICOM_S3_SECRET_ACCESS_KEY,
    )
    if not any(b["Name"] == settings.DICOM_S3_BUCKET for b in client.list_buckets().get("Buckets", [])):
        client.create_bucket(Bucket=settings.DICOM_S3_BUCKET)

    # 512x512 RGB tiles x 32 frames =~ 25MB of PixelData -- comfortably past
    # boto3's 8MB multipart threshold, same rationale as the AC #4 RustFS test.
    large_file = write_dicom(
        build_wsi(tile_rows=512, tile_columns=512, number_of_frames=32),
        tmp_path / "large-slide.dcm",
    )
    acceptance_seconds = 20  # generous for a ~25MB multipart upload over the docker-compose bridge network

    project_counter = itertools.count()

    def setup():
        n = next(project_counter)
        project = ResearchProject.objects.create(name=f"Large-file perf project {n}", description="Project for #126 large-file test")
        return (project, large_file), {}

    def run(project, source):
        return run_ingestion(project, source)

    report = benchmark.pedantic(run, setup=setup, rounds=2, iterations=1)

    assert report.counts["ingested"] == 1
    assert benchmark.stats.stats.mean < acceptance_seconds, (
        f"large-file ingestion took {benchmark.stats.stats.mean:.1f}s, over the {acceptance_seconds}s threshold"
    )
```

- [ ] **Step 2: Run test to verify it fails for the right reason**

Run (requires the dev-test docker-compose stack up, `mires_fs` reachable): `uv run --no-sync pytest tests/test_dicom_ingestion_performance.py::test_large_series_via_s3_backend_meets_acceptance_threshold -v -m long_running`
Expected: as in Task 4 Step 2 — temporarily set `acceptance_seconds = 0` to see it fail on the threshold, then restore `20`.

- [ ] **Step 3: Run test to verify it passes**

Run: same command with `acceptance_seconds = 20` restored.
Expected: PASS (1 passed)

- [ ] **Step 4: Commit**

```bash
git add tests/test_dicom_ingestion_performance.py
git commit -m "DICOM ingestion: large-file/S3 benchmark (#126)"
```

---

## Task 6: Concurrency test — real task dispatch (AC #3)

**Files:**
- Modify: `tests/test_dicom_ingestion_performance.py` (append)

**Interfaces:**
- Consumes: `ingest_dicom_source` (Task 2), `django.tasks.base.TaskResultStatus`, `django.conf.settings.BASE_DIR`.
- Requires: `mires_worker_dicom` (Task 3) live and consuming `dicomIngestion`; this test's local scratch paths must match that worker's `MIRES_DICOM_ALLOWED_SOURCE_ROOTS`/`MIRES_MEDIA_ROOT` exactly (both resolve to `/app/.dev-data/dicom_perf_concurrency` inside the shared bind-mounted `/app`).
- Uses pytest-django's `transactional_db` fixture, not `db` — the default `db` fixture wraps the test in one outer transaction that's rolled back at the end, so a separate process (the worker, on its own DB connection) would never see the `ResearchProject` row this test creates. `transactional_db` commits for real (flushing the affected tables afterward instead), which is required whenever another process must see this test's writes.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_dicom_ingestion_performance.py` (add `time` and `shutil` to the existing imports, plus `from pathlib import Path`, `from django.conf import settings as django_settings`, `from django.tasks.base import TaskResultStatus`, `from MiqaResearch.tasks.dicom_handling.tasks import ingest_dicom_source`):

```python
import shutil
import time
from pathlib import Path

from django.conf import settings as django_settings
from django.tasks.base import TaskResultStatus

from MiqaResearch.tasks.dicom_handling.tasks import ingest_dicom_source

# ... (existing imports/fixtures/tests above stay as-is)


@pytest.mark.long_running
def test_concurrent_ingestion_runs_via_real_task_dispatch_complete_correctly_and_within_threshold(settings, transactional_db):
    """AC #3: concurrent ingestion dispatched as real tasks on the actual
    queue (#116's one deliberate exception to calling run_ingestion
    directly) -- not in-process calls.

    Requires a live mires_worker_dicom consuming `dicomIngestion` (see
    docker-compose.dev-test.yml). The scratch source/media paths below must
    match that worker's MIRES_DICOM_ALLOWED_SOURCE_ROOTS/MIRES_MEDIA_ROOT
    env vars exactly -- this test's own settings overrides only apply in
    *this* process; the dispatched task runs inside the worker container.
    """
    # Undo tests/conftest.py's autouse dummy-backend override so this run
    # actually goes through django_tasks_celery.CeleryBackend.
    settings.TASKS = {
        **settings.TASKS,
        "default": {**settings.TASKS["default"], "BACKEND": "django_tasks_celery.CeleryBackend"},
    }
    scratch_root = Path(django_settings.BASE_DIR) / ".dev-data" / "dicom_perf_concurrency"
    settings.DICOM_ALLOWED_SOURCE_ROOTS = [scratch_root]
    settings.MEDIA_ROOT = scratch_root / "media"
    settings.DICOM_STORAGE_BACKEND = "local"

    shutil.rmtree(scratch_root, ignore_errors=True)
    scratch_root.mkdir(parents=True, exist_ok=True)
    try:
        project = ResearchProject.objects.create(name="Concurrency perf project", description="Project for #126 concurrency test")
        run_count = 4
        files_per_run = 10
        acceptance_seconds = 60  # generous: dispatch + queue + worker pickup + ingest + result round-trip, over docker-compose

        sources = []
        for run in range(run_count):
            folder = scratch_root / f"run-{run}"
            for i in range(files_per_run):
                write_dicom(
                    build_ct_image(
                        patient_id=f"P-CONC-{run}-{i}",
                        study_instance_uid=f"1.2.9999.126.3.{run}.{i}.1",
                        series_instance_uid=f"1.2.9999.126.3.{run}.{i}.2",
                        sop_instance_uid=f"1.2.9999.126.3.{run}.{i}.3",
                    ),
                    folder / f"file-{i}.dcm",
                )
            sources.append(str(folder))

        start = time.monotonic()
        task_results = [ingest_dicom_source.enqueue(str(project.id), source) for source in sources]

        deadline = start + acceptance_seconds
        while not all(result.is_finished for result in task_results) and time.monotonic() < deadline:
            time.sleep(0.5)
            for result in task_results:
                if not result.is_finished:
                    result.refresh()
        elapsed = time.monotonic() - start

        assert all(result.is_finished for result in task_results), "not every dispatched run finished before the deadline"
        assert all(result.status == TaskResultStatus.SUCCESSFUL for result in task_results), [
            (r.id, r.status, r.errors) for r in task_results
        ]
        assert elapsed < acceptance_seconds, f"{run_count} concurrent runs took {elapsed:.1f}s, over the {acceptance_seconds}s threshold"

        for result in task_results:
            assert result.return_value == {
                "ingested": files_per_run, "skipped_duplicate": 0, "duplicate_conflict": 0, "error": 0,
            }
        assert DicomFile.objects.filter(research_project=project).count() == run_count * files_per_run
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)
```

`DicomFile.research_project` is a direct FK (`MiqaResearch/data/models/dicom_file.py`) — no need to traverse `series__study__study_participant`.

- [ ] **Step 2: Run test to verify it fails for the right reason**

Run (requires the dev-test docker-compose stack up, including the new `mires_worker_dicom`): `uv run --no-sync pytest tests/test_dicom_ingestion_performance.py::test_concurrent_ingestion_runs_via_real_task_dispatch_complete_correctly_and_within_threshold -v -m long_running`
Expected: before Task 2/3 exist, this fails with `ModuleNotFoundError`/connection errors. Once Tasks 2-3 are in place but before this step, it should reach the polling loop — confirm the "red" case for this specific test by pointing `ingest_dicom_source.enqueue` at a queue nothing consumes (e.g. temporarily lower `acceptance_seconds` to `2`) to see the deadline assertion fail, then restore `60`.

- [ ] **Step 3: Run test to verify it passes**

Run: same command with `acceptance_seconds = 60` restored, full docker-compose dev-test stack up.
Expected: PASS (1 passed)

- [ ] **Step 4: Commit**

```bash
git add tests/test_dicom_ingestion_performance.py
git commit -m "DICOM ingestion: concurrency test via real task dispatch (#126)"
```

---

## Task 7: Full verification pass

- [ ] **Step 1: Typecheck** (if the repo has a configured type checker — check `pyproject.toml`/`Makefile` for a `mypy`/`pyright` target; run it if one exists).

- [ ] **Step 2: Run each new test file individually**

```bash
uv run --no-sync pytest tests/test_dicom_ingestion_task.py -v
uv run --no-sync pytest tests/test_dicom_ingestion_performance.py -v -m long_running
```

- [ ] **Step 3: Run the full default suite once** (excludes `long_running`/`ocr`/`vlm` per `pyproject.toml`'s `addopts` — do not override `-m` here, and do not add `ocr`-marked tests per AGENTS.md since OCR code isn't touched by this work)

```bash
uv run --no-sync pytest
```

Expected: all pass, no new failures, no new warnings introduced by this work (the pre-existing `pydicom` VR-format warnings from other DICOM tests are out of scope).

- [ ] **Step 4: `/code-review` the branch, then close out**

Run `/code-review` against the base commit this work started from. Address any findings, then `gh issue comment 126` with a summary and `gh issue close 126`.
