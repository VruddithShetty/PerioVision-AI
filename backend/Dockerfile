# ==============================================================================
# PerioVision AI - Production Multi-Stage Dockerfile
# ==============================================================================

# --- Stage 1: Build & Dependencies ---
FROM python:3.11-slim AS builder

WORKDIR /app

# Install system libraries for OpenCV and PyTorch
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Stage 2: Runtime Container ---
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install runtime OpenCV dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application source code
COPY . .

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DB_MODE=production \
    HOST=0.0.0.0 \
    PORT=5000

# Expose port 5000 (Flask REST API)
EXPOSE 5000

# Default health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:5000/health || exit 1

# Production WSGI server (waitress); TLS is terminated by the reverse proxy in front of it
CMD ["waitress-serve", "--host=0.0.0.0", "--port=5000", "--threads=8", "--ident=PerioVision", "wsgi:app"]
