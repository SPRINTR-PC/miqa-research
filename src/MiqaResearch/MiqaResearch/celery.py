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
