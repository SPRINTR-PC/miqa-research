"""Seed data for the local Playwright viewer harness (#278). DEBUG only.

Creates (once) a "Viewer harness" Research Project with a PI user, a view-only (Investigator) user,
an ingested synthetic CT stack, three 2D images for spacing calibration (#281: a CR with only
ImagerPixelSpacing, an SC with PixelSpacing, an SC without spacing), a synthetic TILED_FULL
whole-slide image (#285) and bulk annotations (ANN) on it (#292), and fusion series in the CT's study (#284:
a PET with every SUV input and one without PatientWeight on the CT's Frame of Reference, an MR on another),
and a "Viewer harness blinded" project (#290: Blinded Annotation on, the PI as PI, a 2D image and an ingested
SR on it, hidden until a Blinding Reveal), then prints JSON for the harness:
fresh session cookies for both and the pseudonymized study/series UIDs to open. Idempotent: re-runs
reuse the project and its series.
Fully synthetic pixel data and demo identifiers only.
"""
import io
import json
import tempfile
from pathlib import Path

import numpy as np
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.test import Client, override_settings
from PIL import Image
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.encaps import encapsulate
from pydicom.uid import (
    Comprehensive3DSRStorage,
    ComputedRadiographyImageStorage,
    CTImageStorage,
    ExplicitVRLittleEndian,
    JPEGBaseline8Bit,
    MicroscopyBulkSimpleAnnotationsStorage,
    MRImageStorage,
    PositronEmissionTomographyImageStorage,
    SecondaryCaptureImageStorage,
    VLWholeSlideMicroscopyImageStorage,
)

from contract.constants.research_project_role import PROJECT_ROLE_INVESTIGATOR, PROJECT_ROLE_PI
from MiqaResearch.data.models import (
    DicomSeries,
    ResearchProject,
    ResearchProjectRole,
    ResearchProjectUserRoleMap,
)
from MiqaResearch.tasks.dicom_handling.pipeline import run_ingestion

PROJECT_NAME = "Viewer harness"
BLINDED_PROJECT_NAME = "Viewer harness blinded"
BLINDED_UID_ROOT = "2.25.290290290"
USERNAME = "viewer-harness"
VIEW_ONLY_USERNAME = "viewer-harness-view-only"
CT_SLICES = 16
CT_SIZE = 64
SLICE_SPACING = 2.5
CT_UID_ROOT = "2.25.278278278"
PLANAR_UID_ROOT = "2.25.281281281"
PLANAR_SIZE = 128
# #281 2D fixtures: key in the seed JSON → (SeriesDescription, SOP class, modality, spacing tags, BurnedInAnnotation).
# No ImagePositionPatient/ImageOrientationPatient: like real CR and SC.
PLANAR_FIXTURES = {
    "cr": (
        "Harness CR detector spacing", ComputedRadiographyImageStorage, "CR", {"ImagerPixelSpacing": [0.2, 0.2]}, "NO",
    ),
    "sc": ("Harness SC with spacing", SecondaryCaptureImageStorage, "OT", {"PixelSpacing": [0.5, 0.5]}, None),
    "noSpacing": ("Harness SC no spacing", SecondaryCaptureImageStorage, "OT", {}, "NO"),
}
# #284 fusion series in the CT's study: key in the seed JSON → (SeriesDescription, modality, series UID suffix,
# Frame of Reference UID, PatientWeight). The PETs share the CT's Frame of Reference; the MR has its own.
FUSION_FIXTURES = {
    "pet": ("Harness PET SUV", "PT", "20", f"{CT_UID_ROOT}.4", 75),
    "petNoWeight": ("Harness PET no weight", "PT", "21", f"{CT_UID_ROOT}.4", None),
    "mrOtherFor": ("Harness MR other FoR", "MR", "22", f"{CT_UID_ROOT}.40", None),
}
# PET activity: SUVbw = Bq/ml × weight (g) / decayed dose. 370 MBq F-18 injected 1 h before the scan,
# 75 kg: background SUV 1, a hot sphere of SUV 6 in the CT sphere's centre.
PET_DOSE_BQ, PET_HALF_LIFE_S, PET_DELAY_S = 370e6, 6586.2, 3600
PET_BQML_PER_SUV = PET_DOSE_BQ * 2 ** (-PET_DELAY_S / PET_HALF_LIFE_S) / 75000
WSI_UID_ROOT = "2.25.285285285"
WSI_TILE = 256
WSI_WIDTH, WSI_HEIGHT = 2048, 1536  # base level, pixels: 8 × 6 tiles
WSI_PIXEL_MM = 0.0005  # 0.5 µm at the base level
WSI_DOWNSAMPLES = (1, 4)  # two pyramid levels, so the viewer opens zoomed out and can zoom in
# Bulk annotations (#292): label, property type (SCT code, meaning), display colour (DICOM CIELab of pure
# green / magenta) and closed polygons in base-level (column, row) pixels. Colours unlike the slide's, so a
# test can find them on screen. The label is PHI-scrubbed at serve time (De-identification Profile: D), the
# property type is not.
ANN_GROUPS = (
    ("Tumour", ("108369006", "Neoplasm"), (57498, 10747, 54273), (
        ((200, 200), (700, 200), (700, 600), (200, 600)),
        ((1300, 900), (1800, 900), (1800, 1300), (1300, 1300)),
    )),
    ("Stroma", ("21793004", "Connective tissue"), (39530, 58148, 17258), (
        ((1200, 150), (1850, 150), (1525, 650)),
    )),
)


