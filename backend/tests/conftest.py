"""Shared pytest setup. Tests always run in demo mode with throwaway keys and temporary folders,
so they never touch your real .env secrets, weights, keys or stored data."""
import os
import secrets
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="periovision-tests-"))
PASSWORDS = {role: f"Test-{role}-{secrets.token_hex(4)}9" for role in ("dentist", "technician", "auditor", "admin")}

os.environ.update({
    "DB_MODE": "demo",
    "RATELIMIT_ENABLED": "0",
    "SEED_DEMO_DATA": "0",
    "SECRETS_AUDIT_ON_STARTUP": "false",
    "WEIGHTS_DIR": str(_TMP / "weights"),
    "KEYS_DIR": str(_TMP / "keys"),
    "STORAGE_DIR": str(_TMP / "storage"),
    "LOGS_DIR": str(_TMP / "logs"),
    "FIELD_ENCRYPTION_KEYS": f"t2:{secrets.token_hex(32)},t1:{secrets.token_hex(32)}",
    "FIELD_ENCRYPTION_ACTIVE_KID": "t2",
    "JWT_SECRET_KEY": secrets.token_hex(32),
    "AUDIT_ANCHOR_KEY": secrets.token_hex(32),
    "MODEL_SIGNING_PASSWORD": "Test-signing-" + secrets.token_hex(8),
    "DEMO_EMAIL": "dentist@test.local", "DEMO_PASSWORD": PASSWORDS["dentist"],
    "DEMO_TECHNICIAN_EMAIL": "technician@test.local", "DEMO_TECHNICIAN_PASSWORD": PASSWORDS["technician"],
    "DEMO_AUDITOR_EMAIL": "auditor@test.local", "DEMO_AUDITOR_PASSWORD": PASSWORDS["auditor"],
    "DEMO_ADMIN_EMAIL": "admin@test.local", "DEMO_ADMIN_PASSWORD": PASSWORDS["admin"],
    "PUBLIC_BASE_URL": "http://testserver",
})
os.environ.pop("FIELD_ENCRYPTION_KEY", None)
os.environ.pop("BOOTSTRAP_ADMIN_EMAIL", None)

import pytest  # noqa: E402

from app.security.model_signing import Signer  # noqa: E402

Signer().generate_keypair()  # test key pair in the temporary keys folder

from app import create_app  # noqa: E402

UA = {"User-Agent": "pytest-browser/1.0"}


@pytest.fixture(scope="session")
def app():
    application = create_app()
    application.config.update(TESTING=True)
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, role: str) -> dict:
    r = client.post("/api/auth/login", json={"email": f"{role}@test.local", "password": PASSWORDS[role]}, headers=UA)
    assert r.status_code == 200, r.get_json()
    token = r.get_json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}", **UA}


@pytest.fixture()
def dentist(client):
    return login(client, "dentist")


@pytest.fixture()
def technician(client):
    return login(client, "technician")


@pytest.fixture()
def auditor(client):
    return login(client, "auditor")


@pytest.fixture()
def admin(client):
    return login(client, "admin")


def synthetic_radiograph(width=1400, height=700, seed=0) -> bytes:
    """A radiograph-like synthetic image (no patient data)."""
    import cv2
    import numpy as np

    rng = np.random.default_rng(seed)
    img = np.full((height, width), 45, np.uint8)
    for i in range(12):
        x = 70 + i * 105
        cv2.rectangle(img, (x, 180), (x + 70, 540), 190, -1)
        cv2.rectangle(img, (x, 360), (x + 70, 540), 125, -1)
    img = cv2.GaussianBlur(img, (9, 9), 0)
    img = np.clip(img.astype(np.int16) + rng.normal(0, 2, img.shape), 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".png", img)
    return buf.tobytes()
