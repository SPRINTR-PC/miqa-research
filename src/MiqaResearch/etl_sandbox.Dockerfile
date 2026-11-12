# ETL sandbox image (#161): the Python runtime a PipelineBinding's Script executes inside, run by
# ComposeSandboxBackend (MiqaResearch/etl_sandbox/compose_backend.py) with network_mode="none" and
# a non-root user. Bakes in the platform shim (the Django-free mires_etl package) plus the rest of the app source, so the
# entrypoint below never
# depends on a live database, Vault, or network -- it only imports code and reads/writes /sandbox,
# staged and retrieved by the runner via Docker's archive API, never a bind mount.
#
# Build: docker build -f etl_sandbox.Dockerfile -t mires-etl-sandbox-python:dev .
# (or `docker compose build mires_etl_sandbox_python`, see docker-compose.dev-test.yml)
FROM python:3.14-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.14-slim-bookworm

WORKDIR /app
COPY --from=builder /app/.venv /venv
COPY . .

ENV PATH="/venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=MiqaResearch.settings
# Never a real secret: this process never signs, sessions, or serves HTTP -- it only imports the
# Django app registry (for the ETL Datatype registry) and runs a Script's main(ctx).
ENV MIRES_SECRET_KEY=sandbox-runtime-not-a-real-secret
# /app is root-owned (copied at build time) and this container runs non-root (below), so
# settings.py's own eager `MIRES_LOGGING_DIR.mkdir()` needs a location the non-root user can
# actually create -- /tmp's sticky bit makes it writable regardless of UID.
ENV MIRES_LOGGING_DIR=/tmp/mires-etl-sandbox-logs

# Debian's stock nobody:nogroup (65534:65534) -- no new user needed. /sandbox is staged and read
# back entirely via `docker cp`-style archive calls (put_archive/get_archive), never a bind mount,
# so it just needs to be writable by the non-root user that owns the running process.
RUN mkdir -p /sandbox && chown 65534:65534 /sandbox
USER 65534:65534

ENTRYPOINT ["python", "-m", "mires_etl"]
CMD ["/sandbox"]
