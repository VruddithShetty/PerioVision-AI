"""Analysis routes: run the pipeline on an upload, view results, and stream the (decrypted) image layers."""
from __future__ import annotations

import io
import logging

from flask import Blueprint, g, request, send_file
from pydantic import ValidationError

from app.api._common import fail, ok, validation_error
from app.api.patients import load_patient_or_404
from app.api.radiographs import take_upload
from app.extensions import limiter
from app.schemas import AnalyzeIn
from app.security.audit_log import audit
from app.security.zero_trust import secured
from app.services import container, storage_service
from app.services.analysis_service import ModelsUnavailable, QualityRejected, explain_tooth, run_analysis

bp = Blueprint("analysis", __name__)
logger = logging.getLogger(__name__)
LAYERS = {"radiograph", "annotated", "gradcam"}


def public_view(a: dict) -> dict:
    """Analysis as returned to the client: blob IDs become image URLs."""
    view = {k: v for k, v in a.items() if k not in ("blobs",)}
    view["images"] = {layer: f"/api/analyses/{a['analysis_id']}/image/{layer}" for layer in a.get("blobs", {})}
    return view


def load_analysis_or_404(analysis_id: str):
    a = container.analysis_store().get(analysis_id)
    if not a:
        return None, None, fail(404, "Analysis not found.")
    patient, err = load_patient_or_404(a["patient_id"])
    if err:
        return None, None, err
    return a, patient, None


@bp.post("/api/analyses")
@secured("analysis:run")
@limiter.limit("10 per minute")
def create_analysis():
    try:
        body = AnalyzeIn.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return validation_error(exc)
    patient, err = load_patient_or_404(body.patient_id)
    if err:
        return err
    upload = take_upload(body.upload_id, g.user["id"])
    if not upload:
        return fail(404, "Upload not found, already used, or expired. Please upload the radiograph again.")
    raw_patient = container.patient_manager().get_raw(body.patient_id)
    study = upload.get("study_date") or ""
    study_iso = f"{study[:4]}-{study[4:6]}-{study[6:8]}" if len(study) == 8 and study.isdigit() else None
    try:
        record = run_analysis(
            upload["png_bytes"], raw_patient, g.user, visit_date=body.visit_date or study_iso,
            pixel_spacing_mm=upload.get("pixel_spacing_mm"),
            upload_meta={k: upload.get(k) for k in ("kind", "width", "height", "removed_metadata")})
    except QualityRejected as exc:
        return fail(422, "The radiograph did not pass the quality check.", exc.quality)
    except ModelsUnavailable:
        return fail(503, "No verified AI model is loaded (missing or failed its signature check), so this radiograph "
                         "cannot be analysed. Nothing was estimated. Ask the administrator to restore and re-sign the "
                         "model files.")
    except Exception:
        logger.exception("Analysis failed")
        audit().record("ANALYSIS_FAILED", outcome="error", actor=g.user["id"], resource=patient["pseudo_id"])
        return fail(500, "The analysis could not be completed. The error has been logged.")
    return ok(public_view(record), 201)


@bp.get("/api/analyses/<analysis_id>")
@secured("analysis:read")
def get_analysis(analysis_id):
    a, patient, err = load_analysis_or_404(analysis_id)
    if err:
        return err
    audit().record("ANALYSIS_VIEWED", actor=g.user["id"], resource=patient["pseudo_id"],
                   details={"analysis_id": analysis_id})
    view = public_view(a)
    view["patient"] = {"patient_id": patient["patient_id"], "pseudo_id": patient["pseudo_id"],
                       "name": patient.get("patient_name"), "age": patient.get("age")}
    return ok(view)


@bp.get("/api/analyses/<analysis_id>/image/<layer>")
@secured("analysis:read")
def analysis_image(analysis_id, layer):
    if layer not in LAYERS:
        return fail(404, "Unknown image layer.")
    a, _patient, err = load_analysis_or_404(analysis_id)
    if err:
        return err
    blob = a.get("blobs", {}).get(layer)
    if not blob:
        return fail(404, "This layer is not available for this analysis.")
    try:
        data = storage_service.get(blob, layer)
    except Exception:
        audit().record("STORAGE_INTEGRITY_FAILURE", outcome="error", actor=g.user["id"],
                       details={"analysis_id": analysis_id, "layer": layer})
        return fail(409, "Stored image failed its integrity check.")
    resp = send_file(io.BytesIO(data), mimetype="image/png", max_age=0)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.get("/api/analyses/<analysis_id>/teeth/<tooth_id>/gradcam")
@secured("analysis:read")
@limiter.limit("30 per minute")
def tooth_gradcam(analysis_id, tooth_id):
    """Grad-CAM of one tooth's detection only (computed on demand from the stored radiograph)."""
    a, patient, err = load_analysis_or_404(analysis_id)
    if err:
        return err
    if not any(t["tooth_id"] == tooth_id for t in a.get("teeth", [])):
        return fail(404, "Tooth not found in this analysis.")
    try:
        out = explain_tooth(a, tooth_id)
    except Exception:
        logger.exception("Per-tooth Grad-CAM failed")
        audit().record("STORAGE_INTEGRITY_FAILURE", outcome="error", actor=g.user["id"],
                       details={"analysis_id": analysis_id, "layer": "radiograph"})
        return fail(409, "The stored radiograph could not be read for this explanation.")
    if out is None:
        return fail(404, "Per-tooth Grad-CAM needs a verified model (not available in demo mode).")
    audit().record("GRADCAM_TOOTH_VIEWED", actor=g.user["id"], resource=patient["pseudo_id"],
                   details={"analysis_id": analysis_id, "tooth_id": tooth_id})
    resp = send_file(io.BytesIO(out["png"]), mimetype="image/png", max_age=0)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-ROI-Attention"] = "" if out["roi_attention"] is None else str(out["roi_attention"])
    resp.headers["X-Explained-Model"] = out["model"]
    return resp


@bp.get("/api/analyses")
@secured("analysis:read")
def list_analyses():
    from app.api._common import visible_patient_ids

    limit = min(int(request.args.get("limit", 20) or 20), 100)
    items = container.analysis_store().recent(limit, visible_patient_ids())
    return ok([{"analysis_id": a["analysis_id"], "pseudo_id": a["pseudo_id"], "patient_id": a["patient_id"],
                "visit_date": a["visit_date"], "mode": a.get("mode"), "created": a["created"],
                "review_status": a.get("review", {}).get("status"), "stage": a.get("summary", {}).get("stage"),
                "risk": a.get("risk", {}).get("category")} for a in items])
