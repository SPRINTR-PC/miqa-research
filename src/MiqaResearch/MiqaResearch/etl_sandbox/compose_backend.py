"""The docker-compose `SandboxBackend` (#161): runs a Script's pinned image via a plain Docker
API connection -- in production, a per-worker-host docker-socket-proxy (`MIRES_SANDBOX_DOCKER_HOST`
pointed at its TCP endpoint), never a raw mounted socket; in local dev/test, the same client can
point straight at the dev daemon's socket. I/O is staged and retrieved entirely through Docker's
archive API (`put_archive`/`get_archive`) rather than a bind mount, since a worker and the Docker
daemon it talks to are not assumed to share a filesystem.

A run is: resolve+validate the image key (before anything else -- an unknown key must never reach
`containers.create`), check the staged input against `limits.max_input_bytes`, create the
container stopped (network-less, non-root, resource-limited), stage `/sandbox` via `put_archive`,
start it, wait up to `limits.timeout_seconds`, retrieve `/sandbox/output` via `get_archive`, then
always remove the container -- a crashed worker's own leftovers are `sweep()`'s job, not this
method's.
"""
import io
import json
import tarfile

import docker
from docker.errors import NotFound
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import ReadTimeout

from MiqaResearch.etl_shim import contract

from .backend import SandboxBackend
from .exceptions import SandboxInputTooLarge
from .images import resolve_sandbox_image
from .spec import SandboxRunResult, SandboxRunSpec

SANDBOX_ROOT = "/sandbox"
CONTAINER_NAME_PREFIX = "mires-etl-"
SANDBOX_LABEL = "mires.etl.sandbox"
RUN_ID_LABEL = "mires.etl.run_id"

# Debian's stock nobody:nogroup -- matches the UID/GID `etl_sandbox.Dockerfile` chowns /sandbox to.
NON_ROOT_USER = "65534:65534"


class ComposeSandboxBackend(SandboxBackend):
    def __init__(self, *, client: docker.DockerClient | None = None):
        self._client = client

    def run(self, spec: SandboxRunSpec) -> SandboxRunResult:
        image = resolve_sandbox_image(spec.image_key)
        _check_input_size(spec)

        client = self._get_client()
        container = client.containers.create(
            image=image,
            name=_container_name(spec.run_id),
            labels={SANDBOX_LABEL: "1", RUN_ID_LABEL: spec.run_id},
            user=NON_ROOT_USER,
            network_mode="none",
            mem_limit=f"{spec.limits.memory_mb}m",
            nano_cpus=spec.limits.cpu_millicores * 1_000_000,
            pids_limit=spec.limits.pids_limit,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges"],
            detach=True,
        )
        try:
            container.put_archive(SANDBOX_ROOT, _build_input_archive(spec))
            container.start()
            killed = False
            try:
                wait_result = container.wait(timeout=spec.limits.timeout_seconds)
                exit_code = wait_result["StatusCode"]
                container.reload()
                if container.attrs.get("State", {}).get("OOMKilled"):
                    exit_code, killed = contract.EXIT_TIMEOUT_OR_KILLED, True
            except (ReadTimeout, RequestsConnectionError):
                # docker-py's client-side wait() timeout surfaces as a plain ReadTimeout on some
                # transports and as a ConnectionError wrapping a urllib3 ReadTimeoutError on
                # others (observed against a Unix-socket connection) -- both mean the same thing:
                # the container outran `limits.timeout_seconds` and must be killed here, since a
                # killed process can never produce its own exit code (contract.py).
                container.kill()
                exit_code, killed = contract.EXIT_TIMEOUT_OR_KILLED, True

            result_jsonl, log = _retrieve_output(container, max_bytes=spec.limits.max_output_bytes)
            return SandboxRunResult(exit_code=exit_code, result_jsonl=result_jsonl, log=log, killed=killed)
        finally:
            container.remove(force=True)

    def cancel(self, run_id: str) -> None:
        client = self._get_client()
        try:
            container = client.containers.get(_container_name(run_id))
        except NotFound:
            return
        container.remove(force=True)

    def sweep(self) -> None:
        client = self._get_client()
        for container in client.containers.list(all=True, filters={"label": f"{SANDBOX_LABEL}=1"}):
            container.remove(force=True)

    def _get_client(self) -> docker.DockerClient:
        if self._client is None:
            from django.conf import settings
            self._client = docker.DockerClient(base_url=settings.SANDBOX_DOCKER_HOST)
        return self._client


def _container_name(run_id: str) -> str:
    return f"{CONTAINER_NAME_PREFIX}{run_id}"


def _check_input_size(spec: SandboxRunSpec) -> None:
    total = len(spec.script_source) + sum(len(content) for content in spec.input_files.values())
    if total > spec.limits.max_input_bytes:
        raise SandboxInputTooLarge(
            f"Run {spec.run_id}'s staged input is {total} bytes, over the {spec.limits.max_input_bytes} byte cap.")


def _build_input_archive(spec: SandboxRunSpec) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        _add_bytes(tar, contract.MANIFEST_FILENAME, json.dumps(spec.manifest).encode())
        _add_bytes(tar, contract.SCRIPT_FILENAME, spec.script_source)
        for relative_path, content in spec.input_files.items():
            _add_bytes(tar, f"{contract.INPUT_DIRNAME}/{relative_path}", content)
    return buf.getvalue()


def _add_bytes(tar: tarfile.TarFile, name: str, content: bytes) -> None:
    info = tarfile.TarInfo(name=name)
    info.size = len(content)
    tar.addfile(info, io.BytesIO(content))


def _retrieve_output(container, *, max_bytes: int) -> tuple[bytes | None, bytes]:
    try:
        stream, _ = container.get_archive(f"{SANDBOX_ROOT}/{contract.OUTPUT_DIRNAME}")
    except NotFound:
        return None, b""

    buf = io.BytesIO()
    size = 0
    for chunk in stream:
        size += len(chunk)
        if size > max_bytes:
            return None, b""
        buf.write(chunk)
    buf.seek(0)

    result_jsonl, log = None, b""
    with tarfile.open(fileobj=buf, mode="r") as tar:
        result_jsonl = _read_member(tar, f"{contract.OUTPUT_DIRNAME}/{contract.RESULT_FILENAME}")
        log = _read_member(tar, f"{contract.OUTPUT_DIRNAME}/{contract.LOG_FILENAME}") or b""
    return result_jsonl, log


def _read_member(tar: tarfile.TarFile, name: str) -> bytes | None:
    try:
        member = tar.getmember(name)
    except KeyError:
        return None
    extracted = tar.extractfile(member)
    return extracted.read() if extracted else None
