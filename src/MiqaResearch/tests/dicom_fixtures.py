"""Synthetic DICOM fixture builders for the ingestion test suite (#98 testing decisions).

Plain functions (no factory library), fully synthetic data — nothing here is
derived from real patient data. Every builder produces a valid pydicom
Dataset; `write_dicom` serializes it to disk with a standard 128-byte
preamble + "DICM" magic (or without a preamble, on request).
"""
from pathlib import Path

from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, XRayRadiationDoseSRStorage

# Well-known, non-identifying demo values only
DEFAULT_PATIENT_ID = "P-1001"
DEFAULT_PATIENT_NAME = "DOE^JANE"
DEFAULT_BIRTH_DATE = "19750131"


def build_ct_image(
    *,
    patient_id: str = DEFAULT_PATIENT_ID,
    patient_name: str = DEFAULT_PATIENT_NAME,
    patient_birth_date: str = DEFAULT_BIRTH_DATE,
    patient_sex: str = "F",
    study_instance_uid: str = "1.2.9999.42.1.1001",
    series_instance_uid: str = "1.2.9999.42.1.1002",
    sop_instance_uid: str = "1.2.9999.42.1.1003",
    frame_of_reference_uid: str | None = "1.2.9999.42.1.1004",
    study_date: str = "20240315",
    study_time: str = "101500.123456",
    study_description: str = "CT HEAD NO CONTRAST",
    series_description: str = "PHASE_1",
    modality: str = "CT",
    sop_class_uid: str = CTImageStorage,
    image_orientation_patient: str = "1\\0\\0",
    image_position_patient: str = "-10.0\\-20.0\\50.5",
    pixel_spacing: str = "0.5\\0.5",
    burned_in_annotation: str | None = "N",
    referring_physician_name: str = "SMITH^ARTHUR",
) -> Dataset:
    """Build a synthetic standard-radiology (CT by default) image dataset.

    Carries the standard image-plane geometry tags plus a deliberately
    PHI-rich header (patient name/ID/birth date, referring physician,
    other patient IDs) so tests can assert the PHI strip.
    """
    ds = _base_dataset(
        patient_id=patient_id,
        patient_name=patient_name,
        patient_birth_date=patient_birth_date,
        patient_sex=patient_sex,
        study_instance_uid=study_instance_uid,
        series_instance_uid=series_instance_uid,
        sop_instance_uid=sop_instance_uid,
        sop_class_uid=sop_class_uid,
        study_date=study_date,
        study_time=study_time,
        study_description=study_description,
        series_description=series_description,
        modality=modality,
    )
    if frame_of_reference_uid is not None:
        ds.add_new(0x00200052, "UI", frame_of_reference_uid)
    if image_orientation_patient is not None:
        ds.add_new(0x00200037, "DS", image_orientation_patient)
    if image_position_patient is not None:
        ds.add_new(0x00200032, "DS", image_position_patient)
    if pixel_spacing is not None:
        ds.add_new(0x00280030, "DS", pixel_spacing)
    if burned_in_annotation is not None:
        ds.BurnedInAnnotation = burned_in_annotation
    # Non-PHI technical tags that must survive the PHI strip
    ds.KVP = "120"
    ds.BodyPartExamined = "HEAD"
    ds.InstitutionName = "FAKE MEDICAL CENTER"
    # Extra PHI tags beyond the core three
    ds.add_new(0x00101000, "LO", "OLD-ID-99")  # OtherPatientIDs
    ds.ReferringPhysicianName = referring_physician_name
    _add_small_pixel_block(ds, rows=4, columns=4)
    return ds


def build_generic_dataset(
    *,
    patient_id: str = DEFAULT_PATIENT_ID,
    study_instance_uid: str = "1.2.9999.42.9.9001",
    series_instance_uid: str = "1.2.9999.42.9.9002",
    sop_instance_uid: str = "1.2.9999.42.9.9003",
    sop_class_uid: str = XRayRadiationDoseSRStorage,
    modality: str = "SR",
    study_date: str = "20240315",
) -> Dataset:
    """Build a synthetic non-image dataset (dose SR by default): no image-plane tags,
    no pixel data — exercises the generic fall-through extractor."""
    ds = _base_dataset(
        patient_id=patient_id,
        patient_name=DEFAULT_PATIENT_NAME,
        patient_birth_date=DEFAULT_BIRTH_DATE,
        patient_sex="F",
        study_instance_uid=study_instance_uid,
        series_instance_uid=series_instance_uid,
        sop_instance_uid=sop_instance_uid,
        sop_class_uid=sop_class_uid,
        study_date=study_date,
        study_time="110000",
        study_description="DOSE REPORT",
        series_description="XRAY DOSE SR",
        modality=modality,
    )
    ds.XRayTubeCurrent = "2.5"  # a non-PHI tag that must be captured
    return ds


def _base_dataset(
    *,
    patient_id,
    patient_name,
    patient_birth_date,
    patient_sex,
    study_instance_uid,
    series_instance_uid,
    sop_instance_uid,
    sop_class_uid,
    study_date,
    study_time,
    study_description,
    series_description,
    modality,
) -> Dataset:
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.MediaStorageSOPClassUID = sop_class_uid
    ds.file_meta.MediaStorageSOPInstanceUID = sop_instance_uid
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds.SOPClassUID = sop_class_uid
    ds.SOPInstanceUID = sop_instance_uid
    ds.StudyInstanceUID = study_instance_uid
    ds.SeriesInstanceUID = series_instance_uid
    ds.StudyID = "ST-001"
    ds.SeriesNumber = 1
    ds.InstanceNumber = 1

    ds.PatientID = patient_id
    ds.PatientName = patient_name
    if patient_birth_date:
        ds.PatientBirthDate = patient_birth_date
    ds.PatientSex = patient_sex
    ds.StudyDate = study_date
    ds.StudyTime = study_time
    ds.StudyDescription = study_description
    ds.SeriesDescription = series_description
    ds.Modality = modality
    return ds


def _add_small_pixel_block(ds: Dataset, rows: int, columns: int) -> None:
    ds.Rows = rows
    ds.Columns = columns
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.PixelData = bytes((i * 7) % 256 for i in range(rows * columns))


def write_dicom(ds: Dataset, path: str | Path, *, with_preamble: bool = True) -> Path:
    """Serialize a dataset to `path` (creating parents) and return the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ds.save_as(str(path), enforce_file_format=True)
    if not with_preamble:
        raw = path.read_bytes()
        # Strip the 128-byte preamble + 4-byte "DICM" magic to emulate PACS
        # exports that write metadata starting at byte 0.
        path.write_bytes(raw[132:])
    return path
