import os

from celery import Celery
from celery.schedules import crontab
from kombu import Queue

from contract.constants.celery import (
    QUEUE_CALCULATE_CONSENT_STATISTICS,
    QUEUE_DICOM_INGESTION,
    QUEUE_EMAIL,
    QUEUE_ETL_POLL,
    QUEUE_ETL_RUN,
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
    Queue(QUEUE_ETL_POLL, queue_arguments={"x-queue-type": "quorum"}, routing_key="etl.poll.#"),
    Queue(QUEUE_ETL_RUN, queue_arguments={"x-queue-type": "quorum"}, routing_key="etl.run.#"),
)
app.conf.broker_transport_options = {'confirm_publish': True}
# The DICOM backfill tasks re-read every stored file, far longer than this codebase's other
# tasks. django.tasks' `@task()`
# decorator has no time-limit kwarg (unlike raw Celery `@app.task`, which
# tasks/ocr/__init__.py uses instead) -- so the limit is set here, per-task,
# via Celery's own task_annotations, keyed by the task's dotted Python path.
# Comfortably larger than the 30min MIRES_CELERY_TASK_TIME_LIMIT global default.
DICOM_INGESTION_TASK_SOFT_TIME_LIMIT = 55 * 60
DICOM_INGESTION_TASK_TIME_LIMIT = 60 * 60
app.conf.task_annotations = {
    # One-off re-sanitizing of every stored dump (#273) re-reads each file's header
    "MiqaResearch.tasks.dicom_handling.metadata_backfill.resanitize_dicom_metadata": {
        "time_limit": DICOM_INGESTION_TASK_TIME_LIMIT,
        "soft_time_limit": DICOM_INGESTION_TASK_SOFT_TIME_LIMIT,
    },
}
# ETL orchestrator (#162): fan_out_etl_polls is the one Celery-beat-scheduled entry point in the
# codebase so far -- there's no existing django_celery_beat.PeriodicTask precedent to follow, so
# this seeds the DatabaseScheduler's PeriodicTask rows via the static beat_schedule dict, which it
# syncs in on startup (and which stays authoritative for these three entries; an operator editing
# them via /django-admin instead is not expected to persist across a scheduler restart).
from django.conf import settings as _django_settings  # noqa: E402

app.conf.beat_schedule = {
    "etl-fan-out-polls": {
        "task": "MiqaResearch.tasks.etl_orchestrator.tasks.fan_out_etl_polls",
        "schedule": _django_settings.ETL_POLL_INTERVAL_SECONDS,
    },
    "etl-recover-stuck-jobs": {
        "task": "MiqaResearch.tasks.etl_orchestrator.tasks.recover_stuck_etl_jobs",
        "schedule": 60.0,
    },
    "etl-prune-job-logs": {
        "task": "MiqaResearch.tasks.etl_orchestrator.tasks.prune_etl_job_logs",
        "schedule": crontab(hour=2, minute=0),
    },
    "etl-retry-source-cleanup": {
        "task": "MiqaResearch.tasks.etl_orchestrator.tasks.retry_etl_source_cleanup",
        "schedule": 60.0,
    },
    "etl-sweep-orphaned-sandboxes": {
        "task": "MiqaResearch.tasks.etl_orchestrator.tasks.sweep_orphaned_sandboxes",
        "schedule": 300.0,
    },
    "dicom-sweep-orphan-blobs": {
        "task": "MiqaResearch.tasks.dicom_handling.orphan_sweep.sweep_dicom_orphans",
        "schedule": crontab(hour=3, minute=0),
    },
}
app.autodiscover_tasks([
    "MiqaResearch.tasks"
])
