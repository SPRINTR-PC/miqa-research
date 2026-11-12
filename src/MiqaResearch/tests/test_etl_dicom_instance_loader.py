"""The `dicom_instance` loader (#418, spec #411): the native script's rows plus the staged originals in,
Studies/Series/Files and stored blobs out. Layer B/C: real script run in-process, real DB, local-disk
`DicomStorage`, the Job's `inputs` reader over a temp "scratch" directory.
"""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from contract.constants.etl import ETL_SCRIPT_ORIGIN_CUSTOM
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
from MiqaResearch.etl_datatypes.exceptions import UnrecordedInput
from MiqaResearch.etl_native_scripts import native_script_path
from mires_etl import contract
from mires_etl.shim import read_result_jsonl, run_script
from tests.dicom_fixtures import (
    build_ct_image,
    build_rtstruct,
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


def test_script_supplied_tag_dump_is_ignored_and_metadata_is_rebuilt_from_bytes(ingest):
    def poison(rows):
        for row in rows:
            row["tags"] = {"PatientName": "LEAKY^NAME", "Poison": "POISON"}
        return rows

    ingest({"a.dcm": build_ct_image()}, rows_hook=poison)
    dumped = json.dumps(DicomFile.objects.get().metadata)
    assert "POISON" not in dumped
    assert "LEAKY" not in dumped
    assert "SOPClassUID" in dumped


def test_identifier_tags_outside_the_allow_list_are_ignored(ingest):
    def widen(rows):
        for row in rows:
            row["identifiers"] = {**row["identifiers"], "PatientBirthDate": "19750131", "Whatever": "x"}
        return rows

    ingest({"a.dcm": build_ct_image()}, rows_hook=widen)
    assert list(ParticipantKey.objects.values_list("key_type", flat=True)) == ["dicom:PatientID"]


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
