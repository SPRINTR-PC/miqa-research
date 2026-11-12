"""The native "DICOM -> dicom_instance" ETL Script (#417), run through the shim's `run_script` as the
sandbox runs it. Synthetic files only (built with pydicom at test time). Raw UIDs out, headers only.
Ports the RT/RDSR (#121) and pathology (#124) extraction tests of the retired ingest task.
"""
import importlib.util
import json

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from MiqaResearch.etl_config_schema import ConfigSchema, parse_config_schema
from MiqaResearch.etl_native_scripts import NATIVE_SCRIPTS, native_script_path
from mires_etl import contract
from mires_etl.schemas import DicomUid, UidField, get_schema
from mires_etl.schemas.dicom_instance import DicomInstanceRowSchema
from mires_etl.shim import read_result_jsonl, run_script
from tests.dicom_fixtures import (
    build_ct_image,
    build_generic_dataset,
    build_rdsr,
    build_rtdose,
    build_rtimage,
    build_rtplan,
    build_rtstruct,
    build_wsi,
    write_dicom,
)


@pytest.fixture(scope="module")
def script_main():
    spec = importlib.util.spec_from_file_location("dicom_instance", native_script_path("dicom_instance.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


@pytest.fixture
def run(tmp_path, script_main):
    counter = iter(range(10_000))

    def _run(files: dict, config: dict | None = None):
        root = tmp_path / f"run{next(counter)}"
        input_dir = root / "input"
        input_dir.mkdir(parents=True)
        for name, content in files.items():
            if isinstance(content, bytes):
                (input_dir / name).parent.mkdir(parents=True, exist_ok=True)
                (input_dir / name).write_bytes(content)
            else:
                write_dicom(content, input_dir / name)
        output_dir = root / "output"
        result = run_script(
            main=script_main, manifest={"datatype": "dicom_instance", "config": config or {}},
            input_dir=input_dir, output_dir=output_dir)
        rows = []
        if result.succeeded:
            text = read_result_jsonl(output_dir / contract.RESULT_FILENAME).rows_jsonl
            rows = [json.loads(line) for line in text.splitlines()]
        return result, rows

    return _run


def _one(run, ds, config=None):
    result, rows = run({"f.dcm": ds}, config)
    assert result.exit_code == contract.EXIT_SUCCESS, result.log + result.error
    assert len(rows) == 1
    return rows[0]


def test_schema_is_registered_and_native_script_listed():
    assert get_schema("dicom_instance") is DicomInstanceRowSchema
    assert any(n.datatype_name == "dicom_instance" and n.filename == "dicom_instance.py" for n in NATIVE_SCRIPTS)


def test_ct_image_row_has_raw_uids_header_and_geometry(run):
    row = _one(run, build_ct_image())

    assert row["status"] == "ok"
    assert row["study_instance_uid"] == "1.2.9999.42.1.1001"
    assert row["series_instance_uid"] == "1.2.9999.42.1.1002"
    assert row["sop_instance_uid"] == "1.2.9999.42.1.1003"
    assert row["sop_class_uid"] == "1.2.840.10008.5.1.4.1.1.2"
    assert row["modality"] == "CT"
    assert row["study_datetime"].startswith("2024-03-15T10:15:00.123456")
    assert row["rows"] == 4 and row["columns"] == 4
    assert row["image_orientation_patient"] == [1.0, 0.0, 0.0]
    assert row["image_position_patient"] == [-10.0, -20.0, 50.5]
    assert row["pixel_spacing"] == [0.5, 0.5]
    assert row["frame_of_reference_uid"] == "1.2.9999.42.1.1004"
    assert row["contains_burned_in_annotations"] is False
    assert row["payload"] == {"kind": "image"}
    assert "PixelData" not in row["tags"]
    assert row["tags"]["KVP"] == 120.0


def test_study_datetime_falls_back_through_series_acquisition_content(run):
    ds = build_ct_image(study_date="")
    ds.SeriesDate, ds.SeriesTime = "20240102", "030405"
    assert _one(run, ds)["study_datetime"].startswith("2024-01-02T03:04:05")

    ds = build_ct_image(study_date="")
    ds.ContentDate = "20230606"
    assert _one(run, ds)["study_datetime"].startswith("2023-06-06T00:00:00")

    assert _one(run, build_ct_image(study_date=""))["study_datetime"] is None


def test_identifiers_come_from_configured_tags(run):
    config = {"identifiers": {"tags": ["PatientID", "0010,1000", "AccessionNumber"]}}
    row = _one(run, build_ct_image(), config)

    assert row["identifiers"] == {"PatientID": "P-1001", "0010,1000": "OLD-ID-99"}


def test_no_identifiers_without_config(run):
    assert _one(run, build_ct_image())["identifiers"] == {}


def test_unknown_identifier_tag_fails_the_script(run):
    result, _ = run({"f.dcm": build_ct_image()}, {"identifiers": {"tags": ["NotARealTag"]}})

    assert result.exit_code == contract.EXIT_SCRIPT_ERROR


def test_rdsr_totals_and_events(run):
    payload = _one(run, build_rdsr())["payload"]

    assert payload["kind"] == "rdsr"
    assert payload["totals"]["dose_area_product_total"] == {"value": 12.5, "unit": "Gy.m2"}
    assert payload["totals"]["dose_rp_total"] == {"value": 0.85, "unit": "Gy"}
    events = payload["irradiation_events"]
    assert len(events) == 2
    assert events[0]["dose_area_product"] == {"value": 4.5, "unit": "Gy.m2"}
    assert events[0]["kvp"] == {"value": 81.0, "unit": "kV"}
    assert events[0]["exposure_time"] == {"value": 120.0, "unit": "ms"}
    assert events[1]["kvp"] == {"value": 110.0, "unit": "kV"}
    assert "dose_rp" not in events[1]


def test_rdsr_has_no_geometry_and_empty_tree_gives_empty_report(run):
    ds = build_rdsr()
    del ds.ContentSequence
    row = _one(run, ds)

    assert row["payload"] == {"kind": "rdsr", "totals": {}, "irradiation_events": []}
    assert row["image_orientation_patient"] is None and row["pixel_spacing"] is None


def test_rtstruct_references_are_raw_uids(run):
    row = _one(run, build_rtstruct())
    payload = row["payload"]

    assert payload["kind"] == "rtstruct"
    assert payload["referenced_frame_of_reference_uids"] == ["1.2.9999.42.1.1004"]
    assert payload["referenced_series_instance_uids"] == ["1.2.9999.42.1.1002"]
    assert payload["referenced_image_sop_instance_uids"] == ["1.2.9999.42.1.1003"]
    assert payload["roi_count"] == 2
    assert payload["rois"] == [
        {"number": 1, "name": "PTV", "interpreted_type": "PTV"},
        {"number": 2, "name": "BLADDER", "interpreted_type": "ORGAN"},
    ]
    assert row["frame_of_reference_uid"] is None and row["pixel_spacing"] is None


def test_rtplan_summary(run):
    row = _one(run, build_rtplan())
    payload = row["payload"]

    assert payload["kind"] == "rtplan"
    assert payload["referenced_structure_set_sop_instance_uids"] == ["1.2.9999.42.6.6003"]
    assert (payload["plan_label"], payload["plan_intent"]) == ("PLAN_A", "CURATIVE")
    assert (payload["beam_count"], payload["fraction_group_count"]) == (2, 1)
    assert row["frame_of_reference_uid"] is None


def test_rtdose_summary_and_grid_geometry(run):
    row = _one(run, build_rtdose())
    payload = row["payload"]

    assert payload["kind"] == "rtdose"
    assert payload["referenced_rt_plan_sop_instance_uids"] == ["1.2.9999.42.7.7003"]
    assert payload["referenced_structure_set_sop_instance_uids"] == ["1.2.9999.42.6.6003"]
    assert payload["dose_grid_scaling"] == 0.0025
    assert (payload["dose_units"], payload["dose_type"], payload["dose_summation_type"]) == ("GY", "PHYSICAL", "PLAN")
    assert row["image_position_patient"] == [-10.0, -20.0, 50.5]
    assert row["pixel_spacing"] == [2.5, 2.5]
    assert row["frame_of_reference_uid"] == "1.2.9999.42.1.1004"


def test_rtimage_summary(run):
    payload = _one(run, build_rtimage())["payload"]

    assert payload["kind"] == "rtimage"
    assert payload["referenced_rt_plan_sop_instance_uids"] == ["1.2.9999.42.7.7003"]
    assert payload["referenced_beam_number"] == 1
    assert payload["referenced_fraction_group_number"] == 1
    assert payload["rt_image_label"] == "PORTAL_1"
    assert payload["rt_image_sid"] == 1500.0


def test_wsi_pyramid_summary_and_spacing(run):
    row = _one(run, build_wsi(pixel_spacing="0.0005\\0.0005", objective_lens_power=40.0))
    payload = row["payload"]

    assert payload["kind"] == "wsi"
    assert payload["frame_count"] == 3
    assert (payload["tile_rows"], payload["tile_columns"]) == (4, 4)
    assert (payload["total_pixel_matrix_rows"], payload["total_pixel_matrix_columns"]) == (8, 8)
    assert payload["image_type"] == "VOLUME"
    assert payload["objective_lens_power"] == 40.0 and payload["optical_path_count"] == 1
    assert row["pixel_spacing"] == [0.0005, 0.0005]
    assert row["frame_of_reference_uid"] == "1.2.9999.42.10.10004"
    assert row["image_orientation_patient"] is None and row["image_position_patient"] is None
    assert row["number_of_frames"] == 3


def test_wsi_spacing_falls_back_to_per_frame_groups_or_none(run):
    ds = build_wsi(include_shared_functional_groups=False, per_frame_pixel_spacing="0.0004\\0.0004")
    assert _one(run, ds)["pixel_spacing"] == [0.0004, 0.0004]
    assert _one(run, build_wsi(include_shared_functional_groups=False))["pixel_spacing"] is None


def test_wsi_without_optical_path(run):
    payload = _one(run, build_wsi(objective_lens_power=None))["payload"]

    assert payload["objective_lens_power"] is None and payload["optical_path_count"] == 0


def test_unknown_sop_class_is_generic_never_rejected(run):
    row = _one(run, build_generic_dataset())

    assert row["payload"] == {"kind": "generic"}
    assert row["tags"]["XRayTubeCurrent"] == 2.5
    assert row["image_orientation_patient"] is None


def test_non_dicom_file_is_skipped(run):
    result, rows = run({"notes.txt": b"hello world", "empty.bin": b""})

    assert result.exit_code == contract.EXIT_SUCCESS
    assert {r["source_path"]: (r["status"], r["skip_reason"]) for r in rows} == {
        "empty.bin": ("skipped", "not_dicom"), "notes.txt": ("skipped", "not_dicom")}


def test_dicomdir_is_skipped_without_parsing(run):
    result, rows = run({"DICOMDIR": b"\x00" * 128 + b"DICM" + b"garbage"})

    assert result.exit_code == contract.EXIT_SUCCESS
    assert rows == [{**rows[0], "status": "skipped", "skip_reason": "dicomdir"}]


def test_directory_record_sop_class_is_skipped(run):
    ds = build_generic_dataset(sop_class_uid="1.2.840.10008.1.3.10")
    ds.file_meta.MediaStorageSOPClassUID = "1.2.840.10008.1.3.10"
    result, rows = run({"INDEX.dcm": ds})

    assert result.exit_code == contract.EXIT_SUCCESS
    assert rows[0]["status"] == "skipped" and rows[0]["skip_reason"] == "directory_sop_class"


def test_preamble_less_dicom_is_still_read(run, tmp_path):
    path = write_dicom(build_ct_image(), tmp_path / "np.dcm", with_preamble=False)
    result, rows = run({"np.dcm": path.read_bytes()})

    assert result.exit_code == contract.EXIT_SUCCESS
    assert rows[0]["status"] == "ok" and rows[0]["sop_instance_uid"] == "1.2.9999.42.1.1003"


def test_sop_instance_uid_falls_back_to_file_meta(run):
    ds = build_ct_image()
    del ds.SOPInstanceUID

    assert _one(run, ds)["sop_instance_uid"] == ds.file_meta.MediaStorageSOPInstanceUID


@pytest.mark.parametrize("missing", ["StudyInstanceUID", "SeriesInstanceUID"])
def test_dicom_missing_a_uid_fails_naming_the_file(run, missing):
    ds = build_ct_image()
    delattr(ds, missing)
    result, _ = run({"bad.dcm": ds})

    assert result.exit_code == contract.EXIT_SCRIPT_ERROR
    assert "bad.dcm" in result.log


def test_dicm_preamble_that_fails_to_parse_fails(run):
    result, _ = run({"trunc.dcm": b"\x00" * 128 + b"DICM" + b"\x08\x00\x16\x00UI\xff\xff"})

    assert result.exit_code == contract.EXIT_SCRIPT_ERROR
    assert "trunc.dcm" in result.log


def test_one_row_per_file_in_subdirectories_sorted(run):
    result, rows = run({
        "b/two.dcm": write_bytes(build_ct_image(sop_instance_uid="1.2.3.2")),
        "a/one.dcm": write_bytes(build_ct_image(sop_instance_uid="1.2.3.1")),
        "a/readme.txt": b"x",
    })

    assert result.exit_code == contract.EXIT_SUCCESS
    assert [r["source_path"] for r in rows] == ["a/one.dcm", "a/readme.txt", "b/two.dcm"]


def write_bytes(ds) -> bytes:
    import io
    buffer = io.BytesIO()
    ds.save_as(buffer, enforce_file_format=True)
    return buffer.getvalue()


def test_payload_is_strict_on_kind_and_extra_fields():
    base = {"source_path": "x", "status": "ok", "study_instance_uid": "1", "series_instance_uid": "2",
            "sop_instance_uid": "3"}
    with pytest.raises(ValueError):
        DicomInstanceRowSchema.model_validate({**base, "payload": {"kind": "bogus"}})
    with pytest.raises(ValueError):
        DicomInstanceRowSchema.model_validate({**base, "payload": {"kind": "image", "extra": 1}})
    with pytest.raises(ValueError):
        DicomInstanceRowSchema.model_validate({**base, "payload": None})
    with pytest.raises(ValueError):
        DicomInstanceRowSchema.model_validate({"source_path": "x", "status": "skipped"})


def _has_uid_marker(annotation) -> bool:
    import typing
    if isinstance(annotation, UidField):
        return True
    return any(_has_uid_marker(arg) for arg in (*typing.get_args(annotation), *getattr(annotation, "__metadata__", ())))


def test_uid_fields_are_marked_for_the_loader():
    from mires_etl.schemas.dicom_instance import RtstructPayload
    fields = DicomInstanceRowSchema.model_fields
    for name in ("study_instance_uid", "series_instance_uid", "sop_instance_uid", "frame_of_reference_uid"):
        assert _has_uid_marker(fields[name].rebuild_annotation()), name
    assert not _has_uid_marker(fields["sop_class_uid"].rebuild_annotation())
    assert _has_uid_marker(RtstructPayload.model_fields["referenced_image_sop_instance_uids"].rebuild_annotation())
    assert _has_uid_marker(DicomUid)


def test_config_schema_sidecar_validates_identifiers():
    schema = ConfigSchema(parse_config_schema(native_script_path("dicom_instance.schema.json").read_bytes()))

    assert schema.errors({"identifiers": {"tags": ["PatientID"], "match_person_source_value": True}}) == []
    assert schema.errors({"identifiers": {"tags": "PatientID"}})
    assert schema.errors({"identifiers": {"nope": 1}})
    assert schema.errors({"other": 1})


@pytest.fixture(scope="module")
def seed_bytes():
    return write_bytes(build_ct_image())


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(data=st.data())
def test_mutated_files_only_exit_with_defined_codes(data, seed_bytes, run):
    mutated = bytearray(seed_bytes)
    for _ in range(data.draw(st.integers(1, 8))):
        index = data.draw(st.integers(0, len(mutated) - 1))
        mutated[index] = data.draw(st.integers(0, 255))
    if data.draw(st.booleans()):
        del mutated[data.draw(st.integers(0, len(mutated))):]

    result, rows = run({"m.dcm": bytes(mutated)})

    assert result.exit_code in (contract.EXIT_SUCCESS, contract.EXIT_SCRIPT_ERROR, contract.EXIT_CONTRACT_VIOLATION)
    assert all(r["status"] in ("ok", "skipped") for r in rows)
