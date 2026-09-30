"""The ETL sandbox R shim (#166), Python side: `run_r_sandbox` launches the R half (`Rscript
shim.R <root> <rows file>`) as a child process, then validates the rows it emitted through the same
`run_script` path the Python shim uses, so both languages share one schema source of truth and one
`result.jsonl`/log/exit-code contract. The R half itself needs a real R runtime and is exercised
against the built image in test_etl_sandbox_r_integration.py; here a small Python program stands in
for it, speaking the same child protocol: argv `<root> <rows file>`, rows as JSON lines, exit 0
(ran), 1 (script error) or 2 (contract violation, e.g. no `main`), stdout/stderr as the log.
"""
import json
import sys
from uuid import uuid4

from MiqaResearch.etl_shim import contract
from MiqaResearch.etl_shim.r_shim import run_r_sandbox


def _fake_r_child(tmp_path, body):
    """A stand-in for `Rscript shim.R`: `body` runs with `root` and `rows_path` bound."""
    child = tmp_path / "fake_r_child.py"
    child.write_text(
        "import json, sys\n"
        "from pathlib import Path\n"
        "root, rows_path = Path(sys.argv[1]), Path(sys.argv[2])\n"
        + body
    )
    return [sys.executable, str(child)]


def _sandbox_root(tmp_path, manifest=None):
    root = tmp_path / "sandbox"
    (root / contract.INPUT_DIRNAME).mkdir(parents=True)
    (root / contract.MANIFEST_FILENAME).write_text(
        json.dumps(manifest if manifest is not None else {"datatype": "measurement", "config": {}}))
    (root / contract.R_SCRIPT_FILENAME).write_text("main <- function(ctx) NULL\n")
    return root


def _measurement_row(**overrides):
    concept_id = str(uuid4())
    row = {
        "alias1": "P001",
        "measurement_concept_id": concept_id,
        "measurement_type_concept_id": concept_id,
        "measurement_date": "2026-01-15",
        "measurement_source_value": "WEIGHT",
        "value_as_number": 71.5,
    }
    row.update(overrides)
    return row


def test_emitted_rows_become_a_well_formed_result_file_with_the_childs_output_logged(tmp_path):
    root = _sandbox_root(tmp_path)
    row = _measurement_row()
    command = _fake_r_child(tmp_path, (
        "print('reading input')\n"
        f"rows_path.write_text(json.dumps({row!r}) + '\\n')\n"
    ))

    result = run_r_sandbox(root, command=command)

    assert result.exit_code == contract.EXIT_SUCCESS
    assert result.rows_written == 1
    lines = (root / contract.OUTPUT_DIRNAME / contract.RESULT_FILENAME).read_text().splitlines()
    assert json.loads(lines[0]) == {"datatype": "measurement"}
    assert json.loads(lines[1])["measurement_source_value"] == "WEIGHT"
    assert "reading input" in (root / contract.OUTPUT_DIRNAME / contract.LOG_FILENAME).read_text()


def test_the_child_is_given_the_sandbox_root(tmp_path):
    root = _sandbox_root(tmp_path)
    command = _fake_r_child(tmp_path, (
        "assert (root / 'script.R').exists()\n"
        "rows_path.write_text('')\n"
    ))

    result = run_r_sandbox(root, command=command)

    assert result.exit_code == contract.EXIT_SUCCESS
    assert result.rows_written == 0


def test_a_script_error_in_r_exits_1_with_its_output_logged_and_no_result_file(tmp_path):
    root = _sandbox_root(tmp_path)
    command = _fake_r_child(tmp_path, (
        "sys.stderr.write('Error in main(ctx) : could not parse lab file\\n')\n"
        "sys.exit(1)\n"
    ))

    result = run_r_sandbox(root, command=command)

    assert result.exit_code == contract.EXIT_SCRIPT_ERROR
    assert not (root / contract.OUTPUT_DIRNAME / contract.RESULT_FILENAME).exists()
    assert "could not parse lab file" in (root / contract.OUTPUT_DIRNAME / contract.LOG_FILENAME).read_text()


def test_a_contract_violation_reported_by_r_exits_2_with_no_result_file(tmp_path):
    root = _sandbox_root(tmp_path)
    command = _fake_r_child(tmp_path, (
        "print('script.R does not define a function `main`.')\n"
        "sys.exit(2)\n"
    ))

    result = run_r_sandbox(root, command=command)

    assert result.exit_code == contract.EXIT_CONTRACT_VIOLATION
    assert not (root / contract.OUTPUT_DIRNAME / contract.RESULT_FILENAME).exists()
    assert "does not define a function" in (root / contract.OUTPUT_DIRNAME / contract.LOG_FILENAME).read_text()


def test_an_emitted_row_failing_the_datatype_schema_exits_2_with_no_result_file(tmp_path):
    root = _sandbox_root(tmp_path)
    bad_row = _measurement_row(measurement_date="not a date")
    command = _fake_r_child(tmp_path, f"rows_path.write_text(json.dumps({bad_row!r}) + '\\n')\n")

    result = run_r_sandbox(root, command=command)

    assert result.exit_code == contract.EXIT_CONTRACT_VIOLATION
    assert not (root / contract.OUTPUT_DIRNAME / contract.RESULT_FILENAME).exists()


def test_an_unreadable_manifest_exits_2_without_launching_r(tmp_path):
    root = _sandbox_root(tmp_path)
    (root / contract.MANIFEST_FILENAME).write_text("{not json")
    marker = tmp_path / "launched"
    command = _fake_r_child(tmp_path, f"Path({str(marker)!r}).touch()\n")

    result = run_r_sandbox(root, command=command)

    assert result.exit_code == contract.EXIT_CONTRACT_VIOLATION
    assert not marker.exists()


def test_the_intermediate_rows_file_is_not_left_in_the_sandbox(tmp_path):
    root = _sandbox_root(tmp_path)
    row = _measurement_row()
    command = _fake_r_child(tmp_path, f"rows_path.write_text(json.dumps({row!r}) + '\\n')\n")

    run_r_sandbox(root, command=command)

    assert {path.name for path in root.iterdir()} == {
        contract.MANIFEST_FILENAME, contract.INPUT_DIRNAME, contract.OUTPUT_DIRNAME, contract.R_SCRIPT_FILENAME,
    }
