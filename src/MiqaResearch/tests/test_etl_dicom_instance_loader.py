"""The `dicom_instance` loader (#418, spec #411): the native script's rows plus the staged originals in,
Studies/Series/Files and stored blobs out. Layer B/C: real script run in-process, real DB, local-disk
`DicomStorage`, the Job's `inputs` reader over a temp "scratch" directory.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from contract.constants.etl import ETL_SCRIPT_ORIGIN_CUSTOM
from helpers.dicom_uid import pseudonymize_uid
from MiqaResearch.actions.dicom_ingest import records, storage
from MiqaResearch.data.models import (
    DerivedObjectProvenance,
    DicomFile,
    DicomSeries,
    DicomStudy,
    EtlJob,
    EtlJobInput,
    EtlScript,
    EtlScriptVersion,
    ParticipantKey,
    PipelineBinding,
    ResearchProject,
    StudyParticipant,
)
from MiqaResearch.etl_datatypes import EtlLoadError, JobInputs, get_datatype, load_jsonl
from MiqaResearch.etl_datatypes.exceptions import EtlRowError, UnrecordedInput
from MiqaResearch.etl_datatypes.loader import _parse_rows
from MiqaResearch.etl_native_scripts import native_script_path
from mires_etl import contract
from mires_etl.schemas.dicom_instance import DicomInstanceRowSchema
from mires_etl.shim import read_result_jsonl, run_script
from tests.dicom_fixtures import (
    build_ct_image,
    build_rdsr,
    build_rtdose,
    build_rtimage,
    build_rtplan,
    build_rtstruct,
    build_wsi,
    write_dicom,
)

IDENTIFIERS = {"identifiers": {"tags": ["PatientID"]}}


@pytest.fixture(autouse=True)
def _env(settings, tmp_path):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture(scope="module")
def script_main():
    spec = importlib.util.spec_from_file_location("dicom_instance", native_script_path("dicom_instance.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


@pytest.fixture
def project(db):
    return ResearchProject.objects.create(name="DICOM loader project", description="")


@pytest.fixture
def participant(project):
    return StudyParticipant.objects.create(alias1="P-1001", person_source_value="SRC1", research_project=project)


@pytest.fixture
def ingest(project, tmp_path, script_main):
    """ingest(files, config=None, rows_hook=None, inputs_hook=None) -> LoadResult; one Job per call."""
    counter = iter(range(10_000))

    def _ingest(files: dict, config: dict | None = IDENTIFIERS, *, rows_hook=None, sha_override=None):
        root = tmp_path / f"job{next(counter)}"
        input_dir = root / "input"
        input_dir.mkdir(parents=True)
        for name, content in files.items():
            if isinstance(content, bytes):
                (input_dir / name).write_bytes(content)
            else:
                write_dicom(content, input_dir / name)
        output_dir = root / "output"
        result = run_script(
            main=script_main, manifest={"datatype": "dicom_instance", "config": config or {}},
            input_dir=input_dir, output_dir=output_dir)
        assert result.exit_code == contract.EXIT_SUCCESS, result.log + result.error
        text = read_result_jsonl(output_dir / contract.RESULT_FILENAME).rows_jsonl
        rows = [json.loads(line) for line in text.splitlines()]
        if rows_hook:
            rows = rows_hook(rows)

        script = EtlScript.objects.create(name="s", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
        version = EtlScriptVersion.objects.create(
            script=script, version=1, source=SimpleUploadedFile("script.py", b"x"), sha256="0" * 64)
        binding = PipelineBinding.objects.create(
            project=project, source_bucket="in", source_prefix=f"p{root.name}/", script_version=version,
            raw_bucket="raw", raw_prefix=f"p{root.name}/")
        job = EtlJob.objects.create(binding=binding, script_version=version, config_snapshot=config or {})
        pairs = []
        for name in files:
            path = input_dir / name
            sha = (sha_override or {}).get(name) or hashlib.sha256(path.read_bytes()).hexdigest()
            job_input = EtlJobInput.objects.create(
                job=job, bucket="in", key=f"p{root.name}/{name}", sha256=sha, size_bytes=path.stat().st_size)
            pairs.append((name, job_input, path))
        return load_jsonl(
            datatype_name="dicom_instance", project=project, etl_job=job,
            jsonl_text="\n".join(json.dumps(r) for r in rows), inputs=JobInputs.from_staged(pairs))

    return _ingest


def _blobs(settings) -> list[Path]:
    root = Path(settings.MEDIA_ROOT) / "DICOM"
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


def test_datatype_declares_delete_as_default_raw_retention():
    assert get_datatype("dicom_instance").default_raw_retention == "delete"


def test_ct_is_stored_with_pseudonymized_uids_sanitized_metadata_and_linked_key(ingest, participant, settings):
    ds = build_ct_image()
    result = ingest({"a.dcm": ds})

    assert (result.created, result.updated, result.skipped, result.kept_inputs) == (1, 0, 0, ())
    dcm = DicomFile.objects.get()
    study = dcm.series.study
    assert study.participant_key.study_participant == participant
    assert study.participant_key.key_type == "dicom:PatientID"
    assert ds.SOPInstanceUID not in (dcm.sop_instance_uid, json.dumps(dcm.metadata))
    assert study.study_instance_uid != ds.StudyInstanceUID
    assert dcm.content_sha256 and dcm.frame_index is not None
    assert dcm.series.modality == "CT"
    assert "DOE" not in json.dumps(dcm.metadata)  # PatientName stripped
    assert len(_blobs(settings)) == 1


def test_unknown_identifier_ingests_unlinked_and_never_creates_a_participant(ingest, project):
    ingest({"a.dcm": build_ct_image()})
    key = ParticipantKey.objects.get()
    assert key.study_participant is None
    assert StudyParticipant.objects.filter(research_project=project).count() == 0


def test_study_datetime_falls_back_to_job_started_at_when_the_script_found_none(ingest, project):
    def strip(rows):
        for row in rows:
            row["study_datetime"] = None
        return rows

    ingest({"a.dcm": build_ct_image()}, rows_hook=strip)
    study = DicomStudy.objects.get()
    assert study.study_datetime is not None


def test_script_supplied_tag_dump_is_rejected_and_nothing_is_stored(ingest, settings):
    """The row schema has no raw-header-dump field (PHI), so a script cannot smuggle one into the metadata."""
    def poison(rows):
        for row in rows:
            row["tags"] = {"PatientName": "LEAKY^NAME", "Poison": "POISON"}
        return rows

    with pytest.raises(EtlRowError):
        ingest({"a.dcm": build_ct_image()}, rows_hook=poison)
    assert DicomFile.objects.count() == 0
    assert _blobs(settings) == []


def test_stored_metadata_is_rebuilt_from_the_bytes_and_carries_no_phi(ingest):
    ingest({"a.dcm": build_ct_image()})
    dumped = json.dumps(DicomFile.objects.get().metadata)
    assert "DOE" not in dumped
    assert "SOPClassUID" in dumped


def test_identifier_tags_outside_the_allow_list_are_ignored(ingest):
    def widen(rows):
        for row in rows:
            row["identifiers"] = {**row["identifiers"], "PatientBirthDate": "19750131", "Whatever": "x"}
        return rows

    ingest({"a.dcm": build_ct_image()}, rows_hook=widen)
    assert list(ParticipantKey.objects.values_list("key_type", flat=True)) == ["dicom:PatientID"]


def test_loader_memory_stays_bounded_for_a_large_original(ingest, settings, tmp_path):
    """#406/#414: one big original is hashed, stored and read back in chunks, never held whole in memory."""
    import tracemalloc

    size_mib = 128
    ds = build_ct_image()
    ds.Rows = ds.Columns = 8192
    ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
    ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 16, 15, 0
    ds.PixelData = bytes(8192 * 8192 * 2)
    big = write_dicom(ds, tmp_path / "big.dcm")
    del ds
    assert big.stat().st_size >= size_mib * 1024 * 1024
    digest = hashlib.sha256()
    with big.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    big_bytes = big.read_bytes()  # the fixture writes dict values as-is
    big.unlink()
    peaks = []

    def start_tracing(rows):  # runs after the script, right before the loader
        tracemalloc.start()
        return rows

    try:
        result = ingest({"big.dcm": big_bytes}, rows_hook=start_tracing, sha_override={"big.dcm": digest.hexdigest()})
        peaks.append(tracemalloc.get_traced_memory()[1])
    finally:
        tracemalloc.stop()

    assert result.created == 1
    assert peaks[0] < 32 * 1024 * 1024, f"loader peaked at {peaks[0] / 1024 ** 2:.0f} MiB for a {size_mib} MiB file"
    stored = _blobs(settings)[0]
    assert hashlib.sha256(stored.read_bytes()).hexdigest() == digest.hexdigest()


