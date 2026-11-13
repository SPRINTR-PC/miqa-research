"""Test helper: run the native `dicom_instance` script plus the loader in-process over local files.

The way tests get DICOM into the database (the old local-folder pipeline is retired, #419). One call is one ETL
Job (all-or-nothing). By default it also creates the Study Participant the file's PatientID names, so
consumer tests get a linked Study as before (the loader itself never creates participants, ADR 0035).
"""
import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pydicom

from helpers.dicom_uid import pseudonymize_uid
from MiqaResearch.actions.dicom_ingest.local import (
    DEFAULT_CONFIG,
    create_local_job,
    create_missing_participants,
    run_native_script,
)
from MiqaResearch.etl_datatypes import load_jsonl

__all__ = ["DEFAULT_CONFIG", "IngestReport", "ingest_files"]


@dataclass
class IngestedFile:
    source_path: str
    sop_instance_uid: str | None  # pseudonymized; None when the file is not DICOM


@dataclass
class IngestReport:
    load_result: object
    results: list[IngestedFile] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return {
            "ingested": self.load_result.created + self.load_result.updated,
            "skipped": self.load_result.skipped,
        }


def ingest_files(
        project, source, *, config: dict | None = DEFAULT_CONFIG, duplicate_handling: str | None = None,
        link_participants: bool = True, rows_hook=None) -> IngestReport:
    """Ingest a file or a folder as one Job; returns an `IngestReport` (raises `EtlLoadError` on failure).

    `rows_hook(rows) -> rows` edits the script's rows before loading."""
    source = Path(source)
    with tempfile.TemporaryDirectory(prefix="dicom-ingest-test-") as scratch:
        input_dir = Path(scratch) / "input"
        input_dir.mkdir()
        if source.is_dir():
            shutil.copytree(source, input_dir, dirs_exist_ok=True)
        else:
            shutil.copy(source, input_dir / source.name)
        if link_participants:
            create_missing_participants(project, input_dir)
        snapshot = dict(config or {})
        if duplicate_handling:
            snapshot["duplicate_handling"] = duplicate_handling
        rows = run_native_script(input_dir, Path(scratch) / "output", snapshot)
        if rows_hook:
            rows = rows_hook(rows)
        job, inputs = create_local_job(project, input_dir, snapshot)
        load_result = load_jsonl(
            datatype_name="dicom_instance", project=project, etl_job=job,
            jsonl_text="\n".join(json.dumps(r) for r in rows), inputs=inputs)
        results = [
            IngestedFile(p.relative_to(input_dir).as_posix(), _pseudonymized_sop(project, p))
            for p in sorted(p for p in input_dir.rglob("*") if p.is_file())
        ]
        return IngestReport(load_result=load_result, results=results)


def _pseudonymized_sop(project, path: Path) -> str | None:
    try:
        ds = pydicom.dcmread(str(path), force=True, stop_before_pixels=True)
    except Exception:
        return None
    sop = str(ds.get("SOPInstanceUID") or "").strip()
    return pseudonymize_uid(sop, project) if sop else None
