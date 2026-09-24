# Research: sandbox runner options (docker-compose + Kubernetes)

Resolves #141 (parent map #140). Findings + recommendation. No spec decisions locked here.

Legend: **[F]** = fetched from primary doc this session. **[M]** = from maintainer knowledge, NOT re-verified; check before spec lock. **[E]** = empirically measured this session (kind v0.33 + Calico, single node, arm64).
Note: a fetch summarizer claimed `readOnlyRootFilesystem` is in PSS Restricted. It is not (Restricted = runAsNonRoot, seccomp RuntimeDefault/Localhost, drop ALL, allowPrivilegeEscalation=false [F]). Treat RO rootfs as extra hardening.

## Sources
- gVisor k8s: https://gvisor.dev/docs/user_guide/quick_start/kubernetes/ [F]
- K8s Job: https://kubernetes.io/docs/concepts/workloads/controllers/job/ [F]
- NetworkPolicy: https://kubernetes.io/docs/concepts/services-networking/network-policies/ [F]
- Pod Security Standards: https://kubernetes.io/docs/concepts/security/pod-security-standards/ [F]
- docker-socket-proxy: https://github.com/Tecnativa/docker-socket-proxy [F]
- Docker rootless: https://docs.docker.com/engine/security/rootless/ [F, thin]
- Sysbox: https://github.com/nestybox/sysbox (docs/user-guide) [F, TOC only]
- Docker Engine API (ContainerCreate HostConfig): https://docs.docker.com/reference/api/engine/ [M: fields below not confirmed by fetch]

## Options

| Option | Compose | K8s | Verdict |
|---|---|---|---|
| Docker socket-proxy sidecar | yes | no (no docker daemon) | Compose backend only |
| Rootless Docker/Podman | possible | no | Doesn't remove need for socket access; ops-heavy |
| Sysbox | yes (runtime) | node-level install, aimed at system containers/DinD | Overkill; wrong problem (nested containers) |
| gVisor (runsc) | yes: `--runtime=runsc` [M] | RuntimeClass `gvisor` [F] | Optional hardening layer, orthogonal |
| Kata | yes [M] | RuntimeClass [M] | Same as gVisor; needs virt on nodes |
| K8s Job | no | native | K8s backend |
| Dedicated runner service | yes | yes | Adds a service that itself needs a backend; not an alternative |

### Docker socket-proxy sidecar
- Gates Docker API by section via env (`CONTAINERS`, `IMAGES`, `POST`, ...); `POST` off by default, so read-only unless enabled [F].
- Filtering is URL-prefix level, **no request-body filtering** [F]. With `CONTAINERS=1 POST=1` the worker can create ANY container, incl. privileged / host bind mounts (body not inspected). So it does not enforce image allowlist or "no network" itself; the runner code must, and a compromised worker bypasses it. Mitigation: worker is trusted platform code, only untrusted script runs in the child; proxy on an isolated internal network with only worker attached [F: "only reside the proxy and the service that uses it"].
- Container create knobs needed [M]: `HostConfig.NetworkMode=none`, `Memory`, `NanoCpus`, `PidsLimit`, `ReadonlyRootfs`, `CapDrop=[ALL]`, `SecurityOpt=[no-new-privileges]`, `User`, `AutoRemove`, optional `Runtime=runsc`.
- Alternative to proxy: mount raw `/var/run/docker.sock` = root on host. Reject.

### K8s Jobs
- `backoffLimit`, `activeDeadlineSeconds` (terminates job when exceeded), `ttlSecondsAfterFinished`, `podFailurePolicy` [F]. Set `backoffLimit: 0` (platform owns retry per map), `activeDeadlineSeconds` = timeout.
- NetworkPolicy: pods non-isolated by default; select pod with `policyTypes: [Egress]` and no egress rules = deny all egress. Requires CNI that enforces NetworkPolicy, else silently no effect [F]. Traffic to the local node is always allowed [F] (note for IMDS/node services).
- Restricted PSS: runAsNonRoot, seccomp RuntimeDefault, drop ALL, allowPrivilegeEscalation false [F]; enforce via Pod Security Admission on the sandbox namespace. Also set `automountServiceAccountToken: false`, resources limits, `emptyDir.sizeLimit` [M].
- gVisor plugs in via `runtimeClassName: gvisor` when nodes have runsc [F].
- Worker needs RBAC (create/get/delete Jobs, get pods/log) scoped to the sandbox namespace [M].

