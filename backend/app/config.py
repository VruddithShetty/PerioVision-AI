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
