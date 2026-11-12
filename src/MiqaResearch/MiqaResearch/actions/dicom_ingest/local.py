"""Ingest a local folder through the native `dicom_instance` script and loader, outside the ETL orchestrator.

For dev tooling only (the `viewer_harness_seed` command, tests): production ingestion runs as an ETL Job
polled from an S3 Source Location. This runs the same script in-process and the same loader inside a
real, throwaway Job so the two paths cannot diverge. One call is one all-or-nothing Job.
"""
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path

import pydicom
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction

from contract.constants.etl import ETL_SCRIPT_ORIGIN_CUSTOM
from helpers.db_fields import get_deterministic_hash
from helpers.person_source_value import format_person_source_value
from helpers.study_participant_alias import generate_study_participant_alias1
from MiqaResearch.data.models import (
    EtlJob,
    EtlJobInput,
    EtlScript,
    EtlScriptVersion,
    PipelineBinding,
    StudyParticipant,
)
from MiqaResearch.etl_datatypes import JobInputs, load_jsonl
from MiqaResearch.etl_datatypes.registry import LoadResult
from MiqaResearch.etl_native_scripts import native_script_path
from mires_etl import contract
from mires_etl.shim import read_result_jsonl, run_script

# PatientID is the Participant Key; an existing participant is matched on its person source value too.
DEFAULT_CONFIG = {"identifiers": {"tags": ["PatientID"], "match_person_source_value": True}}


def _script_main():
    spec = importlib.util.spec_from_file_location("dicom_instance", native_script_path("dicom_instance.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


def run_native_script(input_dir: Path, output_dir: Path, config: dict | None) -> list[dict]:
    """The script's rows (dicts) for every file under `input_dir`."""
    result = run_script(
        main=_script_main(), manifest={"datatype": "dicom_instance", "config": config or {}},
        input_dir=input_dir, output_dir=output_dir)
    if result.exit_code != contract.EXIT_SUCCESS:
        raise RuntimeError(f"dicom_instance script failed: {result.log}{result.error}")
    text = read_result_jsonl(output_dir / contract.RESULT_FILENAME).rows_jsonl
    return [json.loads(line) for line in text.split("\n") if line.strip()]


def create_missing_participants(project, input_dir: Path) -> None:
    """Create the Study Participant each file's PatientID names, when none matches yet (dev data only)."""
    for path in sorted(p for p in input_dir.rglob("*") if p.is_file()):
        try:
            ds = pydicom.dcmread(str(path), force=True, stop_before_pixels=True)
        except Exception:
            continue
        raw = ds.get("PatientID")
        patient_id = format_person_source_value(str(raw)) if raw is not None else ""
        if not patient_id or StudyParticipant.objects.filter(
                research_project=project, person_source_value_hash=get_deterministic_hash(patient_id)).exists():
            continue
        StudyParticipant.objects.create(
            person_source_value=patient_id, alias1=generate_study_participant_alias1(),
            name=str(ds.get("PatientName") or "").strip() or None, research_project=project)


def create_local_job(project, input_dir: Path, config: dict | None):
    """A throwaway Job with one recorded input per file under `input_dir`; returns `(job, JobInputs)`."""
    script = EtlScript.objects.create(name="local dicom ingest", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=project)
    version = EtlScriptVersion.objects.create(
        script=script, version=1, source=SimpleUploadedFile("script.py", b"local"), sha256="0" * 64)
    prefix = f"local/{script.pk}/"
    binding = PipelineBinding.objects.create(
        project=project, source_bucket="local", source_prefix=prefix, script_version=version,
        raw_bucket="local-raw", raw_prefix=prefix)
    job = EtlJob.objects.create(binding=binding, script_version=version, config_snapshot=config or {})
    pairs = []
    for path in sorted(p for p in input_dir.rglob("*") if p.is_file()):
        name = path.relative_to(input_dir).as_posix()
        job_input = EtlJobInput.objects.create(
            job=job, bucket="local", key=prefix + name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            size_bytes=path.stat().st_size)
        pairs.append((name, job_input, path))
    return job, JobInputs.from_staged(pairs)


def ingest_local_folder(
        project, folder: Path, *, config: dict | None = DEFAULT_CONFIG, link_participants: bool = False) -> LoadResult:
    """Run the script over `folder` and load its rows as one Job; raises `EtlLoadError` on any failure.

    `link_participants` first creates the Study Participants the files' PatientIDs name, for dev data."""
    folder = Path(folder)
    if link_participants:
        create_missing_participants(project, folder)
    with tempfile.TemporaryDirectory(prefix="dicom-ingest-") as scratch:
        rows = run_native_script(folder, Path(scratch) / "output", config)
        with transaction.atomic():
            job, inputs = create_local_job(project, folder, config)
            return load_jsonl(
                datatype_name="dicom_instance", project=project, etl_job=job,
                jsonl_text="\n".join(json.dumps(row) for row in rows), inputs=inputs)