def build_ct_slice(index: int) -> Dataset:
    """One slice of a synthetic 16-slice CT: a sphere with a left→right HU ramp in air."""
    ds = Dataset()
    sop = f"{CT_UID_ROOT}.3.{index + 1}"
    ds.file_meta = FileMetaDataset()
    ds.file_meta.MediaStorageSOPClassUID = CTImageStorage
    ds.file_meta.MediaStorageSOPInstanceUID = sop
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.SOPClassUID, ds.SOPInstanceUID = CTImageStorage, sop
    ds.StudyInstanceUID, ds.SeriesInstanceUID = f"{CT_UID_ROOT}.1", f"{CT_UID_ROOT}.2"
    ds.FrameOfReferenceUID = f"{CT_UID_ROOT}.4"
    ds.PatientID, ds.PatientName, ds.PatientSex = "HARNESS-1", "HARNESS^CT", "O"
    ds.StudyDate, ds.StudyTime, ds.StudyID = "20260101", "120000", "H1"
    ds.StudyDescription, ds.SeriesDescription = "Viewer harness CT", "Synthetic sphere"
    ds.Modality, ds.SeriesNumber, ds.InstanceNumber = "CT", 1, index + 1
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    ds.ImagePositionPatient = [0.0, 0.0, index * SLICE_SPACING]
    ds.SliceThickness = SLICE_SPACING
    ds.PixelSpacing = [1.0, 1.0]
    ds.Rows = ds.Columns = CT_SIZE
    ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
    ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 16, 15, 1
    ds.RescaleIntercept, ds.RescaleSlope, ds.RescaleType = -1024, 1, "HU"
    ds.WindowCenter, ds.WindowWidth = 40, 400
    ds.BurnedInAnnotation = "NO"

    y, x = np.mgrid[0:CT_SIZE, 0:CT_SIZE]
    centre = (CT_SIZE - 1) / 2
    z = (index - (CT_SLICES - 1) / 2) * SLICE_SPACING
    inside = (x - centre) ** 2 + (y - centre) ** 2 + z ** 2 <= (CT_SIZE * 0.45) ** 2
    hu = np.where(inside, -200 + 400 * x / (CT_SIZE - 1), -1000)
    ds.PixelData = (hu + 1024).astype("<i2").tobytes()
    return ds


