import asyncio
import logging

import httpx2
import requests
from django.conf import settings
from django.tasks import task
from django.utils import timezone
from httpx2 import AsyncClient
from requests import Response

from contract.constants.celery import QUEUE_GET_CONSENTS
from MiqaResearch.tasks.etl_orchestrator.s3 import build_etl_s3_client

logger = logging.getLogger("mires")


@task(queue_name=QUEUE_GET_CONSENTS)
async def fetch_participant_consent(form_id: str, separator: str = ",", from_date: str = None, to_date: str = None):
    """
    Fetches a SamtyckenUmu consent export (ADFS M2M authentication) and writes it, unchanged, to
    MIRES_TASK_CONSENT_UPLOAD_BUCKET under `_export_key`. The Pipeline Binding on that location
    (native "CSV -> participant consent" script) loads it (#241).
    """
    if not (bucket := settings.TASK_CONSENT_UPLOAD_BUCKET):
        raise ValueError("MIRES_TASK_CONSENT_UPLOAD_BUCKET is not set; nowhere to write the consent export.")

    async with httpx2.AsyncClient() as client:
        access_token = await _get_access_token(client=client)

        get_csv_data_response = await _get_csv_data(
            client=client, access_token=access_token, form_id=form_id,
            from_date=from_date, to_date=to_date, separator=separator)

    if (status_code := get_csv_data_response.status_code) == 200:
        logger.info("Successfully fetched participant consent CSV data from API")
        key = _export_key(form_id)
        await asyncio.to_thread(
            build_etl_s3_client().put_object, Bucket=bucket, Key=key, Body=get_csv_data_response.content)
        uri = f"s3://{bucket}/{key}"
        logger.info(f"Wrote participant consent export to {uri}")
        return uri
    elif status_code == 400:
        msg = "Invalid parameters for CSV fetch (HTTP 400)."
        logger.error(msg)
        raise Exception(msg)
    elif status_code == 401:
        msg = "Access denied (HTTP 401). Check token and ADFS configuration."
        logger.error(msg)
        raise Exception(msg)
    elif status_code == 404:
        msg = f"Form {form_id} not found (HTTP 404)."
        logger.error(msg)
        raise Exception(msg)
    else:
        msg = f"Unexpected response from CSV fetch: HTTP {status_code}"
        logger.error(msg)
        raise Exception(msg)


def _export_key(form_id: str) -> str:
    """The one place the upload key layout is defined: <prefix><form_id>/<UTC timestamp>.csv."""
    return f"{settings.TASK_CONSENT_UPLOAD_PREFIX}{form_id}/{timezone.now():%Y%m%dT%H%M%SZ}.csv"


async def _get_access_token(client: AsyncClient):
    """Fetches an access token from ADFS for the Consent API authentication."""
    resource = settings.TASK_CONSENT_RESOURCE
    client_id = settings.TASK_CONSENT_CLIENT_ID
    client_secret = settings.TASK_CONSENT_CLIENT_SECRET

    if not all([client_id, client_secret]):
        raise ValueError("TASK_CONSENT_CLIENT_ID and/or TASK_CONSENT_CLIENT_SECRET is not set in settings.")

    token_data = {
        "grant_type": "client_credentials",
        "resource": resource,
        "client_id": client_id,
        "client_secret": client_secret,
    }

    async with httpx2.AsyncClient() as client:
        token_response = await client.post(settings.TASK_CONSENT_ADFS_TOKEN_URL, data=token_data)

        access_token = token_response.json

    token_response = requests.post(settings.TASK_CONSENT_ADFS_TOKEN_URL, data=token_data)
    if token_response.status_code != 200:
        raise Exception(f"Failed to get access token: HTTP{token_response.status_code} - {token_response.text}")

    access_token = token_response.json().get("access_token")
    if not access_token:
        raise Exception("Access token missing in ADFS response.")

    return access_token


async def _get_csv_data(
    client: AsyncClient,
    access_token: str,
    form_id: str,
    from_date: str | None = None,
    to_date: str | None = None,
    separator: str = ",",
) -> Response:
    base_url = settings.TASK_CONSENT_BASE_URL
    export_url = f"{base_url}/api/formular/{form_id}/export-csv"

    params = {
        "separator": separator
    }
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    return await client.get(export_url, params=params, headers=headers)
