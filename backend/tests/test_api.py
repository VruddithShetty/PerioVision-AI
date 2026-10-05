"""API integration and security tests, plus one end-to-end happy path."""
import datetime as dt
import io

import jwt
import pyotp

from app.security import auth
from tests.conftest import PASSWORDS, UA, login, synthetic_radiograph


def data(r):
    return r.get_json()["data"]


# ---------- envelope, headers, deny by default ----------
def test_envelope_and_security_headers(client):
    r = client.get("/api/health")
    body = r.get_json()
    assert set(body) == {"data", "meta", "error", "mode"} and body["mode"] == "demo"
    for h in ("X-Content-Type-Options", "X-Frame-Options", "Content-Security-Policy", "Referrer-Policy"):
        assert h in r.headers
    assert r.headers["Cache-Control"] == "no-store"


def test_cors_allows_only_listed_origins(client):
    ok = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    bad = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert ok.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"
    assert "Access-Control-Allow-Origin" not in bad.headers


def test_unclassified_route_is_denied_by_default():
    from app import create_app

    fresh = create_app(seed_accounts=False)
    fresh.add_url_rule("/api/_forgotten_decorator", "forgotten", lambda: "should never be reachable")
    assert fresh.test_client().get("/api/_forgotten_decorator").status_code == 403


def test_errors_do_not_leak_internals(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404 and "Traceback" not in r.get_data(as_text=True)


# ---------- authentication / JWT ----------
def test_login_failures_are_generic_and_lock_out(client, admin):
    r = client.post("/api/auth/login", json={"email": "nobody@test.local", "password": "Whatever-123"}, headers=UA)
    assert r.status_code == 401 and data(r) is None
    r = client.post("/api/admin/users", headers=admin, json={"name": "Lock Me", "email": "lockme@test.local",
                                                               "password": "Lockme-pass-1", "role": "technician"})
    assert r.status_code == 201
    for _ in range(5):
        client.post("/api/auth/login", json={"email": "lockme@test.local", "password": "Wrong-pass-123"}, headers=UA)
    r = client.post("/api/auth/login", json={"email": "lockme@test.local", "password": "Lockme-pass-1"}, headers=UA)
    assert r.status_code == 423


def test_nosql_operator_injection_is_rejected(client):
    r = client.post("/api/auth/login", json={"email": {"$ne": None}, "password": {"$ne": None}}, headers=UA)
    assert r.status_code == 422


def test_protected_route_requires_valid_token(client, dentist):
    assert client.get("/api/patients").status_code == 401
    assert client.get("/api/patients", headers={"Authorization": "Bearer not-a-jwt", **UA}).status_code == 401
    token = dentist["Authorization"].split()[1]
    head, payload, sig = token.split(".")
    tampered = f"{head}.{payload}.{sig[:-2]}AA"
    assert client.get("/api/patients", headers={"Authorization": f"Bearer {tampered}", **UA}).status_code == 401
    assert client.get("/api/patients", headers=dentist).status_code == 200


def test_expired_token_is_rejected(client, dentist):
    claims = jwt.decode(dentist["Authorization"].split()[1], options={"verify_signature": False})
    claims["exp"] = int((dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)).timestamp())
    expired = jwt.encode(claims, auth.jwt_secret(), algorithm="HS256")
    r = client.get("/api/patients", headers={"Authorization": f"Bearer {expired}", **UA})
    assert r.status_code == 401 and r.get_json()["error"]["message"] == "Token expired"


def test_token_from_another_device_is_rejected(client, dentist):
    stolen = {"Authorization": dentist["Authorization"], "User-Agent": "attacker-laptop/9.9"}
    assert client.get("/api/patients", headers=stolen).status_code == 401
    assert client.get("/api/patients", headers=dentist).status_code == 401  # session revoked after the mismatch


def test_refresh_rotation_and_reuse_detection(client):
    login(client, "technician")
    old_cookie = client.get_cookie("pv_refresh", path="/api/auth").value
    r1 = client.post("/api/auth/refresh", headers=UA)
    assert r1.status_code == 200 and data(r1)["access_token"]
    client.set_cookie("pv_refresh", old_cookie, path="/api/auth")      # replay the old refresh token
    assert client.post("/api/auth/refresh", headers=UA).status_code == 401
    new_access = {"Authorization": f"Bearer {data(r1)['access_token']}", **UA}
    assert client.get("/api/patients", headers=new_access).status_code == 401  # whole session revoked


