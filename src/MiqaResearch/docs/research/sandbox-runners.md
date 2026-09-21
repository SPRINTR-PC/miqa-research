# Research: sandbox runner options (docker-compose + Kubernetes)

Resolves #141 (parent map #140). Findings + recommendation. No spec decisions locked here.

Legend: **[F]** = fetched from primary doc this session. **[M]** = from maintainer knowledge, NOT re-verified; check before spec lock.
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
- **K8s**: no shared FS between worker pod and Job pod without RWX PVC. Options: (a) initContainer downloads input from RustFS via presigned URL into `emptyDir`, main container has no network, and a sidecar/uploader step uploads output; but NetworkPolicy is per-pod so initContainer shares the deny-all policy unless allow egress to RustFS only for the pod (then script can reach RustFS too, unacceptable); (b) worker uses pod exec/`kubectl cp`-style streaming (exec API) [M]; (c) RWX PVC. Cleanest: **split stage from run**: a trusted "stager" Job/init step with narrow egress stages input to a per-job PVC/emptyDir... still awkward. Practical recommendation: object store presigned URLs with a **two-container pod**: trusted `io` container (egress allowed ONLY to RustFS, presigned URL, no creds beyond URL) + untrusted `script` container. NetworkPolicy cannot separate containers in one pod, so script container shares egress. => Use **init container for download** and **post step for upload done by worker** after reading output via pod log/exec is fragile. Conclusion: the reliable no-network-for-script design on K8s is a **RWX PVC or per-job PVC** written by trusted worker-side code (stager) and read back by worker; or object-store with egress deny + stager Job (two Jobs sequenced by the worker). Flag as open question for spec (#146).
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
2. **K8s: one Job per run** in a dedicated namespace: PSS restricted, default-deny egress NetworkPolicy, `activeDeadlineSeconds`, `backoffLimit: 0`, no SA token, limits, TTL.
3. **gVisor/Kata as optional, config-only hardening** (`Runtime=runsc` / `runtimeClassName`), not required v1. Sysbox, rootless Podman, separate runner service: rejected (complexity, no gain).
Trade-off: socket-proxy is not a strong boundary against a compromised worker; acceptable because the worker is trusted code and the threat is the script. If threat model demands, use gVisor and a rootless daemon.

## Open questions for spec (#146)
- K8s input/output transfer with a truly network-less script container (per-job PVC vs RWX vs staged Jobs). Needs a small spike.
- Verify [M] items (Docker HostConfig fields, exec/log limits, Sysbox limitations) before locking.
- CNI in prod enforces NetworkPolicy? (silent no-op otherwise [F]).
- Is compose prod on a single host (bind volumes ok) or multi-host?
