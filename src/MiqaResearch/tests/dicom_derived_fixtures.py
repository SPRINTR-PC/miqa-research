"""Synthetic SR/SEG builders for Annotations and Segmentations (#287).

Shaped like what the viewer builds: references carry the pseudonymized UIDs
the viewer got from WADO /metadata, while the browser-chosen Study/Series/SOP
UIDs and the PHI-rich patient module are what the server must not trust.
"""
from pydicom.dataset import Dataset
from pydicom.uid import Comprehensive3DSRStorage, CTImageStorage, SegmentationStorage

from tests.dicom_fixtures import (
    DEFAULT_BIRTH_DATE,
    DEFAULT_PATIENT_ID,
    DEFAULT_PATIENT_NAME,
    _base_dataset,
    _code,
    _num_item,
    _ref_item,
)


def build_viewer_sr(
    *,
    referenced_study_uid: str,
    referenced_series_uid: str,
    referenced_sop_uid: str,
    referenced_sop_class_uid: str = CTImageStorage,
    frame_of_reference_uid: str | None = None,
    study_instance_uid: str = "2.25.1111",
    series_instance_uid: str = "2.25.2222",
    sop_instance_uid: str = "2.25.3333",
    patient_id: str = DEFAULT_PATIENT_ID,
) -> Dataset:
    """A Comprehensive 3D SR (TID 1500-like) with one length measurement on one image."""
    ds = _base(
        Comprehensive3DSRStorage, "SR", "Viewer measurements",
        study_instance_uid, series_instance_uid, sop_instance_uid, patient_id,
    )
    if frame_of_reference_uid is not None:
        ds.add_new(0x00200052, "UI", frame_of_reference_uid)
    ds.ValueType = "CONTAINER"
    ds.ConceptNameCodeSequence = [_code("126000", "Imaging Measurement Report")]
    image = Dataset()
    image.RelationshipType = "CONTAINS"
    image.ValueType = "IMAGE"
    image.ReferencedSOPSequence = [_ref_item(referenced_sop_class_uid, referenced_sop_uid)]
    ds.ContentSequence = [_num_item("410668003", "Length", "12.5", "mm"), image]
    series_ref = Dataset()
    series_ref.SeriesInstanceUID = referenced_series_uid
    series_ref.ReferencedSOPSequence = [_ref_item(referenced_sop_class_uid, referenced_sop_uid)]
    study_ref = Dataset()
    study_ref.StudyInstanceUID = referenced_study_uid
    study_ref.ReferencedSeriesSequence = [series_ref]
    ds.CurrentRequestedProcedureEvidenceSequence = [study_ref]
    return ds


def build_viewer_seg(
    *,
    referenced_series_uid: str,
    referenced_sop_uid: str,
    referenced_sop_class_uid: str = CTImageStorage,
    frame_of_reference_uid: str | None = None,
    study_instance_uid: str = "2.25.4444",
    series_instance_uid: str = "2.25.5555",
    sop_instance_uid: str = "2.25.6666",
    patient_id: str = DEFAULT_PATIENT_ID,
) -> Dataset:
    """A minimal SEG (BINARY): one 4x4 frame of one manual segment."""
    ds = _base(
        SegmentationStorage, "SEG", "Viewer segmentation",
        study_instance_uid, series_instance_uid, sop_instance_uid, patient_id,
    )
    if frame_of_reference_uid is not None:
        ds.add_new(0x00200052, "UI", frame_of_reference_uid)
    ds.SegmentationType = "BINARY"
    segment = Dataset()
    segment.SegmentNumber = 1
    segment.SegmentLabel = "Lesion"
    segment.SegmentAlgorithmType = "MANUAL"
    ds.SegmentSequence = [segment]
    series_ref = Dataset()
    series_ref.SeriesInstanceUID = referenced_series_uid
    series_ref.ReferencedInstanceSequence = [_ref_item(referenced_sop_class_uid, referenced_sop_uid)]
    ds.ReferencedSeriesSequence = [series_ref]
    ds.Rows = 4
    ds.Columns = 4
    ds.NumberOfFrames = 1
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = 1
    ds.BitsStored = 1
    ds.HighBit = 0
    ds.PixelRepresentation = 0
    ds.PixelData = b"\xff\x00"
    return ds


def _base(sop_class_uid, modality, series_description, study_uid, series_uid, sop_uid, patient_id) -> Dataset:
    ds = _base_dataset(
        patient_id=patient_id,
        patient_name=DEFAULT_PATIENT_NAME,
        patient_birth_date=DEFAULT_BIRTH_DATE,
        patient_sex="F",
        study_instance_uid=study_uid,
        series_instance_uid=series_uid,
        sop_instance_uid=sop_uid,
        sop_class_uid=sop_class_uid,
        study_date="20240315",
        study_time="101500",
        study_description="CT HEAD NO CONTRAST",
        series_description=series_description,
        modality=modality,
    )
    ds.add_new(0x00101000, "LO", "OLD-ID-99")  # OtherPatientIDs (PHI)
    ds.PatientAddress = "1 Fake Street"  # PHI
    return ds
