import csv
from fpdf import FPDF
import os

class DentalReport(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'AI Dental Progression Report', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

def generate_pdf_report(patient, record, progression_table, predictions, output_path,
                        velocity_metrics=None, talpa_map_image_path=None):
    pdf = DentalReport()
    pdf.add_page()
    pdf.set_font('Arial', '', 12)

    # Patient Info
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, 'Patient Information', 0, 1)
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 8, f"Name: {patient.get('patient_name', 'N/A')}", 0, 1)
    pdf.cell(0, 8, f"ID: {patient.get('patient_id', 'N/A')}", 0, 1)
    pdf.cell(0, 8, f"Age: {patient.get('age', 'N/A')}", 0, 1)
    pdf.ln(5)

    # Analysis Info
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, 'Radiograph Analysis Summary', 0, 1)
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 8, f"Analysis Date: {record.get('analysis_date', 'N/A')}", 0, 1)
    pdf.cell(0, 8, f"Record ID: {record.get('record_id', 'N/A')}", 0, 1)
    pdf.ln(5)

    # Results Table header
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(30, 10, 'Tooth', 1)
    pdf.cell(35, 10, 'Bone Loss %', 1)
    pdf.cell(35, 10, 'Progression', 1)
    pdf.cell(35, 10, 'Velocity(%/yr)', 1)
    pdf.cell(45, 10, 'Future Risk', 1)
    pdf.ln(10)

    pdf.set_font('Arial', '', 11)
    bone_loss = record.get('bone_loss_results', {})
    velocity_metrics = velocity_metrics or {}

    for row in progression_table:
        tooth = row["Tooth"]
        loss = f"{bone_loss.get(tooth, 0.0)}%"
        prog = row.get("Change", "N/A")
        vel_val = velocity_metrics.get(f"tooth_{tooth}", velocity_metrics.get(tooth, None))
        velocity_str = f"{vel_val:+.1f}" if isinstance(vel_val, (int, float)) else "N/A"
        risk = predictions.get(tooth, "Unknown")

        pdf.cell(30, 10, str(tooth), 1)
        pdf.cell(35, 10, loss, 1)
        pdf.cell(35, 10, str(prog), 1)
        pdf.cell(35, 10, velocity_str, 1)
        pdf.cell(45, 10, risk, 1)
        pdf.ln(10)

    # ---- TALPA Section ----
    pdf.ln(5)
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, 'TALPA - Temporal Progression Analysis', 0, 1)
    pdf.set_font('Arial', '', 11)
    pdf.multi_cell(0, 7, (
        'The following section presents the longitudinal disease progression computed using the '
        'Temporal Anatomical Landmark-Based Progression Analysis (TALPA) algorithm. '
        'X-rays were automatically aligned via affine transformation using CEJ, Root Apex, '
        'and Alveolar Bone Crest landmarks before measurements were made.'
    ))

    pdf.ln(3)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 8, 'Progression Velocity Summary:', 0, 1)
    pdf.set_font('Arial', '', 11)
    for tooth_key, vel in velocity_metrics.items():
        if isinstance(vel, (int, float)):
            direction = "deteriorating" if vel > 0 else ("stable/improving" if vel < 0 else "stable")
            pdf.cell(0, 7, f"  {tooth_key}: {vel:+.2f}%/year  [{direction}]", 0, 1)

    # Embed progression map image if available
    if talpa_map_image_path and os.path.exists(talpa_map_image_path):
        pdf.ln(5)
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 8, 'Longitudinal Disease Map (Color-Coded):', 0, 1)
        pdf.image(talpa_map_image_path, w=180)
        pdf.set_font('Arial', 'I', 9)
        pdf.cell(0, 6, 'Green=Healthy  Yellow=Mild  Orange=Moderate  Red=Severe', 0, 1)

    pdf.output(output_path)
    return output_path


def generate_csv_report(patient, record, progression_table, predictions, output_path, velocity_metrics=None):
    bone_loss = record.get('bone_loss_results', {})
    velocity_metrics = velocity_metrics or {}

    with open(output_path, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["Patient ID", patient.get("patient_id")])
        writer.writerow(["Patient Name", patient.get("patient_name")])
        writer.writerow(["Analysis Date", record.get("analysis_date")])
        writer.writerow([])
        writer.writerow(["Tooth Number", "Bone Loss %", "Progression over Time", "Velocity (%/yr)", "Future Risk Prediction"])

        for row in progression_table:
            tooth = row["Tooth"]
            vel_val = velocity_metrics.get(f"tooth_{tooth}", velocity_metrics.get(tooth, "N/A"))
            writer.writerow([
                tooth,
                bone_loss.get(tooth, 0.0),
                row.get("Change", "N/A"),
                vel_val,
                predictions.get(tooth, "Unknown")
            ])

    return output_path
