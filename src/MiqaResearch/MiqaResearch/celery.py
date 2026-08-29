import os

from celery import Celery
from kombu import Queue

from contract.constants.celery import QUEUE_EMAIL, QUEUE_GET_CONSENTS, QUEUE_OCR

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MiqaResearch.settings')

app = Celery('MiqaResearch')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.conf.task_default_queue = 'mires'
app.conf.task_default_queue_type="quorum"
app.conf.task_default_exchange_type = 'topic'
app.conf.task_queues = (
    Queue(QUEUE_EMAIL, queue_arguments={"x-queue-type": "quorum"}, routing_key="notification.email.#"),
    Queue(QUEUE_GET_CONSENTS, queue_arguments={"x-queue-type": "quorum"}, routing_key="data.get.consent.#"),
    Queue(QUEUE_OCR, queue_arguments={"x-queue-type": "quorum"}, routing_key="analysis.ocr.#"),
)
app.conf.broker_transport_options = {'confirm_publish': True}
app.autodiscover_tasks([
    "MiqaResearch.tasks"
])
