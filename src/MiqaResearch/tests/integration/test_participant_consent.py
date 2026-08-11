from pathlib import Path
from typing import Any
from unittest.mock import patch, MagicMock
from uuid import UUID

import polars as pl
import pytest
from django.conf import settings

from MiqaResearch.data.models import StudyParticipant
from MiqaResearch.data.serializers.participant_consent import UploadConsentSchema
from MiqaResearch.tasks.participant_consent import fetch_participant_consent, _process_consent_data


@pytest.fixture(autouse=True)
def mock_encryption_keys(settings):
    settings.FERNET_KEY = b'EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc='
    settings.SENSITIVE_DATA_HASH_KEY = 'H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA='


@pytest.fixture(scope="module")
def participant_consent_data(example_data_main_dir: Path) -> pl.DataFrame:
    return pl.read_csv(example_data_main_dir / "participant_consent/consents_example.csv")


@pytest.mark.django_db
@patch("MiqaResearch.tasks.participant_consent._get_access_token")
@patch("MiqaResearch.tasks.participant_consent._get_csv_data")
def test_fetch_participant_consent_should_generate_study_ids_for_new_study_participants(
        mock_get_csv_data, mock_get_access_token, participant_consent_data: pl.DataFrame):
    # Arrange
    mock_get_access_token.return_value = "fake-token"
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = participant_consent_data.write_csv()
    mock_get_csv_data.return_value = mock_response

    # Act
    fetch_participant_consent(form_id="test-form")

    # Assert
    # Check that study participants were created
    # The example data has some unique participants.
    pid_list = participant_consent_data.get_column(settings.TASK_CONSENT_FORM_COL_PID).str.replace_all("-", "").to_list()
    unique_pids = set(pid_list)

    assert StudyParticipant.objects.count() == len(unique_pids)
    for pid in unique_pids:
        assert StudyParticipant.objects.filter_by_person_source_value_list([pid]).exists()


@pytest.mark.django_db
@patch("MiqaResearch.tasks.participant_consent._get_access_token")
@patch("MiqaResearch.tasks.participant_consent._get_csv_data")
def test_fetch_participant_consent_should_encrypt_participant_ids_and_names(
        mock_get_csv_data, mock_get_access_token, participant_consent_data: pl.DataFrame):
    # Arrange
    mock_get_access_token.return_value = "fake-token"
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = participant_consent_data.write_csv()
    mock_get_csv_data.return_value = mock_response

    # Act
    fetch_participant_consent(form_id="test-form")

    # Assert
    # Verify encryption by checking if we can retrieve them by PID (which uses hashing)
    # and that the name is correctly decrypted when accessed.
    for row in participant_consent_data.iter_rows(named=True):
        pid = row[settings.TASK_CONSENT_FORM_COL_PID].replace("-", "")
        name = row[settings.TASK_CONSENT_FORM_COL_NAME]

        participant = StudyParticipant.objects.filter_by_person_source_value_list([pid]).first()
        assert participant is not None
        assert participant.name == name
        assert participant.person_source_value == pid


@pytest.mark.django_db
@patch("MiqaResearch.tasks.participant_consent._get_access_token")
@patch("MiqaResearch.tasks.participant_consent._get_csv_data")
def test_fetch_participant_consent_should_update_existing_consent_data(
        mock_get_csv_data, mock_get_access_token, participant_consent_data: pl.DataFrame):
    # Arrange
    mock_get_access_token.return_value = "fake-token"

    # Pre-create one participant
    first_row = participant_consent_data.row(0, named=True)
    first_pid = first_row[settings.TASK_CONSENT_FORM_COL_PID].replace("-", "")
    first_name = first_row[settings.TASK_CONSENT_FORM_COL_NAME]
    existing_participant = StudyParticipant.objects.create(
        person_source_value=first_pid,
        name=first_name,
        alias1="OLD_ALIAS"
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = participant_consent_data.write_csv()
    mock_get_csv_data.return_value = mock_response

    # Act
    fetch_participant_consent(form_id="test-form")

    # Assert
    # Verify that the existing participant was NOT re-created (still has old alias)
    # and others were created.
    updated_participant = StudyParticipant.objects.filter_by_person_source_value_list([first_pid]).first()
    assert updated_participant.id == existing_participant.id
    assert updated_participant.alias1 == "OLD_ALIAS"

    pid_list = participant_consent_data.get_column(settings.TASK_CONSENT_FORM_COL_PID).str.replace_all("-", "").to_list()
    unique_pids = set(pid_list)
    assert StudyParticipant.objects.count() == len(unique_pids)


@pytest.mark.django_db
def test__process_consent_data_should_reformat_consent_data_into_list_of_UploadConsentSchema_formatted_dicts(
        participant_consent_data: pl.DataFrame):
    # Arrange

    # Act
    result = _process_consent_data(participant_consent_data)

    # Assert
    assert isinstance(result, list)
    assert all(isinstance(item, dict) for item in result)

    def _is_valid_upload_consent_entry(entry: dict[str, Any]) -> bool:
        try:
            _ = UploadConsentSchema(**entry)
            return True
        except Exception as e:
            print(e)
            return False

    assert all(_is_valid_upload_consent_entry(entry) for entry in result)


@pytest.mark.django_db
def test__process_consent_data_should_replace_personal_identifiers_with_participant_study_ids(
        participant_consent_data: pl.DataFrame):
    # Arrange
    def is_valid_uuid7(value: str) -> bool:
        try:
            _ = UUID(value, version=7)
            return True
        except Exception as e:
            return False

    # Act
    result = _process_consent_data(participant_consent_data)

    # Assert
    assert all((pid := entry.get("participant_study_id")) is not None and is_valid_uuid7(str(pid)) for entry in result)