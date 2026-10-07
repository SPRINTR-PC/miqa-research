"""Synthetic DICOM fixture builders for the ingestion test suite (#98 testing decisions).

Plain functions (no factory library), fully synthetic data — nothing here is
derived from real patient data. Every builder produces a valid pydicom
Dataset; `write_dicom` serializes it to disk with a standard 128-byte
preamble + "DICM" magic (or without a preamble, on request).
"""
from pathlib import Path

from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import (
    BasicTextSRStorage,
    CTImageStorage,
    ExplicitVRLittleEndian,
    RTDoseStorage,
    RTImageStorage,
    RTPlanStorage,
    RTStructureSetStorage,
    VLWholeSlideMicroscopyImageStorage,
    XRayRadiationDoseSRStorage,
)

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
    sop_class_uid: str = BasicTextSRStorage,
    modality: str = "SR",
    study_date: str = "20240315",
) -> Dataset:
    """Build a synthetic non-image dataset (Basic Text SR by default — a SOP Class with no
    bespoke handler): no image-plane tags, no pixel data — exercises the generic fall-through."""
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
        study_description="TEXT REPORT",
        series_description="BASIC TEXT SR",
        modality=modality,
    )
    ds.XRayTubeCurrent = "2.5"  # a non-PHI tag that must be captured
    return ds


def build_wsi(
    *,
    patient_id: str = DEFAULT_PATIENT_ID,
    study_instance_uid: str = "1.2.9999.42.10.10001",
    series_instance_uid: str = "1.2.9999.42.10.10002",
    sop_instance_uid: str = "1.2.9999.42.10.10003",
    frame_of_reference_uid: str | None = "1.2.9999.42.10.10004",
    number_of_frames: int = 3,
    tile_rows: int = 4,
    tile_columns: int = 4,
    total_pixel_matrix_rows: int = 8,
    total_pixel_matrix_columns: int = 8,
    image_type: tuple[str, ...] = ("ORIGINAL", "PRIMARY", "VOLUME", "NONE"),
    pixel_spacing: str | None = "0.00025\\0.00025",
    include_shared_functional_groups: bool = True,
    per_frame_pixel_spacing: str | None = None,
    objective_lens_power: float | None = 20.0,
) -> Dataset:
    """Build a synthetic multi-frame VL Whole Slide Microscopy Image (#124).

    One pyramid level: a tiled multi-frame instance whose per-tile pixel
    spacing lives in a functional-groups macro (never a top-level PixelSpacing
    tag), per PS3.3 C.8.12 — Shared by default, or Per-Frame when
    `per_frame_pixel_spacing` is given (spacing that varies frame-to-frame
    lives there instead). `frame_of_reference_uid` is still a top-level tag,
    shared across a slide's pyramid levels.
    """
    ds = _base_dataset(
        patient_id=patient_id,
        patient_name=DEFAULT_PATIENT_NAME,
        patient_birth_date=DEFAULT_BIRTH_DATE,
        patient_sex="F",
        study_instance_uid=study_instance_uid,
        series_instance_uid=series_instance_uid,
        sop_instance_uid=sop_instance_uid,
        sop_class_uid=VLWholeSlideMicroscopyImageStorage,
        study_date="20240315",
        study_time="120000",
        study_description="PATHOLOGY SLIDE",
        series_description="WSI SERIES",
        modality="SM",
    )
    if frame_of_reference_uid is not None:
        ds.add_new(0x00200052, "UI", frame_of_reference_uid)
    ds.ImageType = list(image_type)
    ds.NumberOfFrames = number_of_frames
    ds.TotalPixelMatrixRows = total_pixel_matrix_rows
    ds.TotalPixelMatrixColumns = total_pixel_matrix_columns
    if include_shared_functional_groups:
        measures = Dataset()
        if pixel_spacing is not None:
            measures.add_new(0x00280030, "DS", pixel_spacing)
        shared = Dataset()
        shared.PixelMeasuresSequence = [measures]
        ds.SharedFunctionalGroupsSequence = [shared]
    if per_frame_pixel_spacing is not None:
        per_frame_measures = Dataset()
        per_frame_measures.add_new(0x00280030, "DS", per_frame_pixel_spacing)
        per_frame_group = Dataset()
        per_frame_group.PixelMeasuresSequence = [per_frame_measures]
        ds.PerFrameFunctionalGroupsSequence = [per_frame_group]
    if objective_lens_power is not None:
        optical_path = Dataset()
        optical_path.OpticalPathIdentifier = "1"
        optical_path.ObjectiveLensPower = objective_lens_power
        ds.OpticalPathSequence = [optical_path]
    _add_small_pixel_block(
        ds, rows=tile_rows, columns=tile_columns,
        samples_per_pixel=3, photometric_interpretation="RGB", frames=number_of_frames,
    )
    return ds


