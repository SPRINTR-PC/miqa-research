"""Fast tests for `KubernetesSandboxBackend` (#165): exercised against fake `CoreV1Api`/`BatchV1Api`/
`NetworkingV1Api` clients and a fake exec-stream function -- no real cluster needed. A real cluster is
covered separately by `test_etl_sandbox_kubernetes_integration.py`, opt-in and `long_running`-marked per
#98/#113/#114's established convention (matching `test_etl_sandbox_compose_integration.py`).
"""
import io
import json
import tarfile
from unittest.mock import MagicMock

import pytest
from kubernetes.client.exceptions import ApiException

from MiqaResearch.etl_sandbox import (
    SandboxBackendUnhealthy,
    SandboxInputTooLarge,
    SandboxRunSpec,
    UnknownSandboxImage,
)
from MiqaResearch.etl_sandbox.kubernetes_backend import KubernetesSandboxBackend
from MiqaResearch.etl_sandbox.limits import SandboxLimits
from mires_etl import contract
from tests.sandbox_staging import stage_inputs


def _limits(**overrides):
    defaults = dict(
        timeout_seconds=600, memory_mb=1024, cpu_millicores=1000, pids_limit=128,
        max_input_bytes=15 * 1024 ** 3, max_output_bytes=1 * 1024 ** 3)
    defaults.update(overrides)
    return SandboxLimits(**defaults)


@pytest.fixture
def allowlisted(settings):
    settings.SANDBOX_IMAGE_ALLOWLIST = {"python-etl-v1": "mires-etl-sandbox-python@sha256:deadbeef"}
    settings.SANDBOX_K8S_NAMESPACE = "mires-etl-sandbox"


def _backend(*, healthy=True):
    core_v1, batch_v1, networking_v1 = MagicMock(), MagicMock(), MagicMock()
    stream_fn = MagicMock()
    backend = KubernetesSandboxBackend(
        core_v1=core_v1, batch_v1=batch_v1, networking_v1=networking_v1, stream_fn=stream_fn)
    if healthy:
        backend._healthy_until = float("inf")  # skip the self-test probe in tests that don't cover it
    return backend, core_v1, batch_v1, networking_v1, stream_fn


def test_run_rejects_an_unknown_image_key_before_touching_kubernetes(settings):
    settings.SANDBOX_IMAGE_ALLOWLIST = {}
    settings.SANDBOX_K8S_NAMESPACE = "mires-etl-sandbox"
    backend, core_v1, batch_v1, networking_v1, _ = _backend()
    spec = SandboxRunSpec(
        run_id="r1", image_key="nope", manifest={"datatype": "measurement"}, script_source=b"", limits=_limits())

    with pytest.raises(UnknownSandboxImage):
        backend.run(spec)

    core_v1.create_namespaced_persistent_volume_claim.assert_not_called()
    batch_v1.create_namespaced_job.assert_not_called()


def test_run_rejects_oversized_input_before_touching_kubernetes(allowlisted):
    backend, core_v1, batch_v1, networking_v1, _ = _backend()
    spec = SandboxRunSpec(
        run_id="r1", image_key="python-etl-v1", manifest={"datatype": "measurement"},
        script_source=b"x" * 100, limits=_limits(max_input_bytes=10))

    with pytest.raises(SandboxInputTooLarge):
        backend.run(spec)

    core_v1.create_namespaced_persistent_volume_claim.assert_not_called()
    batch_v1.create_namespaced_job.assert_not_called()


# --- _ensure_healthy --------------------------------------------------------

def _pod(phase, *, exit_code=0, reason=None, pod_reason=None):
    terminated = MagicMock(exit_code=exit_code, reason=reason)
    container_status = MagicMock()
    container_status.state.terminated = terminated
    pod = MagicMock()
    pod.status.phase = phase
    pod.status.reason = pod_reason
    pod.status.container_statuses = [container_status]
    return pod


def test_ensure_healthy_passes_when_the_egress_probe_pod_fails_to_connect(allowlisted):
    backend, core_v1, batch_v1, networking_v1, _ = _backend(healthy=False)
    core_v1.read_namespaced_pod.return_value = _pod("Failed", exit_code=1)

    backend._ensure_healthy()  # must not raise

    core_v1.create_namespace.assert_called_once()
    networking_v1.create_namespaced_network_policy.assert_called_once()
    core_v1.create_namespaced_pod.assert_called_once()
    core_v1.delete_namespaced_pod.assert_called_once()


