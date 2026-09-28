"""Longitudinal progression and clinician review routes."""
from __future__ import annotations

import datetime as dt

from flask import Blueprint, g, request
from pydantic import ValidationError

from app.api._common import fail, ok, validation_error, visible_patient_ids
from app.api.analysis import load_analysis_or_404
from app.api.patients import load_patient_or_404
from app.schemas import ReviewIn
from app.security.audit_log import audit
from app.security.zero_trust import secured
from app.services import container
from app.services.progression_service import patient_progression

bp = Blueprint("progression", __name__)


@bp.get("/api/patients/<int:patient_id>/progression")
@secured("analysis:read")
def progression(patient_id):
    patient, err = load_patient_or_404(patient_id)
    if err:
        return err
    result = patient_progression(container.analysis_store().for_patient(patient_id))
    audit().record("PROGRESSION_VIEWED", actor=g.user["id"], resource=patient["pseudo_id"])
    return ok(result)


@bp.get("/api/review/queue")
@secured("review:read")
def review_queue():
    items = container.analysis_store().review_queue(visible_patient_ids())
    return ok([{"analysis_id": a["analysis_id"], "patient_id": a["patient_id"], "pseudo_id": a["pseudo_id"],
                "visit_date": a["visit_date"], "created": a["created"], "mode": a.get("mode"),
                "reasons": a.get("review", {}).get("reasons", []), "stage": a.get("summary", {}).get("stage"),
                "teeth": len(a.get("teeth", []))} for a in items], count=len(items))


@bp.post("/api/review/<analysis_id>")
@secured("review:signoff")
def sign_off(analysis_id):
    """Approve, correct or reject an analysis. Corrections are stored for future retraining."""
    try:
        body = ReviewIn.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return validation_error(exc)
    a, patient, err = load_analysis_or_404(analysis_id)
    if err:
        return err
    if body.decision == "correct" and not body.corrections:
        return fail(422, "A 'correct' decision needs at least one tooth correction.")
    known = {t["tooth_id"] for t in a.get("teeth", [])}
    unknown = [c.tooth_id for c in body.corrections if c.tooth_id not in known]
    if unknown:
        return fail(422, f"Unknown tooth IDs: {', '.join(unknown)}")

    status = {"approve": "approved", "correct": "corrected", "reject": "rejected"}[body.decision]
    decision = {
        "status": status, "reviewer_id": g.user["id"], "reviewer_name": g.user.get("name"),
        "reviewer_role": g.user["role"], "at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "comment": body.comment, "corrections": [c.model_dump() for c in body.corrections],
    }
    container.analysis_store().record_review(analysis_id, decision)
    if body.corrections:
        from app.models.connection import db

        db["corrections"].insert_many([{**c.model_dump(), "analysis_id": analysis_id,
                                        "pseudo_id": a["pseudo_id"], "reviewer_id": g.user["id"],
                                        "at": decision["at"]} for c in body.corrections])
    audit().record("REVIEW_" + status.upper(), actor=g.user["id"], resource=patient["pseudo_id"],
                   details={"analysis_id": analysis_id, "corrections": len(body.corrections)})
    return ok({"analysis_id": analysis_id, "review": decision})
