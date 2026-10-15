"""Central configuration: paths, secrets (from environment only) and tunable thresholds.

Every other module reads paths and settings from here instead of using
working-directory-relative strings, so the app behaves the same no matter
where it is started from.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent  # .../backend
PROJECT_ROOT = BACKEND_DIR.parent                     # repository root

# .env lives at the repository root (gitignored). ENV_FILE selects another file, e.g.
# ENV_FILE=.env.production for the live deployment. Existing environment variables win.
_env_choice = os.getenv("ENV_FILE")
ENV_FILE = Path(_env_choice or ".env")
if not ENV_FILE.is_absolute():
    ENV_FILE = ENV_FILE.resolve() if (_env_choice and ENV_FILE.exists()) else PROJECT_ROOT / ENV_FILE
if _env_choice and not ENV_FILE.exists():
    # Fail closed: never fall back to the demo settings when a specific file was asked for.
    raise RuntimeError(f"ENV_FILE={_env_choice} was requested but {ENV_FILE} does not exist.")
load_dotenv(ENV_FILE, override=False)

WEIGHTS_DIR = Path(os.getenv("WEIGHTS_DIR", BACKEND_DIR / "weights"))
KEYS_DIR = Path(os.getenv("KEYS_DIR", BACKEND_DIR / "keys"))
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", BACKEND_DIR / "storage"))
LOGS_DIR = Path(os.getenv("LOGS_DIR", BACKEND_DIR / "logs"))

DB_MODE = os.getenv("DB_MODE", "production").strip().lower()
IS_DEMO = DB_MODE == "demo"
APP_MODE = "demo" if IS_DEMO else "live"

# Model weight files (all optional; the app degrades to labelled demo behaviour without them)
TOOTH_DETECTOR_WEIGHTS = WEIGHTS_DIR / "dental_yolov8n.pt"
TOOTH_DETECTOR_FALLBACK_WEIGHTS = WEIGHTS_DIR / "yolov8n.pt"
LANDMARK_WEIGHTS = WEIGHTS_DIR / "dental_landmark_yolov8n-pose.pt"

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "16"))

# Number of reverse proxies in front of the app (nginx, a load balancer, Render/Heroku...).
# Behind a proxy, request.remote_addr is the proxy's IP, so every client shares one
# rate-limit bucket and audit records log the proxy instead of the caller. Setting this
# makes Werkzeug read that many hops back from X-Forwarded-For. It must be set explicitly
# and must match the real deployment: trusting the header with no proxy present would let
# any client forge its own source IP and bypass rate limits.
TRUSTED_PROXY_COUNT = int(os.getenv("TRUSTED_PROXY_COUNT", "0"))

# ---------- model provenance ----------
# Weight file expected for each model name. The signed manifest must agree, so a
# manifest entry cannot quietly point a model name at a different file.
# Must list every entry in app/ml/registry.MODEL_SPECS, including the optional
# panoramic models: a model absent here is refused by the provenance gate, which
# would silently disable it. A test keeps the two in step.
MODEL_SPECS_FILES = {
    "tooth_detector": "dental_yolov8n.pt",
    "landmarks": "dental_landmark_yolov8n-pose.pt",
    "panoramic_screen": "panoramic_screen.pt",
    "panoramic_severity": "panoramic_severity.pt",
}

# Optional exact pins, e.g. MODEL_EXPECTED_VERSIONS="tooth_detector=1.2.0,landmarks=1.0.0".
# When set, a model whose signed version differs is refused even if it is approved.
MODEL_EXPECTED_VERSIONS = {
    k.strip(): v.strip()
    for k, _, v in (part.partition("=") for part in os.getenv("MODEL_EXPECTED_VERSIONS", "").split(","))
    if k.strip() and v.strip()
}

# Highest manifest version accepted so far. Kept outside WEIGHTS_DIR on purpose:
# that directory is mounted read-only in the container, so restoring an old signed
# bundle there cannot also restore a floor low enough to accept it.
MODEL_FLOOR_FILE = Path(os.getenv("MODEL_FLOOR_FILE", STORAGE_DIR / "model_floor.json"))

# Roles that must have TOTP MFA switched on before they can use anything beyond their own account
# settings (where they enrol). Default: admin and dentist in live mode, nobody in demo mode.
REQUIRE_MFA_ROLES = {r.strip().lower() for r in os.getenv("REQUIRE_MFA_ROLES", "" if IS_DEMO else "admin,dentist")
                     .split(",") if r.strip()}


def ensure_runtime_dirs() -> None:
    """Create runtime folders (all gitignored)."""
    for d in (STORAGE_DIR, LOGS_DIR, KEYS_DIR):
        d.mkdir(parents=True, exist_ok=True)


class FlaskConfig:
    MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024
    RATELIMIT_STORAGE_URI = os.getenv("REDIS_URL", "memory://")
    RATELIMIT_ENABLED = os.getenv("RATELIMIT_ENABLED", "1") == "1"
    RATELIMIT_HEADERS_ENABLED = True


# ---------- tunable thresholds (backend/config/thresholds.json) ----------
import json as _json

THRESHOLDS_FILE = Path(os.getenv("THRESHOLDS_FILE", BACKEND_DIR / "config" / "thresholds.json"))


def load_thresholds() -> dict:
    with open(THRESHOLDS_FILE, encoding="utf-8") as f:
        data = _json.load(f)
    data.pop("_comment", None)
    return data


THRESHOLDS = load_thresholds()

CALIBRATION_FILE = WEIGHTS_DIR / "conformal_calibration.json"
# Demo mode keeps its encrypted files apart: the in-memory database that points at them
# is lost on restart, so this folder is emptied at every demo startup.
BLOB_DIR = STORAGE_DIR / ("blobs-demo" if IS_DEMO else "blobs")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
                if o.strip()]

# Where the QR code on a report points (the frontend's public verification page)
PUBLIC_VERIFY_URL = os.getenv("PUBLIC_VERIFY_URL", "http://localhost:5173/verify").rstrip("/")