def _code(value: str, meaning: str, scheme: str = "DCM") -> Dataset:
    item = Dataset()
    item.CodeValue = value
    item.CodingSchemeDesignator = scheme
    item.CodeMeaning = meaning
    return item


def _num_item(code: str, meaning: str, value: str, unit: str) -> Dataset:
    item = Dataset()
    item.RelationshipType = "CONTAINS"
    item.ValueType = "NUM"
    item.ConceptNameCodeSequence = [_code(code, meaning)]
    measured = Dataset()
    measured.NumericValue = value
    measured.MeasurementUnitsCodeSequence = [_code(unit, unit, "UCUM")]
    item.MeasuredValueSequence = [measured]
    return item


def _container_item(code: str, meaning: str, children: list) -> Dataset:
    item = Dataset()
    item.RelationshipType = "CONTAINS"
    item.ValueType = "CONTAINER"
    item.ConceptNameCodeSequence = [_code(code, meaning)]
    item.ContentSequence = children
    return item


def build_rdsr(
    *,
    patient_id: str = DEFAULT_PATIENT_ID,
    study_instance_uid: str = "1.2.9999.42.5.5001",
    series_instance_uid: str = "1.2.9999.42.5.5002",
    sop_instance_uid: str = "1.2.9999.42.5.5003",
) -> Dataset:
    """Synthetic X-Ray Radiation Dose SR (TID 10001): accumulated totals (TID 10007)
    plus two irradiation events (TID 10003 / 10003B). Values are fake."""
    ds = _base_dataset(
        patient_id=patient_id,
        patient_name=DEFAULT_PATIENT_NAME,
        patient_birth_date=DEFAULT_BIRTH_DATE,
        patient_sex="F",
        study_instance_uid=study_instance_uid,
        series_instance_uid=series_instance_uid,
        sop_instance_uid=sop_instance_uid,
        sop_class_uid=XRayRadiationDoseSRStorage,
        study_date="20240315",
        study_time="110000",
        study_description="DOSE REPORT",
        series_description="XRAY DOSE SR",
        modality="SR",
    )
    accumulated = _container_item("113702", "Accumulated X-Ray Dose Data", [
        _num_item("113722", "Dose Area Product Total", "12.5", "Gy.m2"),
        _num_item("113725", "Dose (RP) Total", "0.85", "Gy"),
    ])
    events = [
        _container_item("113706", "Irradiation Event X-Ray Data", [
            _num_item("122130", "Dose Area Product", "4.5", "Gy.m2"),
            _container_item("113742", "Irradiation Event X-Ray Source Data", [
                _num_item("113738", "Dose (RP)", "0.3", "Gy"),
                _num_item("113733", "KVP", "81", "kV"),
                _num_item("113824", "Exposure Time", "120", "ms"),
                _num_item("113734", "X-Ray Tube Current", "250", "mA"),
            ]),
        ]),
        _container_item("113706", "Irradiation Event X-Ray Data", [
            _num_item("122130", "Dose Area Product", "8.0", "Gy.m2"),
            _container_item("113742", "Irradiation Event X-Ray Source Data", [
                _num_item("113733", "KVP", "110", "kV"),
                _num_item("113824", "Exposure Time", "45", "ms"),
            ]),
        ]),
    ]
    ds.ValueType = "CONTAINER"
    ds.ConceptNameCodeSequence = [_code("113701", "X-Ray Radiation Dose Report")]
    ds.ContentSequence = [accumulated, *events]
    return ds


