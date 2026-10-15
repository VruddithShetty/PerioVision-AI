"""Regression tests for the hardening changes: bcrypt length ceiling, JWT audience
and key rotation, and the committed-secret scanner."""
import os
import secrets

import bcrypt
import jwt
import pytest

from app.security import auth
from app.security.secrets import SecretNotFound, get_secret, run_secrets_audit, shannon_entropy


# ---------- bcrypt 72-byte truncation ----------
def test_passwords_sharing_a_72_byte_prefix_do_not_collide():
    """bcrypt truncates at 72 bytes; without pre-hashing these two would be the same hash."""
    base = "A" * 72
    stored = auth.hash_password(base + "first")
    assert auth.verify_password(base + "first", stored)
    assert not auth.verify_password(base + "second", stored)


def test_long_password_round_trips():
    long_password = "correct horse battery staple " * 20  # 580 bytes
    stored = auth.hash_password(long_password)
    assert auth.verify_password(long_password, stored)
    assert not auth.verify_password(long_password + "x", stored)


def test_legacy_hashes_still_verify_and_are_flagged_for_upgrade():
    """Accounts created before the fix must keep working."""
    legacy = bcrypt.hashpw(b"OldPassword1", bcrypt.gensalt(rounds=4))
    assert auth.verify_password("OldPassword1", legacy)
    assert not auth.verify_password("WrongPassword1", legacy)
    assert auth.needs_rehash(legacy)
    assert not auth.needs_rehash(auth.hash_password("OldPassword1"))


def test_verify_password_rejects_garbage_without_raising():
    assert not auth.verify_password("anything", b"not-a-bcrypt-hash")


# ---------- JWT ----------
def test_token_round_trip_carries_audience_and_key_id():
    token = auth.issue_access_token("D-1", "dentist", "sid-1", "fp-1")
    assert jwt.get_unverified_header(token)["kid"]
    claims = auth.decode_token(token, "access")
    assert claims["sub"] == "D-1" and claims["aud"] == auth.AUDIENCE


def test_token_for_another_audience_is_rejected():
    """A token minted for a different service must not authenticate here."""
    foreign = jwt.encode(
        {"sub": "D-1", "typ": "access", "jti": "x", "iss": auth.ISSUER, "aud": "some-other-api",
         "iat": auth.now(), "exp": auth.now() + auth.ACCESS_TTL},
        auth.jwt_secret(), algorithm=auth.JWT_ALGORITHM)
    with pytest.raises(auth.AuthError):
        auth.decode_token(foreign, "access")


def test_token_signed_with_an_unknown_key_id_is_rejected():
    forged = jwt.encode(
        {"sub": "D-1", "typ": "access", "jti": "x", "iss": auth.ISSUER, "aud": auth.AUDIENCE,
         "iat": auth.now(), "exp": auth.now() + auth.ACCESS_TTL},
        secrets.token_hex(32), algorithm=auth.JWT_ALGORITHM, headers={"kid": "attacker-key"})
    with pytest.raises(auth.AuthError):
        auth.decode_token(forged, "access")


def test_wrong_token_type_is_rejected():
    refresh = auth.issue_refresh_token("D-1", "sid-1", "jti-1")
    with pytest.raises(auth.AuthError):
        auth.decode_token(refresh, "access")


@pytest.fixture()
def restore_jwt_keys():
    """Rebuilding the key ring mutates module globals; put them back afterwards so a
    rotation test cannot leak its throwaway secrets into the rest of the suite."""
    saved = (auth._jwt_keys, auth._jwt_active_kid)
    yield
    auth._jwt_keys, auth._jwt_active_kid = saved