def test_inputs_open_refuses_unrecorded_paths(ingest):
    def redirect(rows):
        rows[0]["source_path"] = "../elsewhere.dcm"
        return rows

    with pytest.raises(UnrecordedInput):
        ingest({"a.dcm": build_ct_image()}, rows_hook=redirect)
    assert DicomFile.objects.count() == 0


def test_inputs_reader_open_and_record(ingest, tmp_path, project):
    path = tmp_path / "x.bin"
    path.write_bytes(b"abc")
    inputs = JobInputs.from_staged([("x.bin", object(), path)])
    with inputs.open("x.bin") as handle:
        assert handle.read() == b"abc"
    with pytest.raises(UnrecordedInput):
        inputs.open("y.bin")


def test_sha256_mismatch_with_the_staged_record_fails_the_job(ingest, settings):
    with pytest.raises(EtlLoadError):
        ingest({"a.dcm": build_ct_image()}, sha_override={"a.dcm": "f" * 64})
    assert DicomFile.objects.count() == 0
    assert _blobs(settings) == []


def test_non_dicom_files_are_skipped_and_kept_in_source(ingest):
    result = ingest({"a.dcm": build_ct_image(), "notes.txt": b"hello"})
    assert result.created == 1
    assert result.skipped == 1
    assert result.kept_inputs == ("notes.txt",)
    assert any("not_dicom" in line for line in result.log_lines)


