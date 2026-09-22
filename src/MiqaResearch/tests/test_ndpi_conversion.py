"""Standalone *.ndpi -> DICOM converter tests (#125).

Two tiers: fast, default-suite unit tests against a mocked `WsiDicomizer`
boundary, and a `long_running`-marked integration tier that downloads a real
Hamamatsu sample (CC0, from OpenSlide's public test-data mirror at
openslide.cs.cmu.edu) and proves an actual round-trip: ndpi -> DICOM ->
ordinary `run_ingestion`. Real NDPI samples are hundreds of MB and
hand-crafting a valid synthetic one would mean reverse-engineering NDPI's
proprietary 64-bit-offset TIFF hybrid layout and Hamamatsu's private strip
tags -- even opentile's own test suite downloads real files rather than
synthesizing them (its tests/download_test_images.py).
"""
from pathlib import Path
from unittest.mock import patch

import pydicom
import pytest
import requests
from pydicom.uid import VLWholeSlideMicroscopyImageStorage

from MiqaResearch.data.models import DicomFile, ResearchProject
from MiqaResearch.tasks.dicom_handling.ndpi_conversion import (
    NdpiConversionError,
    NdpiSourceNotFoundError,
    NdpiUnsupportedSourceError,
    convert_ndpi_to_dicom,
)
from MiqaResearch.tasks.dicom_handling.pipeline import run_ingestion

NDPI_SAMPLE_URL = "https://openslide.cs.cmu.edu/download/openslide-testdata/Hamamatsu/CMU-1.ndpi"
NDPI_SAMPLE_CACHE = Path(__file__).parent / "testdata" / "ndpi" / "CMU-1.ndpi"


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
    return ResearchProject.objects.create(name="Ndpi conversion project", description="Project for #125 tests")


class TestConvertNdpiToDicom:
    def test_raises_for_missing_source(self, tmp_path):
        with pytest.raises(NdpiSourceNotFoundError):
            convert_ndpi_to_dicom(tmp_path / "missing.ndpi", tmp_path / "out")

    def test_rejects_non_ndpi_suffix(self, tmp_path):
        source = tmp_path / "slide.svs"
        source.write_bytes(b"not really an svs")

        with pytest.raises(NdpiUnsupportedSourceError):
            convert_ndpi_to_dicom(source, tmp_path / "out")

    def test_delegates_to_wsidicomizer_and_returns_produced_paths(self, tmp_path):
        source = tmp_path / "slide.ndpi"
        source.write_bytes(b"fake ndpi bytes")
        output_dir = tmp_path / "out"
        produced = [output_dir / "level0.dcm", output_dir / "level1.dcm"]

        with patch(
            "MiqaResearch.tasks.dicom_handling.ndpi_conversion.WsiDicomizer.convert",
            return_value=produced,
        ) as mock_convert:
            result = convert_ndpi_to_dicom(source, output_dir)

        assert result == produced
        args, kwargs = mock_convert.call_args
        assert args[0] == source
        assert kwargs["output_path"] == output_dir
        assert output_dir.is_dir()

    def test_wraps_underlying_conversion_errors(self, tmp_path):
        source = tmp_path / "slide.ndpi"
        source.write_bytes(b"fake ndpi bytes")

        with patch(
            "MiqaResearch.tasks.dicom_handling.ndpi_conversion.WsiDicomizer.convert",
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(NdpiConversionError, match="boom"):
                convert_ndpi_to_dicom(source, tmp_path / "out")


def test_ingestion_pipeline_treats_ndpi_files_like_any_non_dicom_file(research_project, tmp_path):
    """No special-casing (#125 AC): an *.ndpi source is never auto-converted, just reported like any
    other file `run_ingestion` can't parse as DICOM."""
    ndpi_path = tmp_path / "slide.ndpi"
    ndpi_path.write_bytes(b"not a dicom file, just an ndpi-named blob")

    report = run_ingestion(research_project, ndpi_path)

    assert report.counts["error"] == 1
    assert report.counts["ingested"] == 0


@pytest.fixture(scope="session")
def real_ndpi_sample() -> Path:
    """Download and cache a real Hamamatsu NDPI sample (~190MB, CC0-licensed OpenSlide test data).

    Not committed to the repo; cached under tests/testdata/ so repeat runs
    don't re-download. Skips (rather than fails) if the download isn't
    reachable, mirroring opentile's own missing-file skip behavior.
    """
    if not NDPI_SAMPLE_CACHE.exists():
        NDPI_SAMPLE_CACHE.parent.mkdir(parents=True, exist_ok=True)
        partial_path = NDPI_SAMPLE_CACHE.with_suffix(".part")
        try:
            with requests.get(NDPI_SAMPLE_URL, stream=True, timeout=60) as response:
                response.raise_for_status()
                with open(partial_path, "wb") as fh:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        fh.write(chunk)
        except requests.RequestException as exc:
            pytest.skip(f"could not download NDPI sample: {exc}")
        partial_path.rename(NDPI_SAMPLE_CACHE)
    return NDPI_SAMPLE_CACHE


@pytest.mark.long_running
class TestRealNdpiConversion:
    """Gated integration tier (#125 AC): a real download, excluded from the default suite."""

    def test_produces_valid_wsi_dicom_file_set(self, real_ndpi_sample, tmp_path):
        produced = convert_ndpi_to_dicom(real_ndpi_sample, tmp_path / "out")

        assert produced
        for file_path in produced:
            ds = pydicom.dcmread(file_path)
            assert ds.SOPClassUID == VLWholeSlideMicroscopyImageStorage

    def test_converted_output_ingests_via_normal_pipeline(self, real_ndpi_sample, tmp_path, research_project):
        """CMU-1.ndpi is public, pre-anonymized test data with no embedded PatientID; a real
        scanner's NDPI output already carries one via the site's slide-labeling workflow. Confirmed
        (by running this test against the converter's raw, unpatched output) that a missing PatientID
        is the *only* thing standing between this real sample's conversion and successful ingestion --
        every produced file errored with exactly "no usable patient identifier (PatientID missing or
        empty)" and nothing else, so patching only that field here exercises the pipeline's normal
        patient-matching path faithfully; the converter itself does no patient-identity handling."""
        output_dir = tmp_path / "converted"
        produced = convert_ndpi_to_dicom(real_ndpi_sample, output_dir)
        for file_path in produced:
            ds = pydicom.dcmread(file_path)
            ds.PatientID = "NDPI-TEST-PATIENT-125"
            ds.save_as(file_path)

        report = run_ingestion(research_project, output_dir)

        assert report.counts["ingested"] >= 1, report.results
        assert DicomFile.objects.filter(research_project=research_project).exists()
