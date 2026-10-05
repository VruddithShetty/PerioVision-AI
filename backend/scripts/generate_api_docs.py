"""Generate docs/API.md (with REAL request/response examples) and docs/openapi.json.

It starts the app in demo mode with throwaway keys and temporary folders, signs in as each role,
calls every documented endpoint once, and records what was sent and what came back. Because the
examples are captured from live calls, the documentation matches the running code.

    cd backend && python scripts/generate_api_docs.py
"""
import io
import json
import os
import secrets
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
TMP = Path(tempfile.mkdtemp(prefix="pv-apidocs-"))
PW = {r: f"Docs-{r}-{secrets.token_hex(3)}7" for r in ("dentist", "technician", "auditor", "admin")}
os.environ.update({
    "DB_MODE": "demo", "RATELIMIT_ENABLED": "0", "SECRETS_AUDIT_ON_STARTUP": "false",
    "WEIGHTS_DIR": str(TMP / "weights"), "KEYS_DIR": str(TMP / "keys"), "STORAGE_DIR": str(TMP / "storage"),
    "LOGS_DIR": str(TMP / "logs"), "FIELD_ENCRYPTION_KEYS": f"d1:{secrets.token_hex(32)}", "FIELD_ENCRYPTION_ACTIVE_KID": "d1",
    "JWT_SECRET_KEY": secrets.token_hex(32), "AUDIT_ANCHOR_KEY": secrets.token_hex(32),
    "MODEL_SIGNING_PASSWORD": "Docs-" + secrets.token_hex(8), "SEED_DEMO_DATA": "1",
    "DEMO_EMAIL": "dentist@example.test", "DEMO_PASSWORD": PW["dentist"],
    "DEMO_TECHNICIAN_EMAIL": "technician@example.test", "DEMO_TECHNICIAN_PASSWORD": PW["technician"],
    "DEMO_AUDITOR_EMAIL": "auditor@example.test", "DEMO_AUDITOR_PASSWORD": PW["auditor"],
    "DEMO_ADMIN_EMAIL": "admin@example.test", "DEMO_ADMIN_PASSWORD": PW["admin"],
})
os.environ.pop("FIELD_ENCRYPTION_KEY", None)

from app.security.model_signing import Signer  # noqa: E402

Signer().generate_keypair()
from app import create_app  # noqa: E402
from app.api.docs import build_spec  # noqa: E402
from app.ml import synthetic  # noqa: E402

UA = {"User-Agent": "api-docs-generator"}
app = create_app()
client = app.test_client()
calls: list[dict] = []


def shorten(obj, depth=0):
    """Keep examples readable: trim long strings, lists and deep nesting."""
    if isinstance(obj, str):
        return obj if len(obj) <= 70 else obj[:40] + "…" + obj[-12:]
    if isinstance(obj, list):
        items = [shorten(x, depth + 1) for x in obj[:2]]
        if len(obj) > 2:
            items.append(f"… {len(obj) - 2} more")
        return items
    if isinstance(obj, dict):
        if depth > 4:
            return "{…}"
        keys = list(obj)
        out = {k: shorten(obj[k], depth + 1) for k in keys[:14]}
        if len(keys) > 14:
            out["…"] = f"{len(keys) - 14} more fields"
        return out
    return obj


def call(section, title, method, path, headers=None, json_body=None, data=None, note=None, expect=None):
    kwargs = {"headers": {**UA, **(headers or {})}}
    if json_body is not None:
        kwargs["json"] = json_body
    if data is not None:
        kwargs["data"] = data
        kwargs["content_type"] = "multipart/form-data"
    r = client.open(path, method=method, **kwargs)
    body = r.get_json(silent=True)
    if expect and r.status_code != expect:
        raise SystemExit(f"{method} {path} returned {r.status_code}: {body}")
    calls.append({"section": section, "title": title, "method": method, "path": path, "status": r.status_code,
                  "request": shorten(json_body) if json_body is not None else ("multipart form" if data else None),
                  "response": shorten(body) if body is not None else f"<{r.mimetype}, {len(r.data)} bytes>",
                  "note": note})
    return body