def test_identical_duplicate_is_a_no_op_and_not_kept(ingest):
    ingest({"a.dcm": build_ct_image()})
    result = ingest({"a.dcm": build_ct_image()})
    assert (result.created, result.updated, result.skipped, result.kept_inputs) == (0, 0, 0, ())
    assert DicomFile.objects.count() == 1


def test_differing_duplicate_is_kept_in_source_in_skip_mode(ingest):
    ingest({"a.dcm": build_ct_image()})
    before = DicomFile.objects.get().content_sha256
    result = ingest({"a.dcm": build_ct_image(series_description="CHANGED")},
                    {**IDENTIFIERS, "duplicate_handling": "skip"})
    assert (result.updated, result.skipped, result.kept_inputs) == (0, 1, ("a.dcm",))
    assert DicomFile.objects.get().content_sha256 == before


def test_differing_duplicate_is_replaced_in_update_mode(ingest, settings, monkeypatch):
    ingest({"a.dcm": build_ct_image()})
    callbacks = []
    monkeypatch.setattr(
        "MiqaResearch.actions.dicom_ingest.load.transaction.on_commit", lambda fn: callbacks.append(fn))
    old = DicomFile.objects.get()
    old_sha = old.content_sha256
    result = ingest({"a.dcm": build_ct_image(series_description="CHANGED")},
                    {**IDENTIFIERS, "duplicate_handling": "update"})
    assert (result.updated, result.kept_inputs) == (1, ())
    new = DicomFile.objects.get()
    assert new.content_sha256 != old_sha
    assert len(_blobs(settings)) == 2  # the replaced blob is discarded only on commit
    for callback in callbacks:
        callback()
    assert len(_blobs(settings)) == 1


def test_project_duplicate_handling_is_the_default_for_inherit(ingest, project):
    project.dicom_duplicate_handling = "update"
    project.save()
    ingest({"a.dcm": build_ct_image()})
    result = ingest({"a.dcm": build_ct_image(series_description="CHANGED")})
    assert result.updated == 1


def test_implausible_pixel_dimensions_fail_the_job(ingest, settings):
    settings.DICOM_MAX_PIXEL_DIMENSIONS = 1
    with pytest.raises(EtlLoadError):
        ingest({"a.dcm": build_ct_image()})
    assert DicomFile.objects.count() == 0


def test_a_study_whose_rows_resolve_to_different_participants_fails(ingest, project):
    StudyParticipant.objects.create(alias1="P-1001", person_source_value="A", research_project=project)
    StudyParticipant.objects.create(alias1="P-1002", person_source_value="B", research_project=project)
    files = {
        "a.dcm": build_ct_image(patient_id="P-1001", sop_instance_uid="1.2.9.1"),
        "b.dcm": build_ct_image(patient_id="P-1002", sop_instance_uid="1.2.9.2"),
    }
    with pytest.raises(EtlLoadError):
        ingest(files)
    assert ParticipantKey.objects.count() == 0


# --- fault injection: zero rows and zero blobs, sources untouched ---

def _two_files():
    return {
        "a.dcm": build_ct_image(sop_instance_uid="1.2.9.1"),
        "b.dcm": build_ct_image(sop_instance_uid="1.2.9.2"),
    }


def _assert_nothing_left(settings):
    assert DicomFile.objects.count() == 0
    assert DicomSeries.objects.count() == 0
    assert DicomStudy.objects.count() == 0
    assert _blobs(settings) == []


def test_storage_failure_on_the_second_file_leaves_nothing(ingest, settings, monkeypatch):
    real = storage.store_file_bytes
    calls = []

    def flaky(dcm_file, data):
        calls.append(1)
        if len(calls) == 2:
            raise OSError("disk full")
        real(dcm_file, data)

    monkeypatch.setattr(storage, "store_file_bytes", flaky)
    with pytest.raises(EtlLoadError):
        ingest(_two_files())
    _assert_nothing_left(settings)


def test_read_back_mismatch_fails_the_job_and_leaves_nothing(ingest, settings, monkeypatch):
    monkeypatch.setattr(storage, "verify_stored_bytes", lambda dcm_file, sha: False)
    with pytest.raises(EtlLoadError):
        ingest(_two_files())
    _assert_nothing_left(settings)


def test_database_error_after_the_blob_is_written_leaves_nothing(ingest, settings, monkeypatch):
    def boom(series, size):
        raise RuntimeError("db down")

    monkeypatch.setattr(records, "add_file_size_to_series", boom)
    with pytest.raises(EtlLoadError):
        ingest(_two_files())
    _assert_nothing_left(settings)


def test_an_unexpected_error_logs_only_its_type_never_its_text(ingest, monkeypatch, caplog):
    """pydicom errors can quote header values (PHI): only the exception type name may reach the log."""
    def boom(series, size):
        raise RuntimeError("Invalid PatientName DOE^JOHN")

    monkeypatch.setattr(records, "add_file_size_to_series", boom)
    with caplog.at_level("DEBUG"), pytest.raises(EtlLoadError):
        ingest(_two_files())
    assert "DOE" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_failure_after_the_loader_returns_rolls_back_rows_and_leaves_only_sweepable_orphan_blobs(
        ingest, settings, monkeypatch):
    """A failure at the driver's final commit (e.g. a deferred constraint) happens after `load_dicom_instances`
    returned, so it cannot delete its blobs: the rows roll back, the blobs stay until the orphan sweep (#420,
    which exists for exactly this: "a crash before rollback") reports and later deletes them."""
    from datetime import timedelta

    from django.db import DatabaseError
    from django.utils import timezone

    from MiqaResearch.actions.dicom_ingest.orphan_sweep import sweep_orphans
    from MiqaResearch.etl_datatypes import loader as driver

    real = driver.get_datatype("dicom_instance")

    def failing_at_commit(**kwargs):
        real.loader(**kwargs)
        raise DatabaseError("deferred constraint failed at commit")

    monkeypatch.setattr(
        driver, "get_datatype", lambda name: SimpleNamespace(schema=real.schema, loader=failing_at_commit))
    with pytest.raises(DatabaseError):
        ingest(_two_files())
    assert (DicomFile.objects.count(), DicomSeries.objects.count(), DicomStudy.objects.count()) == (0, 0, 0)
    assert len(_blobs(settings)) == 2

    swept = sweep_orphans(delete=False, notify=False, record=False, now=timezone.now() + timedelta(days=365))
    assert swept.reportable == 2


# --- RT chain across Jobs ---

def _provenance_sources():
    return {s.series_instance_uid for p in DerivedObjectProvenance.objects.all() for s in p.source_series.all()}


@pytest.mark.parametrize("order", ["image_first", "rtstruct_first"])
def test_rt_chain_links_whichever_order_the_jobs_arrive_in(ingest, order):
    image = build_ct_image()
    rtstruct = build_rtstruct()
    first, second = (image, rtstruct) if order == "image_first" else (rtstruct, image)
    ingest({"first.dcm": first})
    ingest({"second.dcm": second})

    ct_series = DicomSeries.objects.get(modality="CT")
    rt_file = DicomFile.objects.get(series__modality="RTSTRUCT")
    summary = rt_file.metadata["rt_summary"]
    assert summary["type"] == "RTSTRUCT"
    assert summary["referenced_series_instance_uids"] == [ct_series.series_instance_uid]
    assert summary["referenced_image_sop_instance_uids"] == [DicomFile.objects.get(series=ct_series).sop_instance_uid]
    assert _provenance_sources() == {ct_series.series_instance_uid}


def test_rt_chain_never_crosses_between_different_unlinked_keys(ingest):
    """ADR 0035 (#415): an unlinked Study's derived object takes sources only from its own Participant Key."""
    ingest({"image.dcm": build_ct_image(patient_id="PATIENT-A")})
    ingest({"rtstruct.dcm": build_rtstruct(patient_id="PATIENT-B")})

    assert ParticipantKey.objects.filter(study_participant__isnull=True).count() == 2
    assert DerivedObjectProvenance.objects.count() == 1
    assert _provenance_sources() == set()


# --- payload summaries land in the stored metadata with pseudonymized UIDs (ports #121, #124 layer B) ---