def test_logout_revokes_session(client):
    h = login(client, "auditor")
    assert client.post("/api/auth/logout", headers=h).status_code == 200
    assert client.get("/api/auth/me", headers=h).status_code == 401


def test_mfa_enrolment_and_login(client, admin):
    client.post("/api/admin/users", headers=admin, json={"name": "MFA User", "email": "mfa@test.local",
                                                         "password": "Mfa-user-pass-1", "role": "dentist"})
    r = client.post("/api/auth/login", json={"email": "mfa@test.local", "password": "Mfa-user-pass-1"}, headers=UA)
    h = {"Authorization": f"Bearer {data(r)['access_token']}", **UA}
    enrol = data(client.post("/api/auth/mfa/enroll", headers=h))
    assert enrol["otpauth_uri"].startswith("otpauth://") and len(enrol["qr_png_base64"]) > 100
    secret = enrol["otpauth_uri"].split("secret=")[1].split("&")[0]
    assert client.post("/api/auth/mfa/confirm", headers=h, json={"code": "000000"}).status_code == 400
    assert client.post("/api/auth/mfa/confirm", headers=h, json={"code": pyotp.TOTP(secret).now()}).status_code == 200

    r = client.post("/api/auth/login", json={"email": "mfa@test.local", "password": "Mfa-user-pass-1"}, headers=UA)
    step = data(r)
    assert step["mfa_required"] and "access_token" not in step
    totp = pyotp.TOTP(secret)
    next_code = totp.at(dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=30))
    r = client.post("/api/auth/mfa", json={"mfa_token": step["mfa_token"], "code": next_code}, headers=UA)
    assert r.status_code == 200 and data(r)["access_token"]
    replay = client.post("/api/auth/mfa", json={"mfa_token": step["mfa_token"], "code": next_code}, headers=UA)
    assert replay.status_code == 401  # a TOTP code works only once


# ---------- RBAC ----------
def test_rbac_matrix_is_enforced(client, dentist, technician, auditor, admin):
    assert client.get("/api/patients", headers=auditor).status_code == 403          # auditors never see PHI
    assert client.get("/api/audit/logs", headers=auditor).status_code == 200
    assert client.get("/api/audit/logs", headers=dentist).status_code == 403
    assert client.post("/api/patients", headers=technician, json={"name": "X"}).status_code == 403
    assert client.post("/api/review/AN-000000000000", headers=technician,
                       json={"decision": "approve"}).status_code == 403
    assert client.get("/api/admin/users", headers=dentist).status_code == 403
    assert client.get("/api/admin/users", headers=admin).status_code == 200
    matrix = data(client.get("/api/security/rbac-matrix", headers=auditor))["matrix"]
    assert matrix["review:signoff"] == {"admin": False, "dentist": True, "technician": False, "auditor": False}


def test_patient_isolation_between_dentists(client, dentist, admin):
    client.post("/api/admin/users", headers=admin, json={"name": "Other Dentist", "email": "other@test.local",
                                                         "password": "Other-dentist-1", "role": "dentist"})
    r = client.post("/api/auth/login", json={"email": "other@test.local", "password": "Other-dentist-1"}, headers=UA)
    other = {"Authorization": f"Bearer {data(r)['access_token']}", **UA}
    pid = data(client.post("/api/patients", headers=dentist, json={"name": "Private Patient", "age": 50}))["patient_id"]
    assert client.get(f"/api/patients/{pid}", headers=dentist).status_code == 200
    assert client.get(f"/api/patients/{pid}", headers=other).status_code == 404      # no IDOR
    assert client.get(f"/api/patients/{pid}/progression", headers=other).status_code == 404
    assert client.get(f"/api/patients/{pid}", headers=admin).status_code == 200


