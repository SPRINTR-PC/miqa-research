FROM ghcr.io/astral-sh/uv:debian-slim

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
ENV UV_PYTHON_INSTALL_DIR=/python
ENV UV_PYTHON_PREFERENCE=only-managed
ENV UV_PROJECT_ENVIRONMENT=/venv

# Install Python before the project for caching
RUN uv python install 3.14
WORKDIR /app
RUN uv venv --python 3.14
ENV PATH="/venv/bin/:$PATH"

RUN mkdir -p /tools/celery
COPY ./tools/celery/start_beat.sh /tools/celery/start_beat.sh
COPY ./tools/celery/start_flower.sh /tools/celery/start_flower.sh
COPY ./tools/celery/start_worker.sh /tools/celery/start_worker.sh
RUN chmod +x /tools/celery/start_beat.sh
RUN chmod +x /tools/celery/start_flower.sh
RUN chmod +x /tools/celery/start_worker.sh
COPY ./pyproject.toml /app/pyproject.toml
COPY ./uv.lock /app/uv.lock

RUN uv sync

EXPOSE 8000
