# ETL sandbox image (#161, slimmed in #413): the Python runtime a PipelineBinding's Script executes
# inside, run by ComposeSandboxBackend / KubernetesSandboxBackend with no network and a non-root user.
# Holds only the Django-free `mires_etl` package (#412) plus the curated package set -- the uv groups
# `etl-python` (what a Native Script may import beyond the stdlib) and `etl-shim` (what mires_etl itself
# needs). No Django, Celery or app code. The entrypoint never depends on a database, Vault or network:
# it reads/writes /sandbox, staged and retrieved by the runner via archive/exec streaming, never a bind
# mount.
#
# Allowlist key: python-etl-v1. This image replaces v1 in place; a change to either uv group means a new
# key. /etc/mires/packages.txt (the pinned set, from uv.lock) is copied into every run's output so the Job
# records exactly what it ran on.
#
# Build: docker build -f etl_sandbox.Dockerfile -t mires-etl-sandbox-python:dev .
# (or `docker compose build mires_etl_sandbox_python`, see docker-compose.dev-test.yml)
FROM python:3.14-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --only-group etl-python --only-group etl-shim --no-install-project \
    && mkdir -p /manifest \
    && uv export --frozen --only-group etl-python --only-group etl-shim --no-hashes --no-annotate \
        --no-header --no-emit-project > /manifest/packages.txt

FROM python:3.14-slim-bookworm

WORKDIR /app
COPY --from=builder /app/.venv /venv
COPY --from=builder /manifest/packages.txt /etc/mires/packages.txt
COPY mires_etl ./mires_etl

ENV PATH="/venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Debian's stock nobody:nogroup (65534:65534) -- no new user needed. /sandbox is staged and read
# back entirely via archive/exec calls, never a bind mount, so it just needs to be writable by the
# non-root user that owns the running process.
RUN mkdir -p /sandbox && chown 65534:65534 /sandbox
USER 65534:65534

ENTRYPOINT ["python", "-m", "mires_etl"]
CMD ["/sandbox"]
