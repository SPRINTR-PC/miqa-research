"""Security test suite for DICOM ingestion (#114, #127), retargeted to the ETL path (#419, #409).

Adversarial coverage of the threats from #114's threat model, now against the native script plus the
`dicom_instance` loader: decompression-bomb-shaped declared pixel dimensions (the loader's
`MIRES_DICOM_MAX_*` check on the row), PHI leakage into logs, the Job log and error messages, and
hypothesis fuzzing of the whole path. The path-traversal and allowed-roots tests of the retired
local-folder ingestion are gone with it: the runner stages S3 keys into a scratch directory and
`inputs.open` refuses any path that is not a recorded `EtlJobInput` (tests/test_etl_dicom_instance_loader.py).

All tests here are marked long_running -- per #104's marker convention, which covers
"performance/load/extended security" tests -- and excluded from the default test run, so the
whole security suite stays a deliberate opt-in run (#127 AC).
"""
import io
import itertools
import logging
from types import SimpleNamespace

import pytest
from hypothesis import HealthCheck, given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st

from MiqaResearch.actions.dicom_ingest import load as load_stage
from MiqaResearch.actions.dicom_ingest import records as records_stage
from MiqaResearch.data.models import DicomFile, ResearchProject
from MiqaResearch.etl_datatypes import EtlLoadError
from MiqaResearch.etl_datatypes.exceptions import EtlDatatypeError
from mires_etl.schemas.dicom_instance import ImagePayload, WsiPayload
from tests.dicom_fixtures import build_ct_image, build_wsi, write_dicom
from tests.dicom_ingest_helper import ingest_files

pytestmark = pytest.mark.long_running

# Per-example DB rows are fine for these fuzzers: each example is one self-contained Job.
FUZZ_SETTINGS = hyp_settings(
    max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])


@pytest.fixture(autouse=True)
def encryption_keys(settings, tmp_path):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def research_project(db):
    return ResearchProject.objects.create(name="Security test project", description="Project for #127 tests")


# --- AC: implausible declared pixel dimensions/frame count rejected before decode --


def test_wsi_declaring_implausible_total_pixel_matrix_dimensions_is_rejected(research_project, tmp_path, settings):
    settings.DICOM_MAX_PIXEL_DIMENSIONS = 50_000
    settings.DICOM_MAX_FRAME_COUNT = 50_000
    # Actual PixelData stays a tiny 4x4 tile; only the *declared* pyramid
    # extent is bomb-shaped -- exactly the small-compressed-payload/huge-
    # declared-size shape #114 flagged for pathology J2K frames.
    ds = build_wsi(
        number_of_frames=1,
        tile_rows=4,
        tile_columns=4,
        total_pixel_matrix_rows=5_000_000,
        total_pixel_matrix_columns=5_000_000
    )
    src = write_dicom(ds, tmp_path / "bomb.dcm")

    with pytest.raises(EtlLoadError, match="TotalPixelMatrixRows"):
        ingest_files(research_project, src)

    assert DicomFile.objects.count() == 0


def test_file_declaring_implausible_frame_count_is_rejected(research_project, tmp_path, settings):
    settings.DICOM_MAX_FRAME_COUNT = 1_000
    ds = build_wsi(number_of_frames=1, tile_rows=4, tile_columns=4)
    ds.NumberOfFrames = 50_000_000  # declared only -- actual PixelData still covers a single tiny frame
    src = write_dicom(ds, tmp_path / "frame_bomb.dcm")

    with pytest.raises(EtlLoadError, match="NumberOfFrames"):
        ingest_files(research_project, src)

    assert DicomFile.objects.count() == 0


def test_declared_dimensions_within_limits_still_ingest_normally(research_project, tmp_path):
    """The guard must not false-positive on ordinary, realistic files."""
    src = write_dicom(build_ct_image(), tmp_path / "normal.dcm")

    report = ingest_files(research_project, src)

    assert report.counts["ingested"] == 1


# --- AC: no raw PHI in logs, the Job log or error messages ---------------------------


def test_no_raw_phi_in_logs_or_the_job_log_for_successful_ingestion(research_project, tmp_path, caplog):
    patient_id, patient_name = "P-SECURITY-9F3B21", "TESTSUBJECT^SECURITYCHECK"
    src = write_dicom(build_ct_image(patient_id=patient_id, patient_name=patient_name), tmp_path / "phi.dcm")

    with caplog.at_level(logging.DEBUG):
        report = ingest_files(research_project, src)

    assert report.counts["ingested"] == 1
    assert patient_id not in caplog.text
    assert patient_name not in caplog.text
    assert patient_id not in repr(report.load_result)
    assert patient_name not in repr(report.load_result)


