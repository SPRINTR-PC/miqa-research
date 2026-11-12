"""Generic JSONL batch driver for registered ETL Datatypes (#159).

Parses every line against the Datatype's schema, then hands the validated rows to the
Datatype's own loader inside one atomic transaction -- so a single bad or unresolvable row
(malformed row, unresolvable Participant Reference, dangling Concept reference, ...) rolls back
the whole batch, never a partial write. This module only builds the registry + loader as a
direct Python interface, exercised with fixture JSONL; no sandbox or orchestrator involved yet.
"""
from django.db import transaction
from pydantic import BaseModel, ValidationError

from MiqaResearch.data.models import EtlJob, ResearchProject

from .exceptions import EtlJobProjectMismatch, EtlRowError
from .inputs import NO_INPUTS, JobInputs
from .registry import LoadResult, get_datatype


def load_jsonl(
    *, datatype_name: str, project: ResearchProject, etl_job: EtlJob, jsonl_text: str,
    inputs: JobInputs = NO_INPUTS,
) -> LoadResult:
    if etl_job.binding.project_id != project.id:
        raise EtlJobProjectMismatch(f"EtlJob {etl_job.id} belongs to a different project than {project}.")

    registration = get_datatype(datatype_name)
    rows = _parse_rows(registration.schema, jsonl_text)
    with transaction.atomic():
        return registration.loader(project=project, etl_job=etl_job, rows=rows, inputs=inputs)


def _parse_rows(schema: type[BaseModel], jsonl_text: str) -> list[BaseModel]:
    rows = []
    # split on "\n" only: str.splitlines also splits on U+0085/U+2028/U+2029, which JSON strings may contain raw
    for line_number, line in enumerate(jsonl_text.split("\n"), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(schema.model_validate_json(line))
        except ValidationError as exc:
            raise EtlRowError(f"Row {line_number} failed validation: {exc}") from exc
    return rows
