"""Backfill: existing series get the Frame of Reference their files share (#197).

Seam: `backfill_series_frame_of_reference`, the function data migration 0036 runs.
"""
from importlib import import_module

import pytest

from MiqaResearch.data.models import DicomFile, DicomSeries, ResearchProject
from MiqaResearch.tasks.dicom_handling.pipeline import run_ingestion
from tests.dicom_fixtures import build_ct_image, write_dicom

backfill_series_frame_of_reference = import_module(
    "MiqaResearch.data.migrations.0036_dicom_series_frame_of_reference"
).backfill_series_frame_of_reference


@pytest.fixture(autouse=True)
def encryption_keys(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="


@pytest.fixture(autouse=True)
def storage(settings, tmp_path):
    settings.DICOM_ALLOWED_SOURCE_ROOTS = [tmp_path]
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def research_project(db):
    return ResearchProject.objects.create(name="FoR backfill project", description="#197")


def _ingest_series(research_project, tmp_path, series_uid, files):
    """Ingest one series of files, given as (sop_uid, frame_of_reference_uid), then forget its series FoR."""
    for sop_uid, for_uid in files:
        ds = build_ct_image(series_instance_uid=series_uid, sop_instance_uid=sop_uid, frame_of_reference_uid=for_uid)
        run_ingestion(research_project, write_dicom(ds, tmp_path / f"{sop_uid}.dcm"))
    series = DicomFile.objects.order_by("-id").first().series
    DicomSeries.objects.filter(pk=series.pk).update(frame_of_reference_uid=None)
    return series


def test_backfill_sets_the_shared_frame_of_reference_and_nulls_mixed_or_missing(research_project, tmp_path):
    shared = _ingest_series(research_project, tmp_path, "1.2.9999.7.1", [("1.2.9999.7.1.1", "1.2.9999.7.9"),
                                                                          ("1.2.9999.7.1.2", "1.2.9999.7.9")])
    mixed = _ingest_series(research_project, tmp_path, "1.2.9999.7.2", [("1.2.9999.7.2.1", "1.2.9999.7.9"),
                                                                         ("1.2.9999.7.2.2", "1.2.9999.7.8")])
    missing = _ingest_series(research_project, tmp_path, "1.2.9999.7.3", [("1.2.9999.7.3.1", "1.2.9999.7.9"),
                                                                           ("1.2.9999.7.3.2", None)])

    backfill_series_frame_of_reference(DicomSeries, DicomFile)

    expected = DicomFile.objects.filter(series=shared).first().frame_of_reference_uid
    assert expected not in (None, "1.2.9999.7.9")
    assert DicomSeries.objects.get(pk=shared.pk).frame_of_reference_uid == expected
    assert DicomSeries.objects.get(pk=mixed.pk).frame_of_reference_uid is None
    assert DicomSeries.objects.get(pk=missing.pk).frame_of_reference_uid is None
