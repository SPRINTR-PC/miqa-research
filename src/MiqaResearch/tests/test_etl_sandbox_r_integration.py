"""Real-container conformance suite for the R sandbox image (#166) -- opt-in and
`long_running`-marked like the Python image's own (test_etl_sandbox_compose_integration.py): it
needs a Docker/Podman daemon and the `mires-etl-sandbox-r:dev` image (`etl_sandbox_r.Dockerfile`,
built FROM the Python image), and skips gracefully when either isn't available.

Proves the R half of the shim (`shim.R`) against the same file contract and exit codes as the
Python shim: an R Script's `main(ctx)` sees its staged input and config, each `emit(row)` lands in
`result.jsonl` and loads through #159's `load_jsonl` into the same kind of rows as the Python
sample, and a script error / missing `main` / schema-failing row map to exit 1 / 2 / 2.
"""
import json
from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from contract.constants.etl import ETL_SCRIPT_ORIGIN_CUSTOM
from MiqaResearch.data.models import (
    Concept,
    EtlJob,
    EtlScript,
    EtlScriptVersion,
    Measurement,
    PipelineBinding,
    ResearchProject,
    StudyParticipant,
)
from MiqaResearch.etl_datatypes import load_jsonl
from MiqaResearch.etl_sandbox import SandboxRunSpec, resolve_limits
from MiqaResearch.etl_sandbox.compose_backend import ComposeSandboxBackend
from mires_etl import contract
from tests.sandbox_docker import docker_client_for
from tests.sandbox_staging import stage_inputs

IMAGE_KEY = "r-etl-v1"
IMAGE_REF = "mires-etl-sandbox-r:dev"


@pytest.fixture
def docker_client(settings):
    return docker_client_for(IMAGE_REF, settings=settings)


@pytest.fixture(autouse=True)
def r_image_allowlisted(settings):
    settings.SANDBOX_IMAGE_ALLOWLIST = {IMAGE_KEY: IMAGE_REF}


@pytest.fixture(autouse=True)
def mock_encryption_keys(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="


@pytest.fixture(autouse=True)
def _media_root(tmp_path_factory, settings):
    settings.MEDIA_ROOT = tmp_path_factory.mktemp("media")


def _run(docker_client, script_source: str, *, input_files=None, config=None):
    spec = SandboxRunSpec(
        run_id="r-integration-test-run", image_key=IMAGE_KEY,
        manifest={"datatype": "measurement", "config": config or {}}, script_source=script_source.encode(),
        input_files=input_files or [], limits=resolve_limits())
    return ComposeSandboxBackend(client=docker_client).run(spec)


@pytest.mark.long_running
@pytest.mark.django_db
def test_a_sample_r_script_runs_isolated_in_a_real_container_and_its_rows_load(docker_client, tmp_path):
    research_project = ResearchProject.objects.create(name="ETL R sandbox integration project", description="")
    participant = StudyParticipant.objects.create(
        alias1="ETL-R-P001", person_source_value="SRC001", research_project=research_project)
    concept = Concept.objects.create(
        concept_name="Body weight", vocabulary_id="LOINC", concept_class_id="Clinical Observation",
        concept_code="29463-7", valid_start_date=date(2000, 1, 1), valid_end_date=date(2099, 12, 31))
    type_concept = Concept.objects.create(
        concept_name="Lab result", vocabulary_id="Provenance", concept_class_id="Type Concept",
        concept_code="lab-result", valid_start_date=date(2000, 1, 1), valid_end_date=date(2099, 12, 31))
    script = EtlScript.objects.create(
        name="R sandbox sample script", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=research_project)
    script_version = EtlScriptVersion.objects.create(
        script=script, version=1, source=SimpleUploadedFile("script.R", b"main <- function(ctx) NULL"),
        sha256="0" * 64, image_key=IMAGE_KEY)
    binding = PipelineBinding.objects.create(
        project=research_project, source_bucket="incoming", source_prefix="dt/", script_version=script_version,
        raw_bucket="raw", raw_prefix="dt/")
    etl_job = EtlJob.objects.create(binding=binding, script_version=script_version)

    # Reads the staged CSV and the manifest's config, and records whether its own outbound
    # connection attempt succeeded -- a real observation from inside the container.
    script_source = f"""
main <- function(ctx) {{
  weights <- read.csv(file.path(ctx$input_dir, "weights.csv"))
  network_reachable <- tryCatch({{
    close(socketConnection("8.8.8.8", 53, timeout = 3))
    TRUE
  }}, error = function(e) FALSE, warning = function(w) FALSE)
  cat("rows in input:", nrow(weights), "\\n")
  for (i in seq_len(nrow(weights))) {{
    emit(list(
      alias1 = weights$alias1[[i]],
      measurement_concept_id = "{concept.concept_id}",
      measurement_type_concept_id = "{type_concept.concept_id}",
      measurement_date = "2026-01-15",
      measurement_source_value = ctx$config$source_value,
      value_as_number = weights$kg[[i]],
      value_source_value = if (network_reachable) "network-reachable" else "network-blocked"
    ))
  }}
}}
"""
    result = _run(
        docker_client, script_source,
        input_files=stage_inputs(tmp_path, {"weights.csv": f"alias1,kg\n{participant.alias1},71.5\n".encode()}),
        config={"source_value": "WEIGHT"})

    assert result.exit_code == contract.EXIT_SUCCESS, result.log.decode(errors="replace")
    assert b"rows in input: 1" in result.log
    lines = result.result_jsonl.splitlines()
    header = json.loads(lines[0])
    assert header == {"datatype": "measurement"}
    rows_jsonl = b"\n".join(lines[1:]).decode() + "\n"

    load_result = load_jsonl(
        datatype_name=header["datatype"], project=research_project, etl_job=etl_job, jsonl_text=rows_jsonl)

    assert load_result.created == 1
    measurement = Measurement.objects.get()
    assert measurement.person_id == participant.id
    assert measurement.etl_job_id == etl_job.id
    assert measurement.value_as_number == 71.5
    assert measurement.measurement_source_value == "WEIGHT"
    assert measurement.value_source_value == "network-blocked"


@pytest.mark.long_running
def test_an_r_script_that_stops_exits_1_with_its_error_logged_and_no_result(docker_client):
    result = _run(docker_client, 'main <- function(ctx) stop("could not parse lab file")\n')

    assert result.exit_code == contract.EXIT_SCRIPT_ERROR
    assert result.result_jsonl is None
    assert b"could not parse lab file" in result.log


@pytest.mark.long_running
def test_an_r_script_without_main_exits_2(docker_client):
    result = _run(docker_client, 'helper <- function(x) x\n')

    assert result.exit_code == contract.EXIT_CONTRACT_VIOLATION
    assert result.result_jsonl is None
    assert b"does not define a function `main`" in result.log


@pytest.mark.long_running
def test_an_r_script_that_does_not_parse_exits_2(docker_client):
    result = _run(docker_client, 'main <- function(ctx) {\n')

    assert result.exit_code == contract.EXIT_CONTRACT_VIOLATION
    assert result.result_jsonl is None


@pytest.mark.long_running
def test_an_emitted_row_failing_the_datatype_schema_exits_2(docker_client):
    result = _run(docker_client, 'main <- function(ctx) emit(list(alias1 = "P001", measurement_date = "nope"))\n')

    assert result.exit_code == contract.EXIT_CONTRACT_VIOLATION
    assert result.result_jsonl is None
