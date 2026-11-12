"""The ETL sandbox runner (#161): `SandboxBackend` interface + its docker-compose implementation.

Fast tests here exercise the image allowlist, limit-resolution/clamping, and
`ComposeSandboxBackend`'s container-creation and I/O logic against a fake Docker client -- no real
daemon needed. A real Compose backend against a real container is covered separately by
`test_etl_sandbox_compose_integration.py`, opt-in and `long_running`-marked per #98/#113/#114's
established convention.
"""
import io
import json
import tarfile
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from requests.exceptions import ReadTimeout

from MiqaResearch.etl_sandbox import (
    SandboxInputTooLarge,
    SandboxLimits,
    SandboxRunSpec,
    UnknownSandboxImage,
    resolve_limits,
    resolve_sandbox_image,
)
from MiqaResearch.etl_sandbox.compose_backend import ComposeSandboxBackend
from MiqaResearch.etl_shim import contract
from tests.sandbox_staging import stage_inputs

# --- image allowlist -------------------------------------------------------

def test_resolve_sandbox_image_returns_the_allowlisted_reference(settings):
    settings.SANDBOX_IMAGE_ALLOWLIST = {"python-etl-v1": "mires-etl-sandbox-python@sha256:deadbeef"}

    assert resolve_sandbox_image("python-etl-v1") == "mires-etl-sandbox-python@sha256:deadbeef"


def test_resolve_sandbox_image_rejects_an_unlisted_key(settings):
    settings.SANDBOX_IMAGE_ALLOWLIST = {"python-etl-v1": "mires-etl-sandbox-python@sha256:deadbeef"}

    with pytest.raises(UnknownSandboxImage):
        resolve_sandbox_image("some-arbitrary-image")


# --- limits ------------------------------------------------------------

@pytest.fixture(autouse=True)
def sandbox_defaults(settings):
    settings.SANDBOX_DEFAULT_TIMEOUT_SECONDS = 600
    settings.SANDBOX_DEFAULT_MEMORY_MB = 1024
    settings.SANDBOX_DEFAULT_CPU_MILLICORES = 1000
    settings.SANDBOX_DEFAULT_PIDS_LIMIT = 128
    settings.SANDBOX_MAX_INPUT_BYTES = 15 * 1024 ** 3
    settings.SANDBOX_MAX_OUTPUT_BYTES = 1 * 1024 ** 3


def test_resolve_limits_with_no_binding_returns_platform_defaults():
    limits = resolve_limits(binding=None)

    assert limits == SandboxLimits(
        timeout_seconds=600, memory_mb=1024, cpu_millicores=1000, pids_limit=128,
        max_input_bytes=15 * 1024 ** 3, max_output_bytes=1 * 1024 ** 3)


def test_a_binding_override_below_the_default_is_used():
    binding = SimpleNamespace(timeout_seconds_override=120, memory_mb_override=256, cpu_millicores_override=500)

    limits = resolve_limits(binding=binding)

    assert limits.timeout_seconds == 120
    assert limits.memory_mb == 256
    assert limits.cpu_millicores == 500


def test_a_binding_override_above_the_default_is_clamped_to_the_default():
    binding = SimpleNamespace(
        timeout_seconds_override=99_999, memory_mb_override=99_999, cpu_millicores_override=99_999)

    limits = resolve_limits(binding=binding)

    assert limits.timeout_seconds == 600
    assert limits.memory_mb == 1024
    assert limits.cpu_millicores == 1000


def test_a_binding_with_no_overrides_set_defers_to_the_defaults():
    binding = SimpleNamespace(timeout_seconds_override=None, memory_mb_override=None, cpu_millicores_override=None)

    assert resolve_limits(binding=binding) == resolve_limits(binding=None)


# --- ComposeSandboxBackend --------------------------------------------------

def _limits(**overrides):
    defaults = dict(
        timeout_seconds=600, memory_mb=1024, cpu_millicores=1000, pids_limit=128,
        max_input_bytes=15 * 1024 ** 3, max_output_bytes=1 * 1024 ** 3)
    defaults.update(overrides)
    return SandboxLimits(**defaults)


def _output_archive(*, result_jsonl: bytes | None, log: bytes) -> list[bytes]:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        if result_jsonl is not None:
            info = tarfile.TarInfo(name=f"output/{contract.RESULT_FILENAME}")
            info.size = len(result_jsonl)
            tar.addfile(info, io.BytesIO(result_jsonl))
        info = tarfile.TarInfo(name=f"output/{contract.LOG_FILENAME}")
        info.size = len(log)
        tar.addfile(info, io.BytesIO(log))
    return [buf.getvalue()]


