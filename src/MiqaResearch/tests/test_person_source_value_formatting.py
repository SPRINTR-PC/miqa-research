"""Consent loads and DICOM ingestion format a person's identifier the same way (#241 review), so a
personnummer written with or without its dash, or with stray whitespace, is one Study Participant
in a project whichever path saw the person first.
"""
import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from pydicom.dataset import Dataset

from contract.constants.etl import ETL_SCRIPT_ORIGIN_CUSTOM
from helpers.person_source_value import PersonSourceValueCollision, reformat_stored_person_source_values
from MiqaResearch.data.models import (
    EtlJob,
    EtlScript,
    EtlScriptVersion,
    PipelineBinding,
    ResearchProject,
    StudyParticipant,
)
from MiqaResearch.etl_datatypes import load_jsonl
from MiqaResearch.tasks.dicom_handling.participant import match_or_create_participant

SPELLINGS = ["19121212-1212", "191212121212", " 19121212-1212 "]


@pytest.fixture(autouse=True)
def mock_encryption_keys(settings, tmp_path):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def project(db):
    return ResearchProject.objects.create(name="Consent project", description="")


def _load_consent(project: ResearchProject, person_source_value: str) -> None:
    script = EtlScript.objects.create(
        name="Consent import", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project, datatype_name="participant_consent")
    version = EtlScriptVersion.objects.create(
        script=script, version=1, source=SimpleUploadedFile("script.py", b"# unused"), sha256="0" * 64)
    binding = PipelineBinding.objects.create(
        project=project, source_bucket="incoming", source_prefix="consent/", script_version=version,
        raw_bucket="raw", raw_prefix="consent/")
    row = {
        "person_source_value": person_source_value, "consent_type": "Blood samples",
        "consent_signed_date": "2026-03-01T10:00:00+01:00", "clinic_code": "K-01",
    }
    load_jsonl(
        datatype_name="participant_consent", project=project,
        etl_job=EtlJob.objects.create(binding=binding, script_version=version), jsonl_text=json.dumps(row))


def _ingest_dicom(project: ResearchProject, patient_id: str) -> StudyParticipant:
    dataset = Dataset()
    dataset.PatientID = patient_id
    return match_or_create_participant(dataset, project)


@pytest.mark.django_db
@pytest.mark.parametrize("consent_spelling", SPELLINGS)
@pytest.mark.parametrize("dicom_spelling", SPELLINGS)
def test_dicom_ingestion_matches_the_participant_a_consent_load_created(project, consent_spelling, dicom_spelling):
    _load_consent(project, consent_spelling)

    participant = _ingest_dicom(project, dicom_spelling)

    assert StudyParticipant.objects.filter(research_project=project).count() == 1
    assert participant.person_source_value == "191212121212"


@pytest.mark.django_db
@pytest.mark.parametrize("dicom_spelling", SPELLINGS)
@pytest.mark.parametrize("consent_spelling", SPELLINGS)
def test_a_consent_load_matches_the_participant_dicom_ingestion_created(project, dicom_spelling, consent_spelling):
    _ingest_dicom(project, dicom_spelling)

    _load_consent(project, consent_spelling)

    [participant] = StudyParticipant.objects.filter(research_project=project)
    assert participant.person_source_value == "191212121212"
    assert participant.participantconsent_set.count() == 1


# Existing rows: migration 0026 (format_person_source_values) reformats identifiers stored
# before the shared format existed.

def _stored(alias1: str, person_source_value: str | None, project: ResearchProject | None) -> StudyParticipant:
    return StudyParticipant.objects.create(
        alias1=alias1, person_source_value=person_source_value, research_project=project)


@pytest.mark.django_db
def test_reformatting_makes_a_participant_stored_with_a_dash_matchable_again(project):
    existing = _stored("OLD", " 19121212-1212", project)

    reformat_stored_person_source_values(StudyParticipant)

    assert _ingest_dicom(project, "19121212-1212").id == existing.id
    existing.refresh_from_db()
    assert existing.person_source_value == "191212121212"


@pytest.mark.django_db
def test_reformatting_leaves_participants_without_an_identifier_alone(project):
    empty = _stored("EMPTY", None, project)

    reformat_stored_person_source_values(StudyParticipant)

    empty.refresh_from_db()
    assert empty.person_source_value is None


@pytest.mark.django_db
def test_reformatting_refuses_to_merge_two_participants_of_one_project_and_changes_nothing(project):
    other_project = ResearchProject.objects.create(name="Other", description="")
    _stored("DASHED", "19121212-1212", project)
    _stored("PLAIN", "191212121212", project)
    elsewhere = _stored("ELSEWHERE", "19121212-1212", other_project)

    with pytest.raises(PersonSourceValueCollision, match="DASHED.*PLAIN|PLAIN.*DASHED") as exc_info:
        reformat_stored_person_source_values(StudyParticipant)

    assert "191212121212" not in str(exc_info.value)  # never print the personnummer
    elsewhere.refresh_from_db()
    assert elsewhere.person_source_value == "19121212-1212"