def test_rdsr_dose_report_is_stored_and_the_file_has_no_geometry(ingest):
    ingest({"a.dcm": build_rdsr()})
    dcm = DicomFile.objects.get()
    totals = dcm.metadata["dose_report"]["totals"]
    assert totals["dose_area_product_total"] == {"value": 12.5, "unit": "Gy.m2"}
    assert len(dcm.metadata["dose_report"]["irradiation_events"]) == 2
    assert dcm.image_orientation_patient is None and dcm.pixel_spacing is None


@pytest.mark.parametrize(("build", "kind", "reference_key", "original"), [
    (build_rtstruct, "RTSTRUCT", "referenced_series_instance_uids", "1.2.9999.42.1.1002"),
    (build_rtplan, "RTPLAN", "referenced_structure_set_sop_instance_uids", "1.2.9999.42.6.6003"),
    (build_rtdose, "RTDOSE", "referenced_rt_plan_sop_instance_uids", "1.2.9999.42.7.7003"),
    (build_rtimage, "RTIMAGE", "referenced_rt_plan_sop_instance_uids", "1.2.9999.42.7.7003"),
])
def test_rt_summary_references_are_pseudonymized_and_no_original_uid_survives(
        ingest, project, build, kind, reference_key, original):
    ingest({"a.dcm": build()})
    summary = DicomFile.objects.get().metadata["rt_summary"]
    assert summary["type"] == kind
    assert summary[reference_key] == [pseudonymize_uid(original, project)]
    assert original not in json.dumps(DicomFile.objects.get().metadata)


def test_rtdose_grid_geometry_and_pseudonymized_frame_of_reference_are_stored(ingest, project):
    ingest({"a.dcm": build_rtdose()})
    dcm = DicomFile.objects.get()
    assert dcm.image_position_patient == [-10.0, -20.0, 50.5]
    assert dcm.pixel_spacing == [2.5, 2.5]
    assert dcm.frame_of_reference_uid == pseudonymize_uid("1.2.9999.42.1.1004", project)


def test_standard_image_carries_no_modality_summaries(ingest):
    ingest({"a.dcm": build_ct_image()})
    metadata = DicomFile.objects.get().metadata
    assert "dose_report" not in metadata and "rt_summary" not in metadata and "pathology_summary" not in metadata


def test_wsi_pathology_summary_and_pixel_spacing_are_stored(ingest, project):
    ds = build_wsi(pixel_spacing="0.0005\\0.0005", objective_lens_power=40.0)
    ingest({"a.dcm": ds})
    dcm = DicomFile.objects.get()
    summary = dcm.metadata["pathology_summary"]
    assert (summary["frame_count"], summary["image_type"], summary["objective_lens_power"]) == (3, "VOLUME", 40.0)
    assert dcm.pixel_spacing == [0.0005, 0.0005]
    assert dcm.frame_of_reference_uid == pseudonymize_uid(ds.FrameOfReferenceUID, project)
    assert dcm.image_orientation_patient is None and dcm.image_position_patient is None


def test_wsi_pyramid_levels_in_one_job_link_to_one_series(ingest):
    full_res = build_wsi(
        sop_instance_uid="1.2.9999.42.10.10003", total_pixel_matrix_rows=8, total_pixel_matrix_columns=8)
    thumbnail = build_wsi(
        sop_instance_uid="1.2.9999.42.10.20003", total_pixel_matrix_rows=2, total_pixel_matrix_columns=2,
        image_type=("ORIGINAL", "PRIMARY", "LABEL", "NONE"))
    result = ingest({"level0.dcm": full_res, "level1.dcm": thumbnail})
    assert result.created == 2
    assert DicomSeries.objects.count() == 1
    assert DicomFile.objects.count() == 2


def test_a_row_string_with_unicode_line_separators_survives_the_jsonl_round_trip(tmp_path):
    """`str.splitlines` splits on U+0085/U+2028/U+2029, which pydantic's JSON output leaves raw (found by the
    PatientID fuzzer): the result file and the loader must split rows on "\\n" only."""
    path = tmp_path / "result.jsonl"
    row = DicomInstanceRowSchema(
        source_path="a.dcm", status="skipped", skip_reason="not_dicom", study_description="a\x85b\u2028c\u2029d")
    path.write_text(json.dumps({"datatype": "dicom_instance"}) + "\n" + row.model_dump_json() + "\n")

    document = read_result_jsonl(path)
    [parsed] = _parse_rows(DicomInstanceRowSchema, document.rows_jsonl)

    assert parsed.study_description == "a\x85b\u2028c\u2029d"
