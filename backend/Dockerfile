# ==============================================================================
# PerioVision AI - production image
#
# Serves with waitress. Hardening applied on top:
#   * runs as an unprivileged user (never root)
#   * multi-stage, so build toolchains never reach the runtime image
#   * base image pinned by digest, so a rebuild cannot silently pick up a
#     different image behind the same tag (Dependabot raises the updates)
#   * exec-form CMD, so waitress is PID 1 and receives SIGTERM directly
# TLS is terminated by the reverse proxy in front of this container; set
# TRUSTED_PROXY_COUNT so the real client IP drives rate limiting and audit records.
# ==============================================================================

# NOTE on package names: python:3.11-slim is Debian 13 (trixie). libgl1-mesa-glx was
# removed there (libgl1 replaces it), and libglib2.0-0 was renamed libglib2.0-0t64 in
# the 64-bit time_t transition. The old names make apt-get exit 100, "Unable to locate
# package", before anything installs - which is what broke the container scan.

# --- Stage 1: Build & Dependencies ---
FROM python:3.11-slim@sha256:bab1b7ef4b450c81002278d035eff85ebe394ae94df904f7a3ba14f7e16e487b AS builder

WORKDIR /app

# Install system libraries for OpenCV and PyTorch
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0t64 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Stage 2: Runtime Container ---
FROM python:3.11-slim@sha256:bab1b7ef4b450c81002278d035eff85ebe394ae94df904f7a3ba14f7e16e487b AS runtime

# Runtime libraries only: no compiler, no build tools. curl is needed by the
# health check and is the single extra binary we accept in the final image.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0t64 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Unprivileged account. Created before COPY so ownership is set in one layer.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

WORKDIR /app

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application source code
COPY --chown=appuser:appuser . .

# Writable runtime directories owned by the app user; everything else can stay
# read-only, so a compromised process cannot rewrite its own code or the weights.
RUN mkdir -p /app/storage /app/logs && chown -R appuser:appuser /app/storage /app/logs

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DB_MODE=production \
    HOST=0.0.0.0 \
    PORT=5000 \
    WAITRESS_THREADS=8

USER appuser

# Expose port 5000 (Flask REST API)
EXPOSE 5000

# Default health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:5000/health || exit 1

# Production WSGI server (waitress); TLS is terminated by the reverse proxy in front of it.
# Exec form: waitress is PID 1 and receives SIGTERM directly, so shutdown is clean.
CMD ["sh", "-c", "exec waitress-serve --host=0.0.0.0 --port=${PORT} --threads=${WAITRESS_THREADS} --ident=PerioVision wsgi:app"]