def test_honeypot_access_locks_the_account(client, admin):
    from app.models.connection import db

    client.post("/api/admin/users", headers=admin, json={"name": "Snoop", "email": "snoop@test.local",
                                                         "password": "Snoop-pass-123", "role": "admin"})
    r = client.post("/api/auth/login", json={"email": "snoop@test.local", "password": "Snoop-pass-123"}, headers=UA)
    snoop = {"Authorization": f"Bearer {data(r)['access_token']}", **UA}
    decoy = db["patients"].find_one({"doctor_id": "system-decoy-owner"})
    assert decoy is not None
    assert client.get(f"/api/patients/{decoy['patient_id']}", headers=snoop).status_code == 404
    assert client.get("/api/auth/me", headers=snoop).status_code in (401, 403)
    events = data(client.get("/api/audit/logs?action=HONEYPOT_TRIGGERED", headers=admin))
    assert events and events[0]["outcome"] == "alert"


# ---------- uploads ----------
def test_disguised_upload_is_blocked(client, technician):
    r = client.post("/api/radiographs", headers=technician, content_type="multipart/form-data",
                    data={"image": (io.BytesIO(b"MZ\x90\x00" + b"\x00" * 300), "xray.png")})
    assert r.status_code == 415


def _pdf_text(pdf: bytes) -> str:
    """Page content of a ReportLab PDF (inflates the Flate-compressed streams)."""
    import base64
    import re
    import zlib

    out = []
    for m in re.finditer(rb"stream\r?\n(.*?)\s*endstream", pdf, re.S):
        raw = m.group(1).strip()
        try:
            if raw.endswith(b"~>"):  # ReportLab: ASCII85 on top of Flate
                raw = base64.a85decode(raw[:-2])
            out.append(zlib.decompress(raw).decode("latin-1"))
        except (zlib.error, ValueError):
            out.append(m.group(1).decode("latin-1", "ignore"))
    return "\n".join(out)


# ---------- end-to-end happy path ----------
def test_end_to_end_workflow(client, dentist, auditor):
    pid = data(client.post("/api/patients", headers=dentist, json={
        "name": "Synthetic Patient", "age": 52, "sex": "male", "smoking_status": "current",
        "cigarettes_per_day": 12, "diabetic": True, "hba1c": 7.4}))["patient_id"]

    def analyse(date, seed):
        up = client.post("/api/radiographs", headers=dentist, content_type="multipart/form-data",
                         data={"image": (io.BytesIO(synthetic_radiograph(seed=seed)), "scan.png")})
        assert up.status_code == 201, up.get_json()
        r = client.post("/api/analyses", headers=dentist,
                        json={"upload_id": data(up)["upload_id"], "patient_id": pid, "visit_date": date})
        assert r.status_code == 201, r.get_json()
        return data(r)

    first = analyse("2025-03-01", 1)
    second = analyse("2026-03-01", 2)
    assert second["mode"] == "demo" and second["teeth"]                    # no signed weights in tests
    assert second["review"]["status"] == "review_required"
    codes = {x["code"] for x in second["review"]["reasons"]}
    assert {"demo_mode", "uncalibrated"} <= codes
    tooth = second["teeth"][0]
    assert {"tooth_id", "bbox", "cej", "abc", "bone_loss_pct", "stage", "confidence", "uncertainty"} <= set(tooth)
    assert second["previous_analysis_id"] == first["analysis_id"]

    img = client.get(second["images"]["annotated"], headers=dentist)
    assert img.status_code == 200 and img.data.startswith(b"\x89PNG")

    prog = data(client.get(f"/api/patients/{pid}/progression", headers=dentist))
    assert prog["summary"]["visits"] == 2 and prog["comparisons"]

    blocked = client.post("/api/reports", headers=dentist, json={"analysis_id": second["analysis_id"]})
    assert blocked.status_code == 409                                     # needs sign-off first

    t0 = second["teeth"][0]["tooth_id"]
    signed = client.post(f"/api/review/{second['analysis_id']}", headers=dentist,
                         json={"decision": "correct", "comment": "Checked on screen",
                               "corrections": [{"tooth_id": t0, "bone_loss_pct": 22.5, "stage": "II"}]})
    assert signed.status_code == 200
    rep = client.post("/api/reports", headers=dentist, json={"analysis_id": second["analysis_id"]})
    assert rep.status_code == 201, rep.get_json()
    report_id = data(rep)["report_id"]

    pdf = client.get(f"/api/reports/{report_id}/download", headers=dentist)
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF")
    # the report shows exactly the stored numbers (no re-estimation) and the clinician's correction
    text = _pdf_text(pdf.data)
    model_value = second["teeth"][0]["bone_loss_pct"]
    assert model_value is not None and f"({t0}) Tj" in text and f"({model_value:.1f}) Tj" in text
    assert "Clinician corrections" in text and "(22.5) Tj" in text
    ok = data(client.get(f"/api/reports/verify/{report_id}"))
    assert ok["valid"] and ok["signature_valid"]
    by_file = data(client.post("/api/reports/verify", content_type="multipart/form-data",
                               data={"file": (io.BytesIO(pdf.data), "r.pdf")}))
    assert by_file["valid"]
    tampered = pdf.data.replace(b"PerioVision", b"PerioVisioN", 1)
    bad = data(client.post("/api/reports/verify", content_type="multipart/form-data",
                           data={"file": (io.BytesIO(tampered), "r.pdf")}))
    assert not bad["valid"]

    chain = data(client.get("/api/audit/verify", headers=auditor))
    assert chain["chain_intact"]
    actions = {e["action"] for e in data(client.get("/api/audit/logs?limit=500", headers=auditor))}
    assert {"PREDICTION", "REVIEW_CORRECTED", "REPORT_GENERATED", "UPLOAD_ACCEPTED", "LOGIN_SUCCESS"} <= actions
    assert all("Synthetic Patient" not in str(e) for e in data(client.get("/api/audit/logs?limit=500", headers=auditor)))


