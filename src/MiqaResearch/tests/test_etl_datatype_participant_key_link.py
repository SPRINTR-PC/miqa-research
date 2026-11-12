"""The `participant_key_link` ETL Datatype (#421): a mapping of Participant Key -> Study Participant,
loaded all-or-nothing. Same participant = no-op, different participant fails the Job (log names row
numbers only), re-pointing never happens here. A mapping may arrive before the images. No key values or
identities reach the Job log or audit metadata."""
import json

import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile

from contract.constants.audit_log import (
    EVENT_TYPE_PARTICIPANT_KEY_DEMOGRAPHICS_FILLED,
    EVENT_TYPE_PARTICIPANT_KEY_LINKED,
)
from contract.constants.etl import (
    ETL_SCRIPT_ORIGIN_CUSTOM,
    PIPELINE_BINDING_RAW_RETENTION_DELETE,
    PIPELINE_BINDING_RAW_RETENTION_MOVE,
    default_raw_retention,
)
from contract.constants.participant_key import LINK_VIA_DATATYPE
from helpers.db_fields import get_deterministic_hash
from MiqaResearch.actions.participant_keys import link_study_keys
from MiqaResearch.data.models import (
    AuditLog,
    DicomFile,
    DicomSeries,
    DicomStudy,
    EtlJob,
    EtlScript,
    EtlScriptVersion,
    ParticipantKey,
    PipelineBinding,
    ResearchProject,
    StudyParticipant,
)
from MiqaResearch.etl_datatypes import EtlRowError, load_jsonl
from tests.dicom_fixtures import build_ct_image, write_dicom


@pytest.fixture(autouse=True)
def _settings(settings, tmp_path):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.DICOM_STORAGE_BACKEND = "local"


@pytest.fixture
def project(db):
    return ResearchProject.objects.create(name="Link project", description="d")


def _job(project, config=None, prefix="map/") -> EtlJob:
    script = EtlScript.objects.create(
        name=f"Key link {prefix}", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project,
        datatype_name="participant_key_link")
    version = EtlScriptVersion.objects.create(
        script=script, version=1, source=SimpleUploadedFile("script.py", b"# unused"), sha256="0" * 64)
    binding = PipelineBinding.objects.create(
        project=project, source_bucket="incoming", source_prefix=prefix, script_version=version,
        raw_retention=PIPELINE_BINDING_RAW_RETENTION_DELETE, config=config or {})
    return EtlJob.objects.create(binding=binding, script_version=version, config_snapshot=config or {})


@pytest.fixture
def etl_job(project):
    return _job(project)


def _participant(project, alias, psv=None):
    return StudyParticipant.objects.create(alias1=alias, person_source_value=psv, research_project=project)


def _row(key_value, **ref):
    ref = ref or {"alias1": "A1"}
    return {"key_type": "dicom:PatientID", "key_value": key_value, **ref}


def _load(project, etl_job, *rows):
    return load_jsonl(
        datatype_name="participant_key_link", project=project, etl_job=etl_job,
        jsonl_text="\n".join(json.dumps(r) for r in rows))


def _key(project, value, key_type="dicom:PatientID"):
    return ParticipantKey.objects.get(project=project, key_type=key_type, value_hash=get_deterministic_hash(value))


def test_a_missing_key_is_created_already_linked_by_the_datatype(project, etl_job):
    participant = _participant(project, "A1")

    result = _load(project, etl_job, _row("PSEUDO-1"))

    key = _key(project, "PSEUDO-1")
    assert (result.created, result.updated) == (1, 0)
    assert key.study_participant == participant
    assert key.linked_via == LINK_VIA_DATATYPE
    assert key.linked_job == etl_job
    assert key.linked_at is not None


def test_participant_reference_by_person_source_value(project, etl_job):
    participant = _participant(project, "A1", psv="199001011234")

    _load(project, etl_job, _row("P", person_source_value="19900101-1234"))

    assert _key(project, "P").study_participant == participant


def test_an_existing_unlinked_key_gets_linked(project, etl_job):
    participant = _participant(project, "A1")
    ParticipantKey.objects.create(project=project, key_type="dicom:PatientID", value="P")

    result = _load(project, etl_job, _row("P"))

    assert (result.created, result.updated) == (0, 1)
    assert _key(project, "P").study_participant == participant


