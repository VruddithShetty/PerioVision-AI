"""Report routes: generate a signed PDF, list, download, and verify (verification is public and leaks no PHI)."""
from __future__ import annotations

import io

from flask import Blueprint, g, request, send_file
from pydantic import ValidationError

from app.api._common import fail, ok, validation_error, visible_patient_ids
from app.api.patients import load_patient_or_404
from app.extensions import limiter
from app.schemas import ReportIn
from app.security.audit_log import audit, hash_ip
from app.security.model_signing import SigningError
from app.security.zero_trust import public, secured
from app.services import container, storage_service
from app.services.report_service import ReportNotAllowed, create_report, verify_report

bp = Blueprint("reports", __name__)


def _summary(r: dict) -> dict:
    return {k: r.get(k) for k in ("report_id", "analysis_id", "patient_id", "pseudo_id", "created", "sha256",
                                  "signature_algorithm", "key_fingerprint", "mode", "size_bytes")}


@bp.post("/api/reports")
@secured("report:generate")
def generate():
    try:
        body = ReportIn.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return validation_error(exc)
    try:
        record = create_report(body.analysis_id, g.user)
    except ReportNotAllowed as exc:
        return fail(409, str(exc))
    except SigningError as exc:
        return fail(503, f"Report signing is not configured: {exc}")
    return ok(_summary(record), 201)


@bp.get("/api/reports")
@secured("report:read")
def list_reports():
    return ok([_summary(r) for r in container.report_store().list(visible_patient_ids())])


@bp.get("/api/reports/<report_id>/download")
@secured("report:read")
def download(report_id):
    record = container.report_store().get(report_id)
    if not record:
        return fail(404, "Report not found.")
    patient, err = load_patient_or_404(record["patient_id"])
    if err:
        return err
    try:
        pdf = storage_service.get(record["blob"], "report")
    except Exception:
        return fail(409, "Stored report failed its integrity check.")
    audit().record("REPORT_DOWNLOADED", actor=g.user["id"], resource=patient["pseudo_id"],
                   details={"report_id": report_id})
    return send_file(io.BytesIO(pdf), mimetype="application/pdf", as_attachment=True,
                     download_name=f"PerioVision_{report_id}.pdf")


@bp.get("/api/reports/verify/<report_id>")
@public
@limiter.limit("30 per minute")
def verify_by_id(report_id):
    result = verify_report(report_id=str(report_id)[:64])
    audit().record("REPORT_VERIFIED", outcome="valid" if result["valid"] else "invalid",
                   details={"report_id": str(report_id)[:64], "ip": hash_ip(request.remote_addr)})
    return ok(result)


@bp.post("/api/reports/verify")
@public
@limiter.limit("30 per minute")
def verify_upload():
    file = request.files.get("file")
    if file is None:
        return fail(400, "Attach the PDF as form field 'file'.")
    data = file.read(20 * 1024 * 1024 + 1)
    if len(data) > 20 * 1024 * 1024 or not data.startswith(b"%PDF"):
        return fail(415, "Please upload the PDF report.")
    result = verify_report(pdf_bytes=data)
    audit().record("REPORT_VERIFIED", outcome="valid" if result["valid"] else "invalid",
                   details={"by": "file", "ip": hash_ip(request.remote_addr)})
    return ok(result)
