import os

from celery import Celery
from kombu import Queue

from contract.constants.celery import QUEUE_EMAIL, QUEUE_OCR, QUEUE_GET_CONSENTS

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MiqaResearch.settings')

app = Celery('MiqaResearch')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.conf.task_default_queue = 'mires'
app.conf.task_default_exchange_type = 'topic'
app.conf.task_queues = (
    Queue(QUEUE_EMAIL, routing_key="notification.email.#"),
    Queue(QUEUE_GET_CONSENTS, routing_key="data.get.consent.#"),
    Queue(QUEUE_OCR, routing_key="analysis.ocr.#"),
)
app.autodiscover_tasks()