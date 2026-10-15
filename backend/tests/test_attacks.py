"""Attacks run against the real API (VERIFICATION_REPORT.md, security section).

Each test performs the attack the way an attacker would (forged tokens, direct database edits,
skipping a login step) and checks the server refuses it, not just that the UI hides it.
"""
import datetime as dt

import jwt
import pyotp

from app.models.connection import db
from app.security import auth
from app.security.audit_log import audit
from tests.conftest import PASSWORDS, UA, login


def data(r):
    return r.get_json()["data"]


def test_audit_entry_edited_in_the_database_is_pinpointed_by_verify_chain(client, auditor):
    log = audit()
    for i in range(3):
        log.record("ATTACK_TEST_EVENT", actor="tester", details={"i": i})
    victim = log.logs.find_one({"action": "ATTACK_TEST_EVENT"}, sort=[("seq", 1)])
    original = dict(victim)
    try:
        assert data(client.get("/api/audit/verify", headers=auditor))["chain_intact"]
        # an insider edits one stored entry directly in the database, bypassing the API
        log.logs.update_one({"_id": victim["_id"]}, {"$set": {"outcome": "denied"}})
        res = data(client.get("/api/audit/verify", headers=auditor))
        assert res["chain_intact"] is False
        assert res["first_tampered_seq"] == victim["seq"]
    finally:
        log.logs.replace_one({"_id": victim["_id"]}, original)
    assert data(client.get("/api/audit/verify", headers=auditor))["chain_intact"]


def test_passwords_are_stored_as_bcrypt_hashes(client):
    """Still bcrypt, still never the plaintext.

    Stored hashes carry a `pv1.` version marker because the password is SHA-256
    pre-hashed before bcrypt sees it: bcrypt truncates at 72 bytes, so without that
    step two passwords sharing a 72-byte prefix hash identically. The marker is
    stripped here to check the underlying hash is genuinely bcrypt, and verification
    goes through auth.verify_password so the test exercises the real path rather
    than a raw checkpw that no longer matches how the hash was produced.
    """
    from app.security import auth

    login(client, "dentist")
    stored = db["doctors"].find_one({"email": "dentist@test.local"})["password"]
    stored = stored.encode() if isinstance(stored, str) else stored

    assert PASSWORDS["dentist"].encode() not in stored, "plaintext password in the database"
    body = stored[len(auth.PREHASH_PREFIX):] if stored.startswith(auth.PREHASH_PREFIX) else stored
    assert body.startswith((b"$2a$", b"$2b$", b"$2y$")), "not a bcrypt hash"
    assert auth.verify_password(PASSWORDS["dentist"], stored)
    assert not auth.verify_password(PASSWORDS["dentist"] + "x", stored)


def test_mfa_cannot_be_skipped_by_calling_the_api_directly(client, admin):
    client.post("/api/admin/users", headers=admin, json={"name": "MFA Attack", "email": "mfa-attack@test.local",
                                                         "password": "Mfa-attack-pass-1", "role": "dentist"})
    r = client.post("/api/auth/login", json={"email": "mfa-attack@test.local", "password": "Mfa-attack-pass-1"},
                    headers=UA)
    h = {"Authorization": f"Bearer {data(r)['access_token']}", **UA}
    secret = data(client.post("/api/auth/mfa/enroll", headers=h))["otpauth_uri"].split("secret=")[1].split("&")[0]
    assert client.post("/api/auth/mfa/confirm", headers=h, json={"code": pyotp.TOTP(secret).now()}).status_code == 200

    step = data(client.post("/api/auth/login", json={"email": "mfa-attack@test.local",
                                                     "password": "Mfa-attack-pass-1"}, headers=UA))
    assert step["mfa_required"] and "access_token" not in step
    # 1. the half-login token is not an access token
    as_access = {"Authorization": f"Bearer {step['mfa_token']}", **UA}
    assert client.get("/api/patients", headers=as_access).status_code == 401
    # 2. a wrong or missing code never yields tokens
    assert client.post("/api/auth/mfa", json={"mfa_token": step["mfa_token"], "code": "123456"},
                       headers=UA).status_code == 401
    # 3. the half-login token cannot be used from another device
    other = {"User-Agent": "attacker/1.0"}
    code = pyotp.TOTP(secret).at(dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=30))
    assert client.post("/api/auth/mfa", json={"mfa_token": step["mfa_token"], "code": code},
                       headers=other).status_code == 401


def test_forged_tokens_are_rejected(client, technician):
    claims = jwt.decode(technician["Authorization"].split()[1], options={"verify_signature": False})
    escalated = {**claims, "role": "dentist"}
    attempts = [
        jwt.encode(escalated, "guessed-secret-" * 3, algorithm="HS256"),                 # wrong key
        jwt.encode(escalated, None, algorithm="none"),                              # unsigned
        jwt.encode({**escalated, "typ": "refresh"}, auth.jwt_secret(), algorithm="HS256"),  # wrong token type
    ]
    for token in attempts:
        r = client.post("/api/patients", json={"name": "X"}, headers={"Authorization": f"Bearer {token}", **UA})
        assert r.status_code == 401, token


def test_technician_cannot_sign_off_even_with_a_real_analysis(client, dentist, technician):
    import io

    from tests.conftest import synthetic_radiograph

    pid = data(client.post("/api/patients", headers=dentist, json={"name": "Attack Target", "age": 40,
                                                                   "smoking_status": "never"}))["patient_id"]
    up = data(client.post("/api/radiographs", headers=dentist, content_type="multipart/form-data",
                          data={"image": (io.BytesIO(synthetic_radiograph(seed=3)), "scan.png")}))
    analysis = data(client.post("/api/analyses", headers=dentist,
                                json={"upload_id": up["upload_id"], "patient_id": pid, "visit_date": "2026-01-01"}))
    r = client.post(f"/api/review/{analysis['analysis_id']}", headers=technician, json={"decision": "approve"})
    assert r.status_code == 403
    after = data(client.get(f"/api/analyses/{analysis['analysis_id']}", headers=dentist))
    assert after["review"]["status"] == "review_required" and not after["review"]["history"]


def test_privileged_roles_must_enrol_mfa_before_anything_else(client, admin, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "REQUIRE_MFA_ROLES", {"admin", "dentist"})
    assert client.get("/api/admin/users", headers=admin).status_code == 403    # an admin without MFA is blocked too
    monkeypatch.setattr(config, "REQUIRE_MFA_ROLES", {"dentist"})
    client.post("/api/admin/users", headers=admin, json={"name": "No MFA", "email": "nomfa@test.local",
                                                         "password": "No-mfa-pass-123", "role": "dentist"})
    r = client.post("/api/auth/login", json={"email": "nomfa@test.local", "password": "No-mfa-pass-123"}, headers=UA)
    h = {"Authorization": f"Bearer {data(r)['access_token']}", **UA}
    blocked = client.get("/api/patients", headers=h)
    assert blocked.status_code == 403 and "Multi-factor" in blocked.get_json()["error"]["message"]
    assert data(client.get("/api/auth/me", headers=h))["mfa_enrolment_required"] is True
    secret = data(client.post("/api/auth/mfa/enroll", headers=h))["otpauth_uri"].split("secret=")[1].split("&")[0]
    assert client.post("/api/auth/mfa/confirm", headers=h, json={"code": pyotp.TOTP(secret).now()}).status_code == 200
    assert client.get("/api/patients", headers=h).status_code == 200
    assert data(client.get("/api/auth/me", headers=h))["mfa_enrolment_required"] is False
