"""Security test suite for DICOM ingestion (#114, #127).

Adversarial coverage for the threats identified in #114's threat model: path
traversal (local sources and S3 object keys), decompression-bomb-shaped
declared pixel dimensions, and PHI leakage into logs/the run's report. Per
the #98 testing decisions, tests call the top-level `run_ingestion` seam
directly wherever a full run is needed; the two narrowest fuzz tests reach
straight into discovery/pixel_bounds's own pure functions instead, since
those are the exact seams #114 asked to be fuzzed and a DB-backed run per
hypothesis example would make the suite unreasonably slow for no extra
coverage.

All tests here are marked long_running -- per #104's marker convention,
which covers "performance/load/extended security" tests, not just perf/load
-- and excluded from the default test run. This applies to every test in
this module, including the fast deterministic ones, so the whole security
suite stays grouped as a deliberate opt-in run (#127 AC).
"""
import io
import itertools
import logging
import os
from pathlib import Path

import boto3
import pytest
from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st
from moto import mock_aws
from pydicom.dataset import Dataset

from MiqaResearch.data.models import DicomFile, ResearchProject
from MiqaResearch.tasks.dicom_handling import discovery, pixel_bounds
from MiqaResearch.tasks.dicom_handling import records as records_stage
from MiqaResearch.tasks.dicom_handling.discovery import SourceNotAllowedError
from MiqaResearch.tasks.dicom_handling.pipeline import run_ingestion
from tests.dicom_fixtures import build_ct_image, build_wsi, write_dicom

pytestmark = pytest.mark.long_running


@pytest.fixture(autouse=True)
def encryption_keys(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="


@pytest.fixture(autouse=True)
def allow_tmp_sources(settings, tmp_path):
    settings.DICOM_ALLOWED_SOURCE_ROOTS = [tmp_path]


@pytest.fixture(autouse=True)
def s3_settings(settings):
    settings.DICOM_S3_ENDPOINT_URL = None
    settings.DICOM_S3_REGION_NAME = "us-east-1"
    settings.DICOM_S3_ACCESS_KEY_ID = "testing"
    settings.DICOM_S3_SECRET_ACCESS_KEY = "testing"


@pytest.fixture
def research_project(db):
    return ResearchProject.objects.create(name="Security test project", description="Project for #127 tests")


# --- AC: path-traversal-shaped local source rejected before read or delete -------


def test_path_traversal_shaped_source_rejected_before_read_or_delete(research_project, tmp_path, settings):
    """Critical specifically because #123 means a wrongly-allowed path here
    isn't just a read risk -- it's a deletion risk."""
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.DICOM_DELETE_ORIGINALS_AFTER_STORAGE = True
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    settings.DICOM_ALLOWED_SOURCE_ROOTS = [allowed]
    secret = write_dicom(build_ct_image(), tmp_path / "secret" / "outside.dcm")
    traversal_source = f"{allowed}/../secret/outside.dcm"
    assert ".." in traversal_source

    with pytest.raises(SourceNotAllowedError):
        run_ingestion(research_project, traversal_source)

    assert secret.exists()  # never read, and critically never deleted
    assert DicomFile.objects.count() == 0


def test_path_traversal_shaped_symlink_target_mid_walk_rejected_and_never_deleted(research_project, tmp_path, settings):
    """A symlink inside an allowed folder whose (traversal-shaped) target
    escapes the allow-list is rejected per-file, without aborting the rest of
    the folder, and the escaping target survives even with retention on."""
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.DICOM_DELETE_ORIGINALS_AFTER_STORAGE = True
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    settings.DICOM_ALLOWED_SOURCE_ROOTS = [allowed]
    secret = write_dicom(build_ct_image(), tmp_path / "secret" / "real.dcm")
    (allowed / "link.dcm").symlink_to(Path(f"{allowed}/../secret/real.dcm"))
    write_dicom(build_ct_image(sop_instance_uid="1.2.9999.127.1.1"), allowed / "good.dcm")

    report = run_ingestion(research_project, allowed)

    assert report.counts["error"] == 1
    assert report.counts["ingested"] == 1
    assert secret.exists()
    assert DicomFile.objects.count() == 1


# --- AC: S3 object keys with traversal sequences never build a local path --------


@pytest.mark.parametrize(
    "hostile_key",
    [
        "../../evil.dcm",
        "../../../../etc/evil.dcm",
        "..\\..\\evil.dcm",
        "/etc/evil.dcm",
        "a/../../../evil.dcm",
    ],
)
@mock_aws
def test_s3_key_with_traversal_sequences_never_builds_a_local_path(research_project, tmp_path, settings, hostile_key):
    media = tmp_path / "media"
    settings.MEDIA_ROOT = media
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="hostile-bucket")
    payload = write_dicom(build_ct_image(), tmp_path / "payload.dcm").read_bytes()
    client.put_object(Bucket="hostile-bucket", Key=hostile_key, Body=payload)

    report = run_ingestion(research_project, "s3://hostile-bucket")

    assert report.counts["ingested"] == 1, report.results
    dcm_file = DicomFile.objects.get()
    stored_path = os.path.realpath(dcm_file.file.path)
    # Stored under the configured media root, generated from the record id --
    # never derived from the hostile key.
    assert stored_path.startswith(os.path.realpath(str(media)) + os.sep)
    # The key, interpreted as a local relative path, must not exist anywhere.
    assert not Path.cwd().joinpath(hostile_key).resolve().exists()
    assert not (tmp_path / hostile_key).resolve().exists()


