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
