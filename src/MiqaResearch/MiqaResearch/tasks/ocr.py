import base64
import json
import logging

import httpx
from django.conf import settings
from asgiref.sync import sync_to_async

from MiqaResearch.celery import app
from MiqaResearch.data.models import ParsedPromForm, PromData

logger = logging.getLogger(__name__)

@app.task()
def run_ocr_on_prom_data(prom_data_id):
    """
    Task to run OCR on a PromData entry using Gemma4 model in local Ollama.
    """
    try:
        # Django 5.0+ supports aget for ORM
        prom_data = PromData.objects.aget(id=prom_data_id)
    except PromData.DoesNotExist:
        logger.error(f"PromData with id {prom_data_id} does not exist.")
        return

    try:
        # File operations are blocking, use sync_to_async for safety in async loop
        def read_file():
            with prom_data.prom_form_file.open("rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")

        encoded_file = sync_to_async(read_file)()

        # Prepare the prompt for Gemma3
        prompt = (
            f"Please perform OCR on the attached image/file and extract the data "
            f"according to the template: {json.dumps(prom_data.prom_form_template.template)}. "
            f"Return only the extracted data as a JSON object."
        )

        # Send the task to Ollama
        ollama_url = f"{settings.OLLAMA_URL}/api/generate"
        payload = {
            "model": settings.OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "images": [encoded_file]
        }

        with httpx.Client() as client:
            response = client.post(ollama_url, json=payload, timeout=60.0)
            response.raise_for_status()
            result = response.json()

        extracted_text = result.get("response", "{}")

        try:
            parsed_data = json.loads(extracted_text)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse OCR result as JSON: {extracted_text}")
            parsed_data = {"raw_response": extracted_text}

        # Save the result to ParsedPromForm
        ParsedPromForm.objects.create(
            data=parsed_data,
            prom_file=prom_data,
            # validated_by and validated_at are left blank for now
        )

        logger.info(f"Successfully ran OCR on PromData {prom_data_id}")

    except Exception as e:
        logger.exception(f"Error running OCR on PromData {prom_data_id}: {e}")
