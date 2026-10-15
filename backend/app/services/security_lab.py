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
