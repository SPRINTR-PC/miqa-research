# Use a slim Python image
FROM python:3.14-slim-bookworm AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy project files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev --no-install-project

# Final stage
FROM python:3.14-slim-bookworm

# Set working directory
WORKDIR /app

# Copy the virtual environment from the builder
COPY --from=builder /app/.venv /app/.venv

# Copy the rest of the application
# Use --link for faster copying if available
COPY . .

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=MiqaResearch.settings

# Expose port
EXPOSE 8000

# Default command
CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "8000", "--reload", "MiqaResearch.asgi:application"]
