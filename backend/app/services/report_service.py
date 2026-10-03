"""Signed, verifiable PDF clinical reports.

Contents: patient summary (pseudonymised ID + name), annotated radiograph,
per-tooth table, progression chart, risk with its reasons, an uncertainty
statement, the reviewing dentist's sign-off, and a verification block with the
report ID and a QR code.

Integrity: after the PDF is built, its SHA-256 is signed with RSA-PSS. The hash,
signature and key fingerprint are stored with the report record, and the PDF
itself is stored encrypted. `verify_report` recomputes the hash of a presented
PDF (or of the stored copy) and checks the signature, so any edit to the file,
even one byte, is detected.
"""
from __future__ import annotations

import hashlib
import io
import os

from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image as RLImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app import config
from app.security.audit_log import audit
from app.security.model_signing import Signer
from app.services import container, storage_service


class ReportNotAllowed(Exception):
    """The message is safe to show to the user."""


def _qr_png(text: str) -> bytes:
    import qrcode

    buf = io.BytesIO()
    qrcode.make(text).save(buf, format="PNG")
    return buf.getvalue()


def _progression_chart(series: dict) -> Drawing | None:
    lines = [(tid, pts) for tid, pts in series.items() if len(pts) >= 2][:6]
    if not lines:
        return None
    dates = sorted({p["date"] for _, pts in lines for p in pts})
    index = {d: i for i, d in enumerate(dates)}
    drawing = Drawing(170 * mm, 60 * mm)
    plot = LinePlot()
    plot.x, plot.y, plot.width, plot.height = 15 * mm, 10 * mm, 140 * mm, 45 * mm
    plot.data = [[(index[p["date"]], p["bone_loss_pct"]) for p in pts] for _, pts in lines]
    plot.yValueAxis.valueMin, plot.yValueAxis.valueMax = 0, 100
    plot.xValueAxis.valueSteps = list(range(len(dates)))
    plot.xValueAxis.labelTextFormat = lambda i: dates[int(i)] if 0 <= int(i) < len(dates) else ""
    palette = [colors.HexColor(c) for c in ("#0ea5e9", "#14b8a6", "#f59e0b", "#ef4444", "#8b5cf6", "#64748b")]
    for i in range(len(lines)):
        plot.lines[i].strokeColor = palette[i % len(palette)]
    drawing.add(plot)
    for i, (tid, _) in enumerate(lines):
        drawing.add(String(158 * mm, (52 - 5 * i) * mm, f"Tooth {tid}", fontSize=7, fillColor=palette[i % len(palette)]))
    return drawing


