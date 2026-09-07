import logging

from contract.constants.celery import QUEUE_OCR
from MiqaResearch.celery import app
from MiqaResearch.data.models import ParsedPromForm, PromData

from .pipeline import run_pipeline

logger = logging.getLogger(__name__)

# Worst case is the classic path (<=2min/page x up to 10 pages = 20min) plus the
# VLM fallback's own budget ceiling (45min, MIRES_OCR_VLM_FORM_TIMEOUT_SECONDS)
# -- comfortably past the 30min MIRES_CELERY_TASK_TIME_LIMIT global default, so
# this task needs its own, larger limit rather than raising the global one.
OCR_TASK_SOFT_TIME_LIMIT = 70 * 60
OCR_TASK_TIME_LIMIT = 75 * 60


@app.task(queue=QUEUE_OCR, time_limit=OCR_TASK_TIME_LIMIT, soft_time_limit=OCR_TASK_SOFT_TIME_LIMIT)
def run_ocr_on_prom_data(prom_data_id):
    """
    Runs the classic-OCR + VLM-fallback pipeline (docs/prom-ocr-handoff.md)
    on a PromData upload and stores the result as a new ParsedPromForm row.
    """
    try:
        prom_data = PromData.objects.get(id=prom_data_id)
    except PromData.DoesNotExist:
        logger.error(f"PromData with id {prom_data_id} does not exist.")
        return

    try:
        result = run_pipeline(prom_data)
    except Exception:
        logger.exception(f"Error running OCR pipeline on PromData {prom_data_id}")
        return

    ParsedPromForm.objects.create(
        data={"data": result.data, "fieldsOutOfTolerance": result.fields_out_of_tolerance},
        extraction_flags=result.extraction_flags,
        prom_file=prom_data,
        # validated_by and validated_at are left blank until a human reviews it
    )

    logger.info(f"Successfully ran OCR pipeline on PromData {prom_data_id}")
