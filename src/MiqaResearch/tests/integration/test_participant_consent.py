from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID

import polars as pl
import pytest
from django.conf import settings

from MiqaResearch.data.models import Clinic, ParticipantConsent, ParticipantConsentType, StudyParticipant
from MiqaResearch.data.serializers.participant_consent import UploadConsentSchema
from MiqaResearch.tasks.consent.participant_consent import (
    _handle_fetched_data,
    _process_consent_data,
    fetch_participant_consent,
)


@pytest.fixture(autouse=True)
def mock_encryption_keys(settings):
    settings.FERNET_KEY = b'EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc='
    settings.SENSITIVE_DATA_HASH_KEY = 'H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA='


@pytest.fixture(autouse=True)
def mock_task_consent_research_project(settings):
    settings.TASK_CONSENT_RESEARCH_PROJECT_NAME = "test-consent-research-project"


@pytest.fixture(scope="module")
def participant_consent_data(example_data_main_dir: Path) -> pl.DataFrame:
    return pl.read_csv(example_data_main_dir / "participant_consent/consents_example.csv")

@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@patch("MiqaResearch.tasks.consent.participant_consent._get_access_token")
@patch("MiqaResearch.tasks.consent.participant_consent._get_csv_data")
async def test_fetch_participant_consent_should_generate_study_ids_for_new_study_participants(
        mock_get_csv_data, mock_get_access_token, participant_consent_data: pl.DataFrame):
    # Arrange
    mock_get_access_token.return_value = "fake-token"
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = participant_consent_data.write_csv()
    mock_get_csv_data.return_value = mock_response

    # Act
    result = await fetch_participant_consent.acall(form_id="test-form")

    # Assert
    # Check that study participants were created
    # The example data has some unique participants.
    pid_list = participant_consent_data.get_column(settings.TASK_CONSENT_FORM_COL_PID).str.replace_all("-", "").to_list()
    unique_pids = set(pid_list)

    assert await StudyParticipant.objects.acount() == len(unique_pids)
    for pid in unique_pids:
        assert await StudyParticipant.objects.filter_by_person_source_value_list([pid]).aexists()