def _ref_item(sop_class: str, sop_instance: str) -> Dataset:
    item = Dataset()
    item.ReferencedSOPClassUID = sop_class
    item.ReferencedSOPInstanceUID = sop_instance
    return item


def build_rtstruct(
    *,
    patient_id: str = DEFAULT_PATIENT_ID,
    study_instance_uid: str = "1.2.9999.42.6.6001",
    series_instance_uid: str = "1.2.9999.42.6.6002",
    sop_instance_uid: str = "1.2.9999.42.6.6003",
    referenced_frame_of_reference_uid: str = "1.2.9999.42.1.1004",
    referenced_series_instance_uid: str = "1.2.9999.42.1.1002",
    referenced_image_sop_instance_uid: str = "1.2.9999.42.1.1003",
) -> Dataset:
    """Synthetic RT Structure Set: no pixel data, two ROIs, reference chain down to one CT slice."""
    ds = _rt_base(RTStructureSetStorage, "RTSTRUCT", patient_id, study_instance_uid,
                  series_instance_uid, sop_instance_uid)
    ds.StructureSetLabel = "STRUCT_1"
    image_ref = _ref_item(CTImageStorage, referenced_image_sop_instance_uid)
    series = Dataset()
    series.SeriesInstanceUID = referenced_series_instance_uid
    series.ContourImageSequence = [image_ref]
    rt_study = Dataset()
    rt_study.ReferencedSOPClassUID = "1.2.840.10008.3.1.2.3.1"
    rt_study.ReferencedSOPInstanceUID = study_instance_uid + ".ref"
    rt_study.RTReferencedSeriesSequence = [series]
    frame = Dataset()
    frame.FrameOfReferenceUID = referenced_frame_of_reference_uid
    frame.RTReferencedStudySequence = [rt_study]
    ds.ReferencedFrameOfReferenceSequence = [frame]
    rois = []
    for number, name in ((1, "PTV"), (2, "BLADDER")):
        roi = Dataset()
        roi.ROINumber = number
        roi.ReferencedFrameOfReferenceUID = referenced_frame_of_reference_uid
        roi.ROIName = name
        roi.ROIGenerationAlgorithm = "MANUAL"
        rois.append(roi)
    ds.StructureSetROISequence = rois
    observations = []
    for number, kind in ((1, "PTV"), (2, "ORGAN")):
        obs = Dataset()
        obs.ObservationNumber = number
        obs.ReferencedROINumber = number
        obs.RTROIInterpretedType = kind
        observations.append(obs)
    ds.RTROIObservationsSequence = observations
    return ds


def build_rtplan(
    *,
    patient_id: str = DEFAULT_PATIENT_ID,
    study_instance_uid: str = "1.2.9999.42.6.6001",
    series_instance_uid: str = "1.2.9999.42.7.7002",
    sop_instance_uid: str = "1.2.9999.42.7.7003",
    referenced_structure_set_sop_instance_uid: str = "1.2.9999.42.6.6003",
) -> Dataset:
    """Synthetic RT Plan: no pixel data, references a structure set, 2 beams, 1 fraction group."""
    ds = _rt_base(RTPlanStorage, "RTPLAN", patient_id, study_instance_uid,
                  series_instance_uid, sop_instance_uid)
    ds.RTPlanLabel = "PLAN_A"
    ds.RTPlanGeometry = "PATIENT"
    ds.PlanIntent = "CURATIVE"
    ds.ApprovalStatus = "APPROVED"
    ds.ReferencedStructureSetSequence = [
        _ref_item(RTStructureSetStorage, referenced_structure_set_sop_instance_uid)
    ]
    beams = []
    for number in (1, 2):
        beam = Dataset()
        beam.BeamNumber = number
        beam.BeamName = f"BEAM_{number}"
        beams.append(beam)
    ds.BeamSequence = beams
    group = Dataset()
    group.FractionGroupNumber = 1
    group.NumberOfFractionsPlanned = 30
    ds.FractionGroupSequence = [group]
    return ds


