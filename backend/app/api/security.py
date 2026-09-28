"""Security, model-trust and administration routes."""
from __future__ import annotations

from flask import Blueprint, g, request
from pydantic import ValidationError

from app import config
from app.api._common import fail, ok, validation_error
from app.schemas import UserCreateIn, UserUpdateIn
from app.security.audit_log import audit
from app.security.rbac import ROLES, permission_matrix
from app.security.zero_trust import secured
from app.services import container

bp = Blueprint("security", __name__)


# ---------- security centre ----------
@bp.get("/api/security/rbac-matrix")
@secured("self:manage")
def rbac_matrix():
    return ok({"roles": list(ROLES), "matrix": permission_matrix()})


@bp.get("/api/security/sessions")
@secured("security:read")
def all_sessions():
    sessions = container.session_store().active_for()
    for s in sessions:
        s["sid"] = s["sid"][:8] + "..."
    return ok(sessions, count=len(sessions))


# ---------- model trust ----------
@bp.get("/api/models/status")
@secured("model:read")
def models_status():
    signer = container.registry().signer
    return ok({"models": container.registry().status(), "public_key_fingerprint": signer.public_key_fingerprint()})


@bp.get("/api/models/trust")
@secured("model:read")
def model_trust():
    from app.ml.fusion.multimodal_risk import MODEL_TYPE, MODEL_VERSION
    from app.ml.uncertainty import calibration

    store = container.analysis_store()
    total = store.count()
    flagged = store.count({"review.status": {"$in": ["review_required", "approved", "corrected", "rejected"]}})
    reasons: dict[str, int] = {}
    for a in store.collection.find({}, {"review.reasons": 1}):
        for r in a.get("review", {}).get("reasons", []):
            reasons[r["code"]] = reasons.get(r["code"], 0) + 1
    return ok({
        "calibration": calibration.report(),
        "analyses_total": total,
        "auto_flagged": flagged,
        "flagged_share": round(flagged / total, 3) if total else None,
        "flag_reasons": reasons,
        "models": container.registry().status(),
        "risk_model": {"type": MODEL_TYPE, "version": MODEL_VERSION},
    })


# ---------- administration ----------
@bp.get("/api/admin/users")
@secured("admin:users")
def list_users():
    return ok(container.doctor_manager().get_all_doctors())


@bp.post("/api/admin/users")
@secured("admin:users")
def create_user():
    try:
        body = UserCreateIn.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return validation_error(exc)
    try:
        user_id = container.doctor_manager().register_doctor(name=body.name, email=body.email, password=body.password,
                                                             clinic_name=body.clinic_name, role=body.role)
    except ValueError as exc:
        return fail(409 if "already" in str(exc) else 422, str(exc))
    audit().record("USER_CREATED", actor=g.user["id"], resource=user_id, details={"role": body.role})
    return ok(container.doctor_manager().get_doctor(user_id), 201)


@bp.patch("/api/admin/users/<user_id>")
@secured("admin:users")
def update_user(user_id):
    try:
        body = UserUpdateIn.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return validation_error(exc)
    users = container.doctor_manager()
    if not users.get_doctor(user_id):
        return fail(404, "User not found.")
    if user_id == g.user["id"] and (body.active is False or (body.role and body.role != "admin")):
        return fail(409, "You cannot demote or disable your own account.")
    if body.role:
        users.set_role(user_id, body.role)
    if body.active is not None:
        users.set_active(user_id, body.active)
        if not body.active:
            container.session_store().revoke_all_for(user_id, reason="disabled_by_admin")
    audit().record("USER_UPDATED", actor=g.user["id"], resource=user_id, details=body.model_dump(exclude_none=True))
    return ok(users.get_doctor(user_id))


@bp.post("/api/admin/users/<user_id>/lock")
@secured("admin:users")
def lock_user(user_id):
    minutes = min(max(int((request.get_json(silent=True) or {}).get("minutes", 60)), 1), 7 * 24 * 60)
    users = container.doctor_manager()
    if not users.get_doctor(user_id):
        return fail(404, "User not found.")
    users.lock_account(user_id, minutes)
    container.session_store().revoke_all_for(user_id, reason="locked_by_admin")
    audit().record("USER_LOCKED", actor=g.user["id"], resource=user_id, details={"minutes": minutes})
    return ok({"locked_minutes": minutes})


@bp.get("/api/admin/config")
@secured("admin:config")
def get_config():
    from app.security.crypto import get_encryptor

    ring = get_encryptor().keyring
    return ok({
        "thresholds": config.THRESHOLDS,
        "thresholds_file": str(config.THRESHOLDS_FILE.relative_to(config.BACKEND_DIR)),
        "encryption": {"algorithm": "AES-256-GCM", "active_key_id": ring.active_kid, "key_ids": list(ring.keys)},
        "signing": {"algorithm": "RSA-PSS-SHA256",
                    "public_key_fingerprint": container.registry().signer.public_key_fingerprint(),
                    "private_key_available": container.registry().signer.has_private_key()},
        "mode": config.APP_MODE,
    })


# ---------- security lab ----------
@bp.get("/api/security-lab")
@secured("security_lab:run")
def lab_scenarios():
    from app.services.security_lab import list_scenarios

    return ok(list_scenarios())


@bp.post("/api/security-lab/<scenario_id>/run")
@secured("security_lab:run")
def lab_run(scenario_id):
    from app.services.security_lab import SCENARIOS, run

    if scenario_id not in SCENARIOS:
        return fail(404, "Unknown scenario.")
    result = run(scenario_id)
    audit().record("SECURITY_LAB_RUN", outcome="defended" if result["defended"] else "not_defended",
                   actor=g.user["id"], details={"scenario": scenario_id})
    return ok(result)


@bp.post("/api/security-lab/run-all")
@secured("security_lab:run")
def lab_run_all():
    from app.services.security_lab import SCENARIOS, run

    results = [run(s) for s in SCENARIOS]
    audit().record("SECURITY_LAB_RUN", outcome="defended" if all(r["defended"] for r in results) else "not_defended",
                   actor=g.user["id"], details={"scenario": "all"})
    return ok(results, defended=sum(r["defended"] for r in results), total=len(results))
