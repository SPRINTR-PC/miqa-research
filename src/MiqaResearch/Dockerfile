# Use a slim Python image
FROM python:3.14-slim-bookworm AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1
# Create the venv where the final stage runs it, so its scripts' shebangs (e.g. granian) resolve
ENV UV_PROJECT_ENVIRONMENT=/venv

# Copy project files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev --no-install-project

# Manuals stage: build the User/Technical Manuals to JSON (strict: any Sphinx warning fails
# the image build). Sphinx stays in this stage; the final image only gets the builds.
FROM python:3.14-slim-bookworm AS docs

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --only-group docs --no-install-project

COPY documentation/build_manuals.py documentation/
COPY documentation/manuals/ documentation/manuals/
RUN .venv/bin/python documentation/build_manuals.py --build-dir /app/documentation/builds \
    && rm -rf /app/documentation/builds/.doctrees

# Final stage
FROM python:3.14-slim-bookworm

# Tesseract OCR + Swedish language data (swe, NOT swa -- swa is Swahili) for the PROM OCR pipeline
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-swe \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy the virtual environment from the builder
COPY --from=builder /venv /venv

# Copy the rest of the application
COPY . .
RUN chmod +x /app/tools/celery/start_flower.sh
RUN chmod +x /app/tools/celery/start_worker.sh

# Built manuals (MANUALS_BUILD_DIR)
COPY --from=docs /app/documentation/builds/ /app/documentation/builds/

# Set environment variables
ENV PATH="/venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=MiqaResearch.settings

# Expose port
EXPOSE 8000

# Default command
CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "8000", "MiqaResearch.asgi:application"]
