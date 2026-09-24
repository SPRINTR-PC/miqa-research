"""Real-cluster integration test for `KubernetesSandboxBackend` (#165) -- opt-in and `long_running`-
marked per the established convention (#98/#113/#114), matching
`test_etl_sandbox_compose_integration.py`'s shape. It needs a real Kubernetes cluster with a CNI that
enforces NetworkPolicy (kind's default `kindnet` does *not* -- confirmed this session, see
`docs/research/sandbox-runners.md`; a Calico install is what makes this test meaningful rather than a
false pass) and the `mires-etl-sandbox-python:dev` image already loaded into it, and skips gracefully
when no cluster is reachable rather than failing the run.

One-time local setup used to develop this test (kind + podman; adjust for Docker Desktop/another CNI):

    export KIND_EXPERIMENTAL_PROVIDER=podman
    kind create cluster --name etl-spike --config kind-config.yaml   # networking.disableDefaultCNI: true
    kubectl apply -f https://raw.githubusercontent.com/projectcalico/calico/v3.28.0/manifests/calico.yaml
    docker build -f etl_sandbox.Dockerfile -t mires-etl-sandbox-python:dev .
    # kind's `load docker-image` didn't recognize a podman-built image by name this session --
    # `load image-archive` from a `docker save` (podman alias) did:
    docker save localhost/mires-etl-sandbox-python:dev -o /tmp/mires-etl-sandbox-python-dev.tar
    kind load image-archive /tmp/mires-etl-sandbox-python-dev.tar --name etl-spike

Demo, per #165's acceptance criteria: #160's sample script actually executes inside an isolated
Kubernetes Job via `SandboxBackend.run()`, with no network reachable from inside it, its `result.jsonl`
staged onto and read back off a per-run PVC via pod-exec streaming (the one mechanism this ticket's own
research spike didn't already validate), and loaded through #159's `load_jsonl` correctly -- the same
scenario the Compose integration test proves for that backend.
"""
import json
from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from kubernetes import client as k8s
from kubernetes import config as k8s_config

from contract.constants.etl import ETL_SCRIPT_ORIGIN_CUSTOM
from MiqaResearch.data.models import (
    Concept,
    EtlJob,
    EtlScript,
    EtlScriptVersion,
    Measurement,
    PipelineBinding,
    ResearchProject,
    StudyParticipant,
)
from MiqaResearch.etl_datatypes import load_jsonl
from MiqaResearch.etl_sandbox import SandboxLimits, SandboxRunSpec, resolve_limits
from MiqaResearch.etl_sandbox.kubernetes_backend import KubernetesSandboxBackend
from MiqaResearch.etl_shim import contract

IMAGE_REF = "localhost/mires-etl-sandbox-python:dev"
NAMESPACE = "mires-etl-sandbox"


@pytest.fixture
def k8s_apis():
    try:
        k8s_config.load_kube_config()
    except Exception:
        try:
            k8s_config.load_incluster_config()
        except Exception as exc:
            pytest.skip(f"no kubeconfig / in-cluster config available: {exc}")
    core_v1, batch_v1, networking_v1 = k8s.CoreV1Api(), k8s.BatchV1Api(), k8s.NetworkingV1Api()
    try:
        core_v1.list_namespace()
    except Exception as exc:
        pytest.skip(f"no Kubernetes API server reachable: {exc}")
    return core_v1, batch_v1, networking_v1