def test_a_key_already_linked_to_the_same_participant_is_a_no_op(project, etl_job):
    _participant(project, "A1")
    _load(project, etl_job, _row("P"))
    first = _key(project, "P")

    result = _load(project, _job(project, prefix="map2/"), _row("P"))

    assert (result.created, result.updated) == (0, 0)
    key = _key(project, "P")
    assert key.linked_job == etl_job and key.linked_at == first.linked_at


def test_the_same_row_twice_in_one_job_is_idempotent(project, etl_job):
    _participant(project, "A1")

    result = _load(project, etl_job, _row("P"), _row("P"))

    assert (result.created, result.updated) == (1, 0)
    assert ParticipantKey.objects.filter(project=project).count() == 1


def test_a_key_linked_to_a_different_participant_fails_the_job_and_writes_nothing(project, etl_job):
    _participant(project, "A1")
    other = _participant(project, "A2")
    ParticipantKey.objects.create(
        project=project, key_type="dicom:PatientID", value="SECRET-KEY", study_participant=other)

    with pytest.raises(EtlRowError) as error:
        _load(project, etl_job, _row("NEW-KEY"), _row("SECRET-KEY"), _row("OTHER-KEY", alias1="A2"))

    message = str(error.value)
    assert "row 2" in message
    for leaked in ("SECRET-KEY", "NEW-KEY", "A1", "A2"):
        assert leaked not in message
    assert ParticipantKey.objects.filter(project=project).count() == 1
    assert _key(project, "SECRET-KEY").study_participant == other


def test_conflicting_rows_inside_one_job_fail_it(project, etl_job):
    _participant(project, "A1")
    _participant(project, "A2")

    with pytest.raises(EtlRowError, match="row 2"):
        _load(project, etl_job, _row("P", alias1="A1"), _row("P", alias1="A2"))
    assert not ParticipantKey.objects.exists()


def test_an_unresolvable_reference_fails_the_job_without_leaking_identity(project, etl_job):
    with pytest.raises(EtlRowError) as error:
        _load(project, etl_job, _row("P", person_source_value="199001011234"))

    assert "199001011234" not in str(error.value)
    assert "row 1" in str(error.value)


def test_an_ambiguous_reference_fails_the_job_without_leaking_identity(project, etl_job):
    _participant(project, "A1", psv="199001011234")
    _participant(project, "A2", psv="199001011234")

    with pytest.raises(EtlRowError) as error:
        _load(project, etl_job, _row("P", person_source_value="199001011234"))

    assert "199001011234" not in str(error.value)
    assert "row 1" in str(error.value)


def test_a_bad_row_shape_fails_without_echoing_values(project, etl_job):
    with pytest.raises(EtlRowError) as error:
        _load(project, etl_job, {"key_type": "dicom:Nope", "key_value": "LEAKY", "alias1": "A1"})

    assert "LEAKY" not in str(error.value)


def test_a_bare_allow_listed_tag_is_accepted_as_key_type(project, etl_job):
    _participant(project, "A1")

    _load(project, etl_job, {"key_type": "AccessionNumber", "key_value": "ACC1", "alias1": "A1"})

    assert _key(project, "ACC1", key_type="dicom:AccessionNumber").study_participant is not None


def test_a_mapping_loaded_before_the_images_links_the_study_when_it_arrives(project, etl_job):
    participant = _participant(project, "A1")
    _load(project, etl_job, _row("PSEUDO-9"))

    key = link_study_keys(project, [{"PatientID": "PSEUDO-9"}])

    assert key.study_participant == participant


def test_one_summary_audit_event_per_job_without_values(project, etl_job):
    _participant(project, "A1")
    _participant(project, "A2")

    _load(project, etl_job, _row("K1"), _row("K2", alias1="A2"), _row("K1"))

    event = AuditLog.objects.get(event_type=EVENT_TYPE_PARTICIPANT_KEY_LINKED)
    assert event.project == project
    assert event.metadata == {"etl_job_id": str(etl_job.id), "created": 2, "linked": 0, "unchanged": 1}


def test_no_audit_event_when_the_job_fails(project, etl_job):
    with pytest.raises(EtlRowError):
        _load(project, etl_job, _row("P"))
    assert not AuditLog.objects.filter(event_type=EVENT_TYPE_PARTICIPANT_KEY_LINKED).exists()


# --- fill_demographics ---------------------------------------------------------------------------------

def _stored_key(project, value="P"):
    return ParticipantKey.objects.create(project=project, key_type="dicom:PatientID", value=value)


