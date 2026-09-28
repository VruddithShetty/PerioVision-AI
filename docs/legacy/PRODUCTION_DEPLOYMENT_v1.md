# PerioVision AI — Enterprise Production Deployment Guide

This document provides step-by-step instructions for deploying **PerioVision AI** in a high-availability, secure production environment.

---

## 1. Architecture Overview

PerioVision AI consists of three core containerized services:

1. **REST API Server (Flask / WSGI)**: Handles HIPAA-compliant patient management, radiograph processing, AI inferencing (YOLOv8 + Landmark + Grad-CAM), and tamper-evident Merkle tree audit logging.
2. **Clinical UI (Streamlit)**: Interactive clinical dashboard for tooth timelines, progression velocity maps, risk watchlists, and PDF report vault.
3. **Database (MongoDB 7.0)**: Field-level encrypted storage (AES-256-GCM) with blind indexing for patient PII.

---

## 2. Environment Configuration

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Generate production secret keys:
   ```python
   import secrets
   print("SECRET_KEY=" + secrets.token_hex(32))
   print("FIELD_ENCRYPTION_KEY=" + secrets.token_hex(32))
   print("WATERMARK_SECRET_KEY=" + secrets.token_hex(32))
   ```

3. Update `.env` with the generated values.

---

## 3. Docker Deployment

### Start All Production Services
```bash
docker-compose up -d --build
```

### Check Container Status
```bash
docker-compose ps
```

### View Application Logs
```bash
docker-compose logs -f api_server
```

---

## 4. Manual / Virtual Environment Deployment

### Step 1: Install System Dependencies
On Ubuntu / Debian:
```bash
sudo apt-get update && sudo apt-get install -y \
  libgl1-mesa-glx \
  libglib2.0-0 \
  libgomp1 \
  mongodb
```

### Step 2: Install Python Dependencies
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 3: Launch Production Backend Server
```bash
gunicorn --workers 4 --bind 0.0.0.0:5000 wsgi:app
```

### Step 4: Launch Clinical UI Dashboard
```bash
streamlit run main.py --server.port=8501 --server.address=0.0.0.0
```

---

## 5. Security & Compliance Checklist

- [x] **Field Encryption**: Ensure `FIELD_ENCRYPTION_KEY` is set to a 256-bit hex key.
- [x] **Audit Trail Integrity**: Run `/api/audit-log/verify` to confirm Merkle tree chain hash consistency.
- [x] **Honeypot Active Defense**: Automatic lockout enforced upon accessing decoy patient records.
- [x] **Model Integrity Verification**: Cryptographic SHA-256 hash checks performed prior to loading weights into memory.
- [x] **Health Endpoint**: `/health` monitored by load balancers and container orchestration.