def test_no_raw_phi_in_logs_or_the_error_when_loading_fails(research_project, tmp_path, caplog, monkeypatch):
    patient_id, patient_name = "P-SECURITY-9F3B21", "TESTSUBJECT^SECURITYCHECK"
    src = write_dicom(build_ct_image(patient_id=patient_id, patient_name=patient_name), tmp_path / "phi.dcm")

    def boom(*args, **kwargs):
        raise RuntimeError(f"simulated failure for {patient_id}")

    monkeypatch.setattr(records_stage, "build_hierarchy", boom)

    with caplog.at_level(logging.DEBUG), pytest.raises(EtlLoadError) as exc_info:
        ingest_files(research_project, src)

    assert patient_id not in str(exc_info.value)
    assert patient_name not in str(exc_info.value)
    assert patient_name not in caplog.text


# --- AC: hypothesis fuzzing of the loader and the whole path, no crashes, no bypass -----


def test_pixel_dimension_guard_rejects_exactly_what_exceeds_the_configured_limits(settings):
    """Fuzz the loader's declared-dimension check -- the exact seam #114 asked to be fuzzed."""
    settings.DICOM_MAX_PIXEL_DIMENSIONS, settings.DICOM_MAX_FRAME_COUNT = 5_000, 8_000

    @hyp_settings(max_examples=200, deadline=None)
    @given(
        rows=st.one_of(st.none(), st.integers(min_value=-10, max_value=2_000_000)),
        columns=st.one_of(st.none(), st.integers(min_value=-10, max_value=2_000_000)),
        number_of_frames=st.one_of(st.none(), st.integers(min_value=-10, max_value=2_000_000)),
        matrix=st.one_of(st.none(), st.integers(min_value=-10, max_value=2_000_000)),
    )
    def check(rows, columns, number_of_frames, matrix):
        payload = ImagePayload() if matrix is None else WsiPayload(
            total_pixel_matrix_rows=matrix, total_pixel_matrix_columns=matrix)
        row = SimpleNamespace(rows=rows, columns=columns, number_of_frames=number_of_frames, payload=payload)
        should_reject = any(v is not None and v > 5_000 for v in (rows, columns, matrix)) or (
            number_of_frames is not None and number_of_frames > 8_000
        )

        if should_reject:
            with pytest.raises(EtlLoadError):
                load_stage._assert_plausible_pixels(row)
        else:
            load_stage._assert_plausible_pixels(row)

    check()


def _ct_template_bytes() -> bytes:
    buf = io.BytesIO()
    build_ct_image().save_as(buf, enforce_file_format=True)
    return buf.getvalue()


def test_ingestion_never_crashes_on_mutated_valid_dicom_bytes(research_project, tmp_path):
    """Fuzz script plus loader with byte-mutated (structurally near-valid) DICOM content -- a source
    likelier to reach deep parse paths than random garbage. Every mutation either loads or fails with a
    defined error: the script's `RuntimeError` or an `EtlDatatypeError`, never anything else."""
    template = _ct_template_bytes()

    @FUZZ_SETTINGS
    @given(
        indices=st.lists(st.integers(min_value=0, max_value=len(template) - 1), max_size=30, unique=True),
        replacement=st.integers(min_value=0, max_value=255),
    )
    def check(indices, replacement):
        raw = bytearray(template)
        for i in indices:
            raw[i] = replacement
        src = tmp_path / "mutated.dcm"
        src.write_bytes(bytes(raw))

        try:
            report = ingest_files(research_project, src)
        except (RuntimeError, EtlDatatypeError):
            return
        assert len(report.results) == 1

    check()


def test_ingestion_never_crashes_for_adversarial_patient_tag_text(research_project, tmp_path):
    """Fuzz script plus loader with adversarial PatientID/PatientName text (unicode, embedded control
    characters, very long strings): the Job loads or fails with a defined error, never raises anything else."""
    counter = itertools.count()

    @FUZZ_SETTINGS
    @given(patient_id=st.text(min_size=0, max_size=200), patient_name=st.text(min_size=0, max_size=200))
    def check(patient_id, patient_name):
        n = next(counter)
        ds = build_ct_image(
            patient_id=patient_id,
            patient_name=patient_name,
            study_instance_uid=f"1.2.9999.127.5.{n}.1",
            series_instance_uid=f"1.2.9999.127.5.{n}.2",
            sop_instance_uid=f"1.2.9999.127.5.{n}.3",
        )
        src = write_dicom(ds, tmp_path / f"adv-{n}.dcm")

        try:
            ingest_files(research_project, src)
        except (RuntimeError, EtlDatatypeError):
            return

    check()
