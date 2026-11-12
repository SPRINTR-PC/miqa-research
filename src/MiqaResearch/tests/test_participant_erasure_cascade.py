"""Participant erasure cascades through Participant Keys to imaging (ADR 0035, #415).

Seam: deleting a Study Participant, fed by `run_ingestion`.
"""
import pytest

from MiqaResearch.data.models import DicomFile, DicomSeries, DicomStudy, ParticipantKey, ResearchProject
from MiqaResearch.tasks.dicom_handling.pipeline import run_ingestion
from tests.dicom_fixtures import build_ct_image, write_dicom


@pytest.fixture(autouse=True)
def environment(settings, tmp_path):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="
    settings.DICOM_ALLOWED_SOURCE_ROOTS = [tmp_path]
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def ingested(db, tmp_path):
    project = ResearchProject.objects.create(name="Erasure", description="#415")
    report = run_ingestion(project, write_dicom(build_ct_image(), tmp_path / "ct.dcm"))
    assert report.counts["ingested"] == 1, report.results
    return DicomFile.objects.select_related("series__study__participant_key__study_participant").get()


def test_erasing_a_participant_removes_its_keys_and_imaging_rows(ingested):
    ingested.series.study.participant_key.study_participant.delete()

    assert not ParticipantKey.objects.exists()
    assert not DicomStudy.objects.exists()
    assert not DicomSeries.objects.exists()
    assert not DicomFile.objects.exists()


def test_erasing_a_participant_keeps_unlinked_keys_of_the_project(ingested):
    other = ParticipantKey.objects.create(project=ingested.research_project, key_type="dicom:PatientID", value="X")

    ingested.series.study.participant_key.study_participant.delete()

    assert list(ParticipantKey.objects.all()) == [other]


@pytest.mark.xfail(
    strict=True,
    reason="Audit finding (#415): DicomFile has no delete hook, so the DicomStorage blob outlives its row "
    "on cascade; the orphan sweep (#407) is what reclaims it.",
)
def test_erasing_a_participant_removes_the_stored_blobs(ingested):
    storage, name = ingested.file.storage, ingested.file.name
    assert storage.exists(name)

    ingested.series.study.participant_key.study_participant.delete()

    assert not storage.exists(name)
