import os
import datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from security.integrity import ModelIntegrityVerifier
from database.audit import AuditLogger

class GovernanceReporter:
    def __init__(self):
        self.audit_log = AuditLogger()
        self.verifier = ModelIntegrityVerifier()

    def generate_signed_audit_report(self, output_path: str, requester_id: str):
        doc = SimpleDocTemplate(output_path, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = []

        elements.append(Paragraph("PerioVision AI — Governance Report", styles['Title']))
        elements.append(Paragraph(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
        elements.append(Spacer(1, 20))

        integrity = self.audit_log.verify_integrity()
        elements.append(Paragraph("Chain Integrity Status", styles['Heading2']))
        status_text = "VERIFIED" if integrity["chain_intact"] else "BREACHED"
        elements.append(Paragraph(f"Status: {status_text}", styles['Normal']))
        elements.append(Spacer(1, 15))

        elements.append(Paragraph("Recent Audit Activity", styles['Heading2']))
        logs = self.audit_log.get_recent(50)
        data = [["Timestamp", "Doctor", "Action"]]
        for log in logs:
            data.append([log["timestamp"][:19], log["doctor_id"][:8], log["action"]])

        t = Table(data, colWidths=[150, 100, 200])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.grey),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('GRID', (0,0), (-1,-1), 0.5, colors.black)
        ]))
        elements.append(t)
        doc.build(elements)
        
        return self.verifier.sign_model(output_path)
