"""Role-based access control: four roles and an explicit permission matrix.

Deny by default: a permission that is not listed for a role is refused, and an
unknown permission is refused for everyone. The same matrix is printed in
docs/SECURITY.md and served at GET /api/security/rbac-matrix so the UI can show it.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

ROLES = ("admin", "dentist", "technician", "auditor")

# Older records used different role names; they are mapped, never trusted as-is.
LEGACY_ROLE_MAP = {"superadmin": "admin", "doctor": "dentist", "viewer": "auditor"}

PERMISSIONS: dict[str, set[str]] = {
    "patient:read":        {"admin", "dentist", "technician"},
    "patient:write":       {"admin", "dentist"},
    "radiograph:upload":   {"dentist", "technician"},
    "analysis:run":        {"dentist", "technician"},
    "analysis:read":       {"admin", "dentist", "technician"},
    "chart:read":          {"admin", "dentist", "technician"},
    "chart:write":         {"dentist", "technician"},
    "care:read":           {"admin", "dentist", "technician"},
    "review:read":         {"admin", "dentist"},
    "review:signoff":      {"dentist"},
    "report:generate":     {"dentist"},
    "report:read":         {"admin", "dentist"},
    "audit:read":          {"admin", "auditor"},
    "audit:verify":        {"admin", "auditor"},
    "model:read":          {"admin", "dentist", "auditor"},
    "security_lab:run":    {"admin", "auditor"},
    "security:read":       {"admin", "auditor"},
    "admin:users":         {"admin"},
    "admin:config":        {"admin"},
    "self:manage":         {"admin", "dentist", "technician", "auditor"},
}

# Roles that see every patient; the others see only patients on their own care list.
ALL_PATIENT_ROLES = {"admin"}


def normalize_role(role: str | None) -> str | None:
    if not role:
        return None
    role = LEGACY_ROLE_MAP.get(role.lower(), role.lower())
    return role if role in ROLES else None


def has_permission(role: str | None, permission: str) -> bool:
    role = normalize_role(role)
    return bool(role) and role in PERMISSIONS.get(permission, set())


def permission_matrix() -> dict[str, dict[str, bool]]:
    return {perm: {role: role in roles for role in ROLES} for perm, roles in PERMISSIONS.items()}


def can_access_patient(user_id: str, role: str | None, patient_doc: dict | None) -> bool:
    """Object-level check: may this user see this patient record?"""
    if not patient_doc:
        return False
    role = normalize_role(role)
    if role in ALL_PATIENT_ROLES:
        return True
    if role not in ("dentist", "technician"):
        return False
    care_team = {str(x) for x in patient_doc.get("care_team", [])}
    allowed = str(patient_doc.get("doctor_id")) == str(user_id) or str(user_id) in care_team
    if not allowed:
        logger.warning("[SECURITY] Patient access denied for user %s", user_id)
    return allowed


def patient_query_for(user_id: str, role: str | None, base_query: dict | None = None) -> dict:
    """Mongo filter that restricts a patient query to what the user may see."""
    query = dict(base_query or {})
    role = normalize_role(role)
    if role in ALL_PATIENT_ROLES:
        return query
    if role not in ("dentist", "technician"):
        query["patient_id"] = {"$in": []}  # deny by default
        return query
    query["$or"] = [{"doctor_id": str(user_id)}, {"care_team": str(user_id)}]
    return query


class RBACEnforcer:
    """Thin object wrapper kept for modules written against the old class."""

    def can_access(self, current_role: str, required_role: str) -> bool:
        order = {"auditor": 1, "technician": 2, "dentist": 3, "admin": 4}
        return order.get(normalize_role(current_role) or "", 0) >= order.get(normalize_role(required_role) or "", 99)

    def enforce_patient_access(self, doctor_id: str, role: str, patient_doc: dict) -> bool:
        return can_access_patient(doctor_id, role, patient_doc)

    def filter_query_by_role(self, doctor_id: str, role: str, collection_name: str, base_query: dict | None = None):
        if collection_name == "patients":
            return patient_query_for(doctor_id, role, base_query)
        if collection_name == "xray_records":
            from app.models.connection import db
            visible = [p["patient_id"] for p in db["patients"].find(patient_query_for(doctor_id, role), {"patient_id": 1})]
            query = dict(base_query or {})
            if "patient_id" in query and query["patient_id"] not in visible:
                query["patient_id"] = {"$in": []}
            elif "patient_id" not in query:
                query["patient_id"] = {"$in": visible}
            return query
        return dict(base_query or {})
