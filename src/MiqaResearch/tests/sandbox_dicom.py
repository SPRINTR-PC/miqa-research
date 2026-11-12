"""Real-sandbox DICOM Job plumbing (#423): run the `dicom_instance` script in a real sandbox container/Pod, then
load its rows exactly as the orchestrator would (the `dicom_instance` loader over the staged originals).

The R image carries no DICOM library, so its smoke uses `R_DICOM_SCRIPT`, a minimal header reader
(explicit-VR little endian, the only syntax the synthetic fixtures use) that emits the same row shape.
"""
import json
import os
from pathlib import Path

import pytest
from django.db import transaction

from MiqaResearch.actions.dicom_ingest.local import DEFAULT_CONFIG, create_local_job, create_missing_participants
from MiqaResearch.etl_datatypes import load_jsonl
from MiqaResearch.etl_native_scripts import native_script_path
from MiqaResearch.etl_sandbox import SandboxLimits, SandboxRunSpec, StagedInput, resolve_limits
from MiqaResearch.etl_sandbox.compose_backend import ComposeSandboxBackend
from mires_etl import contract
from tests.sandbox_docker import PYTHON_IMAGE, R_IMAGE, docker_client_for

# Kubernetes node image refs: `kind load docker-image <ref>` keeps the docker tag, so the same refs work.
K8S_PYTHON_IMAGE = os.environ.get("MIRES_TEST_K8S_PYTHON_IMAGE", PYTHON_IMAGE)
K8S_R_IMAGE = os.environ.get("MIRES_TEST_K8S_R_IMAGE", R_IMAGE)
K8S_NAMESPACE = "mires-etl-sandbox"

IMAGE_KEYS = {"python-etl-v1": (PYTHON_IMAGE, K8S_PYTHON_IMAGE), "r-etl-v1": (R_IMAGE, K8S_R_IMAGE)}

R_DICOM_SCRIPT = r'''
u16 <- function(b, i) as.integer(b[i]) + 256L * as.integer(b[i + 1])
u32 <- function(b, i) u16(b, i) + 65536 * u16(b, i + 2)
txt <- function(b) trimws(rawToChar(b[b != as.raw(0)]))

read_header <- function(path) {
  con <- file(path, "rb"); b <- readBin(con, "raw", file.size(path)); close(con)
  out <- list(); pos <- 133
  repeat {
    if (pos + 8 > length(b)) break
    grp <- u16(b, pos); el <- u16(b, pos + 2)
    if (grp == 0x7FE0) break
    vr <- rawToChar(b[(pos + 4):(pos + 5)])
    if (vr %in% c("OB", "OW", "OF", "SQ", "UT", "UN")) { len <- u32(b, pos + 8); head <- 12 }
    else { len <- u16(b, pos + 6); head <- 8 }
    if (len >= 4294967295) break
    key <- sprintf("%04X%04X", grp, el)
    if (len > 0 && len < 4096) {
      out[[key]] <- if (vr == "US") u16(b, pos + head) else txt(b[(pos + head):(pos + head + len - 1)])
    }
    pos <- pos + head + len
  }
  out
}

main <- function(ctx) {
  for (f in sort(list.files(ctx$input_dir, recursive = TRUE))) {
    h <- read_header(file.path(ctx$input_dir, f))
    emit(list(
      source_path = f, status = "ok",
      study_instance_uid = h[["0020000D"]], series_instance_uid = h[["0020000E"]],
      sop_instance_uid = h[["00080018"]], sop_class_uid = h[["00080016"]], modality = h[["00080060"]],
      rows = h[["00280010"]], columns = h[["00280011"]],
      identifiers = list(PatientID = h[["00100020"]]), payload = list(kind = "image")))
  }
}
'''


def sandbox_limits(*, memory_mb=512, timeout_seconds=600, max_input_bytes=8 * 1024 ** 3) -> SandboxLimits:
    return SandboxLimits(
        timeout_seconds=timeout_seconds, memory_mb=memory_mb, cpu_millicores=1000, pids_limit=128,
        max_input_bytes=max_input_bytes, max_output_bytes=resolve_limits(None).max_output_bytes)


def compose_backend(settings, image_key: str = "python-etl-v1") -> ComposeSandboxBackend:
    image = IMAGE_KEYS[image_key][0]
    client = docker_client_for(image, settings=settings)
    settings.SANDBOX_IMAGE_ALLOWLIST = {image_key: image}
    return ComposeSandboxBackend(client=client)


def kubernetes_backend(settings, image_key: str = "python-etl-v1"):
    """A `KubernetesSandboxBackend` on the current kube context, or a skip when no cluster answers."""
    from kubernetes import client as k8s
    from kubernetes import config as k8s_config

    from MiqaResearch.etl_sandbox.kubernetes_backend import KubernetesSandboxBackend
    try:
        k8s_config.load_kube_config()
        core_v1, batch_v1, networking_v1 = k8s.CoreV1Api(), k8s.BatchV1Api(), k8s.NetworkingV1Api()
        core_v1.list_namespace()
    except Exception as exc:
        pytest.skip(f"no Kubernetes cluster reachable: {exc}")
    settings.SANDBOX_IMAGE_ALLOWLIST = {image_key: IMAGE_KEYS[image_key][1]}
    settings.SANDBOX_K8S_NAMESPACE = K8S_NAMESPACE
    return KubernetesSandboxBackend(core_v1=core_v1, batch_v1=batch_v1, networking_v1=networking_v1)


def staged_folder(folder: Path) -> list[StagedInput]:
    """Every file under `folder` as a staged input at its relative path (no copy: the tar reads in place)."""
    return [
        StagedInput(relative_path=p.relative_to(folder).as_posix(), size=p.stat().st_size, local_path=p)
        for p in sorted(p for p in Path(folder).rglob("*") if p.is_file())]


def run_dicom_job(
        backend, project, folder: Path, *, run_id: str, image_key: str = "python-etl-v1", limits=None,
        config: dict | None = DEFAULT_CONFIG, link_participants: bool = True):
    """One Job: the script in the real sandbox over `folder`, then the loader. Returns `(result, load_result)`."""
    folder = Path(folder)
    if link_participants:
        create_missing_participants(project, folder)
    source = (R_DICOM_SCRIPT.encode() if image_key == "r-etl-v1"
              else native_script_path("dicom_instance.py").read_bytes())
    spec = SandboxRunSpec(
        run_id=run_id, image_key=image_key, manifest={"datatype": "dicom_instance", "config": config or {}},
        script_source=source, limits=limits or sandbox_limits(), input_files=staged_folder(folder))
    result = backend.run(spec)
    assert result.exit_code == contract.EXIT_SUCCESS, result.log.decode(errors="replace")
    lines = result.result_jsonl.splitlines()
    assert json.loads(lines[0]) == {"datatype": "dicom_instance"}
    with transaction.atomic():
        job, inputs = create_local_job(project, folder, config)
        load_result = load_jsonl(
            datatype_name="dicom_instance", project=project, etl_job=job,
            jsonl_text=b"\n".join(lines[1:]).decode(), inputs=inputs)
    return result, load_result
