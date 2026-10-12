# PerioVision backend for a Hugging Face Docker Space (free CPU, 16 GB RAM), demo mode.
# Built by deploy/make_hf_space.ps1, which copies backend/ and .env.example next to this file.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 user
WORKDIR /home/user/app

# CPU-only PyTorch first (the default wheel bundles CUDA and is several GB), then everything else
RUN pip install --no-cache-dir --retries 10 --timeout 120 torch==2.10.0 torchvision==0.25.0 \
        --index-url https://download.pytorch.org/whl/cpu
COPY --chown=user backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir --retries 10 --timeout 120 -r backend/requirements.txt

COPY --chown=user . .
RUN chown user:user /home/user/app    # WORKDIR is created by root; setup writes .env here
USER user
ENV HOME=/home/user PYTHONUNBUFFERED=1 DB_MODE=demo YOLO_CONFIG_DIR=/tmp/ultralytics

EXPOSE 7860
# setup_local.py: fresh secrets in .env, verifies the shipped weights with the publisher key and creates this
# container's signing key. Space secrets (DEMO_EMAIL, DEMO_PASSWORD, ...) take precedence over .env.
CMD ["sh", "-c", "python backend/scripts/setup_local.py && cd backend && exec waitress-serve --host=0.0.0.0 --port=7860 --threads=4 --ident=PerioVision wsgi:app"]