def build_rtdose(
    *,
    patient_id: str = DEFAULT_PATIENT_ID,
    study_instance_uid: str = "1.2.9999.42.6.6001",
    series_instance_uid: str = "1.2.9999.42.8.8002",
    sop_instance_uid: str = "1.2.9999.42.8.8003",
    referenced_plan_sop_instance_uid: str = "1.2.9999.42.7.7003",
    referenced_structure_set_sop_instance_uid: str = "1.2.9999.42.6.6003",
    frame_of_reference_uid: str = "1.2.9999.42.1.1004",
) -> Dataset:
    """Synthetic RT Dose: small dose grid with scaling, references a plan and a structure set."""
    ds = _rt_base(RTDoseStorage, "RTDOSE", patient_id, study_instance_uid,
                  series_instance_uid, sop_instance_uid)
    ds.DoseUnits = "GY"
    ds.DoseType = "PHYSICAL"
    ds.DoseSummationType = "PLAN"
    ds.add_new(0x3004000E, "DS", "0.0025")  # DoseGridScaling
    ds.ReferencedRTPlanSequence = [_ref_item(RTPlanStorage, referenced_plan_sop_instance_uid)]
    ds.ReferencedStructureSetSequence = [
        _ref_item(RTStructureSetStorage, referenced_structure_set_sop_instance_uid)
    ]
    ds.add_new(0x00200052, "UI", frame_of_reference_uid)
    ds.add_new(0x00200037, "DS", "1\\0\\0")
    ds.add_new(0x00200032, "DS", "-10.0\\-20.0\\50.5")
    ds.add_new(0x00280030, "DS", "2.5\\2.5")
    _add_small_pixel_block(ds, rows=4, columns=4)
    return ds


def build_rtimage(
    *,
    patient_id: str = DEFAULT_PATIENT_ID,
    study_instance_uid: str = "1.2.9999.42.6.6001",
    series_instance_uid: str = "1.2.9999.42.9.9902",
    sop_instance_uid: str = "1.2.9999.42.9.9903",
    referenced_plan_sop_instance_uid: str = "1.2.9999.42.7.7003",
) -> Dataset:
    """Synthetic RT Image (portal image): references a plan, beam and fraction group."""
    ds = _rt_base(RTImageStorage, "RTIMAGE", patient_id, study_instance_uid,
                  series_instance_uid, sop_instance_uid)
    ds.RTImageLabel = "PORTAL_1"
    ds.RTImagePlane = "NORMAL"
    ds.ReferencedRTPlanSequence = [_ref_item(RTPlanStorage, referenced_plan_sop_instance_uid)]
    ds.ReferencedBeamNumber = 1
    ds.ReferencedFractionGroupNumber = 1
    ds.RTImageSID = "1500"
    ds.add_new(0x30020011, "DS", "0.392\\0.392")  # ImagePlanePixelSpacing
    _add_small_pixel_block(ds, rows=4, columns=4)
    return ds


def _rt_base(sop_class_uid, modality, patient_id, study_uid, series_uid, sop_uid) -> Dataset:
    return _base_dataset(
        patient_id=patient_id,
        patient_name=DEFAULT_PATIENT_NAME,
        patient_birth_date=DEFAULT_BIRTH_DATE,
        patient_sex="F",
        study_instance_uid=study_uid,
        series_instance_uid=series_uid,
        sop_instance_uid=sop_uid,
        sop_class_uid=sop_class_uid,
        study_date="20240315",
        study_time="110000",
        study_description="RT COURSE",
        series_description=modality,
        modality=modality,
    )


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