def build_fusion_slice(key: str, index: int) -> Dataset:
    """One slice of a #284 fusion series, on the CT's grid: PET activity (Bq/ml, SUV inputs) or an MR sphere."""
    description, modality, suffix, frame_of_reference, weight = FUSION_FIXTURES[key]
    sop_class = PositronEmissionTomographyImageStorage if modality == "PT" else MRImageStorage
    ds = Dataset()
    sop = f"{CT_UID_ROOT}.{suffix}.{index + 1}"
    ds.file_meta = FileMetaDataset()
    ds.file_meta.MediaStorageSOPClassUID = sop_class
    ds.file_meta.MediaStorageSOPInstanceUID = sop
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.SOPClassUID, ds.SOPInstanceUID = sop_class, sop
    ds.StudyInstanceUID, ds.SeriesInstanceUID = f"{CT_UID_ROOT}.1", f"{CT_UID_ROOT}.2.{suffix}"
    ds.FrameOfReferenceUID = frame_of_reference
    ds.PatientID, ds.PatientName, ds.PatientSex = "HARNESS-1", "HARNESS^CT", "O"
    ds.StudyDate, ds.StudyTime, ds.StudyID = "20260101", "120000", "H1"
    ds.StudyDescription, ds.SeriesDescription = "Viewer harness CT", description
    ds.Modality, ds.SeriesNumber, ds.InstanceNumber = modality, int(suffix), index + 1
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    ds.ImagePositionPatient = [0.0, 0.0, index * SLICE_SPACING]
    ds.SliceThickness = SLICE_SPACING
    ds.PixelSpacing = [1.0, 1.0]
    ds.Rows = ds.Columns = CT_SIZE
    ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
    ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 16, 15, 0
    ds.BurnedInAnnotation = "NO"

    y, x = np.mgrid[0:CT_SIZE, 0:CT_SIZE]
    centre = (CT_SIZE - 1) / 2
    z = (index - (CT_SLICES - 1) / 2) * SLICE_SPACING
    r2 = (x - centre) ** 2 + (y - centre) ** 2 + z ** 2
    if modality == "PT":
        ds.SeriesDate = ds.AcquisitionDate = "20260101"
        ds.SeriesTime = ds.AcquisitionTime = "120000"
        ds.Units, ds.CorrectedImage, ds.DecayCorrection = "BQML", ["ATTN", "DECY"], "START"
        ds.RescaleIntercept, ds.RescaleSlope = 0, 1
        if weight is not None:
            ds.PatientWeight, ds.PatientSize = weight, 1.8
        radiopharmaceutical = Dataset()
        radiopharmaceutical.RadiopharmaceuticalStartTime = "110000"
        radiopharmaceutical.RadionuclideTotalDose = PET_DOSE_BQ
        radiopharmaceutical.RadionuclideHalfLife = PET_HALF_LIFE_S
        ds.RadiopharmaceuticalInformationSequence = [radiopharmaceutical]
        suv = np.where(r2 <= (CT_SIZE * 0.15) ** 2, 6.0, np.where(r2 <= (CT_SIZE * 0.45) ** 2, 1.0, 0.0))
        pixels = suv * PET_BQML_PER_SUV
    else:
        ds.WindowCenter, ds.WindowWidth = 500, 1000
        pixels = np.where(r2 <= (CT_SIZE * 0.35) ** 2, 800, 50)
    ds.PixelData = pixels.astype("<u2").tobytes()
    return ds


def build_planar_image(key: str, index: int) -> Dataset:
    """A single-frame 2D image (#281 PLANAR_FIXTURES[key]): a bright square on a dark ramp."""
    description, sop_class, modality, spacing, burned_in = PLANAR_FIXTURES[key]
    ds = Dataset()
    sop = f"{PLANAR_UID_ROOT}.{index}.3"
    ds.file_meta = FileMetaDataset()
    ds.file_meta.MediaStorageSOPClassUID = sop_class
    ds.file_meta.MediaStorageSOPInstanceUID = sop
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.SOPClassUID, ds.SOPInstanceUID = sop_class, sop
    ds.StudyInstanceUID, ds.SeriesInstanceUID = f"{PLANAR_UID_ROOT}.{index}.1", f"{PLANAR_UID_ROOT}.{index}.2"
    ds.PatientID, ds.PatientName, ds.PatientSex = "HARNESS-1", "HARNESS^CT", "O"
    ds.StudyDate, ds.StudyTime, ds.StudyID = "20260101", "130000", f"H2{index}"
    ds.StudyDescription, ds.SeriesDescription = "Viewer harness 2D", description
    ds.Modality, ds.SeriesNumber, ds.InstanceNumber = modality, 1, 1
    for tag, value in spacing.items():
        setattr(ds, tag, value)
    if burned_in is not None:
        ds.BurnedInAnnotation = burned_in
    ds.Rows = ds.Columns = PLANAR_SIZE
    ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
    ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 12, 11, 0
    ds.WindowCenter, ds.WindowWidth = 2048, 4096

    y, x = np.mgrid[0:PLANAR_SIZE, 0:PLANAR_SIZE]
    lo, hi = PLANAR_SIZE // 4, 3 * PLANAR_SIZE // 4
    pixels = np.where((lo <= x) & (x < hi) & (lo <= y) & (y < hi), 3500, 500 + 4 * x)
    ds.PixelData = pixels.astype("<u2").tobytes()
    return ds


