"""SamtyckenUmu consent task (#241): fetches the export and writes it, untouched, into the consent
upload bucket. Processing is the ETL Binding's job (native "CSV -> participant consent" script)."""
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

from MiqaResearch.data.models import ParticipantConsent, StudyParticipant
from MiqaResearch.tasks.consent.participant_consent import fetch_participant_consent

BUCKET = "consent-incoming"


@pytest.fixture(autouse=True)
def consent_upload_settings(settings):
    settings.ETL_S3_ENDPOINT_URL = None
    settings.ETL_S3_REGION_NAME = "us-east-1"
    settings.ETL_S3_ACCESS_KEY_ID = "testing"
    settings.ETL_S3_SECRET_ACCESS_KEY = "testing"
    settings.TASK_CONSENT_UPLOAD_BUCKET = BUCKET
    settings.TASK_CONSENT_UPLOAD_PREFIX = "samtycken/"


@pytest.fixture
def s3():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client


@pytest.fixture(scope="module")
def consent_csv(example_data_main_dir: Path) -> bytes:
    return (example_data_main_dir / "participant_consent/consents_example.csv").read_bytes()


def _api_returns(mock_get_csv_data, status_code: int, content: bytes = b""):
    response = MagicMock()
    response.status_code = status_code
    response.content = content
    response.text = content.decode()
    mock_get_csv_data.return_value = response


def _keys(s3) -> list[str]:
    return [obj["Key"] for obj in s3.list_objects_v2(Bucket=BUCKET).get("Contents", ())]


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@patch("MiqaResearch.tasks.consent.participant_consent._get_access_token", return_value="fake-token")
@patch("MiqaResearch.tasks.consent.participant_consent._get_csv_data")
async def test_fetch_participant_consent_writes_the_export_unchanged_under_prefix_form_id_and_utc_timestamp(
        mock_get_csv_data, _mock_token, s3, consent_csv: bytes):
    _api_returns(mock_get_csv_data, 200, consent_csv)

    with patch("django.utils.timezone.now", return_value=datetime(2026, 10, 6, 7, 30, 15, tzinfo=UTC)):
        result = await fetch_participant_consent.acall(form_id="form-42")

    assert _keys(s3) == ["samtycken/form-42/20261006T073015Z.csv"]
    assert s3.get_object(Bucket=BUCKET, Key="samtycken/form-42/20261006T073015Z.csv")["Body"].read() == consent_csv
    assert result == f"s3://{BUCKET}/samtycken/form-42/20261006T073015Z.csv"


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@patch("MiqaResearch.tasks.consent.participant_consent._get_access_token", return_value="fake-token")
@patch("MiqaResearch.tasks.consent.participant_consent._get_csv_data")
async def test_fetch_participant_consent_does_not_touch_the_database(
        mock_get_csv_data, _mock_token, s3, consent_csv: bytes):
    _api_returns(mock_get_csv_data, 200, consent_csv)

    await fetch_participant_consent.acall(form_id="form-42")

    assert await StudyParticipant.objects.acount() == 0
    assert await ParticipantConsent.objects.acount() == 0


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("status_code, message", [
    (400, "HTTP 400"), (401, "HTTP 401"), (404, "Form form-42 not found"), (500, "HTTP 500"),
])
@patch("MiqaResearch.tasks.consent.participant_consent._get_access_token", return_value="fake-token")
@patch("MiqaResearch.tasks.consent.participant_consent._get_csv_data")
async def test_fetch_participant_consent_uploads_nothing_when_the_api_fails(
        mock_get_csv_data, _mock_token, status_code, message, s3):
    _api_returns(mock_get_csv_data, status_code)

    with pytest.raises(Exception, match=message):
        await fetch_participant_consent.acall(form_id="form-42")

    assert _keys(s3) == []


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@patch("MiqaResearch.tasks.consent.participant_consent._get_access_token")
@patch("MiqaResearch.tasks.consent.participant_consent._get_csv_data")
async def test_fetch_participant_consent_fails_before_fetching_when_no_upload_bucket_is_configured(
        mock_get_csv_data, mock_get_access_token, settings):
    settings.TASK_CONSENT_UPLOAD_BUCKET = None

    with pytest.raises(ValueError, match="MIRES_TASK_CONSENT_UPLOAD_BUCKET"):
        await fetch_participant_consent.acall(form_id="form-42")

    mock_get_access_token.assert_not_called()
    mock_get_csv_data.assert_not_called()
