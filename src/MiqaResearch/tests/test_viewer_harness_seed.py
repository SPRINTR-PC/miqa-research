"""`viewer_harness_seed` (#278): DEBUG-only seed for the local Playwright viewer harness.

Seam: the command's JSON output, used the way the harness uses it (session cookie → WADO).
"""
import io
import json

import pytest
from django.core.management import CommandError, call_command


@pytest.fixture(autouse=True)
def local_env(settings, tmp_path):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.DICOM_STORAGE_BACKEND = "local"
    settings.MIDDLEWARE = [m for m in settings.MIDDLEWARE if "debug_toolbar" not in m]


def _seed() -> dict:
    out = io.StringIO()
    call_command("viewer_harness_seed", stdout=out)
    return json.loads(out.getvalue())


@pytest.mark.django_db
def test_seed_refuses_to_run_without_debug(settings):
    settings.DEBUG = False

    with pytest.raises(CommandError):
        _seed()


@pytest.mark.django_db
def test_seed_gives_a_session_that_can_read_the_ct_stack(settings, client):
    settings.DEBUG = True

    seeded = _seed()
    client.cookies[seeded["sessionCookie"]["name"]] = seeded["sessionCookie"]["value"]
    response = client.get(
        f"/api/v1/dicom/studies/{seeded['ct']['studyUid']}/series/{seeded['ct']['seriesUid']}/metadata",
    )

    assert response.status_code == 200
    assert len(response.json()) == seeded["ct"]["imageCount"] > 1
    assert client.get(f"/viewer/dev/?study={seeded['ct']['studyUid']}").status_code == 200


@pytest.mark.django_db
def test_seed_is_idempotent(settings):
    settings.DEBUG = True

    first, second = _seed(), _seed()

    assert first["ct"] == second["ct"]


@pytest.mark.django_db
def test_seed_gives_an_annotating_and_a_view_only_session(settings, client):
    """#280 role gating: the PI's dev page enables annotate tools, the view-only user's doesn't."""
    settings.DEBUG = True
    seeded = _seed()
    page = f"/viewer/dev/?study={seeded['ct']['studyUid']}&series={seeded['ct']['seriesUid']}"

    def dev_page_as(cookie):
        client.cookies[cookie["name"]] = cookie["value"]
        return client.get(page).content.decode()

    assert "can-annotate" in dev_page_as(seeded["sessionCookie"])
    assert "can-annotate" not in dev_page_as(seeded["viewOnlySessionCookie"])


@pytest.mark.django_db
def test_seed_gives_2d_spacing_fixtures(settings, client):
    """#281: CR with only ImagerPixelSpacing, SC with PixelSpacing, SC without spacing, served by our WADO."""
    settings.DEBUG = True
    seeded = _seed()
    client.cookies[seeded["sessionCookie"]["name"]] = seeded["sessionCookie"]["value"]

    def metadata(key):
        ref = seeded[key]
        response = client.get(f"/api/v1/dicom/studies/{ref['studyUid']}/series/{ref['seriesUid']}/metadata")
        assert response.status_code == 200
        return response.json()[0]

    cr, sc, no_spacing = metadata("cr"), metadata("sc"), metadata("noSpacing")
    assert "00181164" in cr and "00280030" not in cr  # ImagerPixelSpacing only
    assert cr["00080016"]["Value"] == ["1.2.840.10008.5.1.4.1.1.1"]
    assert sc["00080016"]["Value"] == ["1.2.840.10008.5.1.4.1.1.7"] and "00280030" in sc
    assert "00280301" not in sc  # BurnedInAnnotation missing on an SC → burned-in badge
    assert "00280030" not in no_spacing and "00181164" not in no_spacing


@pytest.mark.django_db
def test_seed_gives_a_tiled_wsi_whose_tiles_are_served_as_jpeg(settings, client):
    """#285: a TILED_FULL slide the WSI viewer can open; dmv asks /frames with its off-standard Accept."""
    settings.DEBUG = True
    seeded = _seed()
    client.cookies[seeded["sessionCookie"]["name"]] = seeded["sessionCookie"]["value"]
    series = f"/api/v1/dicom/studies/{seeded['wsi']['studyUid']}/series/{seeded['wsi']['seriesUid']}"

    instances = client.get(f"{series}/metadata").json()
    base = next(i for i in instances if i["00080008"]["Value"][0] == "ORIGINAL")
    sop = base["00080018"]["Value"][0]
    response = client.get(
        f"{series}/instances/{sop}/frames/{seeded['wsi']['baseTiles']}",
        headers={"Accept": 'multipart/related; type="application/octet-stream"; transfer-syntax=*'},
    )

    assert len(instances) == seeded["wsi"]["levels"] == 2
    assert base["00209311"]["Value"] == ["TILED_FULL"]
    assert base["00480102"]["Value"]  # ImageOrientationSlide
    assert response.status_code == 200
    assert b"image/jpeg" in response.content and b"\xff\xd8\xff" in response.content
