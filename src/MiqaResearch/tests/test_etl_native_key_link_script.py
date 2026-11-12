"""The native "CSV → participant key link" ETL Script (#421), run through the shim's `run_script` as the
sandbox runs it. Its log must never carry key values or identities."""
import importlib.util
import json

import pytest

from MiqaResearch.etl_config_schema import ConfigSchema
from MiqaResearch.etl_native_scripts import NATIVE_SCRIPTS, native_script_path
from mires_etl import contract
from mires_etl.schemas import get_schema
from mires_etl.shim import read_result_jsonl, run_script


@pytest.fixture(scope="module")
def script_main():
    spec = importlib.util.spec_from_file_location(
        "csv_participant_key_link", native_script_path("csv_participant_key_link.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


def _run(tmp_path, script_main, csv_text, config=None):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "map.csv").write_text(csv_text, encoding="utf-8")
    output_dir = tmp_path / "output"
    result = run_script(
        main=script_main, manifest={"datatype": "participant_key_link", "config": config or {}},
        input_dir=input_dir, output_dir=output_dir)
    rows = []
    if result.succeeded:
        rows = [{k: v for k, v in json.loads(line).items() if v is not None}
                for line in read_result_jsonl(output_dir / contract.RESULT_FILENAME).rows_jsonl.splitlines()]
    return result, rows


def test_registered_as_a_native_script_for_the_datatype():
    native = next(s for s in NATIVE_SCRIPTS if s.name == "CSV → participant key link")
    assert native.datatype_name == "participant_key_link"
    assert native_script_path(native.filename).exists()


def test_defaults_map_key_value_and_alias1_columns(tmp_path, script_main):
    result, rows = _run(tmp_path, script_main, "key_value,alias1,person_source_value\nPSEUDO-1,A1,\n")

    assert result.exit_code == contract.EXIT_SUCCESS, result.log
    assert rows == [{"key_type": "dicom:PatientID", "key_value": "PSEUDO-1", "alias1": "A1"}]
    get_schema("participant_key_link").model_validate(rows[0])


def test_person_source_value_column_is_dash_stripped(tmp_path, script_main):
    _, rows = _run(tmp_path, script_main, "key_value,alias1,person_source_value\nP,,19900101-1234\n")

    assert rows == [{"key_type": "dicom:PatientID", "key_value": "P", "person_source_value": "199001011234"}]


def test_key_type_delimiter_and_column_names_are_configurable(tmp_path, script_main):
    config = {"key_type": "dicom:AccessionNumber", "delimiter": ";",
              "columns": {"key_value": "Accession", "person_source_value": "PNR"}}

    _, rows = _run(tmp_path, script_main, "Accession;PNR\nACC1;19900101-1234\n", config)

    assert rows == [{"key_type": "dicom:AccessionNumber", "key_value": "ACC1",
                     "person_source_value": "199001011234"}]


def test_a_row_with_neither_or_both_references_fails_naming_the_row_not_the_values(tmp_path, script_main):
    csv_text = "key_value,alias1,person_source_value\nSECRET-A,,\n"

    result, _ = _run(tmp_path, script_main, csv_text)

    assert result.exit_code == contract.EXIT_SCRIPT_ERROR
    assert "SECRET-A" not in result.log
    assert "2" in result.log


def test_a_missing_required_column_fails(tmp_path, script_main):
    result, _ = _run(tmp_path, script_main, "other\nx\n")

    assert result.exit_code == contract.EXIT_SCRIPT_ERROR
    assert "key_value" in result.log


def test_the_config_schema_accepts_documented_keys_and_fill_demographics():
    from MiqaResearch.etl_native_scripts import native_script_path as path

    schema = ConfigSchema(json.loads(path("csv_participant_key_link.schema.json").read_text()))
    assert schema.errors({}) == []
    assert schema.errors({"key_type": "dicom:PatientID", "delimiter": ";", "encoding": "utf-8",
                          "fill_demographics": True, "columns": {"key_value": "k"}}) == []
    assert schema.errors({"delimeter": ";"}) != []