def _fake_container(*, status_code=0, oom_killed=False, output_archive=None):
    container = MagicMock()
    container.wait.return_value = {"StatusCode": status_code}
    container.attrs = {"State": {"OOMKilled": oom_killed}}
    if output_archive is None:
        output_archive = _output_archive(result_jsonl=b'{"datatype": "measurement"}\n', log=b"ok\n")
    container.get_archive.return_value = (output_archive, {})
    return container


@pytest.fixture
def allowlisted(settings):
    settings.SANDBOX_IMAGE_ALLOWLIST = {"python-etl-v1": "mires-etl-sandbox-python@sha256:deadbeef"}


def test_run_rejects_an_unknown_image_key_before_touching_docker(settings):
    settings.SANDBOX_IMAGE_ALLOWLIST = {}
    client = MagicMock()
    backend = ComposeSandboxBackend(client=client)
    spec = SandboxRunSpec(
        run_id="r1", image_key="nope", manifest={"datatype": "measurement"}, script_source=b"", limits=_limits())

    with pytest.raises(UnknownSandboxImage):
        backend.run(spec)

    client.containers.create.assert_not_called()


def test_run_rejects_oversized_input_before_touching_docker(allowlisted):
    client = MagicMock()
    backend = ComposeSandboxBackend(client=client)
    spec = SandboxRunSpec(
        run_id="r1", image_key="python-etl-v1", manifest={"datatype": "measurement"},
        script_source=b"x" * 100, limits=_limits(max_input_bytes=10))

    with pytest.raises(SandboxInputTooLarge):
        backend.run(spec)

    client.containers.create.assert_not_called()


def test_run_creates_a_network_less_non_root_resource_limited_container(allowlisted):
    client = MagicMock()
    client.containers.create.return_value = _fake_container()
    backend = ComposeSandboxBackend(client=client)
    spec = SandboxRunSpec(
        run_id="r1", image_key="python-etl-v1", manifest={"datatype": "measurement"},
        script_source=b"def main(ctx): return iter(())", limits=_limits())

    backend.run(spec)

    _, kwargs = client.containers.create.call_args
    assert kwargs["image"] == "mires-etl-sandbox-python@sha256:deadbeef"
    assert kwargs["network_mode"] == "none"
    assert kwargs["user"] == "65534:65534"
    assert kwargs["mem_limit"] == "1024m"
    assert kwargs["nano_cpus"] == 1_000_000_000
    assert kwargs["pids_limit"] == 128
    assert kwargs["cap_drop"] == ["ALL"]
    assert kwargs["labels"] == {"mires.etl.sandbox": "1", "mires.etl.run_id": "r1"}


def test_run_stages_manifest_script_and_input_files_via_put_archive(allowlisted, tmp_path):
    client = MagicMock()
    container = _fake_container()
    client.containers.create.return_value = container
    backend = ComposeSandboxBackend(client=client)
    spec = SandboxRunSpec(
        run_id="r1", image_key="python-etl-v1", manifest={"datatype": "measurement", "config": {"a": 1}},
        script_source=b"SCRIPT_SOURCE", input_files=stage_inputs(tmp_path, {"source.csv": b"a,b\n1,2\n"}), limits=_limits())

    captured = []
    container.put_archive.side_effect = lambda path, data: captured.append((path, data.read()))

    backend.run(spec)

    (path, archive_bytes), = captured
    assert path == "/sandbox"
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r") as tar:
        names = tar.getnames()
        assert set(names) == {"manifest.json", "script.py", "input/source.csv"}
        assert json.loads(tar.extractfile("manifest.json").read()) == {"datatype": "measurement", "config": {"a": 1}}
        assert tar.extractfile("script.py").read() == b"SCRIPT_SOURCE"
        assert tar.extractfile("input/source.csv").read() == b"a,b\n1,2\n"


def test_run_stages_an_r_scripts_source_as_script_r(settings):
    settings.SANDBOX_IMAGE_ALLOWLIST = {"r-etl-v1": "mires-etl-sandbox-r@sha256:deadbeef"}
    client = MagicMock()
    container = _fake_container()
    client.containers.create.return_value = container
    backend = ComposeSandboxBackend(client=client)
    spec = SandboxRunSpec(
        run_id="r1", image_key="r-etl-v1", manifest={"datatype": "measurement"},
        script_source=b"main <- function(ctx) NULL", limits=_limits())

    captured = []
    container.put_archive.side_effect = lambda path, data: captured.append(data.read())

    backend.run(spec)

    (archive_bytes,) = captured
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r") as tar:
        assert set(tar.getnames()) == {"manifest.json", "script.R"}
        assert tar.extractfile("script.R").read() == b"main <- function(ctx) NULL"


