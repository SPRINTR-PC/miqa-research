"""OTLP log export (#293): `MIRES_OTLP_*` turned into a logging handler.

Seam: `otlp_handler(...)` is a stdlib logging handler; a record logged through it arrives
at an OTLP/HTTP collector (a local HTTP server here) with the service name and attributes.
"""
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest

from MiqaResearch.telemetry import otlp_handler, otlp_logging_config


@pytest.fixture
def collector():
    received: list[tuple[str, ExportLogsServiceRequest]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            request = ExportLogsServiceRequest()
            request.ParseFromString(body)
            received.append((self.path, request))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/v1/logs", received
    server.shutdown()


def test_a_logged_record_reaches_the_collector_with_service_name_and_attributes(collector):
    endpoint, received = collector
    handler = otlp_handler(endpoint=endpoint, service_name="miqa-research-test")
    logger = logging.getLogger("tests.otlp")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logger.info("viewer first render", extra={"viewer.first_image_ms": 412.5, "viewer.slices": 500})
        handler.flush()  # exports on a background thread
        deadline = time.monotonic() + 5
        while not received and time.monotonic() < deadline:
            time.sleep(0.02)
    finally:
        logger.removeHandler(handler)
        handler.close()

    [(path, request)] = received
    assert path == "/v1/logs"
    [resource_logs] = request.resource_logs
    resource = {a.key: a.value.string_value for a in resource_logs.resource.attributes}
    assert resource["service.name"] == "miqa-research-test"
    [record] = resource_logs.scope_logs[0].log_records
    assert record.body.string_value == "viewer first render"
    attributes = {a.key: a.value for a in record.attributes}
    assert attributes["viewer.first_image_ms"].double_value == 412.5
    assert attributes["viewer.slices"].int_value == 500


def test_logging_config_adds_the_otlp_handler_only_when_enabled():
    disabled = otlp_logging_config(enabled=False, endpoint="http://c:4318/v1/logs", service_name="s")
    enabled = otlp_logging_config(enabled=True, endpoint="http://c:4318/v1/logs", service_name="s")

    assert disabled == {}
    assert enabled == {
        "otlp": {
            "()": "MiqaResearch.telemetry.otlp_handler",
            "endpoint": "http://c:4318/v1/logs",
            "service_name": "s",
        }
    }
