from pathlib import Path
from typing import Any

import polars as pl
import pytest

from MiqaResearch.data.serializers.participant_consent import UploadConsentSchema
from MiqaResearch.tasks.participant_consent import fetch_participant_consent, _process_consent_data


@pytest.fixture(scope="module")
def participant_consent_data(example_data_main_dir: Path) -> pl.DataFrame:
    return pl.read_csv(example_data_main_dir / "participant_consent/consents_example.csv")


def test_fetch_participant_consent_should_generate_study_ids_for_new_study_participants(
        participant_consent_data: pl.DataFrame):
    pass


def test_fetch_participant_consent_should_encrypt_participant_ids_and_names(participant_consent_data: pl.DataFrame):
    pass


def test_fetch_participant_consent_should_update_existing_consent_data(participant_consent_data: pl.DataFrame):
    pass


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