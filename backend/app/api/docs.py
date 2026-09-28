"""Machine-readable API description generated from the registered routes.

GET /api/docs returns an OpenAPI 3.0 document built from three sources of truth:
* the Flask URL map (every route that exists),
* the Zero Trust decorators (public, or which RBAC permission is required: `x-permission`),
* the pydantic request schemas (JSON bodies are described from the same classes that validate them).
So the documentation cannot drift from what is actually enforced.
"""
from __future__ import annotations

import re

from flask import Blueprint, current_app, jsonify

from app import schemas
from app.security.zero_trust import public

bp = Blueprint("docs", __name__)

# endpoint -> (request model, content type). Multipart uploads are described by hand.
REQUEST_BODIES = {
    "auth.login": schemas.LoginIn,
    "auth.mfa_step": schemas.MfaIn,
    "auth.mfa_confirm": schemas.TotpCodeIn,
    "auth.mfa_disable": schemas.TotpCodeIn,
    "patients.create_patient": schemas.PatientIn,
    "patients.update_patient": schemas.PatientUpdateIn,
    "analysis.create_analysis": schemas.AnalyzeIn,
    "progression.sign_off": schemas.ReviewIn,
    "reports.generate": schemas.ReportIn,
    "security.create_user": schemas.UserCreateIn,
    "security.update_user": schemas.UserUpdateIn,
    "clinical.create_chart": schemas.PerioChartIn,
}
MULTIPART = {
    "radiographs.upload": ("image", "PNG, JPEG or DICOM radiograph (≤ 16 MB)"),
    "reports.verify_upload": ("file", "The signed PDF report to verify"),
}
BINARY = {"analysis.analysis_image": "image/png", "reports.download": "application/pdf"}

# Human summaries for routes whose docstring is missing or too technical.
SUMMARIES = {
    "health.health": "Liveness and database check (no sensitive detail)",
    "health.index": "Service banner",
    "health.status": "System status widget: DB, model signatures, audit chain, calibration",
    "health.dashboard": "Role-aware dashboard numbers",
    "auth.login": "Sign in with email and password (returns an access token or an MFA challenge)",
    "auth.mfa_step": "Complete sign-in with a 6-digit TOTP code",
    "auth.refresh": "Get a new access token from the refresh cookie (rotates it)",
    "auth.logout": "Sign out and revoke this session",
    "auth.me": "Current user and their permissions",
    "auth.mfa_enroll": "Start TOTP enrolment (QR code)",
    "auth.mfa_confirm": "Confirm TOTP enrolment with a code",
    "auth.mfa_disable": "Turn TOTP off (needs a current code)",
    "auth.my_sessions": "My active sessions",
    "patients.list_patients": "List or search patients (exact name or pseudonym)",
    "patients.create_patient": "Create a patient (identity fields are encrypted)",
    "patients.get_patient": "Patient detail with visit history",
    "patients.update_patient": "Update patient details or clinical risk factors",
    "patients.add_care_team": "Add a clinician to a patient's care team",
    "radiographs.upload": "Upload a radiograph (upload guard + quality preview)",
    "analysis.create_analysis": "Run the full analysis pipeline on an upload",
    "analysis.list_analyses": "Recent analyses visible to you",
    "analysis.get_analysis": "Analysis detail: teeth, uncertainty, risk, review status",
    "analysis.analysis_image": "Decrypted image layer (radiograph, annotated, gradcam)",
    "progression.progression": "Tooth-by-tooth progression across visits",
    "progression.review_queue": "Cases waiting for mandatory clinician review",
    "reports.generate": "Generate a signed PDF report (needs sign-off first)",
    "reports.list_reports": "Signed reports visible to you",
    "reports.download": "Download a report PDF",
    "reports.verify_by_id": "Public: verify a report by its ID (QR code)",
    "reports.verify_upload": "Public: verify an uploaded PDF",
    "audit.logs": "Browse the tamper-evident audit log",
    "audit.verify": "Verify the hash chain and Merkle anchors",
    "audit.anchor": "Publish (anchor) a Merkle root now",
    "security.rbac_matrix": "Role permission matrix",
    "security.all_sessions": "Active sessions of all users",
    "security.models_status": "Model files and signature status",
    "security.model_trust": "Calibration, flagged share and model integrity",
    "security.list_users": "List user accounts",
    "security.create_user": "Create a user account",
    "security.update_user": "Change a user's role or disable them",
    "security.lock_user": "Lock a user for a number of minutes",
    "security.get_config": "Thresholds, key IDs and signing status",
    "security.lab_scenarios": "List Security Lab attack simulations",
    "security.lab_run": "Run one attack simulation",
    "security.lab_run_all": "Run every attack simulation",
}