def _wsi_level_pixels(downsample: int) -> np.ndarray:
    """The synthetic slide at one pyramid level: a colour gradient with diagonal stripes every 32 base pixels."""
    height, width = WSI_HEIGHT // downsample, WSI_WIDTH // downsample
    y, x = np.mgrid[0:height, 0:width] * downsample
    stripes = ((x + y) // 32) % 2 * 60
    rgb = np.stack([60 + 160 * x // WSI_WIDTH, 220 - 150 * y // WSI_HEIGHT, np.full_like(x, 170)], axis=-1) - stripes[..., None]
    return np.clip(rgb, 0, 255).astype(np.uint8)


def _jpeg_tiles(pixels: np.ndarray) -> list[bytes]:
    """Row-major TILED_FULL tiles; edge tiles padded to the full tile size."""
    tiles = []
    for top in range(0, pixels.shape[0], WSI_TILE):
        for left in range(0, pixels.shape[1], WSI_TILE):
            tile = np.zeros((WSI_TILE, WSI_TILE, 3), dtype=np.uint8)
            part = pixels[top:top + WSI_TILE, left:left + WSI_TILE]
            tile[:part.shape[0], :part.shape[1]] = part
            out = io.BytesIO()
            Image.fromarray(tile, "RGB").save(out, format="JPEG", quality=90, subsampling=1)  # 4:2:2
            tiles.append(out.getvalue())
    return tiles


def build_wsi_level(level: int) -> Dataset:
    """One level of a synthetic VL Whole Slide Microscopy pyramid: TILED_FULL, JPEG Baseline, with a BOT."""
    downsample = WSI_DOWNSAMPLES[level]
    pixels = _wsi_level_pixels(downsample)
    tiles = _jpeg_tiles(pixels)
    ds = Dataset()
    sop = f"{WSI_UID_ROOT}.3.{level + 1}"
    ds.file_meta = FileMetaDataset()
    ds.file_meta.MediaStorageSOPClassUID = VLWholeSlideMicroscopyImageStorage
    ds.file_meta.MediaStorageSOPInstanceUID = sop
    ds.file_meta.TransferSyntaxUID = JPEGBaseline8Bit
    ds.SOPClassUID, ds.SOPInstanceUID = VLWholeSlideMicroscopyImageStorage, sop
    ds.StudyInstanceUID, ds.SeriesInstanceUID = f"{WSI_UID_ROOT}.1", f"{WSI_UID_ROOT}.2"
    ds.FrameOfReferenceUID = f"{WSI_UID_ROOT}.4"
    ds.PatientID, ds.PatientName, ds.PatientSex = "HARNESS-1", "HARNESS^CT", "O"
    ds.StudyDate, ds.StudyTime, ds.StudyID = "20260102", "120000", "H2"
    ds.StudyDescription, ds.SeriesDescription = "Viewer harness slide", "Synthetic tiles"
    ds.Modality, ds.SeriesNumber, ds.InstanceNumber = "SM", 1, level + 1
    ds.ImageType = ["ORIGINAL" if level == 0 else "DERIVED", "PRIMARY", "VOLUME", "NONE"]
    ds.ContainerIdentifier = "HARNESS-SLIDE-1"
    ds.DimensionOrganizationType = "TILED_FULL"
    ds.Rows = ds.Columns = WSI_TILE
    ds.TotalPixelMatrixRows, ds.TotalPixelMatrixColumns = pixels.shape[:2]
    ds.TotalPixelMatrixFocalPlanes = 1
    ds.NumberOfFrames = len(tiles)
    ds.NumberOfOpticalPaths = 1
    ds.ImagedVolumeWidth = WSI_WIDTH * WSI_PIXEL_MM
    ds.ImagedVolumeHeight = WSI_HEIGHT * WSI_PIXEL_MM
    ds.ImagedVolumeDepth = 0.001
    ds.ImageOrientationSlide = [0, -1, 0, -1, 0, 0]
    origin = Dataset()
    origin.XOffsetInSlideCoordinateSystem = 20.0
    origin.YOffsetInSlideCoordinateSystem = 40.0
    ds.TotalPixelMatrixOriginSequence = [origin]
    measures = Dataset()
    measures.PixelSpacing = [WSI_PIXEL_MM * downsample] * 2
    measures.SliceThickness = 0.001
    shared = Dataset()
    shared.PixelMeasuresSequence = [measures]
    ds.SharedFunctionalGroupsSequence = [shared]
    optical_path = Dataset()
    optical_path.OpticalPathIdentifier = "1"
    illumination = Dataset()
    illumination.CodeValue, illumination.CodingSchemeDesignator = "111744", "DCM"
    illumination.CodeMeaning = "Brightfield illumination"
    optical_path.IlluminationTypeCodeSequence = [illumination]
    color = Dataset()
    color.CodeValue, color.CodingSchemeDesignator, color.CodeMeaning = "414298005", "SCT", "Full Spectrum"
    optical_path.IlluminationColorCodeSequence = [color]
    ds.OpticalPathSequence = [optical_path]
    ds.SamplesPerPixel, ds.PhotometricInterpretation, ds.PlanarConfiguration = 3, "YBR_FULL_422", 0
    ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 8, 8, 7, 0
    ds.LossyImageCompression, ds.BurnedInAnnotation = "01", "NO"
    ds.PixelData = encapsulate(tiles, has_bot=True)
    ds["PixelData"].VR = "OB"
    return ds


def build_blinded_image() -> Dataset:
    """#290: the blinded project's 2D image (another patient, its own UIDs)."""
    ds = build_planar_image("sc", 9)
    sop = f"{BLINDED_UID_ROOT}.3"
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID = sop
    ds.StudyInstanceUID, ds.SeriesInstanceUID = f"{BLINDED_UID_ROOT}.1", f"{BLINDED_UID_ROOT}.2"
    ds.PatientID, ds.PatientName, ds.StudyID = "HARNESS-B", "HARNESS^BLINDED", "HB"
    ds.SeriesDescription = "Harness blinded SC"
    return ds


def build_blinded_sr(image: Dataset) -> Dataset:
    """#290: an SR on the blinded image, as another tool would export it (ingested: no author, so hidden)."""
    ds = Dataset()
    sop = f"{BLINDED_UID_ROOT}.13"
    ds.file_meta = FileMetaDataset()
    ds.file_meta.MediaStorageSOPClassUID = Comprehensive3DSRStorage
    ds.file_meta.MediaStorageSOPInstanceUID = sop
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.SOPClassUID, ds.SOPInstanceUID = Comprehensive3DSRStorage, sop
    ds.StudyInstanceUID, ds.SeriesInstanceUID = image.StudyInstanceUID, f"{BLINDED_UID_ROOT}.12"
    ds.PatientID, ds.PatientName = image.PatientID, image.PatientName
    ds.StudyDate, ds.StudyTime, ds.StudyID = image.StudyDate, image.StudyTime, image.StudyID
    ds.Modality, ds.SeriesNumber, ds.InstanceNumber, ds.SeriesDescription = "SR", 2, 1, "Imported measurements"
    ds.ValueType, ds.ContinuityOfContent = "CONTAINER", "SEPARATE"
    ds.ConceptNameCodeSequence = [_code("126000", "DCM", "Imaging Measurement Report")]
    referenced = Dataset()
    referenced.ReferencedSOPClassUID, referenced.ReferencedSOPInstanceUID = image.SOPClassUID, image.SOPInstanceUID
    series_ref = Dataset()
    series_ref.SeriesInstanceUID = image.SeriesInstanceUID
    series_ref.ReferencedSOPSequence = [referenced]
    study_ref = Dataset()
    study_ref.StudyInstanceUID = image.StudyInstanceUID
    study_ref.ReferencedSeriesSequence = [series_ref]
    ds.CurrentRequestedProcedureEvidenceSequence = [study_ref]
    return ds


def _code(value: str, scheme: str, meaning: str) -> Dataset:
    code = Dataset()
    code.CodeValue, code.CodingSchemeDesignator, code.CodeMeaning = value, scheme, meaning
    return code


def build_wsi_annotations() -> Dataset:
    """Microscopy Bulk Simple Annotations (ANN) on the synthetic slide's base level: one POLYGON group per
    ANN_GROUPS entry, 2D coordinates, algorithm output. Same study and Frame of Reference as the slide."""
    ds = Dataset()
    sop = f"{WSI_UID_ROOT}.6.1"
    ds.file_meta = FileMetaDataset()
    ds.file_meta.MediaStorageSOPClassUID = MicroscopyBulkSimpleAnnotationsStorage
    ds.file_meta.MediaStorageSOPInstanceUID = sop
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.SOPClassUID, ds.SOPInstanceUID = MicroscopyBulkSimpleAnnotationsStorage, sop
    ds.StudyInstanceUID, ds.SeriesInstanceUID = f"{WSI_UID_ROOT}.1", f"{WSI_UID_ROOT}.5"
    ds.FrameOfReferenceUID = f"{WSI_UID_ROOT}.4"
    ds.PatientID, ds.PatientName, ds.PatientSex = "HARNESS-1", "HARNESS^CT", "O"
    ds.StudyDate, ds.StudyTime, ds.StudyID = "20260102", "120000", "H2"
    ds.StudyDescription, ds.SeriesDescription = "Viewer harness slide", "Synthetic regions (algorithm)"
    ds.Modality, ds.SeriesNumber, ds.InstanceNumber = "ANN", 2, 1
    ds.ContentLabel, ds.ContentDate, ds.ContentTime = "REGIONS", "20260102", "120000"
    ds.ContainerIdentifier = "HARNESS-SLIDE-1"
    ds.AnnotationCoordinateType = "2D"
    ds.PixelOriginInterpretation = "VOLUME"
    base = Dataset()
    base.ReferencedSOPClassUID = VLWholeSlideMicroscopyImageStorage
    base.ReferencedSOPInstanceUID = f"{WSI_UID_ROOT}.3.1"
    ds.ReferencedImageSequence = [base]
    referenced_series = Dataset()
    referenced_series.SeriesInstanceUID = f"{WSI_UID_ROOT}.2"
    referenced_series.ReferencedInstanceSequence = [base]
    ds.ReferencedSeriesSequence = [referenced_series]

    algorithm = Dataset()
    algorithm.AlgorithmName, algorithm.AlgorithmVersion = "harness-regions", "1"
    algorithm.AlgorithmFamilyCodeSequence = [_code("123109", "DCM", "Manual Processing")]
    groups = []
    for number, (label, (type_code, type_meaning), lab, polygons) in enumerate(ANN_GROUPS, start=1):
        group = Dataset()
        group.AnnotationGroupNumber = number
        group.AnnotationGroupUID = f"{WSI_UID_ROOT}.7.{number}"
        group.AnnotationGroupLabel = label
        group.AnnotationGroupGenerationType = "AUTOMATIC"
        group.AnnotationGroupAlgorithmIdentificationSequence = [algorithm]
        group.AnnotationPropertyCategoryCodeSequence = [_code("91723000", "SCT", "Anatomical structure")]
        group.AnnotationPropertyTypeCodeSequence = [_code(type_code, "SCT", type_meaning)]
        group.AnnotationAppliesToAllOpticalPaths = "YES"
        group.GraphicType = "POLYGON"
        group.NumberOfAnnotations = len(polygons)
        group.RecommendedDisplayCIELabValue = list(lab)
        points = [float(v) for polygon in polygons for point in polygon for v in point]
        group.PointCoordinatesData = np.asarray(points, dtype="<f4").tobytes()
        starts, index = [], 1  # 1-based index of each polygon's first value
        for polygon in polygons:
            starts.append(index)
            index += 2 * len(polygon)
        group.LongPrimitivePointIndexList = np.asarray(starts, dtype="<u4").tobytes()
        groups.append(group)
    ds.AnnotationGroupSequence = groups
    return ds


def _create_database_if_missing() -> None:
    name = connection.settings_dict["NAME"]
    with connection._nodb_cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", [name])
        if cursor.fetchone() is None:
            cursor.execute(f'CREATE DATABASE "{name}"')


def _member(project, username: str, role_name: str):
    user, _ = get_user_model().objects.get_or_create(username=username)
    role, _ = ResearchProjectRole.objects.get_or_create(name=role_name, defaults={"description": role_name})
    ResearchProjectUserRoleMap.objects.get_or_create(user=user, project=project, role=role)
    return user


def _session_cookie(user) -> dict:
    client = Client()
    client.force_login(user)
    name = settings.SESSION_COOKIE_NAME
    return {"name": name, "value": client.cookies[name].value}


def _series_ref(series: DicomSeries) -> dict:
    return {"studyUid": series.study.study_instance_uid, "seriesUid": series.series_instance_uid}


class Command(BaseCommand):
    help = "DEBUG only: seed the viewer harness project/user/CT and print a session cookie + UIDs as JSON."

    def add_arguments(self, parser):
        parser.add_argument(
            "--prepare-db", action="store_true",
            help="Create the configured database if it doesn't exist, migrate it, then seed.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("viewer_harness_seed only runs with DEBUG on (it creates a login session).")
        if options["prepare_db"]:
            _create_database_if_missing()
            call_command("migrate", verbosity=0)

        project, _ = ResearchProject.objects.get_or_create(
            name=PROJECT_NAME, defaults={"description": "Synthetic data for the local viewer browser tests (#278)"},
        )
        user = _member(project, USERNAME, PROJECT_ROLE_PI)
        view_only = _member(project, VIEW_ONLY_USERNAME, PROJECT_ROLE_INVESTIGATOR)

        series = self._ct_series(project)
        planar = {key: self._planar_series(project, key, i) for i, key in enumerate(PLANAR_FIXTURES, start=1)}
        wsi = self._wsi_series(project)
        fusion = {key: self._fusion_series(project, key) for key in FUSION_FIXTURES}
        self._wsi_annotations(project)
        blinded = self._blinded_series()
        self.stdout.write(json.dumps({
            "sessionCookie": _session_cookie(user),
            "viewOnlySessionCookie": _session_cookie(view_only),
            "ct": {
                "studyUid": series.study.study_instance_uid,
                "seriesUid": series.series_instance_uid,
                "imageCount": series.dicomfile_set.count(),
            },
            **{key: _series_ref(s) for key, s in planar.items()},
            **{key: {**_series_ref(s), "imageCount": s.dicomfile_set.count()} for key, s in fusion.items()},
            "wsi": {
                "studyUid": wsi.study.study_instance_uid,
                "seriesUid": wsi.series_instance_uid,
                "levels": len(WSI_DOWNSAMPLES),
                "baseTiles": (WSI_WIDTH // WSI_TILE) * (WSI_HEIGHT // WSI_TILE),
                "participant": str(wsi.study.study_participant_id),
            },
            "wsiAnnotations": {"groups": [meaning for _, (_, meaning), _, _ in ANN_GROUPS]},
            "blinded": {**_series_ref(blinded), "participant": str(blinded.study.study_participant_id)},
        }))

    def _blinded_series(self) -> DicomSeries:
        """#290: Blinded Annotation project, the harness PI as PI, a 2D image and an ingested SR on it."""
        project, _ = ResearchProject.objects.get_or_create(
            name=BLINDED_PROJECT_NAME, defaults={"description": "Blinded Annotation for the viewer browser tests (#290)"},
        )
        if not project.blinded_annotation:
            project.blinded_annotation = True
            project.save(update_fields=["blinded_annotation"])
        _member(project, USERNAME, PROJECT_ROLE_PI)
        lookup = {"study__study_participant__research_project": project, "modality": "OT"}
        existing = DicomSeries.objects.filter(**lookup).first()
        if existing:
            return existing
        image = build_blinded_image()
        with tempfile.TemporaryDirectory() as tmp:
            image.save_as(Path(tmp) / "image.dcm", enforce_file_format=True)
            build_blinded_sr(image).save_as(Path(tmp) / "sr.dcm", enforce_file_format=True)
            with override_settings(DICOM_ALLOWED_SOURCE_ROOTS=[Path(tmp)]):
                report = run_ingestion(project, tmp)
        if report.counts.get("ingested") != 2:
            errors = sorted({r.error for r in report.results if r.error})
            raise CommandError(f"Blinded fixture ingestion failed: {report.counts} {errors}")
        return DicomSeries.objects.get(**lookup)

    def _ct_series(self, project) -> DicomSeries:
        existing = DicomSeries.objects.filter(study__study_participant__research_project=project, modality="CT").first()
        if existing:
            return existing
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(CT_SLICES):
                build_ct_slice(i).save_as(Path(tmp) / f"ct-{i:02}.dcm", enforce_file_format=True)
            with override_settings(DICOM_ALLOWED_SOURCE_ROOTS=[Path(tmp)]):
                report = run_ingestion(project, tmp)
        if report.counts.get("ingested") != CT_SLICES:
            errors = sorted({r.error for r in report.results if r.error})
            raise CommandError(f"CT ingestion failed: {report.counts} {errors}")
        return DicomSeries.objects.get(study__study_participant__research_project=project, modality="CT")

    def _fusion_series(self, project, key: str) -> DicomSeries:
        description = FUSION_FIXTURES[key][0]
        lookup = {"study__study_participant__research_project": project, "series_description": description}
        existing = DicomSeries.objects.filter(**lookup).first()
        if existing:
            return existing
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(CT_SLICES):
                build_fusion_slice(key, i).save_as(Path(tmp) / f"{key}-{i:02}.dcm", enforce_file_format=True)
            with override_settings(DICOM_ALLOWED_SOURCE_ROOTS=[Path(tmp)]):
                report = run_ingestion(project, tmp)
        if report.counts.get("ingested") != CT_SLICES:
            errors = sorted({r.error for r in report.results if r.error})
            raise CommandError(f"{key} ingestion failed: {report.counts} {errors}")
        return DicomSeries.objects.get(**lookup)

    def _planar_series(self, project, key: str, index: int) -> DicomSeries:
        description = PLANAR_FIXTURES[key][0]
        lookup = {"study__study_participant__research_project": project, "series_description": description}
        existing = DicomSeries.objects.filter(**lookup).first()
        if existing:
            return existing
        with tempfile.TemporaryDirectory() as tmp:
            build_planar_image(key, index).save_as(Path(tmp) / f"{key}.dcm", enforce_file_format=True)
            with override_settings(DICOM_ALLOWED_SOURCE_ROOTS=[Path(tmp)]):
                report = run_ingestion(project, tmp)
        if report.counts.get("ingested") != 1:
            errors = sorted({r.error for r in report.results if r.error})
            raise CommandError(f"{key} ingestion failed: {report.counts} {errors}")
        return DicomSeries.objects.get(**lookup)

    def _wsi_series(self, project) -> DicomSeries:
        existing = DicomSeries.objects.filter(study__study_participant__research_project=project, modality="SM").first()
        if existing:
            return existing
        with tempfile.TemporaryDirectory() as tmp:
            for level in range(len(WSI_DOWNSAMPLES)):
                build_wsi_level(level).save_as(Path(tmp) / f"wsi-{level}.dcm", enforce_file_format=True)
            with override_settings(DICOM_ALLOWED_SOURCE_ROOTS=[Path(tmp)]):
                report = run_ingestion(project, tmp)
        if report.counts.get("ingested") != len(WSI_DOWNSAMPLES):
            errors = sorted({r.error for r in report.results if r.error})
            raise CommandError(f"WSI ingestion failed: {report.counts} {errors}")
        return DicomSeries.objects.get(study__study_participant__research_project=project, modality="SM")

    def _wsi_annotations(self, project) -> DicomSeries:
        existing = DicomSeries.objects.filter(study__study_participant__research_project=project, modality="ANN").first()
        if existing:
            return existing
        with tempfile.TemporaryDirectory() as tmp:
            build_wsi_annotations().save_as(Path(tmp) / "ann.dcm", enforce_file_format=True)
            with override_settings(DICOM_ALLOWED_SOURCE_ROOTS=[Path(tmp)]):
                report = run_ingestion(project, tmp)
        if report.counts.get("ingested") != 1:
            errors = sorted({r.error for r in report.results if r.error})
            raise CommandError(f"ANN ingestion failed: {report.counts} {errors}")
        return DicomSeries.objects.get(study__study_participant__research_project=project, modality="ANN")
