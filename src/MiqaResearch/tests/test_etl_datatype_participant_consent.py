"""The `participant_consent` ETL Datatype (#226): consent rows, one per (participant, consent type,
signed date), loaded all-or-nothing through `load_jsonl`. Unlike `measurement`, consent is how a
participant enters a study, so an unknown `person_source_value` creates the Study Participant in
the Binding's project instead of failing the Job. Consent types are resolved -- and created -- per
project, and a re-imported consent is updated in place so a later revocation reaches the database.
"""
import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from contract.constants.etl import ETL_SCRIPT_ORIGIN_CUSTOM
from helpers.db_fields import get_deterministic_hash
from MiqaResearch.data.models import (
    EtlJob,
    EtlScript,
    EtlScriptVersion,
    ParticipantConsent,
    PipelineBinding,
    ResearchProject,
    StudyParticipant,
)
from MiqaResearch.etl_datatypes import load_jsonl


def _jsonl(*rows: dict) -> str:
    return "\n".join(json.dumps(row) for row in rows)


def _consent_row(**overrides) -> dict:
    row = {
        "person_source_value": "191212121212",
        "name": "Tolvan Tolvansson",
        "consent_type": "Blood samples",
        "consent_signed_date": "2026-03-01T10:00:00+01:00",
        "status": "Signerad",
        "consent_revoked_date": None,
        "clinic_code": "K-01",
        "participant_information_version": "v2",
        "source": "SamtyckenUmu",
    }
    row.update(overrides)
    return row


@pytest.fixture(autouse=True)
def mock_encryption_keys(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="


@pytest.fixture(autouse=True)
def _media_root(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def research_project(db):
    return ResearchProject.objects.create(name="Consent ETL project", description="")


def _make_etl_job(project: ResearchProject, prefix: str) -> EtlJob:
    script = EtlScript.objects.create(
        name="Consent import", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project, datatype_name="participant_consent")
    script_version = EtlScriptVersion.objects.create(
        script=script, version=1, source=SimpleUploadedFile("script.py", b"# unused"), sha256="0" * 64)
    binding = PipelineBinding.objects.create(
        project=project, source_bucket="incoming", source_prefix=prefix, script_version=script_version,
        raw_bucket="raw", raw_prefix=prefix)
    return EtlJob.objects.create(binding=binding, script_version=script_version)


@pytest.fixture
def etl_job(research_project):
    return _make_etl_job(research_project, "consent/")


def _load(project, etl_job, *rows):
    return load_jsonl(
        datatype_name="participant_consent", project=project, etl_job=etl_job, jsonl_text=_jsonl(*rows))


@pytest.mark.django_db
def test_a_consent_for_an_unknown_person_creates_the_participant_in_the_bindings_project(research_project, etl_job):
    result = _load(research_project, etl_job, _consent_row())

    participant = StudyParticipant.objects.get(
        person_source_value_hash=get_deterministic_hash("191212121212"))
    assert participant.research_project_id == research_project.id
    assert participant.name == "Tolvan Tolvansson"
    assert participant.alias1  # a generated pseudonym, never the personnummer
    consent = ParticipantConsent.objects.get(study_participant=participant)
    assert consent.consent_type.label == "Blood samples"
    assert consent.consent_type.research_project_id == research_project.id
    assert consent.clinic.clinic_code == "K-01"
    assert consent.status == "Signerad"
    assert result.created == 1


@pytest.mark.django_db
def test_each_project_gets_its_own_consent_type_for_the_same_label(research_project, etl_job):
    other_project = ResearchProject.objects.create(name="Other consent project", description="")
    other_job = _make_etl_job(other_project, "other-consent/")

    _load(research_project, etl_job, _consent_row())
    _load(other_project, other_job, _consent_row())

    types = {consent.consent_type.research_project_id for consent in ParticipantConsent.objects.all()}
    assert types == {research_project.id, other_project.id}


@pytest.mark.django_db
def test_a_re_imported_consent_is_updated_in_place_so_a_revocation_is_recorded(research_project, etl_job):
    _load(research_project, etl_job, _consent_row())

    result = _load(research_project, etl_job, _consent_row(
        status="Återtaget", consent_revoked_date="2026-05-01T09:00:00+02:00"))

    consent = ParticipantConsent.objects.get()
    assert consent.status == "Återtaget"
    assert consent.consent_revoked_date.isoformat() == "2026-05-01T07:00:00+00:00"
    assert (result.created, result.updated) == (0, 1)


@pytest.mark.django_db
def test_an_existing_participant_in_the_project_is_reused(research_project, etl_job):
    existing = StudyParticipant.objects.create(
        alias1="Known-Otter", person_source_value="191212121212", name="Known Name", research_project=research_project)

    _load(research_project, etl_job, _consent_row(name="Different Name"))

    assert StudyParticipant.objects.count() == 1
    assert ParticipantConsent.objects.get().study_participant_id == existing.id


@pytest.mark.django_db
def test_one_bad_row_rolls_back_the_whole_batch_including_new_participants(research_project, etl_job):
    from MiqaResearch.etl_datatypes import EtlRowError

    bad_row = _consent_row(person_source_value="199001011234")
    del bad_row["clinic_code"]

    with pytest.raises(EtlRowError):
        _load(research_project, etl_job, _consent_row(), bad_row)

    assert not StudyParticipant.objects.exists()
    assert not ParticipantConsent.objects.exists()
