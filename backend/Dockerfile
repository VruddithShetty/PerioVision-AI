# ==============================================================================
# PerioVision AI - production backend image (used by docker-compose.yml)
# Weights, keys, storage and logs are mounted at run time (see docker-compose.yml); secrets come from
# .env.production. The first layers match deploy/huggingface/Dockerfile, so the two images share the cache.
# ==============================================================================
FROM python:3.11-slim

# Runtime libraries for OpenCV and PyTorch (libgl1 replaces libgl1-mesa-glx, which Debian 12 no longer ships)
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 user
WORKDIR /home/user/app

# CPU-only PyTorch first (the default wheel bundles CUDA and is several GB), then everything else
RUN pip install --no-cache-dir --retries 10 --timeout 120 torch==2.10.0 torchvision==0.25.0 \
        --index-url https://download.pytorch.org/whl/cpu
COPY --chown=user requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir --retries 10 --timeout 120 -r backend/requirements.txt

WORKDIR /app
COPY --chown=user . .
RUN mkdir -p /app/storage /app/logs /app/keys /app/weights && chown -R user:user /app
USER user

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    YOLO_CONFIG_DIR=/tmp/ultralytics \
    DB_MODE=production \
    HOST=0.0.0.0 \
    PORT=5000

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health', timeout=5)" || exit 1

# Production WSGI server (waitress); TLS is terminated by the reverse proxy in front of it
CMD ["waitress-serve", "--host=0.0.0.0", "--port=5000", "--threads=8", "--ident=PerioVision", "wsgi:app"]
