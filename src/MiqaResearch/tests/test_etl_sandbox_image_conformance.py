"""Image conformance (#413): the real slim Python sandbox image runs every Native Script, ships the
curated set, and reports its baked package manifest and digest. Opt-in and `long_running`, like the other
real-image tests: needs a container daemon and `mires-etl-sandbox-python:dev`."""
import pytest

from MiqaResearch.etl_native_scripts import NATIVE_SCRIPTS, native_script_path
from MiqaResearch.etl_sandbox import SandboxRunSpec, resolve_limits
from MiqaResearch.etl_sandbox.compose_backend import ComposeSandboxBackend
from mires_etl import contract
from tests.sandbox_docker import docker_client_for

IMAGE_REF = "mires-etl-sandbox-python:dev"


@pytest.fixture
def docker_client(settings):
    return docker_client_for(IMAGE_REF, settings=settings)


@pytest.mark.long_running
@pytest.mark.parametrize("script", NATIVE_SCRIPTS, ids=lambda script: script.filename)
def test_every_native_script_imports_and_runs_on_the_real_image(docker_client, settings, script):
    settings.SANDBOX_IMAGE_ALLOWLIST = {"python-etl-v1": IMAGE_REF}
    spec = SandboxRunSpec(
        run_id=f"conformance-{script.filename.removesuffix('.py').replace('_', '-')}",
        image_key="python-etl-v1", manifest={"datatype": script.datatype_name, "config": {}},
        script_source=native_script_path(script.filename).read_bytes(), limits=resolve_limits(None))

    result = ComposeSandboxBackend(client=docker_client).run(spec)

    assert result.exit_code == contract.EXIT_SUCCESS, result.log.decode()


@pytest.mark.long_running
def test_the_real_image_reports_its_digest_and_the_curated_package_manifest(docker_client, settings):
    settings.SANDBOX_IMAGE_ALLOWLIST = {"python-etl-v1": IMAGE_REF}
    spec = SandboxRunSpec(
        run_id="conformance-manifest", image_key="python-etl-v1", manifest={"datatype": "measurement", "config": {}},
        script_source=b"import pydicom, polars, numpy\ndef main(ctx):\n    return iter(())\n",
        limits=resolve_limits(None))

    result = ComposeSandboxBackend(client=docker_client).run(spec)

    assert result.exit_code == contract.EXIT_SUCCESS, result.log.decode()
    assert result.image_digest.startswith("sha256:")
    for package in ("pydicom==", "polars==", "numpy=="):
        assert package in result.image_manifest
