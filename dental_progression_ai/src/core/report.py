import os
import json
import uuid
import hashlib
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from security.integrity import ModelIntegrityVerifier
from database.connection import db
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

def sign_report_data(record_id: str, timestamp: str) -> str:
    """Generate an RSA-4096 signature for the report footer."""
    verifier = ModelIntegrityVerifier()
    priv_key = verifier._get_private_key()
    
    data = f"{record_id}:{timestamp}".encode('utf-8')
    record_hash = hashlib.sha256(data).hexdigest()
    
    signature = priv_key.sign(
        data,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256()
    )
    return record_hash, signature.hex()[:64] + "..." # Truncated for display

def generate_clinical_report(record_id: str, doctor_id: str) -> bytes:
    """Generate a signed PDF clinical report for a completed analysis record."""
    # Fetch data
    xray_record = db["xray_records"].find_one({"record_id": record_id})
    if not xray_record:
        raise ValueError("Record not found")
        
    patient = db["patients"].find_one({"patient_id": xray_record["patient_id"]})
    doctor = db["doctors"].find_one({"doctor_id": doctor_id})
    
    # Setup PDF
    pdf_path = f"/tmp/{record_id}.pdf"
    if os.name == 'nt':
        pdf_path = os.path.join(os.environ.get('TEMP', 'C:\\temp'), f"{record_id}.pdf")
        
    doc = SimpleDocTemplate(pdf_path, pagesize=letter)
    styles = getSampleStyleSheet()
    Story = []
    
    # 1. Header
    title_style = ParagraphStyle(name='Title', parent=styles['Heading1'], alignment=1, spaceAfter=14)
    Story.append(Paragraph(f"<b>PerioVision AI - Clinical Report</b>", title_style))
    
    clinic_name = doctor.get("clinic_name", "PerioVision Clinic") if doctor else "PerioVision Clinic"
    doc_name = f"Dr. {doctor.get('name', 'Unknown')}" if doctor else "Unknown Doctor"
    report_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    header_text = f"<b>Clinic:</b> {clinic_name}<br/><b>Doctor:</b> {doc_name}<br/><b>Date:</b> {report_date}<br/><b>Version:</b> 1.0 (Production)"
    Story.append(Paragraph(header_text, styles["Normal"]))
    Story.append(Spacer(1, 12))
    
    # 2. Patient Demographics
    Story.append(Paragraph("<b>Patient Demographics</b>", styles["Heading2"]))
    pat_info = f"<b>Name:</b> {patient.get('patient_name', 'Unknown')} (ID: {patient.get('patient_id', 'Unknown')})<br/>"
    pat_info += f"<b>Age/Gender:</b> {patient.get('age', '-')} / {patient.get('gender', '-')}<br/>"
    if "dicom_metadata" in xray_record:
        pat_info += f"<b>DICOM Study Date:</b> {xray_record['dicom_metadata'].get('StudyDate', 'N/A')}"
    Story.append(Paragraph(pat_info, styles["Normal"]))
    Story.append(Spacer(1, 12))
    
    # 3. Annotated X-ray
    Story.append(Paragraph("<b>Radiographic Findings</b>", styles["Heading2"]))
    annotated_path = xray_record.get("annotated_path")
    if annotated_path and os.path.exists(annotated_path):
        img = RLImage(annotated_path, width=400, height=250)
        Story.append(img)
    else:
        Story.append(Paragraph("<i>[Annotated Image Not Available]</i>", styles["Normal"]))
    Story.append(Spacer(1, 12))
    
    # 4. Per-tooth TALPA results table
    Story.append(Paragraph("<b>Per-tooth TALPA Results</b>", styles["Heading2"]))
    table_data = [['Tooth', 'Bone Loss %', 'Grade', 'Velocity (mm/yr)', 'Risk']]
    predictions = xray_record.get("predictions", {})
    bl_results = xray_record.get("bone_loss_results", {})
    
    for tid_str, bl_data in bl_results.items():
        if isinstance(bl_data, dict):
            bl_pct = bl_data.get("bone_loss_pct", 0)
            pred = predictions.get(str(tid_str), {})
            grade = pred.get("talpa_grade", "Unknown")
            vel = pred.get("velocity_per_year", 0.0)
            risk = pred.get("risk_level", "Unknown")
            
            table_data.append([
                str(tid_str), 
                f"{bl_pct:.1f}%", 
                grade, 
                f"{vel:.2f}", 
                risk
            ])
            
    t = Table(table_data, colWidths=[60, 80, 80, 100, 80])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0ea5e9')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('BACKGROUND', (0,1), (-1,-1), colors.beige),
        ('GRID', (0,0), (-1,-1), 1, colors.black)
    ]))
    Story.append(t)
    Story.append(Spacer(1, 12))
    
    # 5. Full-mouth summary
    Story.append(Paragraph("<b>Full-Mouth Summary</b>", styles["Heading2"]))
    grades = [r[2] for r in table_data[1:]]
    overall = "Grade C" if "Grade C" in grades else ("Grade B" if "Grade B" in grades else "Grade A")
    velocities = [float(r[3]) for r in table_data[1:]]
    max_vel = max(velocities) if velocities else 0.0
    
    summary = f"<b>Overall Grade:</b> {overall}<br/><b>Highest Velocity Site:</b> {max_vel:.2f} mm/yr"
    Story.append(Paragraph(summary, styles["Normal"]))
    Story.append(Spacer(1, 12))
    
    # 6. Escalation risk section
    Story.append(Paragraph("<b>Escalation Risk Profile (12/24 months)</b>", styles["Heading2"]))
    at_risk = sum(1 for r in table_data[1:] if r[4] in ["High", "Medium"])
    Story.append(Paragraph(f"{at_risk} sites identified with elevated risk for progression.", styles["Normal"]))
    Story.append(Spacer(1, 40))
    
    # 7. Signature block
    Story.append(Paragraph("_" * 40, styles["Normal"]))
    Story.append(Paragraph(f"Clinician Signature: {doc_name}<br/>Date: {datetime.now().strftime('%Y-%m-%d')}", styles["Normal"]))
    Story.append(Spacer(1, 40))
    
    # 8. Category 4 Clinical Validation & Inter-Observer Transparency Block
    disclaimer_style = ParagraphStyle(name='ValidationDisclaimer', parent=styles['Normal'], fontSize=7.5, textColor=colors.HexColor('#991b1b'))
    disclaimer_text = (
        "<b>Validation Status:</b> Validated on synthetic Gaussian noise cohort (n=100). Clinical correlation not established.<br/>"
        "<b>Inter-Observer Variability:</b> Not measured — single annotator dataset."
    )
    Story.append(Paragraph(disclaimer_text, disclaimer_style))
    Story.append(Spacer(1, 10))

    # 9. RSA-4096 signed footer
    record_hash, sig_hex = sign_report_data(record_id, report_date)
    footer_style = ParagraphStyle(name='Footer', parent=styles['Normal'], fontSize=7, textColor=colors.gray)
    Story.append(Paragraph(f"<b>Record Hash (SHA-256):</b> {record_hash}", footer_style))
    Story.append(Paragraph(f"<b>RSA-4096 Signature:</b> {sig_hex}", footer_style))
    
    doc.build(Story)
    
    with open(pdf_path, 'rb') as f:
        pdf_bytes = f.read()
    
    try:
        os.remove(pdf_path)
    except:
        pass
        
    return pdf_bytes