def test_ensure_healthy_raises_when_the_egress_probe_pod_actually_reaches_out(allowlisted):
    backend, core_v1, batch_v1, networking_v1, _ = _backend(healthy=False)
    core_v1.read_namespaced_pod.return_value = _pod("Succeeded", exit_code=0)

    with pytest.raises(SandboxBackendUnhealthy):
        backend._ensure_healthy()

    # still cleaned up even though it failed the health check
    core_v1.delete_namespaced_pod.assert_called_once()


def test_ensure_healthy_tolerates_the_namespace_and_network_policy_already_existing(allowlisted):
    backend, core_v1, batch_v1, networking_v1, _ = _backend(healthy=False)
    core_v1.create_namespace.side_effect = ApiException(status=409)
    networking_v1.create_namespaced_network_policy.side_effect = ApiException(status=409)
    core_v1.read_namespaced_pod.return_value = _pod("Failed", exit_code=1)

    backend._ensure_healthy()  # must not raise


def test_ensure_healthy_is_cached_and_does_not_reprobe_within_the_ttl(allowlisted):
    backend, core_v1, batch_v1, networking_v1, _ = _backend(healthy=False)
    core_v1.read_namespaced_pod.return_value = _pod("Failed", exit_code=1)

    backend._ensure_healthy()
    backend._ensure_healthy()

    assert core_v1.create_namespaced_pod.call_count == 1


# --- run() --------------------------------------------------------------

class _FakeReadStream:
    def __init__(self, data: bytes):
        self._pending = [data]

    def is_open(self):
        return bool(self._pending)

    def update(self, timeout=None):
        pass

    def peek_stdout(self):
        return bool(self._pending)

    def read_stdout(self, binary=False):
        return self._pending.pop(0)

    def peek_stderr(self):
        return False

    def read_stderr(self):
        return b""

    def close(self):
        pass


def _make_stream_fn(output_tar_bytes: bytes = b""):
    write_ws = MagicMock()
    read_ws = _FakeReadStream(output_tar_bytes)

    def stream_fn(*args, **kwargs):
        return write_ws if kwargs.get("stdin") else read_ws

    stream_fn.write_ws = write_ws
    stream_fn.read_ws = read_ws
    return stream_fn


def _output_tar(*, result_jsonl: bytes | None, log: bytes) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        if result_jsonl is not None:
            info = tarfile.TarInfo(name=f"{contract.OUTPUT_DIRNAME}/{contract.RESULT_FILENAME}")
            info.size = len(result_jsonl)
            tar.addfile(info, io.BytesIO(result_jsonl))
        info = tarfile.TarInfo(name=f"{contract.OUTPUT_DIRNAME}/{contract.LOG_FILENAME}")
        info.size = len(log)
        tar.addfile(info, io.BytesIO(log))
    return buf.getvalue()


def _wire_successful_run(core_v1, batch_v1, *, exit_code=0):
    running_pod = MagicMock()
    running_pod.status.phase = "Running"
    core_v1.read_namespaced_pod.return_value = running_pod

    job = MagicMock()
    job.status.succeeded = 1
    job.status.failed = None
    job.status.conditions = []
    batch_v1.read_namespaced_job.return_value = job

    core_v1.list_namespaced_pod.return_value.items = [_pod("Succeeded", exit_code=exit_code)]


def test_run_creates_a_read_write_once_pvc_sized_to_the_input_and_output_ceiling(allowlisted):
    backend, core_v1, batch_v1, networking_v1, stream_fn = _backend()
    backend._stream_fn = _make_stream_fn(_output_tar(result_jsonl=b'{"datatype": "measurement"}\n', log=b""))
    _wire_successful_run(core_v1, batch_v1)
    spec = SandboxRunSpec(
        run_id="r1", image_key="python-etl-v1", manifest={"datatype": "measurement"}, script_source=b"",
        limits=_limits(max_input_bytes=2 * 1024 ** 3, max_output_bytes=1 * 1024 ** 3))

    backend.run(spec)

    (namespace, pvc), _ = core_v1.create_namespaced_persistent_volume_claim.call_args
    assert namespace == "mires-etl-sandbox"
    assert pvc.metadata.labels == {"mires.etl.sandbox": "1", "mires.etl.run_id": "r1"}
    assert pvc.spec.access_modes == ["ReadWriteOnce"]
    assert pvc.spec.resources.requests["storage"] == "3Gi"


