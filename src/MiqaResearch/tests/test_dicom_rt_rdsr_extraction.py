"""RDSR + radiotherapy extraction (#121) — exercises the `run_ingestion` seam and asserts on
the resulting `DicomFile` records, per the #98 testing decisions."""
import pytest

from helpers.dicom_uid import pseudonymize_uid
from MiqaResearch.data.models import DicomFile, ResearchProject
from MiqaResearch.tasks.dicom_handling.pipeline import run_ingestion
from tests.dicom_fixtures import (
    build_ct_image,
    build_generic_dataset,
    build_rdsr,
    build_rtdose,
    build_rtimage,
    build_rtplan,
    build_rtstruct,
    write_dicom,
)


@pytest.fixture(autouse=True)
def encryption_keys(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="


@pytest.fixture(autouse=True)
def allow_tmp_sources(settings, tmp_path):
    settings.DICOM_ALLOWED_SOURCE_ROOTS = [tmp_path]
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def research_project(db):
    return ResearchProject.objects.create(name="RT/RDSR project", description="Project for #121 tests")


def _ingest(research_project, tmp_path, ds, name="obj.dcm") -> DicomFile:
    report = run_ingestion(research_project, write_dicom(ds, tmp_path / name))
    assert report.counts["ingested"] == 1, report.results
    return DicomFile.objects.get(sop_instance_uid=pseudonymize_uid(ds.SOPInstanceUID, research_project))


def _pseudo(research_project, uid):
    return pseudonymize_uid(uid, research_project)


def test_rdsr_populates_accumulated_dose_totals(research_project, tmp_path):
    dcm_file = _ingest(research_project, tmp_path, build_rdsr())

    totals = dcm_file.metadata["dose_report"]["totals"]
    assert totals["dose_area_product_total"] == {"value": 12.5, "unit": "Gy.m2"}
    assert totals["dose_rp_total"] == {"value": 0.85, "unit": "Gy"}


def test_rdsr_populates_per_event_dose_kvp_and_exposure_time(research_project, tmp_path):
    dcm_file = _ingest(research_project, tmp_path, build_rdsr())

    events = dcm_file.metadata["dose_report"]["irradiation_events"]
    assert len(events) == 2
    assert events[0]["dose_area_product"] == {"value": 4.5, "unit": "Gy.m2"}
    assert events[0]["dose_rp"] == {"value": 0.3, "unit": "Gy"}
    assert events[0]["kvp"] == {"value": 81.0, "unit": "kV"}
    assert events[0]["exposure_time"] == {"value": 120.0, "unit": "ms"}
    assert events[0]["tube_current"] == {"value": 250.0, "unit": "mA"}
    # second event carries fewer values; absent ones are simply absent
    assert events[1]["kvp"] == {"value": 110.0, "unit": "kV"}
    assert "dose_rp" not in events[1]


def test_rdsr_leaves_image_geometry_empty(research_project, tmp_path):
    dcm_file = _ingest(research_project, tmp_path, build_rdsr())

    assert dcm_file.image_orientation_patient is None
    assert dcm_file.image_position_patient is None
    assert dcm_file.pixel_spacing is None


def test_rtstruct_summarizes_cross_references_with_pseudonymized_uids(research_project, tmp_path):
    ds = build_rtstruct()
    dcm_file = _ingest(research_project, tmp_path, ds)

    summary = dcm_file.metadata["rt_summary"]
    assert summary["type"] == "RTSTRUCT"
    assert summary["referenced_frame_of_reference_uids"] == [_pseudo(research_project, "1.2.9999.42.1.1004")]
    assert summary["referenced_series_instance_uids"] == [_pseudo(research_project, "1.2.9999.42.1.1002")]
    assert summary["referenced_image_sop_instance_uids"] == [_pseudo(research_project, "1.2.9999.42.1.1003")]
    assert summary["roi_count"] == 2
    assert summary["rois"] == [
        {"number": 1, "name": "PTV", "interpreted_type": "PTV"},
        {"number": 2, "name": "BLADDER", "interpreted_type": "ORGAN"},
    ]


def test_rtstruct_leaves_image_geometry_empty_without_error(research_project, tmp_path):
    dcm_file = _ingest(research_project, tmp_path, build_rtstruct())

    assert dcm_file.image_orientation_patient is None
    assert dcm_file.image_position_patient is None
    assert dcm_file.pixel_spacing is None
    assert dcm_file.frame_of_reference_uid is None


def test_rtplan_summarizes_referenced_structure_set_and_plan_content(research_project, tmp_path):
    dcm_file = _ingest(research_project, tmp_path, build_rtplan())

    summary = dcm_file.metadata["rt_summary"]
    assert summary["type"] == "RTPLAN"
    assert summary["referenced_structure_set_sop_instance_uids"] == [
        _pseudo(research_project, "1.2.9999.42.6.6003")
    ]
    assert summary["plan_label"] == "PLAN_A"
    assert summary["plan_intent"] == "CURATIVE"
    assert summary["beam_count"] == 2
    assert summary["fraction_group_count"] == 1


def test_rtplan_leaves_image_geometry_empty_without_error(research_project, tmp_path):
    dcm_file = _ingest(research_project, tmp_path, build_rtplan())

    assert dcm_file.image_orientation_patient is None
    assert dcm_file.pixel_spacing is None
    assert dcm_file.frame_of_reference_uid is None


def test_rtdose_summarizes_plan_reference_and_dose_scaling(research_project, tmp_path):
    dcm_file = _ingest(research_project, tmp_path, build_rtdose())

    summary = dcm_file.metadata["rt_summary"]
    assert summary["type"] == "RTDOSE"
    assert summary["referenced_rt_plan_sop_instance_uids"] == [_pseudo(research_project, "1.2.9999.42.7.7003")]
    assert summary["referenced_structure_set_sop_instance_uids"] == [
        _pseudo(research_project, "1.2.9999.42.6.6003")
    ]
    assert summary["dose_grid_scaling"] == 0.0025
    assert summary["dose_units"] == "GY"
    assert summary["dose_type"] == "PHYSICAL"
    assert summary["dose_summation_type"] == "PLAN"


def test_rtdose_populates_dose_grid_geometry(research_project, tmp_path):
    dcm_file = _ingest(research_project, tmp_path, build_rtdose())

    assert dcm_file.image_position_patient == [-10.0, -20.0, 50.5]
    assert dcm_file.pixel_spacing == [2.5, 2.5]
    assert dcm_file.frame_of_reference_uid == _pseudo(research_project, "1.2.9999.42.1.1004")


def test_rtimage_summarizes_plan_beam_and_fraction_group(research_project, tmp_path):
    dcm_file = _ingest(research_project, tmp_path, build_rtimage())

    summary = dcm_file.metadata["rt_summary"]
    assert summary["type"] == "RTIMAGE"
    assert summary["referenced_rt_plan_sop_instance_uids"] == [_pseudo(research_project, "1.2.9999.42.7.7003")]
    assert summary["referenced_beam_number"] == 1
    assert summary["referenced_fraction_group_number"] == 1
    assert summary["rt_image_label"] == "PORTAL_1"
    assert summary["rt_image_sid"] == 1500.0


def test_rt_summary_never_contains_original_uids(research_project, tmp_path):
    dcm_file = _ingest(research_project, tmp_path, build_rtstruct())

    summary_text = str(dcm_file.metadata["rt_summary"])
    for original in ("1.2.9999.42.1.1004", "1.2.9999.42.1.1002", "1.2.9999.42.1.1003"):
        assert original not in summary_text


def test_unhandled_sop_class_still_falls_through_to_generic_handler(research_project, tmp_path):
    dcm_file = _ingest(research_project, tmp_path, build_generic_dataset())

    assert "dose_report" not in dcm_file.metadata
    assert "rt_summary" not in dcm_file.metadata
    assert dcm_file.metadata["XRayTubeCurrent"] == 2.5


def test_standard_image_is_unaffected_by_modality_handlers(research_project, tmp_path):
    dcm_file = _ingest(research_project, tmp_path, build_ct_image())

    assert "dose_report" not in dcm_file.metadata
    assert "rt_summary" not in dcm_file.metadata
    assert dcm_file.image_orientation_patient == [1.0, 0.0, 0.0]


def test_rdsr_with_empty_content_tree_ingests_with_empty_report(research_project, tmp_path):
    ds = build_rdsr()
    del ds.ContentSequence
    dcm_file = _ingest(research_project, tmp_path, ds)

    assert dcm_file.metadata["dose_report"] == {"totals": {}, "irradiation_events": []}
