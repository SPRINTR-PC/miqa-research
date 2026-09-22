"""Pathology (WSI) extraction (#124) — exercises the `run_ingestion` seam and asserts on
the resulting `DicomFile`/`DicomSeries` records, per the #98/#110 testing decisions."""
import pytest

from helpers.dicom_uid import pseudonymize_uid
from MiqaResearch.data.models import DicomFile, DicomSeries, ResearchProject
from MiqaResearch.tasks.dicom_handling.pipeline import run_ingestion
from tests.dicom_fixtures import build_wsi, write_dicom


@pytest.fixture(autouse=True)
def encryption_keys(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="


@pytest.fixture(autouse=True)
def allow_tmp_sources(settings, tmp_path):
    settings.DICOM_ALLOWED_SOURCE_ROOTS = [tmp_path]
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def research_project(db):
    return ResearchProject.objects.create(name="Pathology WSI project", description="Project for #124 tests")


def _ingest(research_project, tmp_path, ds, name="slide.dcm") -> DicomFile:
    report = run_ingestion(research_project, write_dicom(ds, tmp_path / name))
    assert report.counts["ingested"] == 1, report.results
    return DicomFile.objects.get(sop_instance_uid=pseudonymize_uid(ds.SOPInstanceUID, research_project))


def test_wsi_populates_pyramid_and_tiling_metadata(research_project, tmp_path):
    dcm_file = _ingest(research_project, tmp_path, build_wsi())

    summary = dcm_file.metadata["pathology_summary"]
    assert summary["frame_count"] == 3
    assert summary["tile_rows"] == 4
    assert summary["tile_columns"] == 4
    assert summary["total_pixel_matrix_rows"] == 8
    assert summary["total_pixel_matrix_columns"] == 8
    assert summary["image_type"] == "VOLUME"


def test_wsi_populates_pixel_spacing_from_shared_functional_groups(research_project, tmp_path):
    dcm_file = _ingest(research_project, tmp_path, build_wsi(pixel_spacing="0.0005\\0.0005"))

    assert dcm_file.pixel_spacing == [0.0005, 0.0005]


def test_wsi_without_shared_functional_groups_leaves_pixel_spacing_none(research_project, tmp_path):
    dcm_file = _ingest(research_project, tmp_path, build_wsi(include_shared_functional_groups=False))

    assert dcm_file.pixel_spacing is None
    assert dcm_file.metadata["pathology_summary"]["frame_count"] == 3


def test_wsi_pixel_spacing_falls_back_to_per_frame_functional_groups(research_project, tmp_path):
    """Spacing that varies frame-to-frame lives in Per-Frame rather than Shared (PS3.3 C.7.6.16.2.3)."""
    ds = build_wsi(include_shared_functional_groups=False, per_frame_pixel_spacing="0.0004\\0.0004")
    dcm_file = _ingest(research_project, tmp_path, ds)

    assert dcm_file.pixel_spacing == [0.0004, 0.0004]


def test_wsi_populates_optical_path_magnification_metadata(research_project, tmp_path):
    dcm_file = _ingest(research_project, tmp_path, build_wsi(objective_lens_power=40.0))

    summary = dcm_file.metadata["pathology_summary"]
    assert summary["objective_lens_power"] == 40.0
    assert summary["optical_path_count"] == 1


def test_wsi_without_optical_path_sequence_leaves_magnification_none(research_project, tmp_path):
    dcm_file = _ingest(research_project, tmp_path, build_wsi(objective_lens_power=None))

    summary = dcm_file.metadata["pathology_summary"]
    assert summary["objective_lens_power"] is None
    assert summary["optical_path_count"] == 0


def test_wsi_populates_frame_of_reference_but_leaves_patient_geometry_empty(research_project, tmp_path):
    ds = build_wsi()
    dcm_file = _ingest(research_project, tmp_path, ds)

    assert dcm_file.frame_of_reference_uid == pseudonymize_uid(ds.FrameOfReferenceUID, research_project)
    assert dcm_file.image_orientation_patient is None
    assert dcm_file.image_position_patient is None


def test_multiple_pyramid_level_files_link_to_one_series(research_project, tmp_path):
    """Separate pyramid levels are separate instances sharing one SeriesInstanceUID —
    the same multi-file-to-one-series linking used by folder/S3 discovery (#110)."""
    full_res = build_wsi(
        sop_instance_uid="1.2.9999.42.10.10003", total_pixel_matrix_rows=8, total_pixel_matrix_columns=8
    )
    thumbnail = build_wsi(
        sop_instance_uid="1.2.9999.42.10.20003",
        total_pixel_matrix_rows=2,
        total_pixel_matrix_columns=2,
        image_type=("ORIGINAL", "PRIMARY", "LABEL", "NONE"),
    )
    write_dicom(full_res, tmp_path / "level0.dcm")
    write_dicom(thumbnail, tmp_path / "level1.dcm")

    report = run_ingestion(research_project, tmp_path)

    assert report.counts == {"ingested": 2, "skipped_duplicate": 0, "duplicate_conflict": 0, "error": 0}
    assert DicomSeries.objects.count() == 1
    assert DicomFile.objects.count() == 2
