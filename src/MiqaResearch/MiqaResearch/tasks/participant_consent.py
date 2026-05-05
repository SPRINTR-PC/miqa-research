from io import StringIO
import logging
from typing import Any

import polars as pl
import requests
from requests import Response

from django.conf import settings

from MiqaResearch.celery import app
from MiqaResearch.settings import TASK_CONSENT_FORM_COL_SIGNED, TASK_CONSENT_FORM_COL_RETRACTED, \
    TASK_CONSENT_FORM_COL_STATUS, TASK_CONSENT_FORM_COL_LAST_UPDATED, TASK_CONSENT_FORM_COL_CLINIC, \
    TASK_CONSENT_FORM_COL_COMMENT, TASK_CONSENT_FORM_COL_PID, TASK_CONSENT_FORM_COL_NAME, \
    TASK_CONSENT_FORM_COL_RESEARCH_PERSON_INFORMATION, TASK_CONSENT_FORM_COL_READ_INFORMATION, \
    TASK_CONSENT_FORM_CONSENTED_TRUE_VALUE
from MiqaResearch.data.models import StudyParticipant

logger = logging.getLogger(__name__)


@app.task()
def fetch_participant_consent(form_id: str, separator: str = ",", from_date: str = None, to_date: str = None):
    """
    - Fetches participant consent from SamtyckenUmu API using ADFS M2M authentication
    - Processes the consent data to replace any participant ID with a study ID
    - Saves the processed consent data to a database or file
    """
    access_token = _get_access_token()

    get_csv_data_response = _get_csv_data(access_token)

    if (status_code := get_csv_data_response.status_code) == 200:
        csv_content = get_csv_data_response.text
        consent_data = pl.read_csv(StringIO(csv_content))
        # TODO: Process the consent data to replace any participant ID with a study ID

        # TODO: Saves the processed consent data to a database or file
        return csv_content
    elif status_code == 400:
        raise Exception("Invalid parameters for CSV export (HTTP 400).")
    elif status_code == 401:
        raise Exception("Access denied (HTTP 401). Check token and ADFS configuration.")
    elif status_code == 404:
        raise Exception(f"Form {form_id} not found (HTTP 404).")
    else:
        raise Exception(f"Unexpected response from CSV export: HTTP {status_code}")


def _get_access_token():
    """Fetches an access token from ADFS for the Consent API authentication."""
    resource = settings.TASK_CONSENT_RESOURCE
    client_id = settings.TASK_CONSENT_CLIENT_ID
    client_secret = settings.TASK_CONSENT_CLIENT_SECRET

    if not all([client_id, client_secret]):
        raise ValueError("SAMTYCKEN_CLIENT_ID or SAMTYCKEN_CLIENT_SECRET is not set in settings.")

    token_data = {
        "grant_type": "client_credentials",
        "resource": resource,
        "client_id": client_id,
        "client_secret": client_secret,
    }

    token_response = requests.post(settings.TASK_CONSENT_ADFS_TOKEN_URL, data=token_data)
    if token_response.status_code != 200:
        raise Exception(f"Failed to get access token: HTTP{token_response.status_code} - {token_response.text}")

    access_token = token_response.json().get("access_token")
    if not access_token:
        raise Exception("Access token missing in ADFS response.")

    return access_token

def _get_csv_data(
        access_token: str, from_date: str | None = None, to_date: str | None = None, separator: str = ",") -> Response:
    base_url = settings.TASK_CONSENT_BASE_URL
    form_id = settings.TASK_CONSENT_FORM_ID
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

    return requests.get(export_url, params=params, headers=headers)


def _process_consent_data(consent_data: pl.DataFrame) -> list[dict[str, Any]]:
    """Processes the consent data to replace any participant ID with a study ID."""
    logger.info(f"Formatting consent data for API endpoint")

    # Get list of normalised participant IDs
    pid_list = (
        consent_data.with_columns(
            pl.col(TASK_CONSENT_FORM_COL_PID).str.replace_all('-', '')
        )).select(TASK_CONSENT_FORM_COL_PID).to_series().unique().to_list()

    participants = StudyParticipant.objects.upsert_study_participant(pid_list)

    standard_columns = (
        TASK_CONSENT_FORM_COL_NAME,
        TASK_CONSENT_FORM_COL_PID,
        TASK_CONSENT_FORM_COL_STATUS,
        TASK_CONSENT_FORM_COL_SIGNED,
        TASK_CONSENT_FORM_COL_LAST_UPDATED,
        TASK_CONSENT_FORM_COL_RETRACTED,
        TASK_CONSENT_FORM_COL_CLINIC,
        TASK_CONSENT_FORM_COL_RESEARCH_PERSON_INFORMATION,
        TASK_CONSENT_FORM_COL_READ_INFORMATION,
        TASK_CONSENT_FORM_COL_COMMENT
    )

    output = [
        {
            "participant_study_id": participants[row["participant_id"]],
            "start_date": row[TASK_CONSENT_FORM_COL_SIGNED],
            "status": row[TASK_CONSENT_FORM_COL_STATUS],
            "last_updated": row[TASK_CONSENT_FORM_COL_LAST_UPDATED],
            "retracted": row[TASK_CONSENT_FORM_COL_RETRACTED],
            "clinic": row[TASK_CONSENT_FORM_COL_CLINIC],
            "comment": row[TASK_CONSENT_FORM_COL_COMMENT],
            "consent_labels": [
                col
                for col in consent_data.columns
                if col not in standard_columns and row[col] == TASK_CONSENT_FORM_CONSENTED_TRUE_VALUE
            ],
        }
        for row in consent_data.iter_rows(named=True)
    ]

    return output