# --- AC: implausible declared pixel dimensions/frame count rejected before decode --


def test_wsi_declaring_implausible_total_pixel_matrix_dimensions_is_rejected(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
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

    report = run_ingestion(research_project, src)

    assert report.counts == {"ingested": 0, "skipped_duplicate": 0, "duplicate_conflict": 0, "error": 1}
    assert "TotalPixelMatrixRows" in report.results[0].error
    assert DicomFile.objects.count() == 0


def test_file_declaring_implausible_frame_count_is_rejected(research_project, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.DICOM_MAX_FRAME_COUNT = 1_000
    ds = build_wsi(number_of_frames=1, tile_rows=4, tile_columns=4)
    ds.NumberOfFrames = 50_000_000  # declared only -- actual PixelData still covers a single tiny frame
    src = write_dicom(ds, tmp_path / "frame_bomb.dcm")

    report = run_ingestion(research_project, src)

    assert report.counts["error"] == 1
    assert "NumberOfFrames" in report.results[0].error
    assert DicomFile.objects.count() == 0


def test_declared_dimensions_within_limits_still_ingest_normally(research_project, tmp_path, settings):
    """The guard must not false-positive on ordinary, realistic files."""
    settings.MEDIA_ROOT = tmp_path / "media"
    src = write_dicom(build_ct_image(), tmp_path / "normal.dcm")

    report = run_ingestion(research_project, src)

    assert report.counts["ingested"] == 1


# --- AC: no raw PHI in logs or the run's report -----------------------------------


def test_no_raw_phi_in_logs_for_successful_ingestion(research_project, tmp_path, settings, caplog):
    settings.MEDIA_ROOT = tmp_path / "media"
    patient_id, patient_name = "P-SECURITY-9F3B21", "TESTSUBJECT^SECURITYCHECK"
    src = write_dicom(build_ct_image(patient_id=patient_id, patient_name=patient_name), tmp_path / "phi.dcm")

    with caplog.at_level(logging.DEBUG):
        report = run_ingestion(research_project, src)

    assert report.counts["ingested"] == 1
    assert patient_id not in caplog.text
    assert patient_name not in caplog.text


def test_no_raw_phi_in_logs_or_report_when_ingestion_errors(research_project, tmp_path, settings, caplog, monkeypatch):
    settings.MEDIA_ROOT = tmp_path / "media"
    patient_id, patient_name = "P-SECURITY-9F3B21", "TESTSUBJECT^SECURITYCHECK"
    src = write_dicom(build_ct_image(patient_id=patient_id, patient_name=patient_name), tmp_path / "phi.dcm")

    def boom(*args, **kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(records_stage, "build_hierarchy", boom)

    with caplog.at_level(logging.DEBUG):
        report = run_ingestion(research_project, src)

    assert report.counts["error"] == 1
    assert patient_id not in caplog.text
    assert patient_name not in caplog.text
    result = report.results[0]
    assert patient_id not in repr(result)
    assert patient_name not in repr(result)


# --- AC: hypothesis fuzzing of discovery/extraction, no crashes, no bypass -------


def test_local_source_allow_list_never_escapes_for_adversarial_paths(tmp_path):
    """Fuzz discovery.assert_local_source_allowed -- the local-source seam
    itself, since the full pipeline already wraps every per-file problem into
    an error outcome and would mask a real escape here."""
    allowed = tmp_path / "allowed"
    allowed.mkdir()

    @hyp_settings(max_examples=150, deadline=None)
    @given(junk=st.text(min_size=0, max_size=60), depth=st.integers(min_value=0, max_value=6))
    def check(junk, depth):
        candidate = str(allowed) + ("/.." * depth) + "/" + junk
        try:
            resolved = discovery.assert_local_source_allowed(candidate, [allowed])
        except SourceNotAllowedError:
            return
        except (OSError, ValueError):
            # Some adversarial junk (e.g. embedded NUL) is an OS-level
            # invalid path -- acceptable as long as it never silently
            # resolves outside the allow-list below.
            return
        assert resolved == allowed or allowed in resolved.parents

    check()


def test_pixel_dimension_guard_rejects_exactly_what_exceeds_the_configured_limits():
    """Fuzz pixel_bounds.assert_plausible_pixel_dimensions directly -- the
    exact declared-dimension seam #114 asked to be fuzzed."""
    max_pixel_dimension, max_frame_count = 5_000, 8_000

    @hyp_settings(max_examples=200, deadline=None)
    @given(
        rows=st.one_of(st.none(), st.integers(min_value=-10, max_value=2_000_000)),
        columns=st.one_of(st.none(), st.integers(min_value=-10, max_value=2_000_000)),
        number_of_frames=st.one_of(st.none(), st.integers(min_value=-10, max_value=2_000_000)),
    )
    def check(rows, columns, number_of_frames):
        ds = Dataset()
        if rows is not None:
            ds.Rows = rows
        if columns is not None:
            ds.Columns = columns
        if number_of_frames is not None:
            ds.NumberOfFrames = number_of_frames
        should_reject = any(v is not None and v > max_pixel_dimension for v in (rows, columns)) or (
            number_of_frames is not None and number_of_frames > max_frame_count
        )

        if should_reject:
            with pytest.raises(pixel_bounds.ImplausiblePixelDimensionsError):
                pixel_bounds.assert_plausible_pixel_dimensions(ds, max_pixel_dimension, max_frame_count)
        else:
            pixel_bounds.assert_plausible_pixel_dimensions(ds, max_pixel_dimension, max_frame_count)

    check()


def _ct_template_bytes() -> bytes:
    buf = io.BytesIO()
    build_ct_image().save_as(buf, enforce_file_format=True)
    return buf.getvalue()


def test_ingestion_never_crashes_on_mutated_valid_dicom_bytes(research_project, tmp_path, settings):
    """Fuzz the full pipeline with byte-mutated (structurally near-valid)
    DICOM content -- a source likelier to reach deep parse/extract paths than
    pure random garbage. run_ingestion must never raise for a per-file
    problem; every mutation resolves to exactly one ingested/error outcome."""
    settings.MEDIA_ROOT = tmp_path / "media"
    template = _ct_template_bytes()

    @hyp_settings(max_examples=60, deadline=None)
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

        report = run_ingestion(research_project, src)

        assert len(report.results) == 1
        # A mutation that happens to leave the SOP Instance UID intact is a
        # legitimate duplicate of an earlier example's file, not a crash.
        assert report.results[0].outcome in {"ingested", "error", "skipped_duplicate", "duplicate_conflict"}

    check()


def test_ingestion_never_crashes_for_adversarial_patient_tag_text(research_project, tmp_path, settings):
    """Fuzz the full pipeline with adversarial PatientID/PatientName text
    (unicode, embedded control characters, very long strings) -- must always
    resolve to exactly one per-file outcome, never raise."""
    settings.MEDIA_ROOT = tmp_path / "media"
    counter = itertools.count()

    @hyp_settings(max_examples=40, deadline=None)
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

        report = run_ingestion(research_project, src)

        assert len(report.results) == 1
        assert report.results[0].outcome in {"ingested", "error"}

    check()
