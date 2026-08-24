import logging
from io import StringIO
from typing import Any

import httpx2
import polars as pl
import requests
from asgiref.sync import sync_to_async
from django.conf import settings
from django.tasks import task
from httpx2 import AsyncClient
from requests import Response

from contract.constants.celery import QUEUE_GET_CONSENTS
from helpers.study_participant_alias import generate_study_participant_alias1_list
from MiqaResearch.data.models import StudyParticipant
from MiqaResearch.settings import (
    TASK_CONSENT_FORM_COL_CLINIC,
    TASK_CONSENT_FORM_COL_COMMENT,
    TASK_CONSENT_FORM_COL_LAST_UPDATED,
    TASK_CONSENT_FORM_COL_NAME,
    TASK_CONSENT_FORM_COL_PID,
    TASK_CONSENT_FORM_COL_RETRACTED,
    TASK_CONSENT_FORM_COL_SIGNED,
    TASK_CONSENT_FORM_COL_STATUS,
    TASK_CONSENT_FORM_CONSENTED_TRUE_VALUES,
)

logger = logging.getLogger("mires")


@task(queue_name=QUEUE_GET_CONSENTS)
async def fetch_participant_consent(form_id: str, separator: str = ",", from_date: str = None, to_date: str = None):
    """
    - Fetches participant consent from SamtyckenUmu API using ADFS M2M authentication
    - Processes the consent data to replace any participant ID with a study ID
    - Saves the processed consent data to a database or file
    """
    async with httpx2.AsyncClient() as client:
        access_token = await _get_access_token(client=client)

        get_csv_data_response = await _get_csv_data(client=client, access_token=access_token, form_id=form_id)

    if (status_code := get_csv_data_response.status_code) == 200:
        csv_content = get_csv_data_response.text
        consent_data = pl.read_csv(StringIO(csv_content))
        processed_consent_data = await _process_consent_data(consent_data)

        # TODO: Saves the processed consent data to a database or file
        return csv_content
    elif status_code == 400:
        msg = "Invalid parameters for CSV export (HTTP 400)."
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
        msg = f"Unexpected response from CSV export: HTTP {status_code}"
        logger.error(msg)
        raise Exception(msg)


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
        client: AsyncClient, access_token: str, form_id: str, from_date: str | None = None, to_date: str | None = None, separator: str = ",") -> Response:
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


async def _process_consent_data(consent_data: pl.DataFrame) -> list[dict[str, Any]]:
    """Processes the consent data to replace any participant ID with a study ID."""
    logger.info(f"Formatting consent data for API endpoint")

    consent_data = consent_data.with_columns(
        pl.col(TASK_CONSENT_FORM_COL_SIGNED).str.to_datetime(format="%Y-%m-%d %H:%M", time_zone=settings.TASK_CONSENT_TIMEZONE),
        pl.col(TASK_CONSENT_FORM_COL_LAST_UPDATED).str.to_datetime(format="%Y-%m-%d %H:%M", time_zone=settings.TASK_CONSENT_TIMEZONE),
        pl.col(TASK_CONSENT_FORM_COL_RETRACTED).str.to_datetime(format="%Y-%m-%d %H:%M", time_zone=settings.TASK_CONSENT_TIMEZONE, strict=False),
    )

    participants = await _get_participant_db_ids(consent_data)

    standard_columns = (
        TASK_CONSENT_FORM_COL_NAME, # Str
        TASK_CONSENT_FORM_COL_PID, # Str
        TASK_CONSENT_FORM_COL_STATUS,  # Str
        TASK_CONSENT_FORM_COL_SIGNED,  # Date Y-m-d H:M
        TASK_CONSENT_FORM_COL_LAST_UPDATED,  # Date Y-m-d H:M
        TASK_CONSENT_FORM_COL_RETRACTED,  # # Date Y-m-d H:M | None
        TASK_CONSENT_FORM_COL_CLINIC,  # Str (id nummer)
        TASK_CONSENT_FORM_COL_COMMENT  # Str
    )

    # Set the source in the extra info field
    extra_info_data = {
        "extra_info": {
            "source": [settings.TASK_CONSENT_SOURCE]
        }
    } if settings.TASK_CONSENT_SOURCE else {
        "extra_info": {}
    }

    output = [
        {
            "participant_study_id": str(participants[row[TASK_CONSENT_FORM_COL_PID].replace("-", "")]),
            "signed_date": row[TASK_CONSENT_FORM_COL_SIGNED],
            "status": row[TASK_CONSENT_FORM_COL_STATUS],
            "last_updated": row[TASK_CONSENT_FORM_COL_LAST_UPDATED],
            "retracted": row[TASK_CONSENT_FORM_COL_RETRACTED],
            "clinic": str(row[TASK_CONSENT_FORM_COL_CLINIC]),
            "comment": row[TASK_CONSENT_FORM_COL_COMMENT],
            "consent_labels": [
                col.replace('""', '"')
                for col in consent_data.columns
                if col not in standard_columns and row[col] in TASK_CONSENT_FORM_CONSENTED_TRUE_VALUES
            ],
        } | extra_info_data
        for row in consent_data.iter_rows(named=True)
    ]

    return output


async def _get_participant_db_ids(consent_data: pl.DataFrame) -> dict[str, str]:
    # Get list of normalised participant IDs
    pid_list = (
        consent_data.with_columns(
            pl.col(TASK_CONSENT_FORM_COL_PID).str.replace_all('-', '')
        )).select(TASK_CONSENT_FORM_COL_PID).to_series().unique().to_list()

    existing_participants = {
        entry["person_source_value"]: entry["id"]
        async for entry in StudyParticipant.objects.filter_by_person_source_value_list(person_source_values=pid_list)
        .values("id", "person_source_value").aiterator()
    }

    new_participant_ids = [psv for psv in pid_list if psv not in existing_participants.keys()]
    new_participant_list = (
        consent_data.with_columns(pl.col(TASK_CONSENT_FORM_COL_PID).str.replace_all('-', ''))
        .filter(pl.col(TASK_CONSENT_FORM_COL_PID).is_in(new_participant_ids))
        .unique(subset=[TASK_CONSENT_FORM_COL_PID])
        .select([TASK_CONSENT_FORM_COL_PID, TASK_CONSENT_FORM_COL_NAME])
        .rows()
    )
    new_aliases = await generate_study_participant_alias1_list(len(new_participant_ids))
    new_participant_objects = await StudyParticipant.objects.abulk_create([
        StudyParticipant(person_source_value=pid, name=participant_name, alias1=alias)
        for (pid, participant_name), alias in zip(new_participant_list, new_aliases)
    ])

    participants = existing_participants | {
        participant.person_source_value: participant.id for participant in new_participant_objects
    }

    return participants