def login(role):
    r = client.post("/api/auth/login", json={"email": f"{role}@example.test", "password": PW[role]}, headers=UA)
    return {"Authorization": f"Bearer {r.get_json()['data']['access_token']}"}


# ---------------------------------------------------------------- exercise the API
call("Health", "Public health check", "GET", "/api/health", expect=200)
r = client.post("/api/auth/login", json={"email": "dentist@example.test", "password": PW["dentist"]}, headers=UA)
calls.append({"section": "Authentication", "title": "Sign in", "method": "POST", "path": "/api/auth/login", "status": r.status_code,
              "request": {"email": "dentist@example.test", "password": "<password>"}, "response": shorten(r.get_json()),
              "note": "Also sets the httpOnly `pv_refresh` cookie (path /api/auth). If MFA is on, returns {mfa_required, mfa_token} instead."})
D = {"Authorization": f"Bearer {r.get_json()['data']['access_token']}"}
call("Authentication", "Wrong password (generic error)", "POST", "/api/auth/login",
     json_body={"email": "dentist@example.test", "password": "wrong-Password-1"})
call("Authentication", "Current user and permissions", "GET", "/api/auth/me", headers=D, expect=200)
call("Authentication", "Refresh the access token", "POST", "/api/auth/refresh", note="Uses the refresh cookie; the old refresh token is rotated and can never be reused.")
call("Authentication", "Start TOTP enrolment (QR code)", "POST", "/api/auth/mfa/enroll", headers=D, expect=200)
call("Authentication", "My active sessions", "GET", "/api/auth/sessions", headers=D, expect=200)
call("Authentication", "Request without a token", "GET", "/api/patients", note="Every protected route answers 401 like this.")

T, A, ADM = login("technician"), login("auditor"), login("admin")
call("Dashboard & status", "Role-aware dashboard", "GET", "/api/dashboard", headers=D, expect=200)
call("Dashboard & status", "System status widget", "GET", "/api/system/status", headers=D, expect=200)

p = call("Patients", "Create a patient", "POST", "/api/patients", headers=D, expect=201, json_body={
    "name": "Example Patient", "age": 47, "sex": "female", "smoking_status": "current", "cigarettes_per_day": 8,
    "diabetic": True, "hba1c": 7.2})
pid = p["data"]["patient_id"]
call("Patients", "Validation error", "POST", "/api/patients", headers=D, json_body={"name": "", "age": 300, "extra": 1},
     note="Unknown fields and out-of-range values are rejected; nothing reaches the database.")
call("Patients", "List / search patients", "GET", "/api/patients?q=Example%20Patient", headers=D, expect=200)
call("Patients", "Patient detail with visits", "GET", f"/api/patients/{pid}", headers=D, expect=200)
call("Patients", "Update clinical fields", "PATCH", f"/api/patients/{pid}", headers=D, json_body={"hba1c": 6.8}, expect=200)
call("Patients", "Auditor cannot read PHI", "GET", "/api/patients", headers=A, note="403: RBAC denies patient:read to auditors.")

up = call("Radiographs & analysis", "Upload a radiograph", "POST", "/api/radiographs", headers=D, expect=201,
          data={"image": (io.BytesIO(synthetic.to_png(synthetic.make_radiograph([18] * 12))), "scan.png")})
call("Radiographs & analysis", "Disguised file is blocked", "POST", "/api/radiographs", headers=D,
     data={"image": (io.BytesIO(b"MZ\x90\x00" + b"\x00" * 200), "xray.png")})
an = call("Radiographs & analysis", "Run the analysis pipeline", "POST", "/api/analyses", headers=D, expect=201,
          json_body={"upload_id": up["data"]["upload_id"], "patient_id": pid, "visit_date": "2026-09-01"})
aid = an["data"]["analysis_id"]
call("Radiographs & analysis", "Analysis detail", "GET", f"/api/analyses/{aid}", headers=D, expect=200)
call("Radiographs & analysis", "Image layer (decrypted on the fly)", "GET", f"/api/analyses/{aid}/image/annotated", headers=D, expect=200,
     note="Layers: radiograph, annotated, gradcam (when a verified model ran). Sent with Cache-Control: no-store.")
