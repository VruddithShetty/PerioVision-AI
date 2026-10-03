"""Chairside clinical routes: periodontal charts, care plan, clinic recall board."""
from __future__ import annotations

import datetime as dt

from flask import Blueprint, g, request
from pydantic import ValidationError

from app.api._common import ok, validation_error, visible_patient_ids
from app.api.patients import load_patient_or_404
from app.schemas import PerioChartIn
from app.security.audit_log import audit
from app.security.zero_trust import secured
from app.services import container
from app.services.clinical_service import care_plan, concordance, summarize_chart
from app.services.progression_service import patient_progression

bp = Blueprint("clinical", __name__)


def _latest_analysis(patient_id: int):
    return container.analysis_store().latest_for_patient(patient_id)


@bp.get("/api/patients/<int:patient_id>/perio-charts")
@secured("chart:read")
def list_charts(patient_id):
    """All periodontal charts for a patient (newest first), each with computed indices."""
    patient, err = load_patient_or_404(patient_id)
    if err:
        return err
    charts = container.chart_store().for_patient(patient_id)
    analysis = _latest_analysis(patient_id)
    out = []
    for c in charts:
        summary = summarize_chart(c)
        out.append({**c, "summary": summary, "concordance": concordance(summary, analysis)})
    audit().record("PERIO_CHART_VIEWED", actor=g.user["id"], resource=patient["pseudo_id"])
    return ok(out, radiographic_analysis_id=analysis["analysis_id"] if analysis else None)


@bp.post("/api/patients/<int:patient_id>/perio-charts")
@secured("chart:write")
def create_chart(patient_id):
    """Save a six-point periodontal chart."""
    try:
        body = PerioChartIn.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return validation_error(exc)
    patient, err = load_patient_or_404(patient_id)
    if err:
        return err
    doc = container.chart_store().create({
        "patient_id": patient_id, "pseudo_id": patient["pseudo_id"], "exam_date": body.exam_date,
        "teeth": {k: v.model_dump() for k, v in body.teeth.items()}, "notes": body.notes,
        "examiner_id": g.user["id"], "examiner_name": g.user.get("name"), "source": "clinician_entry",
    })
    summary = summarize_chart(doc)
    audit().record("PERIO_CHART_SAVED", actor=g.user["id"], resource=patient["pseudo_id"],
                   details={"chart_id": doc["chart_id"], "teeth": len(body.teeth)})
    return ok({**doc, "summary": summary, "concordance": concordance(summary, _latest_analysis(patient_id))}, 201)


@bp.get("/api/patients/<int:patient_id>/care-plan")
@secured("care:read")
def get_care_plan(patient_id):
    """EFP step therapy, per-tooth prognosis, recall interval and referral suggestion."""
    patient, err = load_patient_or_404(patient_id)
    if err:
        return err
    analyses = container.analysis_store().for_patient(patient_id)
    latest = analyses[-1] if analyses else None
    progression = patient_progression(analyses) if analyses else {"latest": []}
    plan = care_plan(patient, latest, container.chart_store().latest(patient_id), progression["latest"])
    plan["patient"] = {k: patient.get(k) for k in ("patient_id", "pseudo_id", "patient_name", "age", "sex",
                                                    "smoking_status", "cigarettes_per_day", "diabetic", "hba1c",
                                                    "teeth_lost_perio")}
    plan["analysis_id"] = latest["analysis_id"] if latest else None
    plan["teeth"] = [{"tooth_id": t["tooth_id"], "bone_loss_pct": t.get("bone_loss_pct"), "stage": t.get("stage")}
                     for t in (latest or {}).get("teeth", [])]
    plan["progression"] = progression["latest"]
    audit().record("CARE_PLAN_VIEWED", actor=g.user["id"], resource=patient["pseudo_id"])
    return ok(plan)


@bp.get("/api/recall")
@secured("care:read")
def recall_board():
    """Clinic-wide supportive-care recall list: who is due or overdue, ranked by risk."""
    mgr, analyses, charts = container.patient_manager(), container.analysis_store(), container.chart_store()
    ids = visible_patient_ids()
    patients = mgr.list_patients(g.user["id"], g.user["role"])
    today = dt.date.today()
    rows = []
    for p in patients:
        if ids is not None and p["patient_id"] not in ids:
            continue
        history = analyses.for_patient(p["patient_id"])
        if not history and not charts.latest(p["patient_id"]):
            continue
        progression = patient_progression(history) if history else {"latest": []}
        plan = care_plan(p, history[-1] if history else None, charts.latest(p["patient_id"]), progression["latest"])
        due = dt.date.fromisoformat(plan["next_recall_due"]) if plan["next_recall_due"] else None
        days = (due - today).days if due else None
        status = "overdue" if days is not None and days < 0 else "due soon" if days is not None and days <= 30 else "scheduled"
        rows.append({
            "patient_id": p["patient_id"], "pseudo_id": p["pseudo_id"], "patient_name": p["patient_name"],
            "stage": plan["stage"], "grade": plan["grade"].get("grade"), "risk": plan["risk"],
            "interval_months": plan["recall"]["months"], "last_visit": plan["last_visit"],
            "next_due": plan["next_recall_due"], "days_until_due": days, "status": status,
            "referral_suggested": plan["referral_suggested"],
        })
    order = {"overdue": 0, "due soon": 1, "scheduled": 2}
    risk_order = {"high": 0, "moderate": 1, "low": 2, None: 3}
    rows.sort(key=lambda r: (order[r["status"]], risk_order.get(r["risk"], 3), r["days_until_due"] or 9999))
    audit().record("RECALL_BOARD_VIEWED", actor=g.user["id"], details={"patients": len(rows)})
    return ok(rows, overdue=sum(r["status"] == "overdue" for r in rows),
              due_soon=sum(r["status"] == "due soon" for r in rows))
