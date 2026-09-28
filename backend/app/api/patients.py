"""Patient routes: list/search, create, view, update, care team."""
from __future__ import annotations

from flask import Blueprint, g, request
from pydantic import ValidationError

from app.api._common import fail, ok, validation_error
from app.schemas import PatientIn, PatientUpdateIn
from app.security.audit_log import audit
from app.security.zero_trust import secured
from app.services import container

bp = Blueprint("patients", __name__)


def load_patient_or_404(patient_id):
    """Fetch a patient the current user may see. Honeypot records trigger an incident."""
    mgr = container.patient_manager()
    raw = mgr.get_raw(patient_id)
    if raw:
        from app.security.honeypot import HoneypotManager

        honeypot = HoneypotManager()
        if honeypot.is_decoy(raw["patient_id"]):
            honeypot.on_access(raw, g.user["id"])
            return None, fail(404, "Patient not found.")
    patient = mgr.get_patient(patient_id, g.user["id"], g.user["role"])
    if not patient:
        audit().record("PATIENT_ACCESS_DENIED", outcome="denied", actor=g.user["id"], resource=str(patient_id)[:12])
        return None, fail(404, "Patient not found.")
    return patient, None


@bp.get("/api/patients")
@secured("patient:read")
def list_patients():
    search = (request.args.get("q") or "").strip()[:120] or None
    patients = container.patient_manager().list_patients(g.user["id"], g.user["role"], search)
    audit().record("PATIENT_LIST", actor=g.user["id"], details={"count": len(patients), "search": bool(search)})
    return ok(patients, count=len(patients))


@bp.post("/api/patients")
@secured("patient:write")
def create_patient():
    try:
        body = PatientIn.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return validation_error(exc)
    patient = container.patient_manager().create_patient(body.model_dump(), owner_id=g.user["id"])
    audit().record("PATIENT_CREATED", actor=g.user["id"], resource=patient["pseudo_id"])
    return ok(patient, 201)


@bp.get("/api/patients/<int:patient_id>")
@secured("patient:read")
def get_patient(patient_id):
    patient, err = load_patient_or_404(patient_id)
    if err:
        return err
    audit().record("PATIENT_VIEWED", actor=g.user["id"], resource=patient["pseudo_id"])
    analyses = container.analysis_store().for_patient(patient_id)
    patient["analyses"] = [{"analysis_id": a["analysis_id"], "visit_date": a["visit_date"], "mode": a.get("mode"),
                            "review_status": a.get("review", {}).get("status"),
                            "stage": a.get("summary", {}).get("stage"),
                            "risk": a.get("risk", {}).get("category")} for a in analyses]
    return ok(patient)


@bp.patch("/api/patients/<int:patient_id>")
@secured("patient:write")
def update_patient(patient_id):
    try:
        body = PatientUpdateIn.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return validation_error(exc)
    _p, err = load_patient_or_404(patient_id)
    if err:
        return err
    patient = container.patient_manager().update_patient(patient_id, body.model_dump(exclude_unset=True),
                                                         g.user["id"], g.user["role"])
    audit().record("PATIENT_UPDATED", actor=g.user["id"], resource=patient["pseudo_id"])
    return ok(patient)


@bp.post("/api/patients/<int:patient_id>/care-team")
@secured("admin:users")
def add_care_team(patient_id):
    member = str((request.get_json(silent=True) or {}).get("user_id", ""))[:64]
    patient, err = load_patient_or_404(patient_id)
    if err:
        return err
    if not container.doctor_manager().get_doctor(member):
        return fail(404, "User not found.")
    container.patient_manager().add_to_care_team(patient_id, member)
    audit().record("CARE_TEAM_ADDED", actor=g.user["id"], resource=patient["pseudo_id"], details={"member": member})
    return ok({"patient_id": patient_id, "added": member})