@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@patch("MiqaResearch.tasks.consent.participant_consent._get_access_token")
@patch("MiqaResearch.tasks.consent.participant_consent._get_csv_data")
async def test_fetch_participant_consent_should_encrypt_participant_ids_and_names(
        mock_get_csv_data, mock_get_access_token, participant_consent_data: pl.DataFrame):
    # Arrange
    mock_get_access_token.return_value = "fake-token"
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = participant_consent_data.write_csv()
    mock_get_csv_data.return_value = mock_response

    # Act
    result = await fetch_participant_consent.acall(form_id="test-form")

    # Assert
    # Verify encryption by checking if we can retrieve them by PID (which uses hashing)
    # and that the name is correctly decrypted when accessed.
    for row in participant_consent_data.iter_rows(named=True):
        pid = row[settings.TASK_CONSENT_FORM_COL_PID].replace("-", "")
        name = row[settings.TASK_CONSENT_FORM_COL_NAME]

        participant = await StudyParticipant.objects.filter_by_person_source_value_list([pid]).afirst()
        assert participant is not None
        assert participant.name == name
        assert participant.person_source_value == pid


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@patch("MiqaResearch.tasks.consent.participant_consent._get_access_token")
@patch("MiqaResearch.tasks.consent.participant_consent._get_csv_data")
async def test_fetch_participant_consent_should_update_existing_consent_data(
        mock_get_csv_data, mock_get_access_token, participant_consent_data: pl.DataFrame):
    # Arrange
    mock_get_access_token.return_value = "fake-token"

    # Pre-create one participant
    first_row = participant_consent_data.row(0, named=True)
    first_pid = first_row[settings.TASK_CONSENT_FORM_COL_PID].replace("-", "")
    first_name = first_row[settings.TASK_CONSENT_FORM_COL_NAME]
    existing_participant = await StudyParticipant.objects.acreate(
        person_source_value=first_pid,
        name=first_name,
        alias1="OLD_ALIAS"
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = participant_consent_data.write_csv()
    mock_get_csv_data.return_value = mock_response

    # Act
    result = await fetch_participant_consent.acall(form_id="test-form")

    # Assert
    # Verify that the existing participant was NOT re-created (still has old alias)
    # and others were created.
    updated_participant = await StudyParticipant.objects.filter_by_person_source_value_list([first_pid]).afirst()
    assert updated_participant.id == existing_participant.id
    assert updated_participant.alias1 == "OLD_ALIAS"

    pid_list = participant_consent_data.get_column(settings.TASK_CONSENT_FORM_COL_PID).str.replace_all("-", "").to_list()
    unique_pids = set(pid_list)
    assert await StudyParticipant.objects.acount() == len(unique_pids)


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test__process_consent_data_should_reformat_consent_data_into_list_of_UploadConsentSchema_formatted_dicts(
        participant_consent_data: pl.DataFrame):
    # Arrange

    # Act
    result = await _process_consent_data(participant_consent_data)

    # Assert
    assert isinstance(result, list)
    assert all(isinstance(item, UploadConsentSchema) for item in result)


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test__process_consent_data_should_replace_personal_identifiers_with_participant_study_ids(
        participant_consent_data: pl.DataFrame):
    # Arrange
    def is_valid_uuid7(value: str) -> bool:
        try:
            _ = UUID(value, version=7)
            return True
        except Exception as e:
            return False

    # Act
    result = await _process_consent_data(participant_consent_data)

    # Assert
    assert all((pid := entry.participant_study_id) is not None and is_valid_uuid7(str(pid)) for entry in result)


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@patch("MiqaResearch.tasks.consent.participant_consent._get_access_token")
@patch("MiqaResearch.tasks.consent.participant_consent._get_csv_data")
async def test_fetch_participant_consent_should_handle_reconsented_participants_getting_a_new_consent_record(
    mock_get_csv_data, mock_get_access_token):
    # Arrange: one participant that consents, retracts it five days later, then re-consents one day after the
    # retraction. The source system keeps one CSV row per signing event, so the second fetch (the update) exports
    # both the retracted row and the new re-consent row.
    mock_get_access_token.return_value = "fake-token"

    pid = "19900101-1234"
    consent_label_col = "Jag samtycker till att delta i studien"

    def consent_rows(status: str, signed: str, last_updated: str, retracted: str) -> pl.DataFrame:
        return pl.DataFrame({
            settings.TASK_CONSENT_FORM_COL_NAME: ["Rea Consent"],
            settings.TASK_CONSENT_FORM_COL_PID: [pid],
            settings.TASK_CONSENT_FORM_COL_STATUS: [status],
            settings.TASK_CONSENT_FORM_COL_SIGNED: [signed],
            settings.TASK_CONSENT_FORM_COL_LAST_UPDATED: [last_updated],
            settings.TASK_CONSENT_FORM_COL_RETRACTED: [retracted],
            settings.TASK_CONSENT_FORM_COL_CLINIC: ["64001"],
            settings.TASK_CONSENT_FORM_COL_COMMENT: [""],
            consent_label_col: ["Ja"],
        })

    retracted_row = consent_rows("Återtaget", "2026-01-01 09:00", "2026-01-05 10:00", "2026-01-05 10:00")
    reconsent_row = consent_rows("Signerat", "2026-01-06 09:00", "2026-01-06 09:00", "")

    def mock_response_for(csv_content: str) -> MagicMock:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = csv_content
        return mock_response

    # Act: first fetch stores the retracted consent
    mock_get_csv_data.return_value = mock_response_for(retracted_row.write_csv())
    await fetch_participant_consent.acall(form_id="test-form")

    [retracted_consent] = [consent async for consent in ParticipantConsent.objects.all()]
    assert retracted_consent.status == "Återtaget"
    assert retracted_consent.consent_signed_date.date() == date(2026, 1, 1)
    assert retracted_consent.consent_revoked_date is not None
    assert retracted_consent.consent_revoked_date.date() == date(2026, 1, 5)

    # Act: second fetch simulates the update where the participant re-consented one day after retracting
    mock_get_csv_data.return_value = mock_response_for(pl.concat([retracted_row, reconsent_row]).write_csv())
    result = await fetch_participant_consent.acall(form_id="test-form")

    # Assert: the retracted consent record was not updated, a new record was created for the re-consent event
    consents = sorted(
        [consent async for consent in
         ParticipantConsent.objects.filter(study_participant_id=retracted_consent.study_participant_id)],
        key=lambda consent: consent.consent_signed_date,
    )
    assert len(consents) == 2

    previous_consent, reconsent = consents
    assert previous_consent.id == retracted_consent.id
    assert previous_consent.status == "Återtaget"
    assert previous_consent.consent_signed_date.date() == date(2026, 1, 1)
    assert previous_consent.consent_revoked_date is not None
    assert previous_consent.consent_revoked_date.date() == date(2026, 1, 5)

    assert reconsent.id != retracted_consent.id
    assert reconsent.status == "Signerat"
    assert reconsent.consent_signed_date.date() == date(2026, 1, 6)
    assert reconsent.consent_revoked_date is None

    assert result == "Created 1 new consents, updated 1 existing consents."


def _non_standard_columns(consent_data: pl.DataFrame) -> list[str]:
    standard_columns = (
        settings.TASK_CONSENT_FORM_COL_NAME,
        settings.TASK_CONSENT_FORM_COL_PID,
        settings.TASK_CONSENT_FORM_COL_STATUS,
        settings.TASK_CONSENT_FORM_COL_SIGNED,
        settings.TASK_CONSENT_FORM_COL_LAST_UPDATED,
        settings.TASK_CONSENT_FORM_COL_RETRACTED,
        settings.TASK_CONSENT_FORM_COL_CLINIC,
        settings.TASK_CONSENT_FORM_COL_COMMENT,
    )
    return [col for col in consent_data.columns if col not in standard_columns]


def _expected_consent_label_counts(consent_data: pl.DataFrame) -> dict[str, int]:
    non_standard_columns = _non_standard_columns(consent_data)
    counts: dict[str, int] = {}
    for row in consent_data.iter_rows(named=True):
        for col in non_standard_columns:
            if row[col] in settings.TASK_CONSENT_FORM_CONSENTED_TRUE_VALUES:
                label = col.replace('""', '"')
                counts[label] = counts.get(label, 0) + 1
    return counts


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@patch("MiqaResearch.tasks.consent.participant_consent._get_access_token")
@patch("MiqaResearch.tasks.consent.participant_consent._get_csv_data")
async def test_fetch_participant_consent_should_store_a_consent_record_per_consented_label_in_db(
        mock_get_csv_data, mock_get_access_token, participant_consent_data: pl.DataFrame):
    # Arrange
    mock_get_access_token.return_value = "fake-token"
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = participant_consent_data.write_csv()
    mock_get_csv_data.return_value = mock_response

    expected_label_counts = _expected_consent_label_counts(participant_consent_data)
    expected_total_consent_count = sum(expected_label_counts.values())

    # Act
    result = await fetch_participant_consent.acall(form_id="test-form")

    # Assert
    assert await ParticipantConsentType.objects.acount() == len(expected_label_counts)
    assert await ParticipantConsent.objects.acount() == expected_total_consent_count

    # Compare count-per-label as a multiset rather than matching exact label strings, since
    # polars does not CSV-unescape quote characters in header names, and the fixture round-trips
    # the data through write_csv()/read_csv() to simulate the fetched CSV response.
    consent_counts_by_type = sorted([
        await ParticipantConsent.objects.filter(consent_type=consent_type).acount()
        async for consent_type in ParticipantConsentType.objects.all()
    ])
    assert consent_counts_by_type == sorted(expected_label_counts.values())

    assert result == f"Created {expected_total_consent_count} new consents, updated 0 existing consents."


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@patch("MiqaResearch.tasks.consent.participant_consent._get_access_token")
@patch("MiqaResearch.tasks.consent.participant_consent._get_csv_data")
async def test_fetch_participant_consent_should_store_consents_linked_to_correct_participant_and_clinic(
        mock_get_csv_data, mock_get_access_token, participant_consent_data: pl.DataFrame):
    # Arrange
    mock_get_access_token.return_value = "fake-token"
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = participant_consent_data.write_csv()
    mock_get_csv_data.return_value = mock_response

    first_row = participant_consent_data.row(0, named=True)
    first_pid = first_row[settings.TASK_CONSENT_FORM_COL_PID].replace("-", "")
    first_clinic = str(first_row[settings.TASK_CONSENT_FORM_COL_CLINIC])

    # Act
    await fetch_participant_consent.acall(form_id="test-form")

    # Assert
    participant = await StudyParticipant.objects.filter_by_person_source_value_list([first_pid]).afirst()
    consents = [consent async for consent in ParticipantConsent.objects.filter(study_participant=participant)]

    assert len(consents) > 0
    assert all(consent.status == first_row[settings.TASK_CONSENT_FORM_COL_STATUS] for consent in consents)
    for consent in consents:
        clinic = await Clinic.objects.aget(id=consent.clinic_id)
        assert clinic.clinic_name == first_clinic


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@patch("MiqaResearch.tasks.consent.participant_consent._get_access_token")
@patch("MiqaResearch.tasks.consent.participant_consent._get_csv_data")
async def test_fetch_participant_consent_should_not_duplicate_consents_when_run_again_on_unchanged_data(
        mock_get_csv_data, mock_get_access_token, participant_consent_data: pl.DataFrame):
    # Arrange
    mock_get_access_token.return_value = "fake-token"
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = participant_consent_data.write_csv()
    mock_get_csv_data.return_value = mock_response

    expected_total_consent_count = sum(_expected_consent_label_counts(participant_consent_data).values())

    # Act
    await fetch_participant_consent.acall(form_id="test-form")
    second_result = await fetch_participant_consent.acall(form_id="test-form")

    # Assert
    assert await ParticipantConsent.objects.acount() == expected_total_consent_count
    assert second_result == f"Created 0 new consents, updated {expected_total_consent_count} existing consents."


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@patch("MiqaResearch.tasks.consent.participant_consent.create_participant_consents")
async def test__handle_fetched_data_should_log_and_reraise_when_storing_consents_fails(
        mock_create_participant_consents, participant_consent_data: pl.DataFrame, caplog):
    # Arrange
    mock_create_participant_consents.side_effect = RuntimeError("could not reach database")
    csv_content = participant_consent_data.write_csv()

    # Act & Assert
    with pytest.raises(RuntimeError, match="could not reach database"):
        await _handle_fetched_data(csv_content)

    assert "Failed to handle fetched participant consent data" in caplog.text
    assert await ParticipantConsent.objects.acount() == 0