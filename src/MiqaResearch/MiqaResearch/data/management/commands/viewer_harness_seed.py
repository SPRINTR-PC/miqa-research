"""Seed data for the local Playwright viewer harness (#278). DEBUG only.

Creates (once) a "Viewer harness" Research Project with a PI user, a view-only (Investigator) user,
an ingested synthetic CT stack and a synthetic TILED_FULL whole-slide image (#285), then prints JSON for the harness: fresh session cookies for both and the
pseudonymized study/series UIDs to open. Idempotent: re-runs reuse the project and its series.
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
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, JPEGBaseline8Bit, VLWholeSlideMicroscopyImageStorage

from MiqaResearch.data.models import (
    DicomSeries,
    ResearchProject,
    ResearchProjectRole,
    ResearchProjectUserRoleMap,
)
from MiqaResearch.tasks.dicom_handling.pipeline import run_ingestion
from contract.constants.research_project_role import PROJECT_ROLE_INVESTIGATOR, PROJECT_ROLE_PI

PROJECT_NAME = "Viewer harness"
USERNAME = "viewer-harness"
VIEW_ONLY_USERNAME = "viewer-harness-view-only"
CT_SLICES = 16
CT_SIZE = 64
SLICE_SPACING = 2.5
CT_UID_ROOT = "2.25.278278278"
WSI_UID_ROOT = "2.25.285285285"
WSI_TILE = 256
WSI_WIDTH, WSI_HEIGHT = 2048, 1536  # base level, pixels: 8 × 6 tiles
WSI_PIXEL_MM = 0.0005  # 0.5 µm at the base level
WSI_DOWNSAMPLES = (1, 4)  # two pyramid levels, so the viewer opens zoomed out and can zoom in


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
        wsi = self._wsi_series(project)
        self.stdout.write(json.dumps({
            "sessionCookie": _session_cookie(user),
            "viewOnlySessionCookie": _session_cookie(view_only),
            "ct": {
                "studyUid": series.study.study_instance_uid,
                "seriesUid": series.series_instance_uid,
                "imageCount": series.dicomfile_set.count(),
            },
            "wsi": {
                "studyUid": wsi.study.study_instance_uid,
                "seriesUid": wsi.series_instance_uid,
                "levels": len(WSI_DOWNSAMPLES),
                "baseTiles": (WSI_WIDTH // WSI_TILE) * (WSI_HEIGHT // WSI_TILE),
            },
        }))

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
