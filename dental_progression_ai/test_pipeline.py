import os
import cv2
import datetime
import uuid
import pandas as pd
from database.patient_manager import PatientManager
from database.xray_record_manager import XrayRecordManager
from utilities.generate_patient_id import generate_next_patient_id
from utilities.dataset_loader import ensure_storage_directories
from image_processing.preprocess_xray import preprocess_for_analysis
from models.tooth_detection_model.inference import ToothDetectionModel
from models.landmark_detection_model.inference import LandmarkDetectionModel
from analysis.calculate_bone_loss import compute_bone_loss
from analysis.progression_analysis import analyze_progression
from analysis.risk_prediction import RiskPredictor
from visualization.draw_annotations import draw_findings_on_image
from report_generation.generate_dental_report import generate_pdf_report

def run_test():
    ensure_storage_directories()
    
    # Init
    patient_mgr = PatientManager()
    xray_mgr = XrayRecordManager()
    td_model = ToothDetectionModel()
    ld_model = LandmarkDetectionModel()
    rp_model = RiskPredictor()
    
    # 1. Register Patient
    pid = generate_next_patient_id()
    patient_mgr.create_patient(pid, "Programmatic Tester", 40, "Other", "555-5555", "Test")
    patient_data = patient_mgr.get_patient(pid)
    print(f"Registered patient: {patient_data}")

    # 2. Simulate Upload
    raw_path = "test_xray.jpg"
    
    # 3. Preprocess
    processed_img = preprocess_for_analysis(raw_path)
    print("Preprocessed image successfully.")

    # 4. Detect Teeth & Landmarks
    detections = td_model.detect_teeth(raw_path)
    landmarks = ld_model.detect_landmarks(processed_img, detections)
    print(f"Detected {len(detections)} teeth. Landmarks generated.")

    # 5. Bone Loss
    bone_loss_results = compute_bone_loss(landmarks)
    print("Bone loss percentages:", bone_loss_results)

    # 6. Progression & Risk
    past_xrays = xray_mgr.get_records_by_patient(pid)
    progression_table = analyze_progression(past_xrays, bone_loss_results)
    predictions = rp_model.evaluate_all_teeth(progression_table, patient_data["age"])
    print("Predictions:", predictions)

    # 7. Visualization
    annotated_img = draw_findings_on_image(processed_img, detections, landmarks, bone_loss_results)
    annot_path = f"storage/annotated_results/{pid}_annotated.jpg"
    cv2.imwrite(annot_path, annotated_img)
    
    # 8. Report
    record_id = "TEST_XR_1"
    xray_mgr.create_record(record_id, pid, raw_path, analysis_date="2026-03-12", bone_loss_results=bone_loss_results, risk_prediction=predictions)
    
    pdf_path = f"storage/annotated_results/{record_id}_report.pdf"
    generate_pdf_report(patient_data, {"analysis_date": "2026-03-12", "record_id": record_id, "bone_loss_results": bone_loss_results}, progression_table, predictions, pdf_path)
    
    if os.path.exists(pdf_path):
        print(f"SUCCESS: Report generated at {pdf_path}")
    else:
        print("FAILED to generate report.")

if __name__ == '__main__':
    run_test()
