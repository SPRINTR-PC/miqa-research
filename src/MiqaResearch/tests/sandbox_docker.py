"""Shared plumbing for the real-container ETL sandbox tests (Docker, Docker Desktop or Podman).

`resolve_docker_host` finds the daemon socket without per-machine edits; `docker_client_for` returns
a connected client with the needed sandbox images present, building any missing one with the
`docker` CLI (the same Dockerfiles as docker-compose.dev-test.yml). Anything that can't be
satisfied is a skip, never an error. Set MIRES_TEST_BUILD_SANDBOX_IMAGES=0 to skip instead of build.
"""
import os
import subprocess
from pathlib import Path

import docker
import pytest
from docker.errors import ImageNotFound

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_HOST = "unix:///var/run/docker.sock"

PYTHON_IMAGE = "mires-etl-sandbox-python:dev"
R_IMAGE = "mires-etl-sandbox-r:dev"
# image -> (Dockerfile, image it is built FROM, if one of ours)
_DOCKERFILES = {
    PYTHON_IMAGE: ("etl_sandbox.Dockerfile", None),
    R_IMAGE: ("etl_sandbox_r.Dockerfile", PYTHON_IMAGE),
}


def resolve_docker_host() -> str:
    """MIRES_SANDBOX_DOCKER_HOST, else DOCKER_HOST, else the active Docker context's endpoint
    (Docker Desktop keeps its socket under ~/.docker), else the conventional /var/run/docker.sock."""
    for variable in ("MIRES_SANDBOX_DOCKER_HOST", "DOCKER_HOST"):
        if os.environ.get(variable):
            return os.environ[variable]
    try:
        result = subprocess.run(
            ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
            capture_output=True, text=True, timeout=10, check=True)
        if result.stdout.strip().startswith(("unix://", "tcp://")):
            return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return DEFAULT_HOST


def docker_client_for(*images: str, settings) -> docker.DockerClient:
    """A client for the resolved daemon, with `images` present (built if missing); points the
    sandbox backend (`settings.SANDBOX_DOCKER_HOST`) at the same daemon."""
    host = resolve_docker_host()
    try:
        client = docker.DockerClient(base_url=host)
        client.ping()
    except Exception as exc:
        pytest.skip(f"no Docker/Podman daemon reachable at {host}: {exc}")
    for image in images:
        _ensure_image(client, image, host)
    settings.SANDBOX_DOCKER_HOST = host
    return client


def _ensure_image(client, image: str, host: str) -> None:
    try:
        client.images.get(image)
        return
    except ImageNotFound:
        pass
    if os.environ.get("MIRES_TEST_BUILD_SANDBOX_IMAGES", "1") == "0":
        pytest.skip(f"{image} not built locally and MIRES_TEST_BUILD_SANDBOX_IMAGES=0")
    dockerfile, base = _DOCKERFILES[image]
    if base is not None:
        _ensure_image(client, base, host)
    result = subprocess.run(
        ["docker", "build", "-f", dockerfile, "-t", image, "."],
        cwd=PROJECT_ROOT, env={**os.environ, "DOCKER_HOST": host}, capture_output=True, text=True)
    if result.returncode != 0:
        pytest.skip(f"could not build {image}: {result.stderr[-1500:]}")