def build_pdf(analysis: dict, patient: dict, progression: dict, reviewer: dict | None, report_id: str) -> bytes:
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8, leading=10)
    warn = ParagraphStyle("warn", parent=small, textColor=colors.HexColor("#92400e"))
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm,
                            bottomMargin=15 * mm, title=f"PerioVision report {report_id}", author="PerioVision AI")
    story = [Paragraph("<b>PerioVision AI: Periodontal Radiograph Report</b>", styles["Title"])]
    mode_note = "DEMO MODE: placeholder results, not model output. " if analysis.get("mode") == "demo" else ""
    story.append(Paragraph(
        f"<b>{mode_note}Clinical decision-support tool; not a certified medical device.</b> "
        "Findings must be confirmed by a qualified clinician.", warn))
    story.append(Spacer(1, 6))

    s = analysis["summary"]
    rows = [["Patient", f"{patient.get('patient_name', '')} ({patient['pseudo_id']})"],
            ["Visit date", analysis["visit_date"]],
            ["Analysis", f"{analysis['analysis_id']} ({analysis.get('mode')})"],
            ["Teeth detected", str(s["teeth_detected"])],
            ["Mean / max bone loss", f"{s['mean_bone_loss_pct']} % / {s['max_bone_loss_pct']} %"
             if s["mean_bone_loss_pct"] is not None else "not measured (no tooth had model landmarks)"],
            ["Teeth measured", f"{s.get('teeth_measured', 'n/a')} of {s['teeth_detected']}"],
            ["Stage suggestion (worst tooth)", str(s["stage"] or "n/a")],
            ["Grade suggestion", f"{s['grade'].get('grade') or 'n/a'} ({s['grade'].get('basis') or 'insufficient data'})"]]
    t = Table(rows, colWidths=[55 * mm, 125 * mm])
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                           ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0f2fe"))]))
    story += [t, Spacer(1, 6)]

    annotated = analysis.get("blobs", {}).get("annotated")
    if annotated:
        png = storage_service.get(annotated, "annotated")
        w, h = analysis["image_size"]
        width = 180 * mm
        story += [RLImage(io.BytesIO(png), width=width, height=width * h / max(w, 1)), Spacer(1, 6)]

    table = [["Tooth", "Bone loss %", "Interval (coverage)", "Stage set", "Stage", "Landmarks", "Flags"]]
    for tooth in analysis["teeth"]:
        unc = tooth.get("uncertainty", {})
        interval = unc.get("interval")
        flags = ", ".join(k.replace("_", " ") for k, v in tooth.get("flags", {}).items() if v) or "-"
        table.append([tooth["tooth_id"], "-" if tooth["bone_loss_pct"] is None else f"{tooth['bone_loss_pct']:.1f}",
                      f"{interval[0]:.0f}-{interval[1]:.0f}" if interval else "-",
                      "/".join(unc.get("stage_set", [])) or "-", tooth.get("stage") or "-",
                      tooth.get("landmark_source", "-"), flags])
    tt = Table(table, repeatRows=1, colWidths=[14 * mm, 20 * mm, 28 * mm, 20 * mm, 14 * mm, 32 * mm, 52 * mm])
    tt.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]))
    story += [Paragraph("<b>Per-tooth findings</b>", styles["Heading3"]), tt, Spacer(1, 6)]

    cal = analysis.get("calibration", {})
    if cal.get("calibrated"):
        unc_text = (f"Intervals are split-conformal prediction intervals at {cal['coverage']:.0%} target coverage "
                    f"(half-width {cal['q']:.1f} percentage points). A stage set with more than one stage means "
                    "the stages cannot be told apart at that coverage.")
    else:
        unc_text = ("Uncertainty is NOT calibrated for this model yet, so no numeric interval can be trusted; "
                    "the case was routed to mandatory clinician review.")
    story += [Paragraph("<b>Uncertainty</b>", styles["Heading3"]), Paragraph(unc_text, small)]

    chart = _progression_chart(progression.get("series", {}))
    story.append(Paragraph("<b>Progression</b>", styles["Heading3"]))
    if chart:
        story.append(chart)
    latest = progression.get("latest", [])
    if latest:
        story.append(Paragraph("; ".join(f"Tooth {c['tooth_id']}: {c['label']}" for c in latest[:16]), small))
    else:
        story.append(Paragraph("No earlier visit to compare with.", small))

    risk = analysis["risk"]
    reasons = "; ".join(f["text"] for f in risk.get("top_factors", [])) or "no strong contributing factors"
    risk_text = (f"Category: <b>{risk['category']}</b> (probability {risk['probability']:.2f}, {risk['model_type']}). "
                 f"Main factors: {reasons}. " if risk.get("probability") is not None
                 else "<b>Not available</b>: " if risk.get("status") in ("insufficient_data", "unavailable") else "")
    story += [Paragraph("<b>Risk</b>", styles["Heading3"]),
              Paragraph(f"{risk_text}<i>{risk['disclaimer']}</i>", small)]

    review = analysis.get("review", {})
    story.append(Paragraph("<b>Clinician review</b>", styles["Heading3"]))
    if reviewer:
        story.append(Paragraph(f"Signed off by {reviewer['name']} ({reviewer['role']}) on {reviewer['at'][:19]} UTC. "
                               f"Decision: {reviewer['decision']}. {reviewer.get('comment') or ''}", small))
        if reviewer.get("corrections"):
            # The clinician's values override the model's for these teeth; both are shown, neither is hidden.
            model = {t["tooth_id"]: t for t in analysis["teeth"]}
            rows = [["Tooth", "Model bone loss %", "Model stage", "Clinician bone loss %", "Clinician stage", "Note"]]
            for c in reviewer["corrections"]:
                m = model.get(c.get("tooth_id"), {})
                fmt = lambda v: "-" if v is None else f"{v:.1f}"  # noqa: E731
                rows.append([c.get("tooth_id"), fmt(m.get("bone_loss_pct")), m.get("stage") or "-",
                             fmt(c.get("bone_loss_pct")), c.get("stage") or "-", c.get("note") or ""])
            ct = Table(rows, repeatRows=1, colWidths=[14 * mm, 30 * mm, 22 * mm, 34 * mm, 26 * mm, 54 * mm])
            ct.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey)]))
            story += [Paragraph("<b>Clinician corrections (these values replace the model's)</b>", small), ct]
    else:
        story.append(Paragraph(f"Review status: {review.get('label')}. No flags required a sign-off.", small))

    verify_url = f"{config.PUBLIC_VERIFY_URL}/{report_id}"
    qr = RLImage(io.BytesIO(_qr_png(verify_url)), width=28 * mm, height=28 * mm)
    vt = Table([[qr, Paragraph(f"<b>Verification ID:</b> {report_id}<br/>Verify at: {verify_url}<br/>"
                               "The SHA-256 of this PDF is digitally signed (RSA-PSS). Any change to the file "
                               "makes verification fail.", small)]], colWidths=[32 * mm, 148 * mm])
    story += [Spacer(1, 8), vt]
    doc.build(story)
    return buf.getvalue()