@pytest.fixture(autouse=True)
def mock_encryption_keys(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="


@pytest.fixture(autouse=True)
def _media_root(tmp_path_factory, settings):
    settings.MEDIA_ROOT = tmp_path_factory.mktemp("media")


@pytest.mark.long_running
@pytest.mark.django_db
def test_a_sample_script_runs_isolated_in_a_real_k8s_job_and_its_rows_load(k8s_apis, settings):
    settings.SANDBOX_IMAGE_ALLOWLIST = {"python-etl-v1": IMAGE_REF}
    settings.SANDBOX_K8S_NAMESPACE = NAMESPACE
    core_v1, batch_v1, networking_v1 = k8s_apis
    research_project = ResearchProject.objects.create(name="K8s sandbox integration project", description="")
    participant = StudyParticipant.objects.create(
        alias1="K8S-SANDBOX-P001", person_source_value="SRC-001", research_project=research_project)
    concept = Concept.objects.create(
        concept_name="Body weight", vocabulary_id="LOINC", concept_class_id="Clinical Observation",
        concept_code="29463-7", valid_start_date=date(2000, 1, 1), valid_end_date=date(2099, 12, 31))
    type_concept = Concept.objects.create(
        concept_name="Lab result", vocabulary_id="Provenance", concept_class_id="Type Concept",
        concept_code="lab-result", valid_start_date=date(2000, 1, 1), valid_end_date=date(2099, 12, 31))
    script = EtlScript.objects.create(
        name="K8s sandbox sample script", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=research_project)
    script_version = EtlScriptVersion.objects.create(
        script=script, version=1, source=SimpleUploadedFile("script.py", b"print('hi')"), sha256="0" * 64)
    binding = PipelineBinding.objects.create(
        project=research_project, source_bucket="incoming", source_prefix="dt/", script_version=script_version,
        raw_bucket="raw", raw_prefix="dt/")
    etl_job = EtlJob.objects.create(binding=binding, script_version=script_version)

    # Same real-observation trick as the Compose integration test: the script records whether its own
    # outbound connection attempt actually succeeded, rather than us guessing from logs.
    script_source = f"""
import socket

def main(ctx):
    network_reachable = True
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
    except OSError:
        network_reachable = False
    yield {{
        "alias1": "{participant.alias1}",
        "measurement_concept_id": "{concept.concept_id}",
        "measurement_type_concept_id": "{type_concept.concept_id}",
        "measurement_date": "2026-01-15",
        "measurement_source_value": "WEIGHT",
        "value_as_number": 71.5,
        "value_source_value": "network-reachable" if network_reachable else "network-blocked",
    }}
""".encode()

    backend = KubernetesSandboxBackend(core_v1=core_v1, batch_v1=batch_v1, networking_v1=networking_v1)
    spec = SandboxRunSpec(
        run_id="k8s-integration-test-run", image_key="python-etl-v1",
        manifest={"datatype": "measurement", "config": {}}, script_source=script_source, limits=resolve_limits())

    result = backend.run(spec)

    assert result.exit_code == contract.EXIT_SUCCESS, result.log.decode(errors="replace")
    lines = result.result_jsonl.splitlines()
    header = json.loads(lines[0])
    assert header == {"datatype": "measurement"}
    rows_jsonl = b"\n".join(lines[1:]).decode() + "\n"

    load_result = load_jsonl(
        datatype_name=header["datatype"], project=research_project, etl_job=etl_job, jsonl_text=rows_jsonl)

    assert load_result.created == 1
    measurement = Measurement.objects.get()
    assert measurement.person_id == participant.id
    assert measurement.etl_job_id == etl_job.id
    # default-deny-egress NetworkPolicy: the script's own outbound-connection attempt must have failed.
    assert measurement.value_source_value == "network-blocked"


@pytest.mark.long_running
def test_a_script_exceeding_its_timeout_is_killed_and_reported_as_exit_code_3(k8s_apis, settings):
    settings.SANDBOX_IMAGE_ALLOWLIST = {"python-etl-v1": IMAGE_REF}
    settings.SANDBOX_K8S_NAMESPACE = NAMESPACE
    core_v1, batch_v1, networking_v1 = k8s_apis
    script_source = b"""
import time

def main(ctx):
    time.sleep(30)
    return iter(())
"""
    backend = KubernetesSandboxBackend(core_v1=core_v1, batch_v1=batch_v1, networking_v1=networking_v1)
    spec = SandboxRunSpec(
        run_id="k8s-integration-test-timeout", image_key="python-etl-v1",
        manifest={"datatype": "measurement", "config": {}}, script_source=script_source,
        limits=SandboxLimits(
            timeout_seconds=5, memory_mb=256, cpu_millicores=500, pids_limit=64,
            max_input_bytes=1024, max_output_bytes=1024))

    result = backend.run(spec)

    assert result.exit_code == contract.EXIT_TIMEOUT_OR_KILLED
    assert result.killed is True
