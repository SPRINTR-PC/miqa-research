"""The Kubernetes `SandboxBackend` (#165): runs a Script's pinned image as one `batch/v1.Job` per run, in
a dedicated namespace, under a namespace-wide default-deny-egress `NetworkPolicy`. Satisfies the exact
same interface `ComposeSandboxBackend` (#161) does -- same image-allowlist and input-size gates (shared
via `_staging.py`), same resource-limit semantics, same `run`/`cancel`/`sweep` contract -- so the
orchestrator (#162) needs no changes to switch backends.

Unlike Compose (which shares a Docker daemon connection the worker can stream archives over directly),
a K8s worker and the Job pod it starts share nothing -- no daemon socket, no filesystem. I/O instead goes
through a per-run `ReadWriteOnce` PersistentVolumeClaim, written and read by short-lived, trusted
"transfer" pods via pod-exec streaming (`tar` over stdin/stdout) -- never by the Script's own Job pod,
which only ever mounts the already-staged volume. This design, and specifically that a `default-deny-
egress` NetworkPolicy leaves PVC I/O untouched (kubelet/CSI mount outside the pod network namespace), was
empirically spiked this session against a local kind+Calico cluster -- see
`docs/research/sandbox-runners.md`. The same spike found that a misconfigured CNI (e.g. kind's default
`kindnet`) can silently fail to enforce NetworkPolicy at all, which is why `_ensure_healthy` doesn't just
check the policy object exists -- it runs a real, fail-closed egress probe before ever scheduling a Job.
"""
import math
import time
from collections.abc import Callable

from kubernetes import client as k8s
from kubernetes.client.exceptions import ApiException
from kubernetes.stream import stream as default_stream_fn

from mires_etl import contract

from ._staging import build_sandbox_archive, check_input_size, read_output_from_tar
from .backend import SandboxBackend
from .exceptions import SandboxBackendUnhealthy
from .images import resolve_sandbox_image
from .spec import SandboxRunResult, SandboxRunSpec

SANDBOX_ROOT = "/sandbox"
NAME_PREFIX = "mires-etl-"
SANDBOX_LABEL = "mires.etl.sandbox"
RUN_ID_LABEL = "mires.etl.run_id"
NETWORK_POLICY_NAME = "mires-etl-sandbox-default-deny-egress"

# Debian's stock nobody:nogroup -- matches the UID/GID `etl_sandbox.Dockerfile` chowns /sandbox to,
# same as ComposeSandboxBackend.NON_ROOT_USER.
NON_ROOT_UID = 65534
NON_ROOT_GID = 65534

HTTP_CONFLICT = 409
HTTP_NOT_FOUND = 404

EGRESS_PROBE_POD_NAME = f"{NAME_PREFIX}egress-probe"
POD_POLL_INTERVAL_SECONDS = 1
PROBE_POD_TIMEOUT_SECONDS = 30
JOB_POLL_INTERVAL_SECONDS = 2
JOB_POLL_GRACE_SECONDS = 30  # on top of the Job's own activeDeadlineSeconds enforcement
TRANSFER_POD_READY_TIMEOUT_SECONDS = 60
EXEC_CHUNK_BYTES = 1024 * 1024
GIB = 1024 ** 3