def test_run_stages_the_manifest_script_and_input_files_via_exec_tar(allowlisted, tmp_path):
    backend, core_v1, batch_v1, networking_v1, _ = _backend()
    stream_fn = _make_stream_fn(_output_tar(result_jsonl=b'{"datatype": "measurement"}\n', log=b""))
    backend._stream_fn = stream_fn
    _wire_successful_run(core_v1, batch_v1)
    spec = SandboxRunSpec(
        run_id="r1", image_key="python-etl-v1", manifest={"datatype": "measurement", "config": {"a": 1}},
        script_source=b"SCRIPT_SOURCE", input_files=stage_inputs(tmp_path, {"source.csv": b"a,b\n1,2\n"}), limits=_limits())

    backend.run(spec)

    write_calls = stream_fn.write_ws.write_stdin.call_args_list
    written = b"".join(call.args[0] for call in write_calls)
    with tarfile.open(fileobj=io.BytesIO(written), mode="r") as tar:
        names = tar.getnames()
        assert set(names) == {"manifest.json", "script.py", "input/source.csv"}
        assert json.loads(tar.extractfile("manifest.json").read()) == {"datatype": "measurement", "config": {"a": 1}}
        assert tar.extractfile("script.py").read() == b"SCRIPT_SOURCE"


def test_run_creates_a_job_with_the_resolved_image_and_restricted_security_context(allowlisted):
    backend, core_v1, batch_v1, networking_v1, stream_fn = _backend()
    backend._stream_fn = _make_stream_fn(_output_tar(result_jsonl=b'{"datatype": "measurement"}\n', log=b""))
    _wire_successful_run(core_v1, batch_v1)
    spec = SandboxRunSpec(
        run_id="r1", image_key="python-etl-v1", manifest={"datatype": "measurement"}, script_source=b"",
        limits=_limits())

    backend.run(spec)

    (namespace, job), _ = batch_v1.create_namespaced_job.call_args
    assert namespace == "mires-etl-sandbox"
    container = job.spec.template.spec.containers[0]
    assert container.image == "mires-etl-sandbox-python@sha256:deadbeef"
    assert container.security_context.run_as_user == 65534
    assert container.security_context.run_as_group == 65534
    assert container.security_context.run_as_non_root is True
    assert container.security_context.allow_privilege_escalation is False
    assert container.security_context.capabilities.drop == ["ALL"]
    assert container.resources.requests == {"memory": "1024Mi", "cpu": "1000m"}
    assert job.spec.active_deadline_seconds == 600
    assert job.spec.backoff_limit == 0
    assert job.spec.template.spec.automount_service_account_token is False


def test_run_returns_the_result_jsonl_and_log_on_success(allowlisted):
    backend, core_v1, batch_v1, networking_v1, stream_fn = _backend()
    backend._stream_fn = _make_stream_fn(
        _output_tar(result_jsonl=b'{"datatype": "measurement"}\nrow\n', log=b"hello\n"))
    _wire_successful_run(core_v1, batch_v1, exit_code=0)
    spec = SandboxRunSpec(
        run_id="r1", image_key="python-etl-v1", manifest={"datatype": "measurement"}, script_source=b"",
        limits=_limits())

    result = backend.run(spec)

    assert result.exit_code == contract.EXIT_SUCCESS
    assert result.result_jsonl == b'{"datatype": "measurement"}\nrow\n'
    assert result.log == b"hello\n"
    assert result.killed is False


def test_run_reports_exit_code_3_when_the_job_hits_its_deadline(allowlisted):
    backend, core_v1, batch_v1, networking_v1, _ = _backend()
    backend._stream_fn = _make_stream_fn(_output_tar(result_jsonl=None, log=b""))
    running_pod = MagicMock()
    running_pod.status.phase = "Running"
    core_v1.read_namespaced_pod.return_value = running_pod
    job = MagicMock()
    job.status.succeeded = None
    job.status.failed = 1
    batch_v1.read_namespaced_job.return_value = job
    core_v1.list_namespaced_pod.return_value.items = [_pod("Failed", pod_reason="DeadlineExceeded")]
    spec = SandboxRunSpec(
        run_id="r1", image_key="python-etl-v1", manifest={"datatype": "measurement"}, script_source=b"",
        limits=_limits(timeout_seconds=1))

    result = backend.run(spec)

    assert result.exit_code == contract.EXIT_TIMEOUT_OR_KILLED
    assert result.killed is True


