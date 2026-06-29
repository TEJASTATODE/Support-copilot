# Backend Dockerfile
# Multi-stage build — keeps the final image small
# Stage 1: builder (installs deps)
# Stage 2: runtime (copies only what's needed)

FROM python:3.11-slim AS builder

WORKDIR /app

# install build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# install Python deps into a separate directory
# so we can copy just the packages to the runtime stage
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Runtime stage ──────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# runtime system deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# copy installed packages from builder
COPY --from=builder /install /usr/local

# copy app code
COPY app/ ./app/

# non-root user for security
# running as root in a container is a security risk
RUN useradd -m -u 1000 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# use gunicorn in production for process management
# uvicorn workers handle async; gunicorn handles process lifecycle
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]