def _add_small_pixel_block(
    ds: Dataset,
    rows: int,
    columns: int,
    *,
    samples_per_pixel: int = 1,
    photometric_interpretation: str = "MONOCHROME2",
    frames: int = 1,
) -> None:
    ds.Rows = rows
    ds.Columns = columns
    ds.SamplesPerPixel = samples_per_pixel
    ds.PhotometricInterpretation = photometric_interpretation
    if samples_per_pixel > 1:
        ds.PlanarConfiguration = 0
    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.PixelData = bytes((i * 7) % 256 for i in range(rows * columns * samples_per_pixel * frames))


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


def build_multiframe_ct(*, number_of_frames: int = 3, rows: int = 4, columns: int = 5, **kwargs) -> Dataset:
    """Build a synthetic native (uncompressed) 16-bit multi-frame CT (#274).

    Every frame's bytes differ, so a test can tell frames apart by content.
    Explicit VR Little Endian, frames stored back to back in PixelData.
    """
    ds = build_ct_image(**kwargs)
    ds.NumberOfFrames = number_of_frames
    ds.Rows = rows
    ds.Columns = columns
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = 16
    ds.BitsStored = 12
    ds.HighBit = 11
    ds.PixelRepresentation = 0
    frame_size = rows * columns * 2
    ds.PixelData = b"".join(
        bytes((frame * 31 + i) % 256 for i in range(frame_size)) for frame in range(number_of_frames)
    )
    return ds


def fake_jpeg_tile(index: int, *, size: int = 14) -> bytes:
    """A small even-length byte string shaped like a JPEG codestream (SOI ... EOI).

    Never decoded by the server, which serves stored frames as-is; only the
    SOI marker matters, for indexing fragments without an offset table.
    """
    return b"\xff\xd8" + bytes([index % 256]) * (size - 4) + b"\xff\xd9"


def build_tiled_wsi_jpeg(
    *,
    tiles: list[bytes] | None = None,
    fragments_per_frame: int = 1,
    has_bot: bool = True,
    extended_offset_table: bool = False,
    **kwargs,
) -> Dataset:
    """Build a synthetic encapsulated JPEG Baseline TILED_FULL WSI level (#274).

    2×2 tiles of 4×4 pixels by default (one tile per frame), with a Basic
    Offset Table unless `has_bot=False` (or an Extended Offset Table and an
    empty BOT with `extended_offset_table=True`). Carries the WSI tags Cornerstone3D's
    WSIViewport needs (ImageOrientationSlide, ImagedVolumeWidth/Height,
    TotalPixelMatrixOriginSequence, DimensionOrganizationType).
    """
    from pydicom.encaps import encapsulate, encapsulate_extended
    from pydicom.uid import JPEGBaseline8Bit

    tiles = tiles if tiles is not None else [fake_jpeg_tile(i) for i in range(4)]
    kwargs.setdefault("number_of_frames", len(tiles))
    kwargs.setdefault("total_pixel_matrix_rows", 8)
    kwargs.setdefault("total_pixel_matrix_columns", 8)
    ds = build_wsi(**kwargs)
    ds.file_meta.TransferSyntaxUID = JPEGBaseline8Bit
    ds.PhotometricInterpretation = "YBR_FULL_422"
    ds.DimensionOrganizationType = "TILED_FULL"
    ds.ImageOrientationSlide = [0, -1, 0, -1, 0, 0]
    ds.ImagedVolumeWidth = 0.002
    ds.ImagedVolumeHeight = 0.002
    origin = Dataset()
    origin.XOffsetInSlideCoordinateSystem = 20.0
    origin.YOffsetInSlideCoordinateSystem = 40.0
    ds.TotalPixelMatrixOriginSequence = [origin]
    ds.LossyImageCompression = "01"
    if extended_offset_table:
        ds.PixelData, ds.ExtendedOffsetTable, ds.ExtendedOffsetTableLengths = encapsulate_extended(tiles)
    else:
        ds.PixelData = encapsulate(tiles, fragments_per_frame=fragments_per_frame, has_bot=has_bot)
    ds["PixelData"].VR = "OB"
    return ds
