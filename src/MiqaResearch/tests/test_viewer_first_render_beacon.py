"""First-render beacon (#293): the viewer's performance marks reach the telemetry log.

Seam: POST /api/v1/viewer/first-render (session auth) → one record on the
`MiqaResearch.telemetry.viewer` logger, which the OTLP handler exports when enabled.
Only timings, series size and transfer syntax pass; anything else is refused.
"""
import logging

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

URL = "/api/v1/viewer/first-render"
LOGGER = "MiqaResearch.telemetry.viewer"

PAYLOAD = {
    "first_image_ms": 412.5,
    "interleaved_ms": 1530.0,
    "volume_loaded_ms": 6120.25,
    "slices": 500,
    "bytes": 262_144_000,
    "transfer_syntax": "1.2.840.10008.1.2.4.70",
}


@pytest.fixture(autouse=True)
def no_debug(settings):
    settings.DEBUG = False
    settings.MIDDLEWARE = [m for m in settings.MIDDLEWARE if "debug_toolbar" not in m]


@pytest.fixture
def viewer(db, client):
    client.force_login(get_user_model().objects.create_user(username="viewer", password="x"))
    return client


def _post(client, body):
    return client.post(URL, body, content_type="application/json")


def _beacon_records(caplog):
    return [r for r in caplog.records if r.name == LOGGER]


def test_beacon_logs_the_marks_series_size_and_transfer_syntax(viewer, caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)

    response = _post(viewer, PAYLOAD)

    assert response.status_code == 204
    [record] = _beacon_records(caplog)
    assert record.message == "viewer first render"
    attributes = {k: v for k, v in record.__dict__.items() if k.startswith("viewer.")}
    assert attributes == {
        "viewer.first_image_ms": 412.5,
        "viewer.interleaved_ms": 1530.0,
        "viewer.volume_loaded_ms": 6120.25,
        "viewer.slices": 500,
        "viewer.bytes": 262_144_000,
        "viewer.transfer_syntax": "1.2.840.10008.1.2.4.70",
    }


def test_stages_not_reached_are_left_out_of_the_record(viewer, caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)

    response = _post(viewer, {"first_image_ms": 300, "slices": 16})

    assert response.status_code == 204
    [record] = _beacon_records(caplog)
    attributes = {k for k in record.__dict__ if k.startswith("viewer.")}
    assert attributes == {"viewer.first_image_ms", "viewer.slices"}


@pytest.mark.parametrize(
    "extra",
    [
        {"study_uid": "2.25.1234"},
        {"series_uid": "2.25.5678"},
        {"participant": "P-001"},
        {"url": "/api/v1/dicom/studies/2.25.1/series/2.25.2/metadata"},
    ],
)
def test_beacon_refuses_any_field_beyond_the_allowed_ones(viewer, caplog, extra):
    caplog.set_level(logging.INFO, logger=LOGGER)

    response = _post(viewer, PAYLOAD | extra)

    assert response.status_code == 422
    assert _beacon_records(caplog) == []


@pytest.mark.parametrize(
    "transfer_syntax",
    ["2.25.329800735698586629295641978511506172918", "1.2.840.10008.5.1.4.1.1.2", "P-001"],
)
def test_transfer_syntax_must_be_a_dicom_transfer_syntax_uid(viewer, caplog, transfer_syntax):
    """A UID-shaped value that isn't a transfer syntax (a study or SOP Class UID) can't slip through."""
    caplog.set_level(logging.INFO, logger=LOGGER)

    response = _post(viewer, PAYLOAD | {"transfer_syntax": transfer_syntax})

    assert response.status_code == 422
    assert _beacon_records(caplog) == []


@pytest.mark.parametrize("field,value", [("first_image_ms", -1), ("slices", -3), ("bytes", -10)])
def test_negative_values_are_refused(viewer, field, value):
    assert _post(viewer, PAYLOAD | {field: value}).status_code == 422


def test_anonymous_beacon_is_refused(db, client, caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)

    assert _post(client, PAYLOAD).status_code == 401
    assert _beacon_records(caplog) == []


def test_beacon_without_csrf_token_is_refused(db):
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(get_user_model().objects.create_user(username="v2", password="x"))

    assert _post(csrf_client, PAYLOAD).status_code == 403