call("Radiographs & analysis", "Recent analyses", "GET", "/api/analyses?limit=5", headers=D, expect=200)

call("Progression & review", "Progression across visits", "GET", f"/api/patients/{pid}/progression", headers=D, expect=200)
call("Progression & review", "Review queue", "GET", "/api/review/queue", headers=D, expect=200)
tooth = an["data"]["teeth"][0]["tooth_id"]
call("Progression & review", "Sign off with a correction", "POST", f"/api/review/{aid}", headers=D, expect=200, json_body={
    "decision": "correct", "comment": "Crest confirmed clinically",
    "corrections": [{"tooth_id": tooth, "bone_loss_pct": 21.0, "stage": "II", "note": None}]})
call("Progression & review", "Technician cannot sign off", "POST", f"/api/review/{aid}", headers=T, json_body={"decision": "approve"})

rep = call("Reports", "Generate a signed PDF report", "POST", "/api/reports", headers=D, expect=201, json_body={"analysis_id": aid})
rid = rep["data"]["report_id"]
call("Reports", "List reports", "GET", "/api/reports", headers=D, expect=200)
call("Reports", "Download the PDF", "GET", f"/api/reports/{rid}/download", headers=D, expect=200)
call("Reports", "Public verification by ID (QR code)", "GET", f"/api/reports/verify/{rid}", expect=200)

chart = {"exam_date": "2026-09-01", "teeth": {tooth: {"pd": [5, 3, 4, 4, 3, 5], "rec": [1, 0, 0, 1, 0, 1],
                                                      "bop": [True, False, True, False, False, True],
                                                      "plaque": [False] * 6, "mobility": 0, "furcation": 0, "missing": False}}}
call("Chairside clinical tools", "Save a 6-point perio chart", "POST", f"/api/patients/{pid}/perio-charts", headers=D, json_body=chart, expect=201)
call("Chairside clinical tools", "Perio charts with concordance", "GET", f"/api/patients/{pid}/perio-charts", headers=D, expect=200)
call("Chairside clinical tools", "Care plan", "GET", f"/api/patients/{pid}/care-plan", headers=D, expect=200)
call("Chairside clinical tools", "Clinic recall board", "GET", "/api/recall", headers=D, expect=200)

call("Audit & security", "Audit log", "GET", "/api/audit/logs?limit=3", headers=A, expect=200)
call("Audit & security", "Verify the hash chain", "GET", "/api/audit/verify", headers=A, expect=200)
call("Audit & security", "Anchor a Merkle root", "POST", "/api/audit/anchor", headers=A, expect=201)
call("Audit & security", "RBAC matrix", "GET", "/api/security/rbac-matrix", headers=A, expect=200)
call("Audit & security", "Active sessions (all users)", "GET", "/api/security/sessions", headers=A, expect=200)
call("Audit & security", "Security Lab scenarios", "GET", "/api/security-lab", headers=A, expect=200)
call("Audit & security", "Run one attack simulation", "POST", "/api/security-lab/audit-tamper/run", headers=A, expect=200)

call("Model trust", "Model signature status", "GET", "/api/models/status", headers=D, expect=200)
call("Model trust", "Model trust report", "GET", "/api/models/trust", headers=D, expect=200)

call("Administration", "List users", "GET", "/api/admin/users", headers=ADM, expect=200)
u = call("Administration", "Create a user", "POST", "/api/admin/users", headers=ADM, expect=201, json_body={
    "name": "New Hygienist", "email": "hygienist@example.test", "password": "Strong-Password-9", "role": "technician",
    "clinic_name": None})
call("Administration", "Change role / disable", "PATCH", f"/api/admin/users/{u['data']['doctor_id']}", headers=ADM,
     json_body={"role": "dentist"}, expect=200)
call("Administration", "Configuration, keys and thresholds", "GET", "/api/admin/config", headers=ADM, expect=200)
call("Authentication", "Sign out (revokes the session)", "POST", "/api/auth/logout", headers=D, expect=200)

# ---------------------------------------------------------------- write the docs
spec = build_spec(app)
docs = BACKEND.parent / "docs"
(docs / "openapi.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")

ops = [(path, m, op) for path, ms in spec["paths"].items() for m, op in ms.items()]
lines = [
    "# PerioVision AI: REST API",
    "",
    "_Generated by `backend/scripts/generate_api_docs.py` from live calls against the app in demo mode. "
    "The machine-readable spec is `docs/openapi.json`, also served at `GET /api/docs`._",
    "",
    "## Conventions",
    "",
    "- **Base URL:** `http://127.0.0.1:5000` (the frontend dev server proxies `/api`).",
    "- **Envelope:** every JSON response is `{\"data\": …, \"meta\": {…}, \"error\": null | {code, message, details}, \"mode\": \"demo\" | \"live\"}`.",
    "- **Auth:** `POST /api/auth/login` returns a 15-minute access token; send it as `Authorization: Bearer <token>`. "
    "The refresh token is an httpOnly cookie used only by `POST /api/auth/refresh`.",
    "- **Zero Trust:** every protected request re-checks token, server-side session, device, account state and the RBAC "
    "permission listed below. Routes without a permission are denied by default.",
    "- **Errors:** 401 not authenticated, 403 not allowed, 404 not found (also used for records you may not see), "
    "409 conflict (e.g. report before sign-off), 415 rejected upload, 422 validation (`error.details` lists fields), 429 rate limit.",
    "- **Privacy:** patients appear in logs only as pseudonyms (`P-…`); radiographs and reports are stored AES-256-GCM encrypted.",
    "- **Accuracy figures carry their test type.** `GET /api/models/trust` returns `evidence.rows`, each with `test_type`: "
    "*same-source held-out* (unseen data from the training dataset), *same-hospital held-out*, *temporal hold-out* "
    "(same survey, later cycle) or *cross-source external* (another hospital, population or labelling protocol). Only "
    "the last says anything about other sites. The table below is the deployed, signed `weights/evidence_summary.json` "
    "(`python -m research.compute_ci`); the example response further down comes from a demo instance without it.",
    "",
]
_ev = BACKEND / "weights" / "evidence_summary.json"
if _ev.exists():
    _rows = json.loads(_ev.read_text(encoding="utf-8"))["rows"]
    lines += ["### Accuracy figures by test type", "", "| Test type | Model / test set | Metric | Value | n |", "|---|---|---|---|---|"]
    for _r in sorted(_rows, key=lambda r: (r["test_type"], r["task"])):
        _v = f"{_r['value'] * 100:.1f} %" if _r["pct"] else f"{_r['value']:.3f}"
        lines.append(f"| {_r['test_type']} | {_r['task']} | {_r['metric']} | {_v} | {_r['n']}"
                     f"{' (small sample)' if _r['small_sample'] else ''} |")
    lines.append("")
lines += [
    "## Endpoint index",
    "",
    "| Method | Path | Permission | Summary |",
    "|---|---|---|---|",
]
for path, m, op in ops:
    lines.append(f"| {m.upper()} | `{path}` | {op.get('x-permission', 'public')} | {op['summary']} |")
lines += ["", "## Examples", ""]
section = None
for c in calls:
    if c["section"] != section:
        section = c["section"]
        lines += [f"### {section}", ""]
    lines += [f"#### {c['title']}", "", f"`{c['method']} {c['path']}` → **{c['status']}**", ""]
    if c["note"]:
        lines += [c["note"], ""]
    if c["request"] is not None:
        req = c["request"] if isinstance(c["request"], str) else json.dumps(c["request"], indent=2, ensure_ascii=False)
        lines += ["Request:", "", "```json" if not isinstance(c["request"], str) else "```", req, "```", ""]
    resp = c["response"] if isinstance(c["response"], str) else json.dumps(c["response"], indent=2, ensure_ascii=False)
    lines += ["Response:", "", "```json" if not isinstance(c["response"], str) else "```", resp, "```", ""]
(docs / "API.md").write_text("\n".join(lines), encoding="utf-8")
print(f"Wrote docs/API.md ({len(calls)} examples, {len(ops)} operations) and docs/openapi.json")
