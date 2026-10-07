"""Seed data for the local Playwright viewer harness (#278). DEBUG only.

Creates (once) a "Viewer harness" Research Project with a PI user, a view-only (Investigator) user
and an ingested synthetic CT stack, then prints JSON for the harness: fresh session cookies for both and the
pseudonymized study/series UIDs to open. Idempotent: re-runs reuse the project and its series.
Fully synthetic pixel data and demo identifiers only.
"""
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
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian

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
        self.stdout.write(json.dumps({
            "sessionCookie": _session_cookie(user),
            "viewOnlySessionCookie": _session_cookie(view_only),
            "ct": {
                "studyUid": series.study.study_instance_uid,
                "seriesUid": series.series_instance_uid,
                "imageCount": series.dicomfile_set.count(),
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
