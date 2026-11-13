"""Real-container integration test for `ComposeSandboxBackend` (#161) -- opt-in and
`long_running`-marked per the established convention (#98/#113/#114): it needs a real Docker/Podman
daemon and the `mires-etl-sandbox-python:dev` image (`etl_sandbox.Dockerfile`, or
`docker compose --profile etl-sandbox-build build mires_etl_sandbox_python`), and skips gracefully
when either isn't available rather than failing the run.

Demo, per #161's acceptance criteria: #160's sample script actually executes inside an isolated
container via `SandboxBackend.run()`, with no network reachable from inside it, and its
`result.jsonl` read back and loaded through #159's `load_jsonl` correctly.
"""
import json
from datetime import date

import docker
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

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
from MiqaResearch.etl_sandbox.compose_backend import ComposeSandboxBackend
from mires_etl import contract
from tests.sandbox_docker import docker_client_for
from tests.sandbox_staging import stage_inputs

IMAGE_REF = "mires-etl-sandbox-python:dev"


@pytest.fixture
def docker_client(settings):
    return docker_client_for(IMAGE_REF, settings=settings)


@pytest.fixture(autouse=True)
def mock_encryption_keys(settings):
    settings.FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="
    settings.SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="


@pytest.fixture(autouse=True)
def _media_root(tmp_path_factory, settings):
    settings.MEDIA_ROOT = tmp_path_factory.mktemp("media")