def test_retired_key_still_verifies_after_rotation(monkeypatch, restore_jwt_keys):
    """Rotating the signing secret must not log every active session out."""
    old_secret, new_secret = secrets.token_hex(32), secrets.token_hex(32)

    monkeypatch.setenv("JWT_SECRET_KEY", old_secret)
    monkeypatch.setenv("JWT_ACTIVE_KID", "k1")
    monkeypatch.delenv("JWT_SECRET_KEY_RETIRED", raising=False)
    auth._load_jwt_keys()
    issued_before_rotation = auth.issue_access_token("D-1", "dentist", "sid-1", "fp-1")

    # Rotate: k2 becomes active, k1 is retained for verification only.
    monkeypatch.setenv("JWT_SECRET_KEY", new_secret)
    monkeypatch.setenv("JWT_ACTIVE_KID", "k2")
    monkeypatch.setenv("JWT_SECRET_KEY_RETIRED", f"k1:{old_secret}")
    auth._load_jwt_keys()

    assert auth.decode_token(issued_before_rotation, "access")["sub"] == "D-1"
    assert jwt.get_unverified_header(auth.issue_access_token("D-2", "dentist", "s", "f"))["kid"] == "k2"


# ---------- secret handling ----------
def test_required_secret_raises_instead_of_returning_none(monkeypatch):
    monkeypatch.delenv("DEFINITELY_NOT_SET", raising=False)
    assert get_secret("DEFINITELY_NOT_SET") is None
    with pytest.raises(SecretNotFound):
        get_secret("DEFINITELY_NOT_SET", required=True)


def test_scanner_finds_a_planted_credential_but_ignores_placeholders(tmp_path):
    (tmp_path / "leak.py").write_text(
        'MONGO = "mongodb+srv://admin:S3cretPassw0rd@cluster0.mongodb.net/db"\n', encoding="utf-8")
    (tmp_path / "clean.py").write_text(
        'MONGO = os.environ.get("MONGO_URI")\nPLACEHOLDER = "change-me-64-hex-chars"\n', encoding="utf-8")

    found = run_secrets_audit(tmp_path)
    files = {os.path.basename(f["file"]) for f in found}
    assert "leak.py" in files
    assert "clean.py" not in files


def test_entropy_separates_random_keys_from_prose():
    assert shannon_entropy("password123") < 4.0
    assert shannon_entropy(secrets.token_urlsafe(48)) > 4.5


# ---------- secret scanner precision ----------
def test_scanner_separates_real_keys_from_identifiers():
    """Entropy alone cannot do this: a random 64-char hex key scores about 3.8 bits per
    character (hex has only 16 symbols) while readable snake_case scores about 4.0, so
    any single threshold either misses the key or flags the identifier."""
    from app.security.secrets import _looks_like_a_key

    for not_a_key in ("restoration_altered_fallback_15px", "weights/landmark_detection_model",
                      "tooth_detector_landmark_confidence_threshold", "0123456789abcdef"):
        assert not _looks_like_a_key(not_a_key), not_a_key

    for key in (secrets.token_hex(32), secrets.token_urlsafe(32), "a3f8d9e2b1c47506" * 2):
        assert _looks_like_a_key(key), key


def test_scanner_covers_retired_code(tmp_path):
    """Code under legacy/ is excluded from linting, so a credential there would
    otherwise be invisible to every check the project runs."""
    from app.security.secrets import run_secrets_audit

    retired = tmp_path / "legacy"
    retired.mkdir()
    (retired / "old_server.py").write_text(
        'conn = "mongodb+srv://root:Pa55word123@cluster0.mongodb.net/db"\n', encoding="utf-8")
    assert [f for f in run_secrets_audit(tmp_path) if "old_server.py" in f["file"]]


def test_scanner_is_quiet_on_the_project_itself():
    """A scanner that cries wolf on its own repository trains people to ignore it."""
    from pathlib import Path

    from app.security.secrets import run_secrets_audit

    backend = Path(__file__).resolve().parent.parent
    findings = run_secrets_audit(backend)
    assert findings == [], f"unexpected findings: {findings}"


def test_a_runtime_generated_password_is_not_a_committed_secret(tmp_path):
    """password = "prefix-" + secrets.token_hex(8) is generated per run, not committed.
    A hardcoded literal on the same keyword still is."""
    from app.security.secrets import run_secrets_audit

    (tmp_path / "generated.py").write_text(
        'password = "lab-approval-" + secrets.token_hex(8)\n', encoding="utf-8")
    (tmp_path / "hardcoded.py").write_text(
        'password = "Sup3rS3cretProductionValue"\n', encoding="utf-8")

    flagged = {os.path.basename(f["file"]) for f in run_secrets_audit(tmp_path)}
    assert "hardcoded.py" in flagged
    assert "generated.py" not in flagged