## Input/output transfer
- **Compose**: per-job named volume or host dir (`/input` ro bind, `/output` rw). Docker API also allows `PUT /containers/{id}/archive` to stream files in without shared volumes [M]. Shared host path breaks if worker itself is containerised on another host; use a named volume mounted in both worker and (via `Binds`) sandbox, subdir per job.
- **K8s**: no shared FS between worker pod and Job pod. NetworkPolicy is per-pod, not per-container [F], so a sidecar/init that talks to RustFS shares the script's network identity: an object-store download inside the sandbox pod means the script could reach RustFS too. Options:
  1. Per-job PVC (or RWX PVC subpath) written/read by trusted worker-side code; script pod deny-all. Simple, needs storage class.
  2. Stager init container with egress to RustFS only, then egress closed: not expressible in one pod policy (init and main share pod). Rejected unless a stager Job is sequenced before the run Job.
  3. Stream via Kubernetes exec/attach API [M]: no storage, but fragile for large files.
  **Decision: (1), sequenced as two Pods.** Spiked on kind v0.33 (single node, `rancher.io/local-path` StorageClass, RWO, `WaitForFirstConsumer`) with Calico installed for real NetworkPolicy enforcement (kind's default `kindnet` CNI does **not** enforce NetworkPolicy — confirmed [E]: an egress request from a `default-deny-egress`-selected pod succeeded unmodified under kindnet; a prod cluster's CNI must be verified to enforce it, e.g. Calico/Cilium, or the policy is a silent no-op).
    - One PVC per job, `ReadWriteOnce`, two `subPath` mounts off the same volume: `/input` (ro) and `/output` (rw). No RWX needed — the PVC is only ever mounted by one pod at a time, sequenced by the worker.
    - **Stage**: worker creates the PVC, then a short-lived trusted "stager" Pod (own NetworkPolicy label, egress allowed to RustFS only) downloads input into `/input` and later uploads `/output`. This pod is *not* subject to the script's deny-all policy.
    - **Run**: the sandboxed script Job Pod, under `default-deny-egress`, mounts the same PVC. **Confirmed [E]:** volume read/write is unaffected by pod-level NetworkPolicy — kubelet/CSI perform the mount and I/O outside the pod's network namespace, so a script pod can be fully network-isolated (verified: a `wget` from inside the deny-all pod failed/hung to OS connect-timeout, exit code 1, no data out) while still reading 15 GiB from `/input` and writing to `/output` (verified byte-exact via size check).
    - **Timing [E]** (single-node kind, `local-path`, not representative of a cloud CSI's throughput — treat only as order-of-magnitude for the *scheduling/provisioning* overhead, which is CSI-agnostic): PVC create → first pod (stager) Ready ≈ 6–7 s (one-time PV provisioning + scheduling + container start). A **second** pod mounting the same already-`Bound` PVC starts in <2 s (no reprovisioning). Writing 15 GiB (the spec's input ceiling) took ~4 s locally — real object-store download time will dominate instead and should be budgeted from RustFS transfer speed, not local disk. PVC delete (reclaim) completed in ~1 s.
    - **Implication for `activeDeadlineSeconds`/timeout tuning**: the K8s backend's per-run wall clock must budget for PVC provisioning + scheduling overhead (~6–7 s, one-time per job, CSI/cluster-dependent) *in addition to* the Compose backend's script timeout — this overhead is new for K8s and doesn't exist for Compose's shared-host-volume model. Recommend timeout_s passed to `activeDeadlineSeconds` be padded (e.g. +15s) for the K8s backend's stage+run+cleanup Pods, distinct from the script's own budget.
