"""The ETL sandbox script contract & Python shim (#160): a platform entrypoint standing between
the sandboxed container and a Script author's own `main(ctx)` code. Exercised entirely in-process
here -- no real sandbox backend exists yet (#161/#165) -- against a fixture `/input` and a sample
script, to prove the contract itself: manifest/input in, `result.jsonl` (+ log) out, exit codes
distinguishing script errors from contract violations.
"""
import json
from datetime import date
from uuid import uuid4

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
from MiqaResearch.etl_shim import contract
from MiqaResearch.etl_shim.context import ScriptContext
from MiqaResearch.etl_shim.shim import read_result_jsonl, run_sandbox, run_script

# --- run_script: the mid-level seam (a script's `main`, already loaded) ----

def test_a_script_yielding_valid_rows_produces_a_well_formed_result_file(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    concept_id = str(uuid4())

    def main(ctx):
        assert isinstance(ctx, ScriptContext)
        yield {
            "alias1": "P001",
            "measurement_concept_id": concept_id,
            "measurement_type_concept_id": concept_id,
            "measurement_date": "2026-01-15",
            "measurement_source_value": "WEIGHT",
            "value_as_number": 71.5,
        }

    result = run_script(
        main=main, manifest={"datatype": "measurement", "config": {}}, input_dir=input_dir, output_dir=output_dir)

    assert result.exit_code == contract.EXIT_SUCCESS
    assert result.rows_written == 1
    result_path = output_dir / contract.RESULT_FILENAME
    lines = result_path.read_text().splitlines()
    assert json.loads(lines[0]) == {"datatype": "measurement"}
    assert json.loads(lines[1])["measurement_source_value"] == "WEIGHT"


def test_the_script_receives_the_input_dir_and_config_from_the_manifest(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "source.csv").write_text("a,b\n1,2\n")
    output_dir = tmp_path / "output"
    seen = {}

    def main(ctx):
        seen["input_dir"] = ctx.input_dir
        seen["config"] = ctx.config
        return iter(())

    run_script(
        main=main, manifest={"datatype": "measurement", "config": {"delimiter": ","}},
        input_dir=input_dir, output_dir=output_dir)

    assert seen["input_dir"] == input_dir
    assert (seen["input_dir"] / "source.csv").read_text() == "a,b\n1,2\n"
    assert seen["config"] == {"delimiter": ","}


def test_a_script_that_raises_exits_1_and_leaves_no_result_file(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"

    def main(ctx):
        raise RuntimeError("boom")
        yield  # pragma: no cover -- makes this a generator function

    result = run_script(
        main=main, manifest={"datatype": "measurement", "config": {}}, input_dir=input_dir, output_dir=output_dir)

    assert result.exit_code == contract.EXIT_SCRIPT_ERROR
    assert not (output_dir / contract.RESULT_FILENAME).exists()
    assert "boom" in result.error


def test_a_row_failing_the_datatype_schema_exits_2_and_leaves_no_result_file(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"

    def main(ctx):
        yield {"alias1": "P001"}  # missing every required measurement field

    result = run_script(
        main=main, manifest={"datatype": "measurement", "config": {}}, input_dir=input_dir, output_dir=output_dir)

    assert result.exit_code == contract.EXIT_CONTRACT_VIOLATION
    assert not (output_dir / contract.RESULT_FILENAME).exists()


def test_an_unregistered_datatype_in_the_manifest_exits_2(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"

    result = run_script(
        main=lambda ctx: iter(()), manifest={"datatype": "does-not-exist"}, input_dir=input_dir, output_dir=output_dir)

    assert result.exit_code == contract.EXIT_CONTRACT_VIOLATION


def test_stdout_and_stderr_from_the_script_are_captured_into_the_log(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"

    def main(ctx):
        print("hello from stdout")
        import sys
        print("hello from stderr", file=sys.stderr)
        return iter(())

    result = run_script(
        main=main, manifest={"datatype": "measurement", "config": {}}, input_dir=input_dir, output_dir=output_dir)

    assert "hello from stdout" in result.log
    assert "hello from stderr" in result.log
    assert (output_dir / contract.LOG_FILENAME).read_text() == result.log


def test_the_log_is_still_written_when_the_script_raises(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"

    def main(ctx):
        print("about to fail")
        raise RuntimeError("boom")
        yield  # pragma: no cover

    run_script(
        main=main, manifest={"datatype": "measurement", "config": {}}, input_dir=input_dir, output_dir=output_dir)

    assert "about to fail" in (output_dir / contract.LOG_FILENAME).read_text()


# --- run_sandbox: the top-level seam (loads manifest.json + script.py from a root dir) ----

def _write_sandbox_root(root, *, script_source, manifest):
    (root / contract.INPUT_DIRNAME).mkdir(parents=True)
    (root / contract.MANIFEST_FILENAME).write_text(json.dumps(manifest))
    (root / contract.SCRIPT_FILENAME).write_text(script_source)
    return root


def test_run_sandbox_loads_the_script_file_and_writes_result_and_log(tmp_path):
    concept_id = str(uuid4())
    script_source = f"""
def main(ctx):
    yield {{
        "alias1": "P001",
        "measurement_concept_id": "{concept_id}",
        "measurement_type_concept_id": "{concept_id}",
        "measurement_date": "2026-01-15",
        "measurement_source_value": "WEIGHT",
        "value_as_number": 71.5,
    }}
"""
    root = _write_sandbox_root(tmp_path, script_source=script_source, manifest={"datatype": "measurement"})

    result = run_sandbox(root)

    assert result.exit_code == contract.EXIT_SUCCESS
    assert (root / contract.OUTPUT_DIRNAME / contract.RESULT_FILENAME).exists()


def test_run_sandbox_reports_a_contract_violation_when_the_script_has_no_main(tmp_path):
    root = _write_sandbox_root(tmp_path, script_source="x = 1\n", manifest={"datatype": "measurement"})

    result = run_sandbox(root)

    assert result.exit_code == contract.EXIT_CONTRACT_VIOLATION


def test_run_sandbox_reports_a_contract_violation_for_invalid_manifest_json(tmp_path):
    (tmp_path / contract.INPUT_DIRNAME).mkdir()
    (tmp_path / contract.MANIFEST_FILENAME).write_text("not json")
    (tmp_path / contract.SCRIPT_FILENAME).write_text("def main(ctx):\n    return iter(())\n")

    result = run_sandbox(tmp_path)

    assert result.exit_code == contract.EXIT_CONTRACT_VIOLATION


def test_run_sandbox_exits_1_and_still_writes_a_log_when_the_script_raises_at_import_time(tmp_path):
    script_source = "print('loading side effect')\nraise RuntimeError('boom at import time')\n"
    root = _write_sandbox_root(tmp_path, script_source=script_source, manifest={"datatype": "measurement"})

    result = run_sandbox(root)

    assert result.exit_code == contract.EXIT_SCRIPT_ERROR
    assert not (root / contract.OUTPUT_DIRNAME / contract.RESULT_FILENAME).exists()
    log = (root / contract.OUTPUT_DIRNAME / contract.LOG_FILENAME).read_text()
    assert "loading side effect" in log
    assert "boom at import time" in log


def test_run_sandbox_reports_a_contract_violation_for_a_script_with_a_syntax_error(tmp_path):
    root = _write_sandbox_root(tmp_path, script_source="def main(ctx:\n", manifest={"datatype": "measurement"})

    result = run_sandbox(root)

    assert result.exit_code == contract.EXIT_CONTRACT_VIOLATION
    assert (root / contract.OUTPUT_DIRNAME / contract.LOG_FILENAME).exists()


def test_module_level_stdout_from_the_script_is_captured_into_the_log_on_success(tmp_path):
    script_source = "print('loaded ok')\n\n\ndef main(ctx):\n    return iter(())\n"
    root = _write_sandbox_root(tmp_path, script_source=script_source, manifest={"datatype": "measurement"})

    result = run_sandbox(root)

    assert result.exit_code == contract.EXIT_SUCCESS
    assert "loaded ok" in result.log


# --- read_result_jsonl: the reader counterpart, bridging into ticket 03's loader ----

def test_read_result_jsonl_splits_the_header_from_the_rows(tmp_path):
    result_path = tmp_path / contract.RESULT_FILENAME
    result_path.write_text(
        json.dumps({"datatype": "measurement"}) + "\n" + json.dumps({"alias1": "P001"}) + "\n")

    document = read_result_jsonl(result_path)

    assert document.datatype == "measurement"
    assert document.rows_jsonl == json.dumps({"alias1": "P001"}) + "\n"


# --- End-to-end: shim output flows straight through ticket 03's loader (#159) --------------

@pytest.fixture(autouse=True)
def mock_encryption_keys(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="


@pytest.fixture(autouse=True)
def _media_root(tmp_path_factory, settings):
    settings.MEDIA_ROOT = tmp_path_factory.mktemp("media")


@pytest.mark.django_db
def test_a_sample_script_run_through_the_shim_then_the_loader_lands_expected_rows(tmp_path):
    research_project = ResearchProject.objects.create(name="ETL shim test project", description="")
    participant = StudyParticipant.objects.create(
        alias1="ETL-SHIM-P001", person_source_value="SRC001", research_project=research_project)
    concept = Concept.objects.create(
        concept_name="Body weight", vocabulary_id="LOINC", concept_class_id="Clinical Observation",
        concept_code="29463-7", valid_start_date=date(2000, 1, 1), valid_end_date=date(2099, 12, 31))
    type_concept = Concept.objects.create(
        concept_name="Lab result", vocabulary_id="Provenance", concept_class_id="Type Concept",
        concept_code="lab-result", valid_start_date=date(2000, 1, 1), valid_end_date=date(2099, 12, 31))
    script = EtlScript.objects.create(name="Sample script", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=research_project)
    script_version = EtlScriptVersion.objects.create(
        script=script, version=1, source=SimpleUploadedFile("script.py", b"print('hi')"), sha256="0" * 64)
    binding = PipelineBinding.objects.create(
        project=research_project, source_bucket="incoming", source_prefix="dt/", script_version=script_version,
        raw_bucket="raw", raw_prefix="dt/")
    etl_job = EtlJob.objects.create(binding=binding, script_version=script_version)

    script_source = f"""
def main(ctx):
    yield {{
        "alias1": "{participant.alias1}",
        "measurement_concept_id": "{concept.concept_id}",
        "measurement_type_concept_id": "{type_concept.concept_id}",
        "measurement_date": "2026-01-15",
        "measurement_source_value": "WEIGHT",
        "value_as_number": 71.5,
    }}
"""
    root = _write_sandbox_root(tmp_path, script_source=script_source, manifest={"datatype": "measurement"})

    shim_result = run_sandbox(root)
    assert shim_result.exit_code == contract.EXIT_SUCCESS

    document = read_result_jsonl(root / contract.OUTPUT_DIRNAME / contract.RESULT_FILENAME)
    load_result = load_jsonl(
        datatype_name=document.datatype, project=research_project, etl_job=etl_job, jsonl_text=document.rows_jsonl)

    assert load_result.created == 1
    measurement = Measurement.objects.get()
    assert measurement.person_id == participant.id
    assert measurement.etl_job_id == etl_job.id
    assert measurement.value_as_number == 71.5
