"""WADO-RS /frames (#274): frame offset index, ranged reads, media types, 406.

Seams: the HTTP endpoint (bytes + part headers, 406), `ingest_files` (the
frame offset index it stores is observed only through the endpoint and
through the stored-bytes read path), and the backfill task.
"""
import re

import boto3
import pytest
from botocore.client import BaseClient
from moto import mock_aws

from MiqaResearch.data.models import DicomFile, ResearchProject
from MiqaResearch.data.models.dicom_storage import DicomStorage
from MiqaResearch.tasks.dicom_handling.frame_index_backfill import backfill_frame_indexes
from tests.client_binding_helpers import bound_client
from tests.dicom_fixtures import build_multiframe_ct, build_tiled_wsi_jpeg, fake_jpeg_tile, write_dicom
from tests.dicom_ingest_helper import ingest_files

TOKEN = "frames-test-token"
NATIVE_PART_TYPE = "application/octet-stream; transfer-syntax=1.2.840.10008.1.2.1"
JPEG_PART_TYPE = "image/jpeg; transfer-syntax=1.2.840.10008.1.2.4.50"


@pytest.fixture(autouse=True)
def encryption_keys(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="


@pytest.fixture(autouse=True)
def local_media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.DEBUG = False
    settings.MIDDLEWARE = [m for m in settings.MIDDLEWARE if "debug_toolbar" not in m]


@pytest.fixture
def research_project(db):
    return ResearchProject.objects.create(name="Frames project", description="Project for #274 tests")


@pytest.fixture
def bearer(research_project):
    """A client bound to the project, all Sites (#277)."""
    return bound_client(research_project, token=TOKEN)


def _ingest(research_project, tmp_path, ds, name="f.dcm") -> DicomFile:
    report = ingest_files(research_project, write_dicom(ds, tmp_path / name))
    assert report.counts["ingested"] == 1, report.results
    return DicomFile.objects.get(sop_instance_uid=report.results[0].sop_instance_uid)


def _frames_url(dcm_file: DicomFile, frame_list: str) -> str:
    return (
        f"/api/v1/dicom/studies/{dcm_file.series.study.study_instance_uid}"
        f"/series/{dcm_file.series.series_instance_uid}"
        f"/instances/{dcm_file.sop_instance_uid}/frames/{frame_list}"
    )


def _parts(response) -> list[tuple[str, bytes]]:
    """Split a multipart/related body into (part Content-Type, payload) pairs."""
    boundary = re.search(r'boundary="?([^";]+)"?', response["Content-Type"]).group(1).encode()
    body = b"".join(response.streaming_content) if response.streaming else response.content
    parts = []
    for chunk in body.split(b"--" + boundary)[1:]:
        if chunk.startswith(b"--"):
            break
        head, _, payload = chunk.removeprefix(b"\r\n").partition(b"\r\n\r\n")
        headers = dict(line.split(": ", 1) for line in head.decode().split("\r\n"))
        parts.append((headers["Content-Type"], payload.removesuffix(b"\r\n")))
    return parts


def _native_frame(ds, n: int) -> bytes:
    size = ds.Rows * ds.Columns * ds.SamplesPerPixel * ds.BitsAllocated // 8
    return ds.PixelData[(n - 1) * size : n * size]


def test_an_unlinked_studys_frames_are_served_to_a_project_admin_byte_exact(research_project, tmp_path, client):
    """ADR 0035 (#415): the frame path tolerates a Study whose Participant Key is unlinked."""
    from contract.constants.research_project_role import PROJECT_ROLE_ADMIN
    from tests.test_annotations_api import _member

    ds = build_multiframe_ct(number_of_frames=2)
    dcm_file = _ingest(research_project, tmp_path, ds)
    key = dcm_file.series.study.participant_key
    key.study_participant = None
    key.save(update_fields=["study_participant"])
    client.force_login(_member(research_project, PROJECT_ROLE_ADMIN))

    response = client.get(_frames_url(dcm_file, "2"))

    assert response.status_code == 200
    assert _parts(response) == [(NATIVE_PART_TYPE, _native_frame(ds, 2))]


def test_native_multiframe_ct_frames_are_served_byte_exact(research_project, tmp_path, client, bearer):
    ds = build_multiframe_ct(number_of_frames=3)
    dcm_file = _ingest(research_project, tmp_path, ds)

    response = client.get(_frames_url(dcm_file, "3,1"), **bearer)

    assert response.status_code == 200
    assert response["Content-Type"].startswith('multipart/related; type="application/octet-stream"')
    assert _parts(response) == [
        (NATIVE_PART_TYPE, _native_frame(ds, 3)),
        (NATIVE_PART_TYPE, _native_frame(ds, 1)),
    ]


@pytest.mark.parametrize(
    "fixture_kwargs",
    [
        pytest.param({}, id="basic-offset-table"),
        pytest.param({"has_bot": False}, id="no-offset-table"),
        pytest.param({"extended_offset_table": True}, id="extended-offset-table"),
        pytest.param(
            {"has_bot": False, "fragments_per_frame": 2, "tiles": [fake_jpeg_tile(i, size=16) for i in range(4)]},
            id="two-fragments-per-frame-no-offset-table",
        ),
        pytest.param(
            {"fragments_per_frame": 2, "tiles": [fake_jpeg_tile(i, size=16) for i in range(4)]},
            id="two-fragments-per-frame-with-offset-table",
        ),
    ],
)
def test_tiled_full_jpeg_wsi_frames_are_served_as_stored(research_project, tmp_path, client, bearer, fixture_kwargs):
    ds = build_tiled_wsi_jpeg(**fixture_kwargs)
    tiles = fixture_kwargs.get("tiles") or [fake_jpeg_tile(i) for i in range(4)]
    dcm_file = _ingest(research_project, tmp_path, ds)

    response = client.get(
        _frames_url(dcm_file, "2,4"),
        HTTP_ACCEPT='multipart/related; type="application/octet-stream"; transfer-syntax=*',
        **bearer,
    )

    assert response.status_code == 200
    assert response["Content-Type"].startswith('multipart/related; type="image/jpeg"')
    assert _parts(response) == [(JPEG_PART_TYPE, tiles[1]), (JPEG_PART_TYPE, tiles[3])]


@pytest.mark.parametrize(
    "accept",
    [
        'multipart/related; type="image/jpeg"',
        "multipart/related; type=image/jpeg; transfer-syntax=1.2.840.10008.1.2.4.50",
        'multipart/related; type="image/jp2", multipart/related; type="image/jpeg"',
        "*/*",
    ],
)
def test_jpeg_frames_satisfy_matching_accept(research_project, tmp_path, client, bearer, accept):
    dcm_file = _ingest(research_project, tmp_path, build_tiled_wsi_jpeg())

    response = client.get(_frames_url(dcm_file, "1"), HTTP_ACCEPT=accept, **bearer)

    assert response.status_code == 200
    assert _parts(response) == [(JPEG_PART_TYPE, fake_jpeg_tile(0))]


@pytest.mark.parametrize(
    "accept",
    [
        'multipart/related; type="image/jp2"',
        'multipart/related; type="image/jpeg"; transfer-syntax=1.2.840.10008.1.2.4.70',
        'multipart/related; type="application/octet-stream"',
        "multipart/related; type=application/octet-stream; transfer-syntax=1.2.840.10008.1.2.1",
        "image/jpeg",
    ],
)
def test_jpeg_frames_refuse_unsatisfiable_accept_with_406(research_project, tmp_path, client, bearer, accept):
    dcm_file = _ingest(research_project, tmp_path, build_tiled_wsi_jpeg())

    response = client.get(_frames_url(dcm_file, "1"), HTTP_ACCEPT=accept, **bearer)

    assert response.status_code == 406


def test_native_frames_refuse_compressed_accept_with_406(research_project, tmp_path, client, bearer):
    dcm_file = _ingest(research_project, tmp_path, build_multiframe_ct())

    response = client.get(_frames_url(dcm_file, "1"), HTTP_ACCEPT='multipart/related; type="image/jpeg"', **bearer)

    assert response.status_code == 406


def test_frame_number_out_of_range_is_404_and_garbage_is_400(research_project, tmp_path, client, bearer):
    dcm_file = _ingest(research_project, tmp_path, build_multiframe_ct(number_of_frames=3))

    assert client.get(_frames_url(dcm_file, "4"), **bearer).status_code == 404
    assert client.get(_frames_url(dcm_file, "0"), **bearer).status_code == 404
    assert client.get(_frames_url(dcm_file, "x"), **bearer).status_code == 400


def test_frame_request_reads_only_its_byte_range_from_local_storage(
    research_project, tmp_path, client, bearer, monkeypatch
):
    ds = build_multiframe_ct(number_of_frames=3)
    dcm_file = _ingest(research_project, tmp_path, ds)

    def full_open_forbidden(self, name, mode="rb"):
        raise AssertionError(f"/frames opened the whole stored file {name}")

    monkeypatch.setattr(DicomStorage, "_open", full_open_forbidden)
    response = client.get(_frames_url(dcm_file, "2"), **bearer)

    assert response.status_code == 200
    assert _parts(response) == [(NATIVE_PART_TYPE, _native_frame(ds, 2))]


@mock_aws
def test_frame_request_is_a_ranged_s3_get(research_project, tmp_path, client, bearer, settings, monkeypatch):
    settings.DICOM_STORAGE_BACKEND = "s3"
    settings.DICOM_S3_BUCKET = "dicom-storage"
    settings.DICOM_S3_ENDPOINT_URL = None
    settings.DICOM_S3_REGION_NAME = "us-east-1"
    settings.DICOM_S3_ACCESS_KEY_ID = "testing"
    settings.DICOM_S3_SECRET_ACCESS_KEY = "testing"
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="dicom-storage")
    tiles = [fake_jpeg_tile(i, size=40) for i in range(4)]
    dcm_file = _ingest(research_project, tmp_path, build_tiled_wsi_jpeg(tiles=tiles))

    get_objects = []
    make_api_call = BaseClient._make_api_call

    def recording_api_call(self, operation_name, api_params):
        if operation_name == "GetObject":
            get_objects.append(api_params)
        return make_api_call(self, operation_name, api_params)

    monkeypatch.setattr(BaseClient, "_make_api_call", recording_api_call)
    response = client.get(_frames_url(dcm_file, "3"), **bearer)

    assert response.status_code == 200
    assert _parts(response) == [(JPEG_PART_TYPE, tiles[2])]
    assert get_objects, "expected the frame to be fetched from S3"
    assert all(params["Key"] == dcm_file.file.name for params in get_objects)
    ranges = [params.get("Range") for params in get_objects]
    assert None not in ranges, "a GetObject without Range downloads the whole object"
    first, last = (int(n) for n in ranges[0].removeprefix("bytes=").split("-"))
    assert last - first + 1 == 8 + len(tiles[2])  # one fragment item: header + tile