def test_run_reports_exit_code_3_when_the_job_pod_was_oom_killed(allowlisted):
    backend, core_v1, batch_v1, networking_v1, _ = _backend()
    backend._stream_fn = _make_stream_fn(_output_tar(result_jsonl=None, log=b""))
    running_pod = MagicMock()
    running_pod.status.phase = "Running"
    core_v1.read_namespaced_pod.return_value = running_pod
    job = MagicMock()
    job.status.succeeded = None
    job.status.failed = 1
    job.status.conditions = []
    batch_v1.read_namespaced_job.return_value = job
    core_v1.list_namespaced_pod.return_value.items = [_pod("Failed", exit_code=137, reason="OOMKilled")]
    spec = SandboxRunSpec(
        run_id="r1", image_key="python-etl-v1", manifest={"datatype": "measurement"}, script_source=b"",
        limits=_limits(memory_mb=1))

    result = backend.run(spec)

    assert result.exit_code == contract.EXIT_TIMEOUT_OR_KILLED
    assert result.killed is True


def test_run_always_deletes_the_pvc_afterwards(allowlisted):
    backend, core_v1, batch_v1, networking_v1, stream_fn = _backend()
    backend._stream_fn = _make_stream_fn(_output_tar(result_jsonl=b'{"datatype": "measurement"}\n', log=b""))
    _wire_successful_run(core_v1, batch_v1)
    spec = SandboxRunSpec(
        run_id="r1", image_key="python-etl-v1", manifest={"datatype": "measurement"}, script_source=b"",
        limits=_limits())

    backend.run(spec)

    core_v1.delete_namespaced_persistent_volume_claim.assert_called_once_with("mires-etl-r1", "mires-etl-sandbox")


# --- cancel() / sweep() ------------------------------------------------

def test_cancel_deletes_the_job_transfer_pods_and_pvc_for_that_run_id(allowlisted):
    backend, core_v1, batch_v1, networking_v1, _ = _backend()

    backend.cancel("r1")

    batch_v1.delete_namespaced_job.assert_called_once_with(
        "mires-etl-r1", "mires-etl-sandbox", propagation_policy="Foreground")
    core_v1.delete_namespaced_persistent_volume_claim.assert_called_once_with("mires-etl-r1", "mires-etl-sandbox")
    assert core_v1.delete_namespaced_pod.call_count == 2


def test_cancel_is_a_no_op_when_nothing_exists_for_that_run_id(allowlisted):
    backend, core_v1, batch_v1, networking_v1, _ = _backend()
    batch_v1.delete_namespaced_job.side_effect = ApiException(status=404)
    core_v1.delete_namespaced_pod.side_effect = ApiException(status=404)
    core_v1.delete_namespaced_persistent_volume_claim.side_effect = ApiException(status=404)

    backend.cancel("r1")  # must not raise


def _labelled(name, run_id=None):
    resource = MagicMock()
    resource.metadata.name = name
    resource.metadata.labels = {"mires.etl.sandbox": "1"} | ({"mires.etl.run_id": run_id} if run_id else {})
    return resource


def test_sweep_removes_orphaned_jobs_pods_and_pvcs_but_keeps_live_runs_and_the_probe_pod(allowlisted):
    backend, core_v1, batch_v1, networking_v1, _ = _backend()
    batch_v1.list_namespaced_job.return_value.items = [
        _labelled("mires-etl-orphan", "orphan"), _labelled("mires-etl-live", "live")]
    core_v1.list_namespaced_pod.return_value.items = [
        _labelled("mires-etl-orphan-drain", "orphan"), _labelled("mires-etl-live-stage", "live"),
        _labelled("mires-etl-egress-probe")]
    core_v1.list_namespaced_persistent_volume_claim.return_value.items = [
        _labelled("mires-etl-orphan", "orphan"), _labelled("mires-etl-live", "live")]

    backend.sweep(live_run_ids=lambda: {"live"})

    batch_v1.list_namespaced_job.assert_called_once_with("mires-etl-sandbox", label_selector="mires.etl.sandbox=1")
    batch_v1.delete_namespaced_job.assert_called_once_with(
        "mires-etl-orphan", "mires-etl-sandbox", propagation_policy="Foreground")
    core_v1.delete_namespaced_pod.assert_called_once_with("mires-etl-orphan-drain", "mires-etl-sandbox")
    core_v1.delete_namespaced_persistent_volume_claim.assert_called_once_with("mires-etl-orphan", "mires-etl-sandbox")