class KubernetesSandboxBackend(SandboxBackend):
    def __init__(
        self, *,
        core_v1: k8s.CoreV1Api | None = None,
        batch_v1: k8s.BatchV1Api | None = None,
        networking_v1: k8s.NetworkingV1Api | None = None,
        stream_fn=default_stream_fn,
    ):
        self._core_v1 = core_v1
        self._batch_v1 = batch_v1
        self._networking_v1 = networking_v1
        self._stream_fn = stream_fn
        self._healthy_until: float = 0.0

    def run(self, spec: SandboxRunSpec) -> SandboxRunResult:
        image = resolve_sandbox_image(spec.image_key)
        check_input_size(spec)
        self._ensure_healthy()

        pvc_name = self._create_pvc(spec)
        try:
            self._stage(pvc_name, spec)
            exit_code, killed = self._run_job(pvc_name, image, spec)
            result_jsonl, log = self._drain(pvc_name, spec.run_id, spec.limits.max_output_bytes)
            return SandboxRunResult(exit_code=exit_code, result_jsonl=result_jsonl, log=log, killed=killed)
        finally:
            self._delete_pvc(pvc_name)

    def cancel(self, run_id: str) -> None:
        namespace = self._namespace()
        job_name = _job_name(run_id)
        try:
            self._batch_v1.delete_namespaced_job(job_name, namespace, propagation_policy="Foreground")
        except ApiException as exc:
            if exc.status != HTTP_NOT_FOUND:
                raise
        for transfer_pod_name in (_stage_pod_name(run_id), _drain_pod_name(run_id)):
            try:
                self._core_v1.delete_namespaced_pod(transfer_pod_name, namespace)
            except ApiException as exc:
                if exc.status != HTTP_NOT_FOUND:
                    raise
        try:
            self._core_v1.delete_namespaced_persistent_volume_claim(_pvc_name(run_id), namespace)
        except ApiException as exc:
            if exc.status != HTTP_NOT_FOUND:
                raise

    def sweep(self, *, live_run_ids: Callable[[], set[str]]) -> None:
        """Only resources carrying a run-id label are ever swept -- the egress probe pod has none
        and is managed by `_ensure_healthy` itself."""
        namespace = self._namespace()
        label_selector = f"{SANDBOX_LABEL}=1"
        jobs = self._batch_v1.list_namespaced_job(namespace, label_selector=label_selector).items
        pods = self._core_v1.list_namespaced_pod(namespace, label_selector=label_selector).items
        pvcs = self._core_v1.list_namespaced_persistent_volume_claim(namespace, label_selector=label_selector).items
        live = live_run_ids()

        def orphaned(resource) -> bool:
            run_id = (resource.metadata.labels or {}).get(RUN_ID_LABEL)
            return run_id is not None and run_id not in live

        for job in filter(orphaned, jobs):
            _ignore_not_found(
                self._batch_v1.delete_namespaced_job, job.metadata.name, namespace, propagation_policy="Foreground")
        for pod in filter(orphaned, pods):
            _ignore_not_found(self._core_v1.delete_namespaced_pod, pod.metadata.name, namespace)
        for pvc in filter(orphaned, pvcs):
            _ignore_not_found(self._core_v1.delete_namespaced_persistent_volume_claim, pvc.metadata.name, namespace)

    # --- PVC --------------------------------------------------------------

    def _create_pvc(self, spec: SandboxRunSpec) -> str:
        name = _pvc_name(spec.run_id)
        pvc = k8s.V1PersistentVolumeClaim(
            metadata=k8s.V1ObjectMeta(
                name=name, labels={SANDBOX_LABEL: "1", RUN_ID_LABEL: spec.run_id}),
            spec=k8s.V1PersistentVolumeClaimSpec(
                access_modes=["ReadWriteOnce"],
                resources=k8s.V1VolumeResourceRequirements(
                    requests={"storage": f"{_pvc_size_gi(spec.limits)}Gi"}),
            ),
        )
        self._core_v1.create_namespaced_persistent_volume_claim(self._namespace(), pvc)
        return name

    def _delete_pvc(self, name: str) -> None:
        try:
            self._core_v1.delete_namespaced_persistent_volume_claim(name, self._namespace())
        except ApiException as exc:
            if exc.status != HTTP_NOT_FOUND:
                raise

    # --- transfer pods (stage / drain) -------------------------------------

    def _stage(self, pvc_name: str, spec: SandboxRunSpec) -> None:
        pod_name = _stage_pod_name(spec.run_id)
        self._run_transfer_pod(pod_name, pvc_name, spec.run_id)
        try:
            self._exec_write(pod_name, ["tar", "-xf", "-", "-C", SANDBOX_ROOT], build_sandbox_archive(spec))
        finally:
            self._core_v1.delete_namespaced_pod(pod_name, self._namespace())

    def _drain(self, pvc_name: str, run_id: str, max_output_bytes: int) -> tuple[bytes | None, bytes]:
        pod_name = _drain_pod_name(run_id)
        self._run_transfer_pod(pod_name, pvc_name, run_id)
        try:
            tar_bytes = self._exec_read(
                pod_name, ["tar", "-cf", "-", "-C", SANDBOX_ROOT, contract.OUTPUT_DIRNAME],
                max_bytes=max_output_bytes)
        finally:
            self._core_v1.delete_namespaced_pod(pod_name, self._namespace())

        if tar_bytes is None:
            return None, b""
        return read_output_from_tar(tar_bytes)

    def _run_transfer_pod(self, pod_name: str, pvc_name: str, run_id: str) -> None:
        from django.conf import settings

        pod = k8s.V1Pod(
            metadata=k8s.V1ObjectMeta(
                name=pod_name, labels={SANDBOX_LABEL: "1", RUN_ID_LABEL: run_id}),
            spec=k8s.V1PodSpec(
                restart_policy="Never",
                automount_service_account_token=False,
                containers=[k8s.V1Container(
                    name="transfer",
                    image=settings.SANDBOX_K8S_STAGER_IMAGE,
                    command=["sleep", str(TRANSFER_POD_READY_TIMEOUT_SECONDS)],
                    volume_mounts=[k8s.V1VolumeMount(name="sandbox", mount_path=SANDBOX_ROOT)],
                )],
                volumes=[k8s.V1Volume(
                    name="sandbox",
                    persistent_volume_claim=k8s.V1PersistentVolumeClaimVolumeSource(claim_name=pvc_name))],
            ),
        )
        self._core_v1.create_namespaced_pod(self._namespace(), pod)
        self._wait_for_pod_running(pod_name, TRANSFER_POD_READY_TIMEOUT_SECONDS)

    def _wait_for_pod_running(self, name: str, timeout_seconds: int) -> None:
        deadline = time.monotonic() + timeout_seconds
        while True:
            pod = self._core_v1.read_namespaced_pod(name, self._namespace())
            if pod.status.phase == "Running":
                return
            if time.monotonic() > deadline:
                raise TimeoutError(f"Pod {name!r} did not reach Running within {timeout_seconds}s.")
            time.sleep(POD_POLL_INTERVAL_SECONDS)

    def _exec_write(self, pod_name: str, command: list[str], data: bytes) -> None:
        ws = self._stream_fn(
            self._core_v1.connect_get_namespaced_pod_exec, pod_name, self._namespace(),
            command=command, stderr=True, stdin=True, stdout=True, tty=False, _preload_content=False)
        try:
            for offset in range(0, len(data), EXEC_CHUNK_BYTES):
                ws.write_stdin(data[offset:offset + EXEC_CHUNK_BYTES])
        finally:
            ws.close()

    def _exec_read(self, pod_name: str, command: list[str], *, max_bytes: int) -> bytes | None:
        # `binary=True` here (not per-read) is how this client library returns raw bytes instead of
        # UTF-8-decoded text from read_stdout() -- tar output is binary and would otherwise corrupt on
        # decode. See kubernetes.stream.stream._websocket_request/ws_client.WSClient.__init__.
        ws = self._stream_fn(
            self._core_v1.connect_get_namespaced_pod_exec, pod_name, self._namespace(),
            command=command, stderr=True, stdin=False, stdout=True, tty=False, _preload_content=False,
            binary=True)
        buf = bytearray()
        try:
            while ws.is_open():
                ws.update(timeout=5)
                if ws.peek_stdout():
                    buf += ws.read_stdout()
                    if len(buf) > max_bytes:
                        return None
                if ws.peek_stderr():
                    ws.read_stderr()
        finally:
            ws.close()
        return bytes(buf)

    # --- script Job ----------------------------------------------------

    def _run_job(self, pvc_name: str, image: str, spec: SandboxRunSpec) -> tuple[int, bool]:
        job_name = _job_name(spec.run_id)
        limits = spec.limits
        job = k8s.V1Job(
            metadata=k8s.V1ObjectMeta(
                name=job_name, labels={SANDBOX_LABEL: "1", RUN_ID_LABEL: spec.run_id}),
            spec=k8s.V1JobSpec(
                backoff_limit=0,
                active_deadline_seconds=limits.timeout_seconds,
                ttl_seconds_after_finished=JOB_POLL_GRACE_SECONDS,
                template=k8s.V1PodTemplateSpec(
                    metadata=k8s.V1ObjectMeta(labels={SANDBOX_LABEL: "1", RUN_ID_LABEL: spec.run_id}),
                    spec=k8s.V1PodSpec(
                        restart_policy="Never",
                        automount_service_account_token=False,
                        containers=[k8s.V1Container(
                            name="script",
                            image=image,
                            args=[SANDBOX_ROOT],
                            volume_mounts=[k8s.V1VolumeMount(name="sandbox", mount_path=SANDBOX_ROOT)],
                            resources=k8s.V1ResourceRequirements(
                                requests={
                                    "memory": f"{limits.memory_mb}Mi",
                                    "cpu": f"{limits.cpu_millicores}m",
                                },
                                limits={
                                    "memory": f"{limits.memory_mb}Mi",
                                    "cpu": f"{limits.cpu_millicores}m",
                                },
                            ),
                            security_context=k8s.V1SecurityContext(
                                run_as_non_root=True,
                                run_as_user=NON_ROOT_UID,
                                run_as_group=NON_ROOT_GID,
                                allow_privilege_escalation=False,
                                capabilities=k8s.V1Capabilities(drop=["ALL"]),
                                seccomp_profile=k8s.V1SeccompProfile(type="RuntimeDefault"),
                            ),
                        )],
                        volumes=[k8s.V1Volume(
                            name="sandbox",
                            persistent_volume_claim=k8s.V1PersistentVolumeClaimVolumeSource(
                                claim_name=pvc_name)),
                        ],
                    ),
                ),
            ),
        )
        self._batch_v1.create_namespaced_job(self._namespace(), job)
        try:
            return self._wait_for_job(job_name, limits.timeout_seconds)
        finally:
            self._batch_v1.delete_namespaced_job(job_name, self._namespace(), propagation_policy="Foreground")

    def _wait_for_job(self, job_name: str, timeout_seconds: int) -> tuple[int, bool]:
        deadline = time.monotonic() + timeout_seconds + JOB_POLL_GRACE_SECONDS
        while True:
            job = self._batch_v1.read_namespaced_job(job_name, self._namespace())
            if job.status.succeeded or job.status.failed:
                return self._read_job_outcome(job_name, deadline)
            if time.monotonic() > deadline:
                raise TimeoutError(f"Job {job_name!r} did not reach a terminal state within {timeout_seconds}s.")
            time.sleep(JOB_POLL_INTERVAL_SECONDS)

    def _read_job_outcome(self, job_name: str, deadline: float) -> tuple[int, bool]:
        """Called once the Job itself is terminal. The Job going terminal and its Pod's own container
        status reflecting *why* are not perfectly synchronized -- observed racing this session's
        integration test, where `container_statuses[0].state.terminated` was still `None` right after
        `job.status.failed` flipped. So this polls the Pod (not the Job) for up to the same deadline,
        checking `pod.status.reason` first -- the canonical place K8s records `DeadlineExceeded` -- since
        a killed container's own `terminated.reason` doesn't reliably carry that same string.
        """
        namespace = self._namespace()
        while True:
            pods = self._core_v1.list_namespaced_pod(namespace, label_selector=f"job-name={job_name}").items
            if pods:
                pod = pods[0]
                if pod.status.reason == "DeadlineExceeded":
                    return contract.EXIT_TIMEOUT_OR_KILLED, True
                container_statuses = pod.status.container_statuses or []
                terminated = container_statuses[0].state.terminated if container_statuses else None
                if terminated is not None:
                    if terminated.reason == "OOMKilled":
                        return contract.EXIT_TIMEOUT_OR_KILLED, True
                    return terminated.exit_code, False
            # Either no Pod observed yet, or one observed with no terminated state yet -- a kubelet
            # that GCs a DeadlineExceeded Pod quickly can make it vanish from list_namespaced_pod
            # entirely before we ever see it (observed this session), so an empty list must retry too,
            # not index into it.
            if time.monotonic() > deadline:
                # The Job is terminal but its Pod never surfaced a terminated container state or an
                # explicit DeadlineExceeded reason -- treat conservatively as killed rather than invent
                # a success/script exit code we never actually observed.
                return contract.EXIT_TIMEOUT_OR_KILLED, True
            time.sleep(JOB_POLL_INTERVAL_SECONDS)

    def _ensure_healthy(self) -> None:
        """Idempotently ensure the sandbox namespace and its default-deny-egress NetworkPolicy exist,
        then -- if the cached result is stale -- run a real, fail-closed egress probe: a throwaway pod
        under that same policy must fail to reach `SANDBOX_K8S_EGRESS_PROBE_HOST:_PORT`. A CNI that
        silently doesn't enforce NetworkPolicy (confirmed possible this session, kind's default kindnet)
        would let that connection succeed -- which raises rather than letting a Job ever schedule
        unisolated.
        """
        from django.conf import settings

        self._ensure_namespace_exists()
        self._ensure_default_deny_egress_network_policy_exists()

        if time.monotonic() < self._healthy_until:
            return

        namespace = self._namespace()
        probe = k8s.V1Pod(
            metadata=k8s.V1ObjectMeta(name=EGRESS_PROBE_POD_NAME, labels={SANDBOX_LABEL: "1"}),
            spec=k8s.V1PodSpec(
                restart_policy="Never",
                automount_service_account_token=False,
                containers=[k8s.V1Container(
                    name="probe",
                    image=settings.SANDBOX_K8S_STAGER_IMAGE,
                    command=[
                        "nc", "-z", "-w", "5",
                        settings.SANDBOX_K8S_EGRESS_PROBE_HOST, str(settings.SANDBOX_K8S_EGRESS_PROBE_PORT),
                    ],
                )],
            ),
        )
        try:
            self._core_v1.create_namespaced_pod(namespace, probe)
        except ApiException as exc:
            if exc.status != HTTP_CONFLICT:
                raise
        try:
            pod = self._wait_for_pod_terminal(EGRESS_PROBE_POD_NAME, PROBE_POD_TIMEOUT_SECONDS)
            reached_out = pod.status.container_statuses[0].state.terminated.exit_code == 0
            if reached_out:
                raise SandboxBackendUnhealthy(
                    "Kubernetes sandbox egress probe reached "
                    f"{settings.SANDBOX_K8S_EGRESS_PROBE_HOST}:{settings.SANDBOX_K8S_EGRESS_PROBE_PORT} "
                    "from inside a default-deny-egress pod -- the cluster's CNI is not enforcing "
                    "NetworkPolicy, so a Script's own outbound network access could not actually be "
                    "blocked. Refusing to schedule any run until this is fixed.")
        finally:
            self._core_v1.delete_namespaced_pod(EGRESS_PROBE_POD_NAME, namespace)

        self._healthy_until = time.monotonic() + settings.SANDBOX_K8S_SELF_TEST_TTL_SECONDS

    def _ensure_namespace_exists(self) -> None:
        namespace = self._namespace()
        try:
            self._core_v1.create_namespace(k8s.V1Namespace(metadata=k8s.V1ObjectMeta(name=namespace)))
        except ApiException as exc:
            if exc.status != HTTP_CONFLICT:
                raise

    def _ensure_default_deny_egress_network_policy_exists(self) -> None:
        policy = k8s.V1NetworkPolicy(
            metadata=k8s.V1ObjectMeta(name=NETWORK_POLICY_NAME),
            spec=k8s.V1NetworkPolicySpec(pod_selector=k8s.V1LabelSelector(), policy_types=["Egress"]),
        )
        try:
            self._networking_v1.create_namespaced_network_policy(self._namespace(), policy)
        except ApiException as exc:
            if exc.status != HTTP_CONFLICT:
                raise

    def _wait_for_pod_terminal(self, name: str, timeout_seconds: int):
        deadline = time.monotonic() + timeout_seconds
        while True:
            pod = self._core_v1.read_namespaced_pod(name, self._namespace())
            if pod.status.phase in ("Succeeded", "Failed"):
                return pod
            if time.monotonic() > deadline:
                raise TimeoutError(f"Pod {name!r} did not reach a terminal phase within {timeout_seconds}s.")
            time.sleep(POD_POLL_INTERVAL_SECONDS)

    def _namespace(self) -> str:
        from django.conf import settings
        return settings.SANDBOX_K8S_NAMESPACE


def _ignore_not_found(delete, *args, **kwargs) -> None:
    """A Job's Foreground deletion can already have removed its pod by the time we get to it."""
    try:
        delete(*args, **kwargs)
    except ApiException as exc:
        if exc.status != HTTP_NOT_FOUND:
            raise


def _pvc_size_gi(limits) -> int:
    return max(1, math.ceil((limits.max_input_bytes + limits.max_output_bytes) / GIB))


def _job_name(run_id: str) -> str:
    return f"{NAME_PREFIX}{run_id}"


def _pvc_name(run_id: str) -> str:
    return f"{NAME_PREFIX}{run_id}"


def _stage_pod_name(run_id: str) -> str:
    return f"{NAME_PREFIX}{run_id}-stage"


def _drain_pod_name(run_id: str) -> str:
    return f"{NAME_PREFIX}{run_id}-drain"