def create_report(analysis_id: str, user: dict) -> dict:
    analyses = container.analysis_store()
    analysis = analyses.get(analysis_id)
    if not analysis:
        raise ReportNotAllowed("Analysis not found.")
    patient = container.patient_manager().get_patient(analysis["patient_id"], user["id"], user["role"])
    if not patient:
        raise ReportNotAllowed("Analysis not found.")
    review = analysis.get("review", {})
    if review.get("status") == "review_required":
        raise ReportNotAllowed("This case needs mandatory clinician review. A dentist must sign it off first.")
    if review.get("status") == "rejected":
        raise ReportNotAllowed("This analysis was rejected in review and cannot be reported.")
    decision = review.get("decision")
    reviewer = None
    if decision:
        reviewer = {"name": decision.get("reviewer_name"), "role": decision.get("reviewer_role"),
                    "at": decision.get("at"), "decision": decision.get("status"), "comment": decision.get("comment"),
                    "corrections": decision.get("corrections") or []}

    from app.services.progression_service import patient_progression

    progression = patient_progression(analyses.for_patient(analysis["patient_id"]))
    reports = container.report_store()
    report_id = "RPT-" + os.urandom(8).hex()
    pdf = build_pdf(analysis, patient, progression, reviewer, report_id)
    digest = hashlib.sha256(pdf).hexdigest()
    signer = Signer()
    signature = signer.sign_bytes(digest.encode())
    record = reports.create({
        "report_id": report_id, "analysis_id": analysis_id, "patient_id": analysis["patient_id"],
        "pseudo_id": analysis["pseudo_id"], "created_by": user["id"], "sha256": digest,
        "signature": signature, "signature_algorithm": "RSA-PSS-SHA256",
        "key_fingerprint": signer.public_key_fingerprint(), "mode": analysis.get("mode"),
        "blob": storage_service.put(pdf, "report"), "size_bytes": len(pdf),
    })
    audit().record("REPORT_GENERATED", actor=user["id"], resource=analysis["pseudo_id"],
                   details={"report_id": report_id, "sha256": digest})
    return record


def verify_report(report_id: str | None = None, pdf_bytes: bytes | None = None) -> dict:
    """Verify a presented PDF, or the stored copy of a report. Returns no patient data."""
    reports = container.report_store()
    signer = Signer()
    if pdf_bytes is not None:
        digest = hashlib.sha256(pdf_bytes).hexdigest()
        record = reports.collection.find_one({"sha256": digest}, {"_id": 0})
        if not record:
            return {"valid": False, "reason": "No signed report matches this file (it was altered or is unknown).",
                    "sha256": digest}
    else:
        record = reports.get(report_id)
        if not record:
            return {"valid": False, "reason": "Unknown report ID."}
        try:
            digest = hashlib.sha256(storage_service.get(record["blob"], "report")).hexdigest()
        except Exception:
            return {"valid": False, "reason": "Stored report could not be decrypted (tampered storage)."}
    sig_ok = signer.verify_bytes(record["sha256"].encode(), record["signature"])
    hash_ok = digest == record["sha256"]
    return {"valid": bool(sig_ok and hash_ok), "report_id": record["report_id"], "created": record["created"],
            "sha256": digest, "signature_valid": sig_ok, "hash_matches": hash_ok,
            "key_fingerprint": record.get("key_fingerprint"), "mode": record.get("mode"),
            "reason": None if sig_ok and hash_ok else "Signature or hash mismatch."}
