"""Health/status and dashboard routes.

/api/health is public and says only whether each subsystem is OK (no details
an attacker could use). /api/system/status and /api/dashboard need a login.
"""
from __future__ import annotations

from flask import Blueprint, g

from app import config
from app.api._common import ok, visible_patient_ids
from app.security.zero_trust import public, secured
from app.services import container


def _db_ok() -> bool:
    try:
        from app.models.connection import db

        db.list_collection_names()
        return True
    except Exception:
        return False


def system_status() -> dict:
    from app.security.audit_log import audit

    models = container.registry().status()
    chain = audit().verify_chain_integrity()
    return {
        "mode": config.APP_MODE,
        "database": _db_ok(),
        "models": [{"name": m["name"], "present": m["present"], "signature_valid": m["signature_valid"],
                    "loaded": m["loaded"], "reason": m["reason"]} for m in models],
        # a missing OPTIONAL model is fine; a present-but-unsigned one never is
        "models_verified": all(m["signature_valid"] or (m.get("optional") and not m["present"]) for m in models),
        "audit_chain_intact": chain["chain_intact"],
        "audit_entries": chain["entries_verified"],
        "calibrated": config.CALIBRATION_FILE.exists(),
    }


bp = Blueprint("health", __name__)


@bp.get("/")
@public
def index():
    return ok({"service": "PerioVision AI API", "health": "/api/health", "docs": "/api/docs"})


@bp.get("/api/health")
@bp.get("/health")
@public
def health():
    db_ok = _db_ok()
    body, _ = ok({"status": "ok" if db_ok else "degraded", "database": db_ok})
    return body, 200 if db_ok else 503


@bp.get("/api/system/status")
@secured("self:manage")
def status():
    return ok(system_status())


@bp.get("/api/dashboard")
@secured("self:manage")
def dashboard():
    import datetime as dt

    from app.security.rbac import has_permission

    role = g.user["role"]
    data = {"role": role, "system": system_status()}
    if has_permission(role, "analysis:read"):
        ids = visible_patient_ids()
        store = container.analysis_store()
        scope = {} if ids is None else {"patient_id": {"$in": ids}}
        today = dt.date.today().isoformat()
        data.update({
            "patients": len(ids) if ids is not None else container.patient_manager().collection.count_documents(
                {"deleted": {"$ne": True}, "doctor_id": {"$ne": "system-decoy-owner"}}),
            "analyses_total": store.count(scope),
            "analyses_today": store.count({**scope, "created": {"$gte": today}}),
            "flagged_for_review": store.count({**scope, "review.status": "review_required"}),
            "stage_distribution": {s: store.count({**scope, "summary.stage": s}) for s in ("I", "II", "III", "IV")},
            "risk_distribution": {r: store.count({**scope, "risk.fusion.level": r}) for r in ("low", "moderate", "high")},
            "recent": [{"analysis_id": a["analysis_id"], "pseudo_id": a["pseudo_id"], "visit_date": a["visit_date"],
                        "created": a["created"], "review_status": a.get("review", {}).get("status"),
                        "mode": a.get("mode")} for a in store.recent(8, ids)],
        })
    if has_permission(role, "audit:read"):
        from app.security.audit_log import audit

        data["recent_security_events"] = [e for e in audit().recent(50) if e["outcome"] not in ("success",)][:10]
    return ok(data)
