"""Response envelope and small helpers shared by all route blueprints.

Every JSON response has the same shape:
    {"data": ..., "meta": {...}, "error": null | {"code": int, "message": str, "details": ...}, "mode": "demo" | "live"}
"""
from __future__ import annotations

from flask import g, jsonify
from pydantic import ValidationError

from app import config


def ok(data=None, status: int = 200, **meta):
    return jsonify({"data": data, "meta": meta, "error": None, "mode": config.APP_MODE}), status


def fail(status: int, message: str, details=None):
    return jsonify({"data": None, "meta": {}, "error": {"code": status, "message": message, "details": details},
                    "mode": config.APP_MODE}), status


def validation_error(exc: ValidationError):
    details = [{"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors()]
    return fail(422, "Some fields are invalid.", details)


def current_user() -> dict:
    return g.user


def visible_patient_ids() -> list[int] | None:
    """None means 'all patients' (admin); otherwise the IDs this user may see."""
    from app.security.rbac import ALL_PATIENT_ROLES, patient_query_for
    from app.services import container

    user = g.user
    if user["role"] in ALL_PATIENT_ROLES:
        return None
    col = container.patient_manager().collection
    return [p["patient_id"] for p in col.find(patient_query_for(user["id"], user["role"]), {"patient_id": 1})]
