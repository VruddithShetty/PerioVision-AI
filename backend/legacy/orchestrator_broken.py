import os
import cv2
import datetime
import logging

from image_processing.preprocess_xray import XRayPreprocessor
from models.inference import ToothDetector, LandmarkDetector
from analysis.calculate_bone_loss import BoneLossCalculator
from analysis.progression_analysis import ProgressionAnalyzer
from analysis.progression_velocity_calculator import TALPAEngine
from analysis.risk_prediction import RiskPredictor
from visualization.draw_annotations import DentalAnnotator
from image_processing.radiograph_alignment import RadiographAligner

from database.patient_manager import get_patient
from database.xray_record_manager import save_xray_record, get_records_for_patient
from database.notification_manager import create_notification

logger = logging.getLogger("DentalAIOrchestrator")

class DentalAIOrchestrator:
    """
    The central 'Brain' of the system.
    Orchestrates the entire end-to-end data flow spanning 12 specialized classes.
    """
    def __init__(self):
        logger.info("Initializing Dental AI Orchestrator...")
        self.preprocessor = XRayPreprocessor()
        self.tooth_detector = ToothDetector()
        self.landmark_detector = LandmarkDetector()
        self.bone_loss_calc = BoneLossCalculator()
        self.progression_analyzer = ProgressionAnalyzer()
        self.talpa_engine = TALPAEngine()
        self.risk_predictor = RiskPredictor()
        self.annotator = DentalAnnotator()
        self.aligner = RadiographAligner()

        # Ensure standardized storage architecture exists
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.storage_dir = os.path.join(base_dir, "storage")
        self.prep_dir = os.path.join(self.storage_dir, "xrays", "preprocessed")
        self.annotated_dir = os.path.join(self.storage_dir, "xrays", "annotated")
        os.makedirs(self.prep_dir, exist_ok=True)
        os.makedirs(self.annotated_dir, exist_ok=True)

    def process_new_xray(self, patient_id, image_input, doctor_id):
        """
        Executes the master Phase 1-8 sequential pipeline.
        Returns (record_id, analysis_result_dict, preprocessed_image_path, annotated_image_path)
        """
        try:
            logger.info(f"Commencing full orchestrator pipeline for Patient {patient_id}")
            
            # 1. Fetch patient and historical records
            patient = get_patient(patient_id)
            age = patient.get("age", 40) if patient else 40
            
            history_records = get_records_for_patient(patient_id)
            history_records = sorted(history_records, key=lambda x: x.get("created_date", ""))

            # 2. Preprocess raw image
            processed_res = self.preprocessor.preprocess(image_input, patient_id=patient_id, return_steps=False)
            if processed_res is None or (isinstance(processed_res, tuple) and processed_res[0] is None):
                err = processed_res[1] if isinstance(processed_res, tuple) else "Unknown preprocessing error"
                raise ValueError(f"Preprocessing failed: {err}")
                
            processed_img = processed_res[0] if isinstance(processed_res, tuple) else processed_res

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            prep_filename = f"{patient_id}_{timestamp}_prep.png"
            prep_path = os.path.join(self.prep_dir, prep_filename)

            # 3. Geometric Alignment (Core to TALPA temporal stability)
            analysis_img = processed_img
            if history_records:
                last_record = history_records[-1]
                ref_path = last_record.get("image_path")
                if ref_path and os.path.exists(ref_path):
                    ref_img = cv2.imread(ref_path, cv2.IMREAD_GRAYSCALE)
                    if ref_img is not None:
                        align_res = self.aligner.align_pair(ref_img, processed_img)
                        if self.aligner.detect_alignment_failure(align_res["quality_score"]):
                            logger.warning(f"Alignment quality low ({align_res['quality_score']:.2f}). Bypassing transform.")
                        else:
                            logger.info("Successfully aligned temporal image to historical baseline.")
                            analysis_img = align_res["aligned_image"]
                            
            cv2.imwrite(prep_path, analysis_img)

            # 4. Detect Teeth Bounding Boxes
            detections = self.tooth_detector.detect_teeth(analysis_img)
            
            # 5. Detect CEJ & Bone Crest Landmarks
            landmarks_per_tooth = {}
            for det in detections:
                t_id = det["tooth_id"]
                roi = self.tooth_detector.get_tooth_roi(analysis_img, det)
                landmarks = self.landmark_detector.detect_landmarks(roi, det["bbox"])
                landmarks_per_tooth[t_id] = landmarks
                
            # 6. Compute Static Bone Loss %
            bone_loss_results = self.bone_loss_calc.compute_all_teeth(detections, landmarks_per_tooth)
            
            # 7. Compute TALPA Velocity Vectors (Requires Temporal Data)
            velocities = {}
            if history_records:
                prog_data = self.progression_analyzer.compare_records(history_records)
                talpa_results, talpa_summary = self.talpa_engine.compute_full_mouth_talpa(prog_data)
                velocities = talpa_results
                
            # 8. Gradient-Boosted Risk Prediction
            risk_results = self.risk_predictor.predict_all_teeth(bone_loss_results, velocities, age)
            
            # Formulate final analysis dictionary
            final_teeth_list = []
            highest_risk_flag = False
            
            for t_id_str, bl_data in bone_loss_results.items():
                t_id = int(t_id_str)
                risk_data = risk_results.get(t_id, {})
                vel_data = velocities.get(t_id, {})
                
                tooth_summary = {
                    "tooth_id": t_id,
                    "bbox": bl_data["bbox"],
                    "landmarks": bl_data["landmarks"],
                    "bone_loss_pct": bl_data["bone_loss_pct"],
                    "severity": bl_data["severity"],
                    "risk_level": risk_data.get("risk_level", "Unknown"),
                    "risk_confidence": risk_data.get("confidence", 0.0),
                    "risk_explanation": risk_data.get("explanation", ""),
                    "velocity_per_year": vel_data.get("velocity_result", {}).get("velocity_per_year", 0.0),
                    "talpa_narrative": vel_data.get("narrative", "")
                }
                final_teeth_list.append(tooth_summary)
                
                # Check absolute safety limits
                if tooth_summary["risk_level"] == "High" or tooth_summary["velocity_per_year"] > 5.0:
                    highest_risk_flag = True
                    
            analysis_result_dict = {"teeth": final_teeth_list}
            
            # 9. Render Clinical Visualizations
            annotated_img = self.annotator.draw_full_analysis(analysis_img, analysis_result_dict, patient_id)
            annotated_filename = f"{patient_id}_{timestamp}_annotated.png"
            annotated_path = os.path.join(self.annotated_dir, annotated_filename)
            cv2.imwrite(annotated_path, annotated_img)
            
            # 11. Write to Distributed Database
            record_id = save_xray_record(patient_id, prep_path, analysis_result_dict)
            
            # 10. Fire Hardware/Web Notifications
            if highest_risk_flag:
                msg = f"High-risk deterioration detected for patient {patient_id}. Review record {record_id} immediately."
                create_notification(doctor_id, "High Risk Detection", msg, patient_id=patient_id)
                
            logger.info(f"Pipeline executed perfectly. Record ID: {record_id}")
            return record_id, analysis_result_dict, prep_path, annotated_path

        except Exception as e:
            logger.error(f"FATAL: Orchestration failed for patient {patient_id}: {str(e)}")
            raise e
