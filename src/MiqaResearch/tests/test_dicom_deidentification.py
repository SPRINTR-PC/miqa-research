"""De-identification Profile sanitizer (#273, ADR 0028).

Seam: `helpers.dicom_deidentification.deidentify(dataset, ...)` — a pydicom
Dataset in, a de-identified copy out. Shared by the ingestion metadata dump,
WADO-RS /metadata (#275) and the viewer-built SR/SEG ingest (#287).
"""
import pytest
from pydicom.dataset import Dataset

from helpers.dicom_deidentification import deidentify
from helpers.dicom_uid import pseudonymize_uid
from MiqaResearch.data.models import ResearchProject
from tests.dicom_fixtures import build_ct_image

ALIAS = "MIRES-0042"


@pytest.fixture(autouse=True)
def encryption_keys(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="


@pytest.fixture
def research_project(db):
    return ResearchProject.objects.create(name="De-id project", description="#273")


def _deid(ds, research_project, **kwargs):
    return deidentify(ds, research_project=research_project, participant_alias=ALIAS, **kwargs)


def _private_block(ds, group, creator, block, elements):
    """Add a private creator at (group, 00<block>) and its (group, <block><offset>) elements."""
    ds.add_new((group << 16) | block, "LO", creator)
    for offset, vr, value in elements:
        ds.add_new((group << 16) | (block << 8) | offset, vr, value)


def test_basic_profile_gaps_are_removed_or_emptied(research_project):
    ds = build_ct_image()
    ds.AccessionNumber = "ACC-123"
    original = Dataset()
    original.PatientName = "OLD^NAME"
    ds.OriginalAttributesSequence = [original]
    icon = Dataset()
    icon.Rows = 2
    ds.IconImageSequence = [icon]
    ds.OperatorsName = "OPERATOR^ONE"
    ds.PatientComments = "lives next door"
    ds.add_new(0x00321060, "LO", "CT HEAD")  # RequestedProcedureDescription

    out = _deid(ds, research_project)

    assert out.AccessionNumber == ""
    assert "OriginalAttributesSequence" not in out
    assert "IconImageSequence" not in out
    assert "PatientComments" not in out
    assert not out.get("RequestedProcedureDescription")  # X/Z: removed or emptied
    assert "OPERATOR^ONE" not in str(out)
    assert "OLD^NAME" not in str(out)
    assert "19750131" not in str(out)  # PatientBirthDate
    assert "OLD-ID-99" not in str(out)  # OtherPatientIDs
    assert "SMITH^ARTHUR" not in str(out)  # ReferringPhysicianName


def test_input_dataset_is_left_untouched(research_project):
    ds = build_ct_image()

    _deid(ds, research_project)

    assert ds.PatientName == "DOE^JANE"
    assert ds.StudyInstanceUID == "1.2.9999.42.1.1001"
    assert "PatientIdentityRemoved" not in ds


def test_patient_name_and_id_become_the_participant_pseudonym(research_project):
    out = _deid(build_ct_image(), research_project)

    assert out.PatientName == ALIAS
    assert out.PatientID == ALIAS


def test_non_safe_private_tags_are_removed_and_safe_ones_kept(research_project):
    ds = build_ct_image()
    _private_block(ds, 0x0011, "ACME HOSPITAL", 0x10, [(0x01, "LO", "Jane Doe home address")])
    _private_block(ds, 0x7053, "Philips PET Private Group", 0x10, [(0x00, "DS", "0.000123"), (0x09, "DS", "1.5")])
    _private_block(ds, 0x0009, "GEMS_PETD_01", 0x10, [(0x0D, "DT", "20240315101000"), (0x0E, "LO", "not safe")])

    out = _deid(ds, research_project)

    assert "Jane Doe home address" not in str(out)
    assert 0x00110010 not in out  # creator of an all-unsafe block goes too
    assert out[0x70531000].value == pytest.approx(0.000123)  # Philips SUV factor (E.3.10-1)
    assert out[0x70531009].value == pytest.approx(1.5)
    assert out[0x70530010].value == "Philips PET Private Group"
    assert out[0x0009100D].value == "20240315101000"  # GE local exception
    assert 0x0009100E not in out


def test_private_block_matching_follows_the_creator_not_a_fixed_block(research_project):
    ds = build_ct_image()
    _private_block(ds, 0x0009, "OTHER VENDOR", 0x10, [(0x0D, "LO", "not GE")])
    _private_block(ds, 0x0009, "GEMS_PETD_01", 0x11, [(0x0D, "DT", "20240315101000")])

    out = _deid(ds, research_project)

    assert 0x0009100D not in out
    assert out[0x0009110D].value == "20240315101000"


def test_retention_options_keep_their_attributes(research_project):
    ds = build_ct_image()
    # Retain Patient Characteristics
    ds.PatientWeight = "70"
    ds.PatientSize = "1.75"
    ds.PatientAge = "049Y"
    # Retain Longitudinal Temporal Information, Full Dates
    ds.AcquisitionDate = "20240315"
    ds.ContentDate = "20240315"
    ds.AcquisitionDateTime = "20240315101500"
    # Retain Device Identity
    ds.DeviceSerialNumber = "SN-42"
    ds.StationName = "CT01"
    # Retain Institution Identity
    ds.InstitutionalDepartmentName = "Radiology"

    out = _deid(ds, research_project)

    assert out.PatientSex == "F"
    assert out.PatientWeight == 70
    assert out.PatientSize == pytest.approx(1.75)
    assert out.PatientAge == "049Y"
    assert out.StudyDate == "20240315"
    assert out.AcquisitionDate == "20240315"
    assert out.ContentDate == "20240315"
    assert out.AcquisitionDateTime == "20240315101500"
    assert out.DeviceSerialNumber == "SN-42"
    assert out.StationName == "CT01"
    assert out.InstitutionName == "FAKE MEDICAL CENTER"
    assert out.InstitutionalDepartmentName == "Radiology"


def test_descriptor_allowlist_is_kept_and_other_descriptors_dropped(research_project):
    ds = build_ct_image()
    ds.ProtocolName = "HEAD ROUTINE"
    ds.ImageComments = "patient moved"
    ds.AdditionalPatientHistory = "history"

    out = _deid(ds, research_project)

    assert out.StudyDescription == "CT HEAD NO CONTRAST"
    assert out.SeriesDescription == "PHASE_1"
    assert out.ProtocolName == "HEAD ROUTINE"
    assert out.BodyPartExamined == "HEAD"
    assert "ImageComments" not in out
    assert "AdditionalPatientHistory" not in out


def test_instance_uids_rewritten_including_references_and_file_meta(research_project):
    ds = build_ct_image()
    source = Dataset()
    source.ReferencedSOPClassUID = ds.SOPClassUID
    source.ReferencedSOPInstanceUID = "1.2.9999.42.1.5555"
    ds.SourceImageSequence = [source]
    referenced_series = Dataset()
    referenced_series.SeriesInstanceUID = "1.2.9999.42.1.6666"
    ds.ReferencedSeriesSequence = [referenced_series]

    out = _deid(ds, research_project)

    def pseudo(uid):
        return pseudonymize_uid(uid, research_project)

    assert out.StudyInstanceUID == pseudo("1.2.9999.42.1.1001")
    assert out.SeriesInstanceUID == pseudo("1.2.9999.42.1.1002")
    assert out.SOPInstanceUID == pseudo("1.2.9999.42.1.1003")
    assert out.FrameOfReferenceUID == pseudo("1.2.9999.42.1.1004")
    assert out.file_meta.MediaStorageSOPInstanceUID == out.SOPInstanceUID
    # References resolve to the referenced objects' own pseudonyms
    assert out.SourceImageSequence[0].ReferencedSOPInstanceUID == pseudo("1.2.9999.42.1.5555")
    assert out.ReferencedSeriesSequence[0].SeriesInstanceUID == pseudo("1.2.9999.42.1.6666")
    # Class and transfer-syntax UIDs aren't touched
    assert out.SOPClassUID == ds.SOPClassUID
    assert out.SourceImageSequence[0].ReferencedSOPClassUID == ds.SOPClassUID
    assert out.file_meta.MediaStorageSOPClassUID == ds.SOPClassUID
    assert out.file_meta.TransferSyntaxUID == ds.file_meta.TransferSyntaxUID


def test_dataset_is_marked_as_deidentified(research_project):
    out = _deid(build_ct_image(), research_project)

    assert out.PatientIdentityRemoved == "YES"
    assert any("Basic Profile" in value for value in out.DeidentificationMethod)
    assert any("Deviation" in value for value in out.DeidentificationMethod)
    codes = {item.CodeValue for item in out.DeidentificationMethodCodeSequence}
    assert codes == {"113100", "113106", "113108", "113109", "113111", "113112"}
    assert {item.CodingSchemeDesignator for item in out.DeidentificationMethodCodeSequence} == {"DCM"}


def test_viewer_needed_tags_survive(research_project):
    ds = build_ct_image(modality="PT")
    # 2D spacing / calibration
    ds.ImagerPixelSpacing = "0.2\\0.2"
    ds.EstimatedRadiographicMagnificationFactor = "1.1"
    ds.PixelSpacingCalibrationType = "GEOMETRY"
    region = Dataset()
    region.PhysicalDeltaX = 0.01
    region.RegionSpatialFormat = 1
    ds.SequenceOfUltrasoundRegions = [region]
    # SUV inputs
    ds.PatientWeight = "70"
    ds.PatientSize = "1.75"
    ds.SeriesDate = "20240315"
    ds.SeriesTime = "101500"
    ds.AcquisitionDate = "20240315"
    ds.AcquisitionTime = "101500"
    ds.Units = "BQML"
    ds.DecayCorrection = "START"
    ds.CorrectedImage = ["ATTN", "DECY"]
    ds.RescaleSlope = "1.5"
    ds.RescaleIntercept = "0"
    drug = Dataset()
    drug.RadionuclideTotalDose = "370000000"
    drug.RadionuclideHalfLife = "6586.2"
    drug.RadiopharmaceuticalStartTime = "093000"
    drug.RadiopharmaceuticalStartDateTime = "20240315093000"
    ds.RadiopharmaceuticalInformationSequence = [drug]

    out = _deid(ds, research_project)

    for keyword in (
        "PixelSpacing", "ImagerPixelSpacing", "EstimatedRadiographicMagnificationFactor",
        "PixelSpacingCalibrationType", "PatientWeight", "PatientSize",
        "PatientSex", "SeriesDate", "SeriesTime", "AcquisitionDate", "AcquisitionTime", "Units",
        "DecayCorrection", "CorrectedImage", "RescaleSlope", "RescaleIntercept",
        "ImageOrientationPatient", "ImagePositionPatient", "Rows", "Columns", "BurnedInAnnotation",
    ):
        assert out[keyword].value == ds[keyword].value, keyword
    assert out.SequenceOfUltrasoundRegions[0].PhysicalDeltaX == 0.01
    out_drug = out.RadiopharmaceuticalInformationSequence[0]
    for keyword in (
        "RadionuclideTotalDose", "RadionuclideHalfLife", "RadiopharmaceuticalStartTime",
        "RadiopharmaceuticalStartDateTime",
    ):
        assert out_drug[keyword].value == drug[keyword].value, keyword


def test_pixel_data_is_carried_over_untouched(research_project):
    ds = build_ct_image()

    out = _deid(ds, research_project)

    assert out.PixelData == ds.PixelData


def test_already_pseudonymized_objects_are_not_hashed_twice(research_project):
    """Viewer-built SR/SEG (#287) already carry pseudonymized references."""
    once = _deid(build_ct_image(), research_project)

    twice = _deid(once, research_project, uids_already_pseudonymized=True)

    assert twice == once
    assert twice.file_meta == once.file_meta


def test_output_serializes_to_dicom_json(research_project):
    out = _deid(build_ct_image(), research_project)

    as_json = out.to_json_dict()

    assert as_json["00100010"]["Value"] == [{"Alphabetic": ALIAS}]
    assert as_json["00120062"]["Value"] == ["YES"]


def test_sr_content_tree_is_kept_with_its_references_rewritten(research_project):
    """Content Sequence is "D" in E.1-1: its items are de-identified, not discarded,
    so SR measurements and their image references survive (#287/#290)."""
    ds = build_ct_image(modality="SR")
    image_ref = Dataset()
    image_ref.ReferencedSOPClassUID = ds.SOPClassUID
    image_ref.ReferencedSOPInstanceUID = "1.2.9999.42.1.5555"
    image_item = Dataset()
    image_item.ValueType = "IMAGE"
    image_item.ReferencedSOPSequence = [image_ref]
    text_item = Dataset()
    text_item.ValueType = "TEXT"
    text_item.TextValue = "lesion 1"
    ds.ContentSequence = [image_item, text_item]

    out = _deid(ds, research_project)

    out_ref = out.ContentSequence[0].ReferencedSOPSequence[0]
    assert out_ref.ReferencedSOPInstanceUID == pseudonymize_uid("1.2.9999.42.1.5555", research_project)
    assert out.ContentSequence[1].TextValue == "lesion 1"


def test_overlay_data_in_repeating_groups_is_removed(research_project):
    ds = build_ct_image()
    ds.add_new(0x60023000, "OW", b"\x01\x02")  # Overlay Data, group 6002
    ds.add_new(0x60024000, "LT", "overlay comment")  # Overlay Comments
    ds.add_new(0x60020010, "US", 4)  # Overlay Rows: kept

    out = _deid(ds, research_project)

    assert 0x60023000 not in out
    assert 0x60024000 not in out
    assert out[0x60020010].value == 4