ENVELOPE = {
    "type": "object",
    "required": ["data", "meta", "error", "mode"],
    "properties": {
        "data": {"description": "Payload (object, list or null on error)"},
        "meta": {"type": "object", "description": "Extra information such as counts"},
        "error": {
            "nullable": True,
            "type": "object",
            "properties": {"code": {"type": "integer"}, "message": {"type": "string"}, "details": {}},
        },
        "mode": {"type": "string", "enum": ["demo", "live"]},
    },
}


def _schema_refs(components: dict, model) -> dict:
    schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
    for name, sub in schema.pop("$defs", {}).items():
        components[name] = sub
    components[model.__name__] = schema
    return {"$ref": f"#/components/schemas/{model.__name__}"}


def build_spec(app) -> dict:
    components: dict = {"Envelope": ENVELOPE}
    paths: dict = {}
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api/") or rule.endpoint == "static":
            continue
        view = app.view_functions[rule.endpoint]
        path = re.sub(r"<(?:[a-z]+:)?([a-z_]+)>", r"{\1}", rule.rule)
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            doc = (view.__doc__ or "").strip().splitlines()
            perm = getattr(view, "zero_trust_permission", None)
            ok_content = ({BINARY[rule.endpoint]: {"schema": {"type": "string", "format": "binary"}}}
                          if rule.endpoint in BINARY
                          else {"application/json": {"schema": {"$ref": "#/components/schemas/Envelope"}}})
            responses = {"200": {"description": "Success", "content": ok_content}}
            if method == "POST":
                responses["201"] = {"description": "Created", "content": ok_content}
            if perm:
                responses["401"] = {"description": "Missing, expired or invalid token / session (Zero Trust check)"}
                responses["403"] = {"description": "Role lacks the permission, or account blocked"}
            if rule.endpoint in REQUEST_BODIES or rule.endpoint in MULTIPART:
                responses["422"] = {"description": "Validation failed; error.details lists each field"}
            op = {
                "summary": SUMMARIES.get(rule.endpoint) or (doc[0] if doc else rule.endpoint.split(".")[-1].replace("_", " ")),
                "operationId": f"{rule.endpoint.replace('.', '_')}_{method.lower()}",
                "tags": [rule.endpoint.split(".")[0]],
                "responses": responses,
                "security": [{"bearerAuth": []}] if perm else [],
            }
            if perm:
                op["x-permission"] = perm
            params = re.findall(r"{([a-z_]+)}", path)
            if params:
                op["parameters"] = [{"name": p, "in": "path", "required": True,
                                     "schema": {"type": "integer" if p == "patient_id" else "string"}} for p in params]
            if method in ("POST", "PATCH"):
                if rule.endpoint in REQUEST_BODIES:
                    op["requestBody"] = {"required": True, "content": {
                        "application/json": {"schema": _schema_refs(components, REQUEST_BODIES[rule.endpoint])}}}
                elif rule.endpoint in MULTIPART:
                    field, desc = MULTIPART[rule.endpoint]
                    op["requestBody"] = {"required": True, "content": {"multipart/form-data": {"schema": {
                        "type": "object", "required": [field],
                        "properties": {field: {"type": "string", "format": "binary", "description": desc}}}}}}
            paths.setdefault(path, {})[method.lower()] = op
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "PerioVision AI API",
            "version": "2.0",
            "description": ("Research prototype for periodontal decision support. Every JSON response uses the envelope "
                            "{data, meta, error, mode}. Authenticate with POST /api/auth/login, then send "
                            "'Authorization: Bearer <access_token>'. x-permission names the RBAC permission each "
                            "operation requires (see docs/SECURITY.md)."),
        },
        "servers": [{"url": "http://127.0.0.1:5000"}],
        "components": {
            "securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}},
            "schemas": dict(sorted(components.items())),
        },
        "paths": dict(sorted(paths.items())),
    }


@bp.get("/api/docs")
@public
def openapi():
    """OpenAPI 3.0 description of this API."""
    return jsonify(build_spec(current_app))
