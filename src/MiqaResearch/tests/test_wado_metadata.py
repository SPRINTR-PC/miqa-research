"""WADO-RS /metadata served through the De-identification Profile (#275).

Seam: the HTTP endpoints (study, series and instance /metadata), fed by
`run_ingestion`. A client builds frame URLs from the returned UIDs, so the
round trip metadata -> /frames is the key behaviour.
"""
import pytest
from pydicom.dataset import Dataset

from MiqaResearch.data.models import DicomFile, ResearchProject
from MiqaResearch.tasks.dicom_handling.pipeline import run_ingestion
from tests.client_binding_helpers import bound_client
from tests.dicom_fixtures import (
    DEFAULT_BIRTH_DATE,
    DEFAULT_PATIENT_ID,
    DEFAULT_PATIENT_NAME,
    build_multiframe_ct,
    build_tiled_wsi_jpeg,
    write_dicom,
)

TOKEN = "metadata-test-token"
STUDY_UID, SERIES_UID, SOP_UID = "0020000D", "0020000E", "00080018"


@pytest.fixture(autouse=True)
def encryption_keys(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="


@pytest.fixture(autouse=True)
def local_media(settings, tmp_path):
    settings.DICOM_ALLOWED_SOURCE_ROOTS = [tmp_path]
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.DEBUG = False
    settings.MIDDLEWARE = [m for m in settings.MIDDLEWARE if "debug_toolbar" not in m]


@pytest.fixture
def research_project(db):
    return ResearchProject.objects.create(name="Metadata project", description="Project for #275 tests")


@pytest.fixture
def bearer(research_project):
    """A client bound to the project, all Sites (#277)."""
    return bound_client(research_project, token=TOKEN)


def _ingest(research_project, tmp_path, *datasets) -> list[DicomFile]:
    files = []
    for index, ds in enumerate(datasets):
        report = run_ingestion(research_project, write_dicom(ds, tmp_path / f"f{index}.dcm"))
        assert report.counts["ingested"] == 1, report.results
        files.append(DicomFile.objects.get(sop_instance_uid=report.results[0].sop_instance_uid))
    return files


def _value(instance: dict, tag: str):
    values = instance[tag].get("Value")
    return values[0] if values else None


def _series_url(dcm_file: DicomFile) -> str:
    return (
        f"/api/v1/dicom/studies/{dcm_file.series.study.study_instance_uid}"
        f"/series/{dcm_file.series.series_instance_uid}/metadata"
    )


def test_frame_urls_built_from_series_metadata_resolve(research_project, tmp_path, client, bearer):
    (dcm_file,) = _ingest(research_project, tmp_path, build_tiled_wsi_jpeg())

    response = client.get(_series_url(dcm_file), **bearer)

    assert response.status_code == 200
    (instance,) = response.json()
    frame_url = (
        f"/api/v1/dicom/studies/{_value(instance, STUDY_UID)}/series/{_value(instance, SERIES_UID)}"
        f"/instances/{_value(instance, SOP_UID)}/frames/1"
    )
    frame = client.get(
        frame_url, HTTP_ACCEPT='multipart/related; type="application/octet-stream"; transfer-syntax=*', **bearer
    )
    assert frame.status_code == 200


def test_metadata_carries_no_phi_and_the_participant_pseudonym(research_project, tmp_path, client, bearer):
    ds = build_multiframe_ct()
    ds.AccessionNumber = "ACC-777"
    ds.PatientAddress = "Home Road 1"
    ds.OperatorsName = "OPERATOR^OLGA"
    (dcm_file,) = _ingest(research_project, tmp_path, ds)
    alias = dcm_file.series.study.participant_key.study_participant.alias1

    response = client.get(_series_url(dcm_file), **bearer)

    assert response.status_code == 200
    (instance,) = response.json()
    assert instance["00100010"]["Value"] == [{"Alphabetic": alias}]  # PatientName
    assert _value(instance, "00100020") == alias  # PatientID
    assert _value(instance, "00120062") == "YES"  # PatientIdentityRemoved
    body = response.content.decode()
    for phi in (DEFAULT_PATIENT_ID, DEFAULT_PATIENT_NAME, DEFAULT_BIRTH_DATE, "ACC-777", "Home Road", "OLGA",
                "SMITH^ARTHUR", "1.2.9999.42.1.1001", "1.2.9999.42.1.1002", "1.2.9999.42.1.1003",
                "1.2.9999.42.1.1004"):
        assert phi not in body, phi
    assert _value(instance, "00200052") == dcm_file.frame_of_reference_uid  # FrameOfReferenceUID pseudonym


def test_metadata_carries_the_tags_cornerstone_needs(research_project, tmp_path, client, bearer):
    """Required-tag list: research cornerstone3d-mpr-fusion §5 (#187)."""
    ds = build_multiframe_ct(modality="PT", image_orientation_patient="1\\0\\0\\0\\1\\0")
    ds.SliceThickness = "2.0"
    ds.SpacingBetweenSlices = "2.0"
    ds.PlanarConfiguration = 0
    ds.RescaleIntercept = "0"
    ds.RescaleSlope = "1.5"
    ds.RescaleType = "BQML"
    ds.WindowCenter = "40"
    ds.WindowWidth = "400"
    ds.VOILUTFunction = "LINEAR"
    ds.SeriesDate, ds.SeriesTime = "20240315", "101500"
    ds.AcquisitionDate, ds.AcquisitionTime = "20240315", "101500"
    ds.SeriesNumber, ds.InstanceNumber = 3, 1
    ds.Units = "BQML"
    ds.CorrectedImage = ["ATTN", "DECY"]
    ds.DecayCorrection = "START"
    ds.PatientWeight, ds.PatientSize = "70", "1.75"
    ds.FrameReferenceTime = "0"
    ds.ActualFrameDuration = 300000
    drug = Dataset()
    drug.RadionuclideTotalDose = "370000000"
    drug.RadionuclideHalfLife = "6586.2"
    drug.RadiopharmaceuticalStartTime = "093000"
    drug.RadiopharmaceuticalStartDateTime = "20240315093000"
    ds.RadiopharmaceuticalInformationSequence = [drug]
    (dcm_file,) = _ingest(research_project, tmp_path, ds)

    (instance,) = client.get(_series_url(dcm_file), **bearer).json()

    required = {
        # imageId construction
        "0020000D", "0020000E", "00080018", "00080016", "00280008",
        # geometry
        "00200032", "00200037", "00280030", "00280010", "00280011", "00200052", "00180050", "00180088",
        # pixel decoding (+ transfer syntax)
        "00280002", "00280004", "00280100", "00280101", "00280102", "00280103", "00280006", "00083002",
        # modality LUT / VOI
        "00281052", "00281053", "00281054", "00281050", "00281051", "00281056",
        # series / fusion gating
        "00080060", "00080021", "00080031", "00080022", "00080032", "00200011", "00200013",
        # PET SUV
        "00541001", "00280051", "00541102", "00540016", "00101030", "00101020", "00100040", "00541300", "00181242",
    }
    assert required - instance.keys() == set()
    assert len(instance["00200037"]["Value"]) == 6
    assert instance["00083002"] == {"vr": "UI", "Value": ["1.2.840.10008.1.2.1"]}
    drug_out = instance["00540016"]["Value"][0]
    assert {"00181074", "00181075", "00181072", "00181078"} <= drug_out.keys()
    assert "7FE00010" not in instance  # never pixel data


def test_available_transfer_syntax_is_the_stored_encapsulated_syntax(research_project, tmp_path, client, bearer):
    (dcm_file,) = _ingest(research_project, tmp_path, build_tiled_wsi_jpeg())

    (instance,) = client.get(_series_url(dcm_file), **bearer).json()

    assert instance["00083002"] == {"vr": "UI", "Value": ["1.2.840.10008.1.2.4.50"]}


def test_study_and_instance_metadata_are_sanitized_too(research_project, tmp_path, client, bearer):
    first, second = _ingest(
        research_project, tmp_path,
        build_multiframe_ct(sop_instance_uid="1.2.9999.42.1.2001"),
        build_multiframe_ct(sop_instance_uid="1.2.9999.42.1.2002"),
    )
    study_uid = first.series.study.study_instance_uid

    study = client.get(f"/api/v1/dicom/studies/{study_uid}/metadata", **bearer)
    instance = client.get(
        f"/api/v1/dicom/studies/{study_uid}/series/{second.series.series_instance_uid}"
        f"/instances/{second.sop_instance_uid}/metadata",
        **bearer,
    )

    assert study.status_code == 200
    assert {_value(item, SOP_UID) for item in study.json()} == {first.sop_instance_uid, second.sop_instance_uid}
    assert instance.status_code == 200
    assert [_value(item, SOP_UID) for item in instance.json()] == [second.sop_instance_uid]
    for response in (study, instance):
        assert DEFAULT_PATIENT_ID not in response.content.decode()


def test_unknown_series_metadata_is_404(research_project, client, bearer):
    response = client.get("/api/v1/dicom/studies/2.25.1/series/2.25.2/metadata", **bearer)

    assert response.status_code == 404
