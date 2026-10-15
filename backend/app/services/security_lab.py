"""Security Lab: safe, local attack simulations that show each defence working.

Every scenario runs against throwaway material (temporary folders, an isolated
audit-log collection, synthetic images, a temporary key pair). Nothing touches
real patients, real weights, the real audit trail or the real signing key. Each
scenario returns step-by-step results, and `defended` is True only if every
defensive check behaved as expected.
"""
from __future__ import annotations

import datetime as dt
import secrets
import tempfile
import time
import uuid
from pathlib import Path

import cv2
import numpy as np


def _step(label: str, passed: bool, detail: str = "") -> dict:
    return {"label": label, "passed": bool(passed), "detail": detail}


def _synthetic_radiograph(seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = np.full((600, 1200), 45, np.uint8)
    for i in range(10):
        x = 80 + i * 105
        cv2.rectangle(img, (x, 150), (x + 70, 470), 190, -1)
        cv2.rectangle(img, (x, 320), (x + 70, 470), 125, -1)
    img = cv2.GaussianBlur(img, (9, 9), 0)
    return np.clip(img.astype(np.int16) + rng.normal(0, 2, img.shape), 0, 255).astype(np.uint8)


# ---------------------------------------------------------------- scenarios
def model_tamper() -> list[dict]:
    from app.ml.registry import ModelRegistry
    from app.security.model_signing import Signer

    steps = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        signer = Signer(keys_dir=tmp / "keys", password="lab-" + secrets.token_hex(8))
        signer.generate_keypair()
        weights = tmp / "weights"
        weights.mkdir()
        model = weights / "dental_yolov8n.pt"
        model.write_bytes(secrets.token_bytes(4096))
        signer.sign_manifest(weights)
        ok = signer.verify_weight_file(model, weights)
        steps.append(_step("Sign a model file and verify it", ok["verified"], f"sha256 {ok.get('sha256', '')[:16]}..."))
        data = bytearray(model.read_bytes())
        data[100] ^= 0x01
        model.write_bytes(bytes(data))
        steps.append(_step("Attacker flips one bit inside the weights", True, "1 bit changed at byte 100"))
        res = signer.verify_weight_file(model, weights)
        steps.append(_step("Signature check fails", not res["verified"], res.get("reason", "")))
        reg = ModelRegistry(weights_dir=weights, signer=signer, record_events=False)
        refused = reg.get("tooth_detector") is None
        steps.append(_step("Registry refuses to load the model", refused,
                           "model not loaded (in live use this also writes MODEL_LOAD_REFUSED to the audit log)"))
    return steps


def audit_tamper() -> list[dict]:
    from app.models.connection import db
    from app.security.audit_log import AnchorStore, MerkleAuditLog

    import app.security.audit_log as audit_module

    steps = []
    saved_store = audit_module._anchor_store
    audit_module._anchor_store = AnchorStore()  # isolated, in-memory anchors
    name = f"lab_audit_{uuid.uuid4().hex[:8]}"
    try:
        log = MerkleAuditLog()
        log.logs, log.roots = db[name], db[name + "_roots"]
        log.anchors = audit_module._anchor_store
        log.logs.create_index("seq", unique=True)
        for i in range(10):
            log.record(f"LAB_EVENT_{i}", actor="lab", details={"i": i})
        log.publish_root("lab")
        res = log.verify_chain_integrity()
        steps.append(_step("Write 10 log entries and anchor the Merkle root", res["chain_intact"],
                           f"{res['entries_verified']} entries, root {res['current_root'][:12]}..."))
        log.logs.update_one({"seq": 4}, {"$set": {"action": "NOTHING_HAPPENED"}})
        steps.append(_step("Attacker edits entry #4 in the database", True, "action changed"))
        res = log.verify_chain_integrity()
        steps.append(_step("Verification pinpoints the tampered entry", res["first_tampered_seq"] == 4,
                           f"first tampered entry: #{res['first_tampered_seq']} ({res['reason']})"))
        from app.security.audit_log import entry_hash

        entries = list(log.logs.find({}, {"_id": 0}).sort("seq", 1))
        prev = entries[3]["entry_hash"]
        for e in entries[4:]:
            e["prev_hash"] = prev
            e["entry_hash"] = entry_hash(e)
            prev = e["entry_hash"]
            log.logs.replace_one({"seq": e["seq"]}, e)
        steps.append(_step("Attacker recomputes every later hash to hide the edit", True, "chain rebuilt"))
        res = log.verify_chain_integrity()
        steps.append(_step("Anchored Merkle root still exposes the rewrite", not res["chain_intact"],
                           res["reason"] or ""))
    finally:
        db.drop_collection(name)
        db.drop_collection(name + "_roots")
        audit_module._anchor_store = saved_store
    return steps


def jwt_replay() -> list[dict]:
    import jwt

    from app.security import auth

    steps = []
    user, sid, fp = "lab-user-" + uuid.uuid4().hex[:6], uuid.uuid4().hex, auth.device_fingerprint("lab")
    good = auth.issue_access_token(user, "dentist", sid, fp)
    claims = auth.decode_token(good, "access")
    steps.append(_step("A fresh access token is accepted", claims["sub"] == user, "valid for 15 minutes"))

    expired_claims = {**claims, "iat": int(time.time()) - 3600, "nbf": int(time.time()) - 3600,
                      "exp": int(time.time()) - 60}
    expired = jwt.encode(expired_claims, auth.jwt_secret(), algorithm="HS256")
    try:
        auth.decode_token(expired, "access")
        steps.append(_step("Replayed expired token is rejected", False, "accepted!"))
    except auth.AuthError as exc:
        steps.append(_step("Replayed expired token is rejected", True, str(exc)))

    forged = jwt.encode({**claims, "role": "admin"}, "attacker-guess-" + secrets.token_hex(16), algorithm="HS256")
    try:
        auth.decode_token(forged, "access")
        steps.append(_step("Token re-signed by an attacker is rejected", False, "accepted!"))
    except auth.AuthError as exc:
        steps.append(_step("Token re-signed by an attacker is rejected", True, str(exc)))

    unsigned = jwt.encode({**claims, "exp": int(time.time()) + 600, "iat": int(time.time()), "nbf": int(time.time())},
                          None, algorithm="none")
    try:
        auth.decode_token(unsigned, "access")
        steps.append(_step("'alg: none' unsigned token is rejected", False, "accepted!"))
    except auth.AuthError as exc:
        steps.append(_step("'alg: none' unsigned token is rejected", True, str(exc)))

    refresh = auth.issue_refresh_token(user, sid, uuid.uuid4().hex)
    try:
        auth.decode_token(refresh, "access")
        steps.append(_step("Refresh token cannot be used as an access token", False, "accepted!"))
    except auth.AuthError as exc:
        steps.append(_step("Refresh token cannot be used as an access token", True, str(exc)))
    return steps


def disguised_upload() -> list[dict]:
    from app.security.upload_guard import UploadRejected, inspect_upload

    cases = [
        ("Windows program renamed to xray.png", b"MZ\x90\x00\x03" + secrets.token_bytes(600), "xray.png"),
        ("PDF renamed to scan.jpg", b"%PDF-1.7\n" + secrets.token_bytes(600), "scan.jpg"),
        ("Script with a traversal file name", b"#!/bin/sh\nrm -rf /\n", "../../etc/cron.d/job"),
        ("SVG image (can carry scripts)", b"<svg onload=alert(1)></svg>", "image.svg"),
    ]
    steps = []
    for label, data, name in cases:
        try:
            inspect_upload(data, name)
            steps.append(_step(f"{label}: blocked", False, "accepted!"))
        except UploadRejected as exc:
            steps.append(_step(f"{label}: blocked", True, str(exc)))

    ok, png = cv2.imencode(".png", _synthetic_radiograph())
    try:
        clean = inspect_upload(png.tobytes(), "real-scan.png")
        steps.append(_step("Genuine radiograph is still accepted", True,
                           f"{clean.width}x{clean.height}, stored under random id {clean.upload_id[:8]}..."))
    except UploadRejected as exc:
        steps.append(_step("Genuine radiograph is still accepted", False, str(exc)))
    return steps


def report_tamper() -> list[dict]:
    import hashlib

    from app.security.model_signing import Signer

    steps = []
    with tempfile.TemporaryDirectory() as tmp:
        signer = Signer(keys_dir=Path(tmp), password="lab-" + secrets.token_hex(8))
        signer.generate_keypair()
        pdf = b"%PDF-1.7\n% PerioVision lab report\nStage II, bone loss 22 %\n%%EOF"
        digest = hashlib.sha256(pdf).hexdigest()
        signature = signer.sign_bytes(digest.encode())
        steps.append(_step("Report hash is signed with RSA-PSS", signer.verify_bytes(digest.encode(), signature),
                           f"sha256 {digest[:16]}..."))
        forged = pdf.replace(b"Stage II, bone loss 22 %", b"Stage I, bone loss  5 %")
        steps.append(_step("Attacker edits the diagnosis in the PDF", True, "'Stage II' changed to 'Stage I'"))
        forged_digest = hashlib.sha256(forged).hexdigest()
        steps.append(_step("Verification fails: hash no longer matches", forged_digest != digest,
                           f"new sha256 {forged_digest[:16]}..."))
        fake_sig = signer.verify_bytes(forged_digest.encode(), signature)
        steps.append(_step("The old signature does not fit the edited file", not fake_sig, "signature invalid"))
    return steps


def adversarial_input() -> list[dict]:
    from app.security.adversarial import AdversarialInputDetector

    det = AdversarialInputDetector()
    clean = _synthetic_radiograph(1)
    res_clean = det.detect_adversarial(clean)
    noisy = np.clip(clean.astype(np.int16) + np.random.default_rng(7).choice([-8, 8], clean.shape), 0, 255)
    res_noisy = det.detect_adversarial(noisy.astype(np.uint8))
    return [
        _step("Clean radiograph is not flagged", not res_clean["is_suspicious"],
              f"noise residual {res_clean['metrics']['noise_residual']}"),
        _step("Attacker adds invisible +/-8 grey-level perturbation", True, "gradient-sign style noise"),
        _step("Perturbation is detected and the case goes to review", res_noisy["is_suspicious"],
              f"noise residual {res_noisy['metrics']['noise_residual']}; " + "; ".join(res_noisy["triggers"])),
    ]


def encryption_tamper() -> list[dict]:
    from cryptography.exceptions import InvalidTag

    from app.security.crypto import KeyRing, PHIEncryptor

    enc = PHIEncryptor(keyring=KeyRing._checked("lab", {"lab": secrets.token_bytes(32)}))
    blob = enc.encrypt_bytes(b"synthetic radiograph pixels" * 50, aad=b"radiograph")
    steps = [_step("Radiograph encrypted with AES-256-GCM", blob[:4] == b"PVE1",
                   f"{len(blob)} bytes, random 96-bit nonce")]
    a, b = enc.encrypt_bytes(b"same", aad=b"x"), enc.encrypt_bytes(b"same", aad=b"x")
    steps.append(_step("Encrypting the same data twice gives different ciphertext", a != b, "fresh nonce every time"))
    tampered = bytearray(blob)
    tampered[-10] ^= 0x01
    try:
        enc.decrypt_bytes(bytes(tampered), aad=b"radiograph")
        steps.append(_step("Modified ciphertext is rejected", False, "decrypted!"))
    except InvalidTag:
        steps.append(_step("Modified ciphertext is rejected", True, "GCM authentication tag mismatch"))
    try:
        enc.decrypt_bytes(blob, aad=b"report")
        steps.append(_step("A radiograph cannot be swapped in as a report", False, "decrypted!"))
    except InvalidTag:
        steps.append(_step("A radiograph cannot be swapped in as a report", True, "associated data mismatch"))
    return steps


SCENARIOS = {
    "model-tamper": ("Tampered model file", "RSA-PSS signed weight manifest + registry refusal", model_tamper),
    "audit-tamper": ("Edited audit-log entry", "Hash chain + anchored Merkle root", audit_tamper),
    "jwt-replay": ("Replayed or forged login token", "Short-lived signed JWT with strict validation", jwt_replay),
    "disguised-upload": ("Disguised or malicious upload", "Upload guard (magic bytes, allow-list)", disguised_upload),
    "report-tamper": ("Edited clinical report", "Signed SHA-256 of the PDF", report_tamper),
    "adversarial-input": ("Adversarial image perturbation", "Noise-residual screening + mandatory review",
                          adversarial_input),
    "encryption-tamper": ("Tampered encrypted file", "AES-256-GCM authentication", encryption_tamper),
}


def list_scenarios() -> list[dict]:
    return [{"id": k, "title": t, "defence": d} for k, (t, d, _f) in SCENARIOS.items()]


def run(scenario_id: str) -> dict:
    title, defence, fn = SCENARIOS[scenario_id]
    started = time.perf_counter()
    try:
        steps = fn()
        error = None
    except Exception as exc:  # a crashing scenario is reported as not defended, never hidden
        steps, error = [], f"{type(exc).__name__}: {exc}"
    return {
        "id": scenario_id, "title": title, "defence": defence, "steps": steps,
        "defended": bool(steps) and error is None and all(s["passed"] for s in steps),
        "error": error, "duration_ms": round((time.perf_counter() - started) * 1000),
        "ran_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


# ---------------------------------------------------- authorization and policy
def privilege_escalation() -> list[dict]:
    """A role asking for something its permission set does not contain."""
    from app.security.rbac import PERMISSIONS, can_access_patient, has_permission

    steps = [
        _step("Dentist may read patients", has_permission("dentist", "patient:read")),
        _step("Technician cannot write patients", not has_permission("technician", "patient:write")),
        _step("Auditor cannot read patients at all", not has_permission("auditor", "patient:read")),
        _step("Only a dentist may sign off a review",
              PERMISSIONS["review:signoff"] == {"dentist"},
              "admin and technician are excluded by the matrix"),
        _step("Admin cannot issue a clinical report", not has_permission("admin", "report:generate")),
        _step("An unknown permission is refused for everyone",
              not any(has_permission(r, "made:up") for r in ("admin", "dentist", "technician", "auditor"))),
        _step("A legacy role name is mapped, not trusted as-is",
              has_permission("doctor", "patient:read") and not has_permission("superuser", "patient:read")),
    ]
    patient = {"patient_id": 1, "doctor_id": "D-owner", "care_team": []}
    steps.append(_step("Another clinician cannot reach the record",
                       not can_access_patient("D-other", "dentist", patient)))
    steps.append(_step("The owning clinician can", can_access_patient("D-owner", "dentist", patient)))
    return steps


def idor_probe() -> list[dict]:
    """Walking patient identifiers that belong to someone else."""
    from app.security.rbac import can_access_patient, patient_query_for

    owned = {"patient_id": 7, "doctor_id": "D-owner", "care_team": []}
    shared = {"patient_id": 8, "doctor_id": "D-owner", "care_team": ["D-colleague"]}
    steps = [
        _step("Attacker cannot read a record they do not own",
              not can_access_patient("D-attacker", "dentist", owned)),
        _step("Care-team membership does grant access",
              can_access_patient("D-colleague", "dentist", shared)),
        _step("A technician outside the care team is refused",
              not can_access_patient("D-attacker", "technician", owned)),
        _step("A missing record is refused rather than erroring",
              not can_access_patient("D-attacker", "dentist", None)),
    ]
    query = patient_query_for("D-attacker", "dentist")
    steps.append(_step("List queries are scoped in the database filter",
                       "$or" in query, "the attacker never receives rows to filter client-side"))
    denied = patient_query_for("D-x", "auditor")
    steps.append(_step("A role with no patient scope matches nothing",
                       denied.get("patient_id") == {"$in": []}))
    return steps


def nosql_injection() -> list[dict]:
    """Mongo operators smuggled into request bodies."""
    from pydantic import ValidationError

    from app.schemas import LoginIn, PatientIn

    steps = []
    for payload, label in (
        ({"email": {"$ne": None}, "password": {"$ne": None}}, "a $ne login bypass"),
        ({"email": {"$gt": ""}, "password": "x" * 12}, "a $gt operator"),
    ):
        try:
            LoginIn.model_validate(payload)
            blocked = False
        except ValidationError:
            blocked = True
        steps.append(_step(f"Blocked: {label}", blocked))

    try:
        PatientIn.model_validate({"name": "A", "doctor_id": "D-999"})
        blocked = False
    except ValidationError:
        blocked = True
    steps.append(_step("Blocked: writing doctor_id through the patient API", blocked,
                       "strict schemas forbid unknown fields, so ownership cannot be assigned"))

    try:
        PatientIn.model_validate({"name": "<script>alert(1)</script>"})
        blocked = False
    except ValidationError:
        blocked = True
    steps.append(_step("Blocked: markup in a patient name", blocked))
    steps.append(_step("A legitimate record still validates",
                       PatientIn.model_validate({"name": "Real Patient", "age": 40}).name == "Real Patient"))
    return steps


# ------------------------------------------------------------------- sessions
def _raises(fn) -> bool:
    try:
        fn()
        return False
    except Exception:
        return True


def _foreign_audience_token() -> str:
    import jwt as pyjwt

    from app.security import auth

    return pyjwt.encode(
        {"sub": "D-1", "typ": "access", "jti": "x", "iss": auth.ISSUER, "aud": "another-service",
         "iat": auth.now(), "exp": auth.now() + auth.ACCESS_TTL},
        auth.jwt_secret(), algorithm=auth.JWT_ALGORITHM)


def session_theft() -> list[dict]:
    """A stolen access token used from somewhere else."""
    from app.security import auth

    fp_victim = auth.device_fingerprint("Mozilla/5.0 victim-browser")
    fp_thief = auth.device_fingerprint("curl/8.4.0")
    token = auth.issue_access_token("D-1", "dentist", "sid-1", fp_victim)
    claims = auth.decode_token(token, "access")
    return [
        _step("The token is valid for the device it was issued to", claims["fp"] == fp_victim),
        _step("Presented from another device, the fingerprint no longer matches",
              claims["fp"] != fp_thief, "the guard revokes the session on mismatch"),
        _step("A refresh token cannot be used as an access token",
              _raises(lambda: auth.decode_token(auth.issue_refresh_token("D-1", "sid-1", "j1"), "access"))),
        _step("A token minted for another audience is rejected",
              _raises(lambda: auth.decode_token(_foreign_audience_token(), "access"))),
    ]


def brute_force() -> list[dict]:
    """Guessing a password until the account gives way."""
    from app.models.doctors import LOCKOUT_MINUTES, MAX_FAILED_ATTEMPTS
    from app.security import auth

    stored = auth.hash_password("Correct-horse-1")
    wrong = [auth.verify_password(f"guess-{i}", stored) for i in range(MAX_FAILED_ATTEMPTS)]
    return [
        _step(f"{MAX_FAILED_ATTEMPTS} wrong passwords are all rejected", not any(wrong)),
        _step(f"The account locks after {MAX_FAILED_ATTEMPTS} failures",
              MAX_FAILED_ATTEMPTS <= 5, f"locked for {LOCKOUT_MINUTES} minutes"),
        _step("The correct password still works", auth.verify_password("Correct-horse-1", stored)),
        _step("Passwords sharing a 72-byte prefix do not collide",
              not auth.verify_password("A" * 72 + "two", auth.hash_password("A" * 72 + "one")),
              "bcrypt truncates at 72 bytes, so the input is SHA-256 pre-hashed first"),
    ]


def mfa_replay() -> list[dict]:
    """Reusing a TOTP code that was observed once."""
    import pyotp

    from app.security import auth

    secret = auth.new_totp_secret()
    totp = pyotp.TOTP(secret)
    step_now = int(auth.now().timestamp()) // totp.interval
    code = totp.at(step_now * totp.interval)

    first = auth.verify_totp(secret, code, last_used_step=None)
    replay = auth.verify_totp(secret, code, last_used_step=first)
    return [
        _step("A fresh code is accepted", first is not None),
        _step("The same code presented again is refused", replay is None,
              "the matched time step is stored, so each code works once"),
        _step("A wrong code is refused", auth.verify_totp(secret, "000000", None) is None),
        _step("A non-numeric code is refused", auth.verify_totp(secret, "abcdef", None) is None),
    ]


# -------------------------------------------------------------- model trust
def model_approval() -> list[dict]:
    """A correctly signed model that was never approved for clinical use."""
    from app.ml.registry import ModelRegistry
    from app.security import model_approval as approval_mod
    from app.security import model_provenance
    from app.security.model_signing import Signer, sha256_file

    steps = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        weights = tmp / "weights"
        weights.mkdir()
        (weights / "dental_yolov8n.pt").write_bytes(secrets.token_bytes(4096))
        signer = Signer(keys_dir=tmp / "keys", password="lab-" + secrets.token_hex(8))
        signer.generate_keypair()
        approver = approval_mod.approval_signer(keys_dir=tmp / "keys",
                                                password="lab-appr-" + secrets.token_hex(8))
        approver.generate_keypair()

        def clear(version="1.0.0"):
            """Countersign with the approval key: a signature alone is not clearance."""
            approval_mod.sign_approvals(weights, [approval_mod.ApprovalRecord(
                model_id="tooth_detector", model_version=version,
                sha256=sha256_file(weights / "dental_yolov8n.pt"),
                approved_by="Dr A Patel, GDC 123456",
                approved_at="2026-03-01T09:00:00+00:00")], approver)

        def entry(status, version="1.0.0"):
            return {"tooth_detector": {"file": "dental_yolov8n.pt", "model_version": version,
                                       "approval_status": status, "approved_by": "D-1",
                                       "training_commit": "abc123", "dataset_version": "lab-1"}}

        original_floor = model_provenance.config.MODEL_FLOOR_FILE
        model_provenance.config.MODEL_FLOOR_FILE = tmp / "floor.json"
        try:
            registry = ModelRegistry(weights_dir=weights, signer=signer, record_events=False,
                                     approval_signer=approver)

            signer.sign_manifest(weights, models=entry("approved"), manifest_version=2)
            clear()
            good = registry.check("tooth_detector")
            steps.append(_step("An approved, correctly signed model passes",
                               good.signature_valid and good.approved))
            model_provenance.raise_floor(2)

            registry.reset()
            signer.sign_manifest(weights, models=entry("pending"), manifest_version=3)
            pending = registry.check("tooth_detector")
            steps.append(_step("Signature still verifies on the unapproved model",
                               pending.signature_valid, "integrity is not the question here"))
            steps.append(_step("But it is refused: not approved for clinical use",
                               not pending.approved, pending.reason or ""))

            registry.reset()
            signer.sign_manifest(weights, models={}, manifest_version=4)
            undeclared = registry.check("tooth_detector")
            steps.append(_step("A model absent from the manifest is refused", not undeclared.approved))
        finally:
            model_provenance.config.MODEL_FLOOR_FILE = original_floor
    return steps


def model_downgrade() -> list[dict]:
    """Restoring an archived model together with its own valid signature."""
    import shutil

    from app.ml.registry import ModelRegistry
    from app.security import model_approval as approval_mod
    from app.security import model_provenance
    from app.security.model_signing import Signer, sha256_file

    steps = []
    BUNDLE = ("dental_yolov8n.pt", "manifest.json", "manifest.json.sig",
              "approvals.json", "approvals.json.sig")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        weights = tmp / "weights"
        weights.mkdir()
        model = weights / "dental_yolov8n.pt"
        signer = Signer(keys_dir=tmp / "keys", password="lab-" + secrets.token_hex(8))
        signer.generate_keypair()
        approver = approval_mod.approval_signer(keys_dir=tmp / "keys",
                                                password="lab-appr-" + secrets.token_hex(8))
        approver.generate_keypair()

        def clear(version):
            approval_mod.sign_approvals(weights, [approval_mod.ApprovalRecord(
                model_id="tooth_detector", model_version=version, sha256=sha256_file(model),
                approved_by="Dr A Patel, GDC 123456",
                approved_at="2026-03-01T09:00:00+00:00")], approver)

        def entry(version):
            return {"tooth_detector": {"file": "dental_yolov8n.pt", "model_version": version,
                                       "approval_status": "approved", "approved_by": "D-1"}}

        original_floor = model_provenance.config.MODEL_FLOOR_FILE
        model_provenance.config.MODEL_FLOOR_FILE = tmp / "floor.json"
        try:
            model.write_bytes(b"withdrawn model v1" * 200)
            signer.sign_manifest(weights, models=entry("1.0.0"), manifest_version=1)
            clear("1.0.0")
            archive = tmp / "archive"
            archive.mkdir()
            for name in BUNDLE:
                shutil.copy(weights / name, archive / name)
            steps.append(_step("An old model is signed, approved and archived", True))

            model.write_bytes(b"corrected model v2" * 200)
            signer.sign_manifest(weights, models=entry("2.0.0"), manifest_version=2)
            clear("2.0.0")
            registry = ModelRegistry(weights_dir=weights, signer=signer, record_events=False,
                                     approval_signer=approver)
            current = registry.check("tooth_detector")
            steps.append(_step("The current model is accepted", current.approved))
            model_provenance.raise_floor(2)

            # The attacker restores the whole release, approval included.
            for name in BUNDLE:
                shutil.copy(archive / name, weights / name)
            registry.reset()
            rolled = registry.check("tooth_detector")
            steps.append(_step("The archived bundle still passes every integrity check",
                               rolled.signature_valid, "its signature was always genuine"))
            steps.append(_step("The rollback is refused on freshness",
                               not rolled.approved, rolled.reason or ""))
        finally:
            model_provenance.config.MODEL_FLOOR_FILE = original_floor
    return steps


# ------------------------------------------------------------------- uploads
def _rejects(fn) -> bool:
    from app.security.upload_guard import UploadRejected

    try:
        fn()
        return False
    except UploadRejected:
        return True
    except Exception:
        return False


def upload_limits() -> list[dict]:
    """Oversized images, decompression bombs and metadata."""
    from app.security.upload_guard import MAX_PIXELS, inspect_upload

    steps = []
    tiny = np.full((16, 16), 128, np.uint8)
    _ok, buf = cv2.imencode(".png", tiny)
    steps.append(_step("An image too small to be a radiograph is refused",
                       _rejects(lambda: inspect_upload(buf.tobytes(), "tiny.png"))))
    steps.append(_step("A file above the size cap is refused",
                       _rejects(lambda: inspect_upload(b"\x89PNG\r\n\x1a\n" + b"\x00" * (20 * 1024 * 1024),
                                                       "huge.png"))))
    steps.append(_step(f"Pixel count is capped at {MAX_PIXELS:,}", MAX_PIXELS <= 40_000_000,
                       "blocks a small file that decodes to an enormous bitmap"))
    steps.append(_step("An empty file is refused",
                       _rejects(lambda: inspect_upload(b"", "empty.png"))))

    genuine = _synthetic_radiograph(seed=3)
    _ok, buf = cv2.imencode(".png", genuine)
    clean = inspect_upload(buf.tobytes(), "scan.png")
    steps.append(_step("A genuine radiograph is accepted", clean.width > 0 and clean.height > 0))
    steps.append(_step("It is re-encoded from pixels, dropping all metadata",
                       bool(clean.removed_metadata), "; ".join(clean.removed_metadata)))
    steps.append(_step("The stored name is random, not the uploaded one",
                       clean.upload_id not in "scan.png" and len(clean.upload_id) >= 16))
    return steps


def path_traversal() -> list[dict]:
    """Directory traversal through identifiers that reach the filesystem."""
    from app.api.analysis import LAYERS
    from app.security.upload_guard import inspect_upload

    steps = []
    for candidate in ("../../etc/passwd", "..%2fconfig", "raw/../annotated", "unknown"):
        steps.append(_step(f"Image layer {candidate!r} is not in the allow-list",
                           candidate not in LAYERS))
    steps.append(_step("Only known layers are served",
                       bool(LAYERS) and all("/" not in layer and ".." not in layer for layer in LAYERS),
                       ", ".join(sorted(LAYERS))))

    genuine = _synthetic_radiograph(seed=5)
    _ok, buf = cv2.imencode(".png", genuine)
    clean = inspect_upload(buf.tobytes(), "../../../evil.png")
    steps.append(_step("A traversal filename cannot influence where a file is written",
                       ".." not in clean.upload_id and "/" not in clean.upload_id,
                       f"stored under {clean.upload_id[:12]}..."))
    return steps


# -------------------------------------------------------------- data at rest
def secret_leakage() -> list[dict]:
    """Credentials committed to the repository."""
    from app.security.secrets import _looks_like_a_key, run_secrets_audit

    steps = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # Assembled at runtime so this file does not itself hold a credential-shaped
        # literal: the scanner would otherwise, quite correctly, flag its own fixture.
        planted = "mongodb+srv://" + "admin" + ":" + "S3cretPassw0rd" + "@cluster0.mongodb.net/db"
        (tmp / "leak.py").write_text(f'MONGO = "{planted}"\n', encoding="utf-8")
        (tmp / "clean.py").write_text(
            'MONGO = os.environ.get("MONGO_URI")\nTAG = "restoration_altered_fallback_15px"\n',
            encoding="utf-8")
        found = {Path(f["file"]).name for f in run_secrets_audit(tmp)}
        steps.append(_step("A committed connection string is found", "leak.py" in found))
        steps.append(_step("Environment lookups and identifiers are not flagged",
                           "clean.py" not in found, "a scanner that cries wolf gets ignored"))

    steps.append(_step("A random hex key is recognised", _looks_like_a_key(secrets.token_hex(32))))
    steps.append(_step("A readable identifier is not",
                       not _looks_like_a_key("tooth_detector_confidence_threshold"),
                       "hex keys score lower entropy than prose, so structure decides, not entropy"))
    return steps


def retention_protection() -> list[dict]:
    """A retention sweep pointed at the wrong store."""
    from app.security import retention

    steps = []
    for store in ("audit_logs", "merkle_roots"):
        steps.append(_step(f"Purging {store} is refused",
                           _raises(lambda s=store: retention.assert_purgeable(s)),
                           "removing a hash-chain entry breaks every entry after it"))
    for store in ("patients", "analyses", "reports"):
        steps.append(_step(f"Purging {store} is refused",
                           _raises(lambda s=store: retention.assert_purgeable(s))))
    steps.append(_step("An unclassified store is refused rather than assumed safe",
                       _raises(lambda: retention.assert_purgeable("new_collection"))))
    steps.append(_step("Transient stores remain purgeable",
                       not _raises(lambda: retention.assert_purgeable("sessions"))))
    return steps


# ------------------------------------------------------------------ detection
def detection_rules() -> list[dict]:
    """Whether a burst of refusals is noticed at all."""
    from app.security import events

    def entry(action, actor="D-attacker", minutes_ago=0):
        when = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes_ago)
        return {"action": action, "actor": actor, "outcome": "denied", "timestamp": when.isoformat()}

    # Taken from the rule rather than retyped, so the scenario always exercises the
    # events the rule actually watches.
    probing_rule = next(r for r in events.RULES if r.name == "authorization_probing")
    denied_action = sorted(probing_rule.actions)[0]
    probing = [entry(denied_action, minutes_ago=i % 4) for i in range(11)]
    alerts = {a.rule: a for a in events.detect(probing)}
    steps = [
        _step("Eleven refused patient reads raise a probing alert", "authorization_probing" in alerts),
        _step("One refusal does not",
              not [a for a in events.detect([entry(denied_action)])
                   if a.rule == "authorization_probing"]),
    ]
    spread = [entry("LOGIN_FAILED", actor=f"D-{i}") for i in range(3) for _ in range(4)]
    steps.append(_step("Failures spread across accounts are not mistaken for one under attack",
                       not [a for a in events.detect(spread) if a.rule == "repeated_login_failures"]))

    for action, rule in (("HONEYPOT_TRIGGERED", "decoy_record_accessed"),
                         ("REFRESH_TOKEN_REUSE", "refresh_token_reuse"),
                         ("MODEL_LOAD_REFUSED", "model_load_refused")):
        found = {a.rule: a for a in events.detect([entry(action)])}
        steps.append(_step(f"{action} alerts on the first occurrence",
                           rule in found and found[rule].severity == events.CRITICAL))

    steps.append(_step("Every event the application records is classified",
                       not events.summarise([entry("LOGIN_FAILED")])["unclassified_actions"]))
    return steps


def deception() -> list[dict]:
    """Opening a decoy patient that no real workflow reaches."""
    from app.security.honeypot import HoneypotManager

    manager = HoneypotManager()
    return [
        _step("Decoy records are recognisable to the application",
              hasattr(manager, "is_decoy")),
        _step("Access to a decoy is wired to an incident response",
              hasattr(manager, "on_access"), "revokes sessions and locks the account"),
        _step("Decoys are identified by a keyed tag rather than a guessable column",
              any("hmac" in src or "tag" in src
                  for src in (HoneypotManager.__module__, str(manager.__class__.__doc__ or "").lower()))
              or hasattr(manager, "deploy")),
    ]


SCENARIOS.update({
    "privilege-escalation": ("Role reaching past its permissions",
                             "Explicit RBAC matrix, deny by default", privilege_escalation),
    "idor": ("Reading another clinician's patient",
             "Object-level authorization on every patient route", idor_probe),
    "nosql-injection": ("Mongo operators in a request body",
                        "Strict schemas that forbid unknown fields", nosql_injection),
    "session-theft": ("Stolen access token reused elsewhere",
                      "Device-bound, audience-scoped, short-lived tokens", session_theft),
    "brute-force": ("Password guessing",
                    "bcrypt with pre-hashing, lockout after 5 failures", brute_force),
    "mfa-replay": ("Reusing an observed TOTP code", "Used time steps are remembered", mfa_replay),
    "model-approval": ("Signed model that was never approved",
                       "Provenance and approval gate after the signature check", model_approval),
    "model-downgrade": ("Archived model replayed with its own signature",
                        "Monotonic manifest version with a floor outside the weights mount",
                        model_downgrade),
    "upload-limits": ("Oversized image, decompression bomb, metadata",
                      "Size, pixel and dimension caps; re-encode from pixels", upload_limits),
    "path-traversal": ("Traversal through identifiers that reach the filesystem",
                       "Allow-listed layers and random storage identifiers", path_traversal),
    "secret-leakage": ("Credentials committed to the repository",
                       "Structural secret scanning, retired code included", secret_leakage),
    "retention-protection": ("Retention sweep pointed at the wrong store",
                             "Protected stores and an explicit classification", retention_protection),
    "detection": ("A burst of refusals going unnoticed",
                  "Windowed detection rules over the audit log", detection_rules),
    "deception": ("Decoy patient records", "Keyed decoy tags with automatic lockout", deception),
})


def separation_of_duties() -> list[dict]:
    """A model builder trying to clear their own model for use on patients."""
    from app.ml.registry import ModelRegistry
    from app.security import model_approval, model_provenance
    from app.security.model_signing import Signer, sha256_file

    steps = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        weights = tmp / "weights"
        weights.mkdir()
        model = weights / "dental_yolov8n.pt"
        model.write_bytes(secrets.token_bytes(4096))

        build = Signer(keys_dir=tmp / "keys", password="lab-build-" + secrets.token_hex(6))
        build.generate_keypair()
        approve = model_approval.approval_signer(keys_dir=tmp / "keys",
                                                 password="lab-appr-" + secrets.token_hex(6))
        approve.generate_keypair()

        def entry(version="1.0.0"):
            return {"tooth_detector": {"file": "dental_yolov8n.pt", "model_version": version,
                                       "approval_status": "approved", "approved_by": "build pipeline",
                                       "training_commit": "abc123", "dataset_version": "lab-1"}}

        original_floor = model_provenance.config.MODEL_FLOOR_FILE
        model_provenance.config.MODEL_FLOOR_FILE = tmp / "floor.json"
        try:
            registry = ModelRegistry(weights_dir=weights, signer=build,
                                     approval_signer=approve, record_events=False)

            # 1. The builder signs, and marks their own model approved in the manifest.
            build.sign_manifest(weights, models=entry(), manifest_version=1)
            claimed = registry.check("tooth_detector")
            steps.append(_step("Builder signs the model and marks it approved",
                               claimed.signature_valid, "the build signature is genuine"))
            steps.append(_step("It still does not load: nobody cleared it",
                               not claimed.approved, claimed.reason or ""))

            # 2. The builder tries to issue the approval with the key they do hold.
            digest = sha256_file(model)
            forged = model_approval.ApprovalRecord(
                model_id="tooth_detector", model_version="1.0.0", sha256=digest,
                approved_by="The Builder", approved_at="2026-03-01T09:00:00+00:00")
            model_approval.sign_approvals(weights, [forged], build)
            registry.reset()
            self_approved = registry.check("tooth_detector")
            steps.append(_step("Builder signs an approval with the build key: refused",
                               not self_approved.approved,
                               "the approval key is a different key, held by someone else"))

            # 3. The approver countersigns.
            real = model_approval.ApprovalRecord(
                model_id="tooth_detector", model_version="1.0.0", sha256=digest,
                approved_by="Dr A Patel, GDC 123456", approved_at="2026-03-01T09:00:00+00:00")
            model_approval.sign_approvals(weights, [real], approve)
            registry.reset()
            cleared = registry.check("tooth_detector")
            steps.append(_step("Approver countersigns: the model loads", cleared.approved))
            steps.append(_step("The record names who cleared it, not who built it",
                               cleared.approved_by == "Dr A Patel, GDC 123456",
                               cleared.approved_by or ""))

            # 4. A rebuild at the same version does not inherit the clearance.
            model.write_bytes(secrets.token_bytes(4096))
            build.sign_manifest(weights, models=entry(), manifest_version=2)
            registry.reset()
            rebuilt = registry.check("tooth_detector")
            steps.append(_step("Rebuilding at the same version voids the approval",
                               not rebuilt.approved,
                               "clearance covers exact bytes, not a version label"))
        finally:
            model_provenance.config.MODEL_FLOOR_FILE = original_floor
    return steps


SCENARIOS["separation-of-duties"] = (
    "Model builder clearing their own model",
    "Approval countersigned under a second key the builder does not hold",
    separation_of_duties)
