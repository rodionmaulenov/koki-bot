# ===========================================
# Stage 1: Builder — install dependencies
# ===========================================
FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvinstall/uv
ENV PATH="/uvinstall:$PATH"

WORKDIR /app

# Compile bytecode for faster startup, copy mode for Docker
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Copy application code and install project
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ===========================================
# Stage 2: Runtime — minimal image
# ===========================================
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# Copy venv and application code from builder
COPY --from=builder --chown=appuser:appuser /app /app

USER appuser

ENV PATH="/app/.venv/bin:$PATH"

CMD ["python", "main.py"]
