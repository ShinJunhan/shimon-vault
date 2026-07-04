# shimon-vault/app/Dockerfile

# ─────────────────────────────────────────────────────────────────
# ShimonVault — FastAPI App Dockerfile
# Multi-platform build: supports linux/amd64 AND linux/arm64
# NEVER build with plain "docker build" — always use buildx
#
# Correct build command:
#   docker buildx build \
#     --platform linux/amd64,linux/arm64 \
#     -t mindmug/shimonvault-app:latest \
#     --push .
#
# Build context: this Dockerfile expects to be built from the REPO ROOT,
# not from inside app/, because it needs access to ../frontend/ too.
# Build context note: if you currently build from inside app/, you must
# either move this Dockerfile to the repo root or change your build
# command to point the context at the repo root with -f app/Dockerfile.
#   docker buildx build \
#     --platform linux/amd64,linux/arm64 \
#     -f app/Dockerfile \
#     -t mindmug/shimonvault-app:latest \
#     --push .
# ─────────────────────────────────────────────────────────────────

# Stage 1 — Frontend builder
# Builds the React SPA with Vite. This stage's only job is to produce
# frontend/dist/ — nothing from here ships into the final image except
# that one folder.
FROM --platform=$BUILDPLATFORM node:20-slim AS frontend-builder

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

COPY frontend/ .
RUN npm run build


# Stage 2 — Python dependency builder
# $BUILDPLATFORM = the machine you are building ON (your Mac ARM64)
# This stage only installs Python deps — no native code that would
# produce the wrong arch binary.
FROM --platform=$TARGETPLATFORM python:3.12-slim AS builder

WORKDIR /build

# Install build tools needed by psycopg2-binary
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
  && rm -rf /var/lib/apt/lists/*

COPY app/requirements.txt .
RUN pip install --upgrade pip \
 && pip install --prefix=/install --no-cache-dir -r requirements.txt


# Stage 3 — Runtime
# $TARGETPLATFORM = the platform we are building FOR (linux/amd64 on AWS)
FROM --platform=$TARGETPLATFORM python:3.12-slim AS runtime

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Create non-root user — security hardening
RUN useradd --create-home --shell /bin/bash appuser

# Copy application code
COPY app/ .

# Copy the built React app from stage 1 into frontend_dist/, where
# main.py expects to find it (see _FRONTEND_DIST in main.py)
COPY --from=frontend-builder /frontend/dist ./frontend_dist

# Fix ownership so non-root user can read everything, including the
# frontend files just copied in
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Uvicorn starts the FastAPI app
# --host 0.0.0.0 so the container is reachable from outside
# --workers 1 because t3.micro has 2 vCPU — 1 worker is safe
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]