def test_duplicate_update_reindexes_replaced_file(research_project, tmp_path, client, bearer):
    dcm_file = _ingest(research_project, tmp_path, build_multiframe_ct(number_of_frames=2), "old.dcm")
    replacement = build_tiled_wsi_jpeg(
        study_instance_uid="1.2.9999.42.1.1001",
        series_instance_uid="1.2.9999.42.1.1002",
        sop_instance_uid="1.2.9999.42.1.1003",
    )

    report = ingest_files(
        research_project, write_dicom(replacement, tmp_path / "new.dcm"), duplicate_handling="update")

    assert report.load_result.updated == 1
    response = client.get(_frames_url(dcm_file, "4"), **bearer)
    assert _parts(response) == [(JPEG_PART_TYPE, fake_jpeg_tile(3))]


def _forget_frame_indexes():
    """Make rows look like they were ingested before #274 (no frame offset index)."""
    DicomFile.objects.update(frame_index=None, transfer_syntax_uid=None)


def test_unindexed_file_is_indexed_on_first_frame_request(research_project, tmp_path, client, bearer, monkeypatch):
    ds = build_multiframe_ct(number_of_frames=2)
    dcm_file = _ingest(research_project, tmp_path, ds)
    _forget_frame_indexes()

    first = client.get(_frames_url(dcm_file, "2"), **bearer)
    monkeypatch.setattr(DicomStorage, "_open", lambda *args, **kwargs: pytest.fail("index was not persisted"))
    second = client.get(_frames_url(dcm_file, "1"), **bearer)

    assert _parts(first) == [(NATIVE_PART_TYPE, _native_frame(ds, 2))]
    assert _parts(second) == [(NATIVE_PART_TYPE, _native_frame(ds, 1))]


def test_backfill_indexes_existing_rows_and_is_idempotent(research_project, tmp_path, client, bearer, monkeypatch):
    ct = build_multiframe_ct(number_of_frames=2)
    ct_file = _ingest(research_project, tmp_path, ct, "ct.dcm")
    wsi_file = _ingest(research_project, tmp_path, build_tiled_wsi_jpeg(), "wsi.dcm")
    _forget_frame_indexes()

    first_run = backfill_frame_indexes.call()
    after_first = {row.pk: (row.transfer_syntax_uid, row.frame_index) for row in DicomFile.objects.all()}
    second_run = backfill_frame_indexes.call()

    assert first_run == {"indexed": 2, "failed": 0}
    assert second_run == {"indexed": 0, "failed": 0}
    assert after_first == {row.pk: (row.transfer_syntax_uid, row.frame_index) for row in DicomFile.objects.all()}
    monkeypatch.setattr(DicomStorage, "_open", lambda *args, **kwargs: pytest.fail("backfill left a row unindexed"))
    assert _parts(client.get(_frames_url(ct_file, "2"), **bearer)) == [(NATIVE_PART_TYPE, _native_frame(ct, 2))]
    assert _parts(client.get(_frames_url(wsi_file, "4"), **bearer)) == [(JPEG_PART_TYPE, fake_jpeg_tile(3))]