def test_openapi_lists_permissions(client):
    spec = client.get("/api/docs").get_json()
    assert spec["openapi"].startswith("3.")
    assert spec["paths"]["/api/review/{analysis_id}"]["post"]["x-permission"] == "review:signoff"
    assert spec["paths"]["/api/auth/login"]["post"]["security"] == []
    assert PASSWORDS  # fixtures loaded


def test_per_tooth_gradcam_needs_a_verified_model_and_rbac(client, dentist, auditor):
    pid = data(client.post("/api/patients", headers=dentist, json={"name": "CAM Patient", "age": 40}))["patient_id"]
    up = client.post("/api/radiographs", headers=dentist, content_type="multipart/form-data",
                     data={"image": (io.BytesIO(synthetic_radiograph(seed=7)), "scan.png")})
    a = data(client.post("/api/analyses", headers=dentist, json={"upload_id": data(up)["upload_id"], "patient_id": pid}))
    url = f"/api/analyses/{a['analysis_id']}/teeth/{a['teeth'][0]['tooth_id']}/gradcam"
    assert client.get(url, headers=dentist).status_code == 404        # demo mode: no verified model, no fake map
    assert client.get(url, headers=auditor).status_code == 403        # auditors never see clinical images
    assert client.get(url.replace(a["teeth"][0]["tooth_id"], "99"), headers=dentist).status_code == 404



def test_model_trust_shows_how_each_number_was_tested(client, dentist):
    from app import config
    from app.security.model_signing import Signer

    path = config.WEIGHTS_DIR / "evidence_summary.json"
    path.write_text('{"generated": "t", "rows": [{"task": "x", "metric": "MAE", "value": 7.3, "ci95": null, "n": 576,'
                    ' "unit_of_n": "teeth", "status": "VERIFIED", "pct": false, "test_type": "same-source held-out",'
                    ' "small_sample": false, "note": ""}]}', encoding="utf-8")
    try:
        assert not data(client.get("/api/models/trust", headers=dentist))["evidence"]["available"]   # unsigned
        Signer().sign_manifest(config.WEIGHTS_DIR)
        ev = data(client.get("/api/models/trust", headers=dentist))["evidence"]
        assert ev["available"] and ev["rows"][0]["test_type"] == "same-source held-out"
    finally:
        path.unlink()
        Signer().sign_manifest(config.WEIGHTS_DIR)