def _stored_study(project, key, tmp_path, *, birth="19800203", sex="F", name="a"):
    study = DicomStudy.objects.create(
        participant_key=key, study_datetime="2026-01-01T00:00:00Z", study_instance_uid=f"1.2.{name}")
    series = DicomSeries.objects.create(study=study, series_instance_uid=f"1.2.{name}.1")
    ds = build_ct_image()
    ds.PatientBirthDate = birth
    ds.PatientSex = sex
    path = write_dicom(ds, tmp_path / f"{name}.dcm")
    return DicomFile.objects.create(
        series=series, sop_instance_uid=f"1.2.{name}.1.1", research_project=project,
        file=ContentFile(path.read_bytes(), name=f"{name}.dcm"), file_size_in_mb=0.1)


def test_fill_demographics_is_off_by_default(project, etl_job, tmp_path):
    participant = _participant(project, "A1")
    _stored_study(project, _stored_key(project), tmp_path)

    _load(project, etl_job, _row("P"))

    participant.refresh_from_db()
    assert participant.year_of_birth is None and participant.gender == "U"


def test_fill_demographics_fills_blank_dob_and_sex_from_the_stored_originals(project, tmp_path):
    job = _job(project, {"fill_demographics": True})
    participant = _participant(project, "A1")
    _stored_study(project, _stored_key(project), tmp_path)

    _load(project, job, _row("P"))

    participant.refresh_from_db()
    assert (participant.year_of_birth, participant.month_of_birth, participant.day_of_birth) == (1980, 2, 3)
    assert participant.gender == "F"
    event = AuditLog.objects.get(event_type=EVENT_TYPE_PARTICIPANT_KEY_DEMOGRAPHICS_FILLED)
    assert event.metadata == {"etl_job_id": str(job.id), "participants": 1}


def test_fill_demographics_never_overwrites_existing_values(project, tmp_path):
    job = _job(project, {"fill_demographics": True})
    participant = _participant(project, "A1")
    participant.year_of_birth, participant.month_of_birth, participant.day_of_birth = 1970, 1, 1
    participant.gender = "M"
    participant.save()
    _stored_study(project, _stored_key(project), tmp_path)

    _load(project, job, _row("P"))

    participant.refresh_from_db()
    assert (participant.year_of_birth, participant.gender) == (1970, "M")
    assert not AuditLog.objects.filter(event_type=EVENT_TYPE_PARTICIPANT_KEY_DEMOGRAPHICS_FILLED).exists()


def test_fill_demographics_with_no_stored_images_is_a_quiet_no_op(project):
    job = _job(project, {"fill_demographics": True})
    participant = _participant(project, "A1")

    _load(project, job, _row("P"))

    participant.refresh_from_db()
    assert participant.year_of_birth is None


def test_fill_demographics_ignores_unusable_values(project, tmp_path):
    job = _job(project, {"fill_demographics": True})
    participant = _participant(project, "A1")
    _stored_study(project, _stored_key(project), tmp_path, birth="", sex="X")

    _load(project, job, _row("P"))

    participant.refresh_from_db()
    assert participant.year_of_birth is None and participant.gender == "U"


def test_datatype_default_raw_retention():
    assert default_raw_retention("participant_key_link") == PIPELINE_BINDING_RAW_RETENTION_DELETE
    assert default_raw_retention("participant_consent") == PIPELINE_BINDING_RAW_RETENTION_MOVE


def test_schema_allow_list_mirrors_the_app_allow_list():
    from contract.constants.participant_key import DICOM_KEY_TAG_ALLOWLIST
    from mires_etl.schemas.participant_key_link import DICOM_KEY_TAG_ALLOWLIST as SCHEMA_ALLOWLIST

    assert SCHEMA_ALLOWLIST == DICOM_KEY_TAG_ALLOWLIST


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_a_binding_created_without_raw_retention_takes_the_datatypes_default(project):
    from asgiref.sync import sync_to_async

    from MiqaResearch.actions.etl.bindings import create_pipeline_binding
    from MiqaResearch.data.models import EtlSourceLocation

    job = await sync_to_async(_job)(project)
    location = await sync_to_async(EtlSourceLocation.objects.create)(
        project=project, name="loc", bucket="b", prefix="p/")

    binding = await create_pipeline_binding(
        project=project, user=None, request=None, source_location=location,
        script_version_id=job.script_version_id, raw_bucket="", raw_prefix="")

    assert binding.raw_retention == PIPELINE_BINDING_RAW_RETENTION_DELETE