def test_run_returns_the_result_jsonl_and_log_on_success(allowlisted):
    client = MagicMock()
    client.containers.create.return_value = _fake_container(
        status_code=0,
        output_archive=_output_archive(result_jsonl=b'{"datatype": "measurement"}\nrow\n', log=b"hello\n"))
    backend = ComposeSandboxBackend(client=client)
    spec = SandboxRunSpec(
        run_id="r1", image_key="python-etl-v1", manifest={"datatype": "measurement"}, script_source=b"",
        limits=_limits())

    result = backend.run(spec)

    assert result.exit_code == contract.EXIT_SUCCESS
    assert result.result_jsonl == b'{"datatype": "measurement"}\nrow\n'
    assert result.log == b"hello\n"
    assert result.killed is False


def test_run_always_removes_the_container_afterwards(allowlisted):
    client = MagicMock()
    container = _fake_container()
    client.containers.create.return_value = container
    backend = ComposeSandboxBackend(client=client)
    spec = SandboxRunSpec(
        run_id="r1", image_key="python-etl-v1", manifest={"datatype": "measurement"}, script_source=b"",
        limits=_limits())

    backend.run(spec)

    container.remove.assert_called_once_with(force=True)


def test_run_reports_exit_code_3_and_kills_the_container_on_timeout(allowlisted):
    client = MagicMock()
    container = _fake_container()
    container.wait.side_effect = ReadTimeout()
    client.containers.create.return_value = container
    backend = ComposeSandboxBackend(client=client)
    spec = SandboxRunSpec(
        run_id="r1", image_key="python-etl-v1", manifest={"datatype": "measurement"}, script_source=b"",
        limits=_limits(timeout_seconds=1))

    result = backend.run(spec)

    assert result.exit_code == contract.EXIT_TIMEOUT_OR_KILLED
    assert result.killed is True
    container.kill.assert_called_once()


def test_run_reports_exit_code_3_when_the_container_was_oom_killed(allowlisted):
    client = MagicMock()
    client.containers.create.return_value = _fake_container(status_code=137, oom_killed=True)
    backend = ComposeSandboxBackend(client=client)
    spec = SandboxRunSpec(
        run_id="r1", image_key="python-etl-v1", manifest={"datatype": "measurement"}, script_source=b"",
        limits=_limits(memory_mb=1))

    result = backend.run(spec)

    assert result.exit_code == contract.EXIT_TIMEOUT_OR_KILLED
    assert result.killed is True


def test_run_returns_no_result_jsonl_when_output_exceeds_the_max_output_bytes(allowlisted):
    client = MagicMock()
    big_log = b"x" * 1000
    client.containers.create.return_value = _fake_container(
        output_archive=_output_archive(result_jsonl=b'{"datatype": "measurement"}\n', log=big_log))
    backend = ComposeSandboxBackend(client=client)
    spec = SandboxRunSpec(
        run_id="r1", image_key="python-etl-v1", manifest={"datatype": "measurement"}, script_source=b"",
        limits=_limits(max_output_bytes=10))

    result = backend.run(spec)

    assert result.result_jsonl is None


def test_cancel_removes_the_running_container_for_that_run_id(allowlisted):
    client = MagicMock()
    container = MagicMock()
    client.containers.get.return_value = container
    backend = ComposeSandboxBackend(client=client)

    backend.cancel("r1")

    client.containers.get.assert_called_once_with("mires-etl-r1")
    container.remove.assert_called_once_with(force=True)


def test_cancel_is_a_no_op_when_no_container_exists_for_that_run_id(allowlisted):
    from docker.errors import NotFound
    client = MagicMock()
    client.containers.get.side_effect = NotFound("no such container")
    backend = ComposeSandboxBackend(client=client)

    backend.cancel("r1")  # must not raise


def _labelled_container(run_id=None):
    container = MagicMock()
    container.labels = {"mires.etl.sandbox": "1"} | ({"mires.etl.run_id": run_id} if run_id else {})
    return container


def test_sweep_removes_orphaned_sandbox_containers_but_keeps_live_runs(allowlisted):
    client = MagicMock()
    orphan, live = _labelled_container("orphan-run"), _labelled_container("live-run")
    client.containers.list.return_value = [orphan, live]
    backend = ComposeSandboxBackend(client=client)

    backend.sweep(live_run_ids=lambda: {"live-run"})

    client.containers.list.assert_called_once_with(all=True, filters={"label": "mires.etl.sandbox=1"})
    orphan.remove.assert_called_once_with(force=True)
    live.remove.assert_not_called()


def test_sweep_asks_which_runs_are_live_only_after_listing_so_a_run_starting_meanwhile_is_kept(allowlisted):
    client = MagicMock()
    client.containers.list.return_value = [_labelled_container("started-meanwhile")]
    backend = ComposeSandboxBackend(client=client)

    def live_run_ids():
        assert client.containers.list.called, "live runs must be read after listing"
        return {"started-meanwhile"}

    backend.sweep(live_run_ids=live_run_ids)

    client.containers.list.return_value[0].remove.assert_not_called()
