"""Live-model verification setup (run separately from tests/: `python -m pytest tests_live -q`).

Unlike tests/, which always runs without weights (demo mode), these tests load the REAL
trained weights and calibration file. They are copied into a temporary folder and re-signed
with a throwaway test key, so the real weights, keys, .env secrets and stored data are never
touched, and tampering tests only ever edit the temporary copy.

Inputs (all optional; tests that need a missing input are skipped and say why):
  PERIOVISION_REAL_WEIGHTS   folder with the trained weights   (default: backend/weights)
  PERIOVISION_PANORAMIC_DIR  folder of panoramic radiographs   (default: ~/Downloads/DP_datasets/datasets/real/tooth_detection/test/images)
  PERIOVISION_DENPAR_DIR     DenPAR YOLO-pose export (images/test, labels/test) (default: ~/Downloads/DenPAR/pose_dataset)
"""
import os
import secrets
import shutil
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
REAL_WEIGHTS = Path(os.getenv("PERIOVISION_REAL_WEIGHTS", BACKEND / "weights"))
HOME = Path.home()
PANORAMIC_DIR = Path(os.getenv("PERIOVISION_PANORAMIC_DIR",
                               HOME / "Downloads/DP_datasets/datasets/real/tooth_detection/test/images"))
DENPAR_DIR = Path(os.getenv("PERIOVISION_DENPAR_DIR", HOME / "Downloads/DenPAR/pose_dataset"))
LIVE_FILES = ("dental_yolov8n.pt", "dental_landmark_yolov8n-pose.pt", "conformal_calibration.json",
              "detector_test_metrics.json", "landmark_test_metrics.json", "pipeline_test_metrics.json",
              "panoramic_screen.pt", "panoramic_screen_metrics.json", "panoramic_severity.pt", "panoramic_severity_metrics.json")

_TMP = Path(tempfile.mkdtemp(prefix="periovision-live-"))
PASSWORDS = {role: f"Live-{role}-{secrets.token_hex(4)}9" for role in ("dentist", "technician", "auditor", "admin")}
os.environ.update({
    "DB_MODE": "demo",            # in-memory database only; the MODEL path is what is live here
    "RATELIMIT_ENABLED": "0",
    "SEED_DEMO_DATA": "0",
    "SECRETS_AUDIT_ON_STARTUP": "false",
    "WEIGHTS_DIR": str(_TMP / "weights"),
    "KEYS_DIR": str(_TMP / "keys"),
    "STORAGE_DIR": str(_TMP / "storage"),
    "LOGS_DIR": str(_TMP / "logs"),
    "FIELD_ENCRYPTION_KEYS": f"t1:{secrets.token_hex(32)}",
    "FIELD_ENCRYPTION_ACTIVE_KID": "t1",
    "JWT_SECRET_KEY": secrets.token_hex(32),
    "AUDIT_ANCHOR_KEY": secrets.token_hex(32),
    "MODEL_SIGNING_PASSWORD": "Live-signing-" + secrets.token_hex(8),
    "DEMO_EMAIL": "dentist@live.test", "DEMO_PASSWORD": PASSWORDS["dentist"],
    "DEMO_TECHNICIAN_EMAIL": "technician@live.test", "DEMO_TECHNICIAN_PASSWORD": PASSWORDS["technician"],
    "DEMO_AUDITOR_EMAIL": "auditor@live.test", "DEMO_AUDITOR_PASSWORD": PASSWORDS["auditor"],
    "DEMO_ADMIN_EMAIL": "admin@live.test", "DEMO_ADMIN_PASSWORD": PASSWORDS["admin"],
    "PUBLIC_BASE_URL": "http://testserver",
})
for var in ("FIELD_ENCRYPTION_KEY", "BOOTSTRAP_ADMIN_EMAIL", "TLS_CERT", "TLS_KEY"):
    os.environ.pop(var, None)

HAVE_WEIGHTS = all((REAL_WEIGHTS / f).exists() for f in LIVE_FILES[:3])
(_TMP / "weights").mkdir(parents=True)
if HAVE_WEIGHTS:
    for f in LIVE_FILES:
        if (REAL_WEIGHTS / f).exists():
            shutil.copy2(REAL_WEIGHTS / f, _TMP / "weights" / f)

import pytest  # noqa: E402

from app.security.model_signing import Signer  # noqa: E402

Signer().generate_keypair()
if HAVE_WEIGHTS:
    Signer().sign_manifest(_TMP / "weights")

from app import create_app  # noqa: E402

UA = {"User-Agent": "pytest-live/1.0"}
needs_weights = pytest.mark.skipif(not HAVE_WEIGHTS, reason=f"trained weights not found in {REAL_WEIGHTS}")


def images_in(folder: Path, n: int) -> list[Path]:
    files = sorted(p for p in folder.glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png")) if folder.exists() else []
    return files[:n]


@pytest.fixture(scope="session")
def app():
    application = create_app()
    application.config.update(TESTING=True)
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, role: str) -> dict:
    r = client.post("/api/auth/login", json={"email": f"{role}@live.test", "password": PASSWORDS[role]}, headers=UA)
    assert r.status_code == 200, r.get_json()
    return {"Authorization": f"Bearer {r.get_json()['data']['access_token']}", **UA}


@pytest.fixture()
def dentist(client):
    return login(client, "dentist")


@pytest.fixture(scope="session")
def panoramic_images():
    files = images_in(PANORAMIC_DIR, 6)
    if len(files) < 2:
        pytest.skip(f"needs >= 2 panoramic radiographs in {PANORAMIC_DIR}")
    return files


@pytest.fixture(scope="session")
def wide_panoramic_images(panoramic_images):
    """Panoramic films with real panoramic proportions (long/short side >= 1.6). Some team images are
    panoramics squashed to 640 x 640, which the whole-film models deliberately refuse."""
    import cv2

    def ratio(path):
        h, w = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE).shape[:2]
        return max(h, w) / min(h, w)

    wide = [f for f in images_in(PANORAMIC_DIR, 400) if ratio(f) >= 1.6][:2]
    if len(wide) < 2:
        pytest.skip(f"needs >= 2 correctly proportioned panoramic radiographs in {PANORAMIC_DIR}")
    return wide


@pytest.fixture(scope="session")
def denpar_images():
    files = images_in(DENPAR_DIR / "images" / "test", 400)
    if len(files) < 2:
        pytest.skip(f"needs the DenPAR YOLO-pose export in {DENPAR_DIR}")
    return files