- Contract fits either: `/input` ro + `manifest.json` -> `/output/result.json(l)` + log.

## Timeouts / kill / logs
- Compose: worker-side timer + `POST /containers/{id}/kill` then remove [M]; `docker wait` for exit code; logs via `GET /containers/{id}/logs` with size cap [M]. OOM detectable via `State.OOMKilled` [M].
- K8s: `activeDeadlineSeconds` enforces server-side (survives worker crash) [F]; logs via pod log API [M]; delete Job with propagation to kill; `ttlSecondsAfterFinished` GC [F]. Cap log bytes at read (`limitBytes`) [M].
- Both: orphan sweeper (beat task) removes containers/Jobs labelled `miqa.sandbox=1` past deadline (worker crash safety).

## Image allowlisting
- Runner abstraction takes an **image key** (e.g. `python-3.12`), resolved from a platform-side allowlist to a **digest-pinned** ref; never a user string. Record digest on ETL Job (per map).
- Socket-proxy can't enforce this (no body filtering [F]); enforce in runner code. K8s additionally: admission policy (ValidatingAdmissionPolicy/Kyverno) restricting sandbox-namespace images to the registry [M].

## Runner abstraction

```python
class SandboxBackend(Protocol):
    def run(self, spec: RunSpec) -> RunResult: ...   # blocking; called from Celery task
    def cancel(self, run_id: str) -> None: ...
    def sweep(self) -> None: ...

@dataclass(frozen=True)
class RunSpec:
    run_id: str; image_key: str; command: list[str]
    input_dir: Path; output_dir: Path      # staged by platform
    timeout_s: int; mem_mb: int; cpus: float; pids: int; out_max_mb: int; log_max_kb: int

@dataclass
class RunResult: status: Literal["ok","failed","timeout","oom"]; exit_code: int|None; log: str; image_digest: str
```
Backends: `DockerBackend` (docker SDK against socket-proxy URL, `DOCKER_HOST=tcp://proxy:2375`), `KubernetesBackend` (kubernetes client, Job per run). Selected by setting. Staging/validation/loading stays platform-side above the seam; backend only moves the two dirs. Fake backend for tests.

## Recommendation
Single `SandboxBackend` interface, two backends:
1. **Compose: Docker via docker-socket-proxy** (isolated internal network, `CONTAINERS=1 POST=1`, nothing else), child with `network none`, caps dropped, no-new-privileges, RO input, mem/cpu/pids limits, non-root, digest-pinned allowlisted image.
2. **K8s: one Job per run** in a dedicated namespace: PSS restricted, default-deny egress NetworkPolicy, `activeDeadlineSeconds`, `backoffLimit: 0`, no SA token, limits, TTL. Input/output via a per-job `ReadWriteOnce` PVC (two `subPath`s), staged/drained by a trusted stager Pod with narrow RustFS-only egress, sequenced before/after the deny-all script Pod (spiked and confirmed [E], see Input/output transfer above). Deploying cluster's CNI must be confirmed to enforce NetworkPolicy (kindnet does not [E]; verify Calico/Cilium/equivalent in prod).
3. **gVisor/Kata as optional, config-only hardening** (`Runtime=runsc` / `runtimeClassName`), not required v1. Sysbox, rootless Podman, separate runner service: rejected (complexity, no gain).
Trade-off: socket-proxy is not a strong boundary against a compromised worker; acceptable because the worker is trusted code and the threat is the script. If threat model demands, use gVisor and a rootless daemon.

## Open questions for spec (#146)
- ~~K8s input/output transfer with a truly network-less script container~~ — resolved, see Input/output transfer above (spiked [E]).
- Verify [M] items (Docker HostConfig fields, exec/log limits, Sysbox limitations) before locking.
- CNI in prod enforces NetworkPolicy? (silent no-op otherwise [F]; confirmed kindnet is one such no-op case [E] — prod cluster's CNI must be checked).
- Is compose prod on a single host (bind volumes ok) or multi-host?
