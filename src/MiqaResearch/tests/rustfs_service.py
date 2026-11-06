"""The dev-test RustFS service (`mires_fs`, container `miresfs`) for the real-S3 DICOM tests.

`ensure_rustfs_endpoint` returns an endpoint URL that answers, in this order: the
MIRES_TEST_DICOM_S3_ENDPOINT_URL override; `http://miresfs:9000` when that hostname resolves (inside
the compose network); otherwise `http://localhost:9000` (the published port). If nothing answers it
starts the service, but never `docker compose up` for a container that already exists: a running one is
just waited on, a stopped one is `docker start`ed. If it still isn't reachable the tests skip.
"""
import os
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

import boto3
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = "docker-compose.dev-test.yml"
SERVICE = "mires_fs"
CONTAINER = "miresfs"
ACCESS_KEY, SECRET_KEY = "MiresAccessKey", "MiresSecretKey"
STARTUP_TIMEOUT_SECONDS = 60


def ensure_rustfs_endpoint() -> str:
    endpoint = _candidate_endpoint()
    if _answers(endpoint):
        return endpoint
    if os.environ.get("MIRES_TEST_DICOM_S3_ENDPOINT_URL"):
        pytest.skip(f"RustFS not reachable at MIRES_TEST_DICOM_S3_ENDPOINT_URL={endpoint}")
    _start_service_if_absent()
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if _answers(endpoint):
            return endpoint
        time.sleep(2)
    pytest.skip(f"RustFS ({CONTAINER}) did not become reachable at {endpoint}")


def _candidate_endpoint() -> str:
    if override := os.environ.get("MIRES_TEST_DICOM_S3_ENDPOINT_URL"):
        return override
    try:
        socket.gethostbyname(CONTAINER)
        return f"http://{CONTAINER}:9000"
    except OSError:
        return "http://localhost:9000"


def _answers(endpoint: str) -> bool:
    host = urlparse(endpoint).hostname
    try:
        socket.create_connection((host, urlparse(endpoint).port or 80), timeout=2).close()
        boto3.client(
            "s3", endpoint_url=endpoint, region_name="us-east-1", aws_access_key_id=ACCESS_KEY,
            aws_secret_access_key=SECRET_KEY).list_buckets()
        return True
    except Exception:
        return False


def _container_state() -> str | None:
    """"running", another Docker state such as "exited", or None if no container of that name exists."""
    result = _docker("ps", "-a", "--filter", f"name=^{CONTAINER}$", "--format", "{{.State}}")
    return result.stdout.strip() or None if result is not None and result.returncode == 0 else None


def _start_service_if_absent() -> None:
    state = _container_state()
    if state == "running":
        return  # already up; just wait for it
    if state is not None:
        _docker("start", CONTAINER)  # exists but stopped: start it, don't recreate it
        return
    _docker("compose", "-f", COMPOSE_FILE, "up", "-d", SERVICE)


def _docker(*args):
    try:
        return subprocess.run(["docker", *args], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError):
        return None