@pytest.mark.long_running
@pytest.mark.django_db
def test_a_sample_script_runs_isolated_in_a_real_container_and_its_rows_load(docker_client, settings):
    settings.SANDBOX_IMAGE_ALLOWLIST = {"python-etl-v1": IMAGE_REF}
    research_project = ResearchProject.objects.create(name="ETL sandbox integration project", description="")
    participant = StudyParticipant.objects.create(
        alias1="ETL-SANDBOX-P001", person_source_value="SRC001", research_project=research_project)
    concept = Concept.objects.create(
        concept_name="Body weight", vocabulary_id="LOINC", concept_class_id="Clinical Observation",
        concept_code="29463-7", valid_start_date=date(2000, 1, 1), valid_end_date=date(2099, 12, 31))
    type_concept = Concept.objects.create(
        concept_name="Lab result", vocabulary_id="Provenance", concept_class_id="Type Concept",
        concept_code="lab-result", valid_start_date=date(2000, 1, 1), valid_end_date=date(2099, 12, 31))
    script = EtlScript.objects.create(
        name="Sandbox sample script", origin=ETL_SCRIPT_ORIGIN_CUSTOM, project=research_project)
    script_version = EtlScriptVersion.objects.create(
        script=script, version=1, source=SimpleUploadedFile("script.py", b"print('hi')"), sha256="0" * 64)
    binding = PipelineBinding.objects.create(
        project=research_project, source_bucket="incoming", source_prefix="dt/", script_version=script_version,
        raw_bucket="raw", raw_prefix="dt/")
    etl_job = EtlJob.objects.create(binding=binding, script_version=script_version)

    # Records whether its own outbound connection attempt succeeded, so the assertion below is a
    # real observation from inside the container rather than a log-scraping guess.
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

    backend = ComposeSandboxBackend(client=docker_client)
    spec = SandboxRunSpec(
        run_id="integration-test-run", image_key="python-etl-v1",
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
    # network_mode="none": the script's own outbound-connection attempt must have failed.
    assert measurement.value_source_value == "network-blocked"


@pytest.mark.long_running
def test_a_script_exceeding_its_timeout_is_killed_and_reported_as_exit_code_3(docker_client, settings):
    settings.SANDBOX_IMAGE_ALLOWLIST = {"python-etl-v1": IMAGE_REF}
    script_source = b"""
import time

def main(ctx):
    time.sleep(30)
    return iter(())
"""
    backend = ComposeSandboxBackend(client=docker_client)
    spec = SandboxRunSpec(
        run_id="integration-test-timeout", image_key="python-etl-v1",
        manifest={"datatype": "measurement", "config": {}}, script_source=script_source,
        limits=SandboxLimits(
            timeout_seconds=2, memory_mb=256, cpu_millicores=500, pids_limit=64,
            max_input_bytes=1024, max_output_bytes=1024))

    result = backend.run(spec)

    assert result.exit_code == contract.EXIT_TIMEOUT_OR_KILLED
    assert result.killed is True


@pytest.mark.long_running
def test_sweep_removes_an_orphaned_sandbox_container_and_keeps_a_live_one(docker_client):
    labels = {"mires.etl.sandbox": "1"}
    orphan = docker_client.containers.create(
        IMAGE_REF, name="mires-etl-it-sweep-orphan", labels=labels | {"mires.etl.run_id": "it-sweep-orphan"})
    live = docker_client.containers.create(
        IMAGE_REF, name="mires-etl-it-sweep-live", labels=labels | {"mires.etl.run_id": "it-sweep-live"})
    try:
        def every_run_but_the_orphan_is_live():
            # Other sandboxes on this daemon (another test run, a local dev stack) must survive this test.
            existing = docker_client.containers.list(all=True, filters={"label": "mires.etl.sandbox=1"})
            return {container.labels.get("mires.etl.run_id") for container in existing} - {"it-sweep-orphan"}

        ComposeSandboxBackend(client=docker_client).sweep(live_run_ids=every_run_but_the_orphan_is_live)

        remaining = {container.name for container in docker_client.containers.list(all=True)}
        assert "mires-etl-it-sweep-orphan" not in remaining
        assert "mires-etl-it-sweep-live" in remaining
    finally:
        for container in (orphan, live):
            try:
                container.remove(force=True)
            except docker.errors.NotFound:
                pass


@pytest.mark.long_running
@pytest.mark.django_db
def test_the_native_consent_script_runs_in_the_real_image_and_its_consents_load(docker_client, settings, tmp_path):
    from django.core.management import call_command

    from MiqaResearch.data.models import ParticipantConsent

    settings.SANDBOX_IMAGE_ALLOWLIST = {"python-etl-v1": IMAGE_REF}
    research_project = ResearchProject.objects.create(name="Native consent integration project", description="")
    call_command("sync_native_etl_scripts")
    native_version = EtlScriptVersion.objects.get(script__origin="native", script__datatype_name="participant_consent")
    binding = PipelineBinding.objects.create(
        project=research_project, source_bucket="incoming", source_prefix="consent/",
        script_version=native_version, raw_bucket="raw", raw_prefix="consent/")
    etl_job = EtlJob.objects.create(binding=binding, script_version=native_version)
    export = (
        "Namn,Personnummer,Status,Signerat,Senast Uppdaterad,Återtaget,klinik,Kommentar,Blodprov,Bilder\n"
        "Tolvan Tolvansson,19121212-1212,Signerad,2026-03-01 10:00:00,2026-03-02 10:00,,K-01,,Ja,Ja\n"
    ).encode()

    spec = SandboxRunSpec(
        run_id="integration-test-native-consent", image_key=native_version.image_key,
        manifest={"datatype": "participant_consent", "config": {}}, script_source=native_version.source.read(),
        limits=resolve_limits(), input_files=stage_inputs(tmp_path, {"export.csv": export}))
    result = ComposeSandboxBackend(client=docker_client).run(spec)

    assert result.exit_code == contract.EXIT_SUCCESS, result.log.decode(errors="replace")
    rows_jsonl = b"\n".join(result.result_jsonl.splitlines()[1:]).decode() + "\n"
    load_result = load_jsonl(
        datatype_name="participant_consent", project=research_project, etl_job=etl_job, jsonl_text=rows_jsonl)

    assert load_result.created == 2
    assert sorted(ParticipantConsent.objects.values_list("consent_type__label", flat=True)) == ["Bilder", "Blodprov"]
    assert StudyParticipant.objects.get().research_project_id == research_project.id
