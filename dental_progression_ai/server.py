import os
import sys
import json
import logging
import tempfile
import shutil
from flask import Flask, request, jsonify, send_file, render_template, session
from flask_wtf.csrf import CSRFProtect, generate_csrf, CSRFError
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "src"))

load_dotenv()

from security.integrity import ModelIntegrityVerifier

# Auto-copy generated images to static folder
os.makedirs(os.path.join(ROOT_DIR, "web", "static", "images"), exist_ok=True)
bg_src = r"C:\Users\vrudd\.gemini\antigravity\brain\f33de816-c1b7-40e9-81ca-043f54e37a05\dental_clinic_bg_1777961904113.png"
tooth_src = r"C:\Users\vrudd\.gemini\antigravity\brain\f33de816-c1b7-40e9-81ca-043f54e37a05\tooth_icon_3d_1777961930135.png"
if os.path.exists(bg_src): shutil.copy(bg_src, os.path.join(ROOT_DIR, "web", "static", "images", "bg.png"))
if os.path.exists(tooth_src): shutil.copy(tooth_src, os.path.join(ROOT_DIR, "web", "static", "images", "tooth.png"))

import cv2
import uuid
import numpy as np
import pydicom
try:
    import magic
except ImportError:
    magic = None
from datetime import datetime

TEMP_UPLOADS = {}


def _is_dicom_file(path, filename=""):
    """Detect whether a file is DICOM without requiring libmagic."""
    if str(filename).lower().endswith(".dcm") or str(path).lower().endswith(".dcm"):
        return True

    if magic is not None:
        try:
            return magic.from_file(path, mime=True) == "application/dicom"
        except Exception:
            pass

    try:
        pydicom.dcmread(path, stop_before_pixels=True)
        return True
    except Exception:
        return False


def _read_dicom_metadata(path):
    """Read the basic DICOM metadata fields used by the UI."""
    ds = pydicom.dcmread(path, stop_before_pixels=True)
    return {
        "PatientName": str(ds.get("PatientName", "")),
        "PatientID": str(ds.get("PatientID", "")),
        "StudyDate": str(ds.get("StudyDate", "")),
        "Modality": str(ds.get("Modality", "")),
    }

# Import NEW refactored modules
from database.patients import PatientManager
from database.doctors import DoctorManager
from database.xrays import XrayRecordManager
from core.preprocessing import preprocess_for_analysis
from models.detection import ToothDetectionModel
from models.landmarks import LandmarkDetectionModel
from core.bone_loss import compute_bone_loss
from core.progression import analyze_progression
from analysis.progression_velocity_calculator import ProgressionVelocityCalculator
from core.risk import RiskPredictor
from core.visualization import draw_findings_on_image
from core.progression_map import generate_progression_map
from core.alignment import RadiographAligner
from core.report import generate_clinical_report
from core.audit_middleware import audit_action
from security.merkle import MerkleAuditLog
import io

_talpa_calculator = ProgressionVelocityCalculator()
_aligner = RadiographAligner()

def _stringify_keys(d):
    if isinstance(d, dict):
        return {str(k): _stringify_keys(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [_stringify_keys(x) for x in d]
    else:
        return d

def build_longitudinal_landmark_dict(current_landmarks, current_date, patient_history, bone_loss_results=None, pixels_per_mm=None, calib_conf=0.0, calib_status="unavailable"):
    """
    Merge current landmarks with historical patient records.
    Uses true mm distances when calibration_confidence >= 0.5.
    Falls back to proxy only below that threshold and sets estimated: true.
    """
    landmark_data = {}
    bone_loss_results = bone_loss_results or {}

    for tooth_id, pts in (current_landmarks or {}).items():
        if "cej" in pts and "bone_crest" in pts:
            bl_pct = bone_loss_results.get(tooth_id, {}).get("bone_loss_pct", 0.0)
            if calib_status == "available" and calib_conf >= 0.5 and pixels_per_mm and pixels_per_mm > 0:
                dist_mm = _aligner.compute_true_cej_abc_distance(pts["cej"], pts["bone_crest"], pixels_per_mm)
                estimated = False
                m_type = "true_mm"
            else:
                dist_mm = 2.0 + (bl_pct / 10.0)
                estimated = True
                m_type = "proxy_mm"
                
            landmark_data.setdefault(tooth_id, {}).setdefault("mesial", []).append({
                "date": current_date,
                "cej_to_abc_mm": dist_mm,
                "alignment_confidence": calib_conf if calib_conf >= 0.5 else 0.4,
                "estimated": estimated,
                "measurement_type": m_type,
                "confidence_source": pts.get("confidence_source", "model")
            })

    for record in (patient_history or []):
        record_date = record.get("analysis_date", current_date)
        analysis_result = record.get("analysis_result", {})
        for tooth_id_str, bl_data in analysis_result.items():
            try:
                tooth_id = int(tooth_id_str)
            except (ValueError, TypeError):
                continue
            bl_pct = bl_data.get("bone_loss_pct", 0.0) if isinstance(bl_data, dict) else 0.0
            cej_to_abc_proxy = 2.0 + (bl_pct / 10.0)  # historical records still use proxy
            landmark_data.setdefault(tooth_id, {}).setdefault("mesial", []).append({
                "date": record_date,
                "cej_to_abc_mm": cej_to_abc_proxy,
                "alignment_confidence": 0.75,
                "estimated": True,
                "measurement_type": "proxy_mm",
                "confidence_source": "model"
            })

    return landmark_data

app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max
app.secret_key = "super_secret_cipher_os_key"
csrf = CSRFProtect(app)
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["60 per minute"],
    storage_uri="memory://",
)

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    return jsonify({"success": False, "error": "CSRF token missing or invalid"}), 400

# Initialize AI Modules
logger = logging.getLogger("FlaskServer")
logging.basicConfig(level=logging.INFO)

patient_mgr = PatientManager()
doctor_mgr = DoctorManager()
xray_mgr = XrayRecordManager()
td_model = ToothDetectionModel()
ld_model = LandmarkDetectionModel()
rp_model = RiskPredictor()

# Create Demo Credentials from environment
demo_email = os.getenv("DEMO_EMAIL")
demo_password = os.getenv("DEMO_PASSWORD")
if demo_email and demo_password:
    try:
        if not doctor_mgr.authenticate_doctor(demo_email, demo_password):
            doctor_mgr.register_doctor(
                name="Demo Doctor",
                email=demo_email,
                password=demo_password,
                clinic_name="PerioVision Demo Clinic"
            )
            logger.info(f"Demo credentials seeded: {demo_email}")
    except Exception as e:
        logger.warning(f"Demo seeding skipped: {e}")
else:
    logger.warning("Demo credentials not configured; skipping demo doctor seed.")

try:
    if not doctor_mgr.authenticate_doctor("superadmin@periovision.ai", "SuperAdminPass!123"):
        doc_id = doctor_mgr.register_doctor(
            name="Super Admin",
            email="superadmin@periovision.ai",
            password="SuperAdminPass!123",
            clinic_name="Global Operations"
        )
        doctor_mgr.collection.update_one(
            {"doctor_id": doc_id},
            {"$set": {"role": "superadmin"}}
        )
        logger.info("SuperAdmin seeded: superadmin@periovision.ai")
except Exception as e:
    logger.warning(f"SuperAdmin seeding skipped: {e}")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/csrf-token", methods=["GET"])
def get_csrf_token():
    return jsonify({"csrf_token": generate_csrf()})

@app.route("/api/register", methods=["POST"])
@audit_action("register_doctor")
def register():
    data = request.json or {}
    errors = {}
    for field in ["name", "email", "password"]:
        if field not in data or not data[field]:
            errors[field] = f"{field.capitalize()} is required."
    if errors:
        return jsonify({"success": False, "errors": errors}), 400
        
    try:
        doc_id = doctor_mgr.register_doctor(
            name=data["name"],
            email=data["email"],
            password=data["password"],
            clinic_name=data.get("clinic_name")
        )
        return jsonify({"success": True, "doctor_id": doc_id})
    except ValueError as ve:
        if "already registered" in str(ve):
            return jsonify({"success": False, "error": str(ve)}), 409
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route("/api/login", methods=["POST"])
@app.route("/api/auth/login", methods=["POST"])
@limiter.limit("5 per minute")
@audit_action("login_doctor")
def login():
    data = request.json
    try:
        doctor = doctor_mgr.authenticate_doctor(data["email"], data["password"])
        if doctor:
            # Fetch doctor record to see if 2FA is enabled
            from database.connection import db
            doc_record = db["doctors"].find_one({"doctor_id": doctor["doctor_id"]})
            if doc_record and doc_record.get("two_factor_enabled"):
                totp_token = data.get("totp_token")
                if not totp_token:
                    return jsonify({"success": False, "error": "TOTP token required"}), 401
                if not doctor_mgr.verify_totp(doctor["doctor_id"], totp_token):
                    return jsonify({"success": False, "error": "Invalid TOTP token"}), 401
            
            session["doctor_id"] = doctor["doctor_id"]
            session["name"] = doctor["name"]
            session["role"] = doctor.get("role", "doctor")
            return jsonify({"success": True, "doctor": doctor})
        else:
            return jsonify({"success": False, "error": "Invalid credentials"}), 401
    except PermissionError as pe:
        return jsonify({"success": False, "error": str(pe)}), 423
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route("/api/logout", methods=["POST"])
@audit_action("logout_doctor")
def logout():
    session.clear()
    return jsonify({"success": True})

@app.route("/api/auth/status", methods=["GET"])
def auth_status():
    if "doctor_id" in session:
        return jsonify({"logged_in": True, "doctor": {"name": session["name"], "id": session["doctor_id"]}})
    return jsonify({"logged_in": False})

@app.route("/api/patients", methods=["GET", "POST"])
@audit_action("manage_patients")
def manage_patients():
    if "doctor_id" not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
        
    if request.method == "POST":
        role = session.get("role", "doctor")
        from security.rbac import RBACEnforcer
        rbac = RBACEnforcer()
        if not rbac.can_access(role, "doctor"):
            return jsonify({"success": False, "error": "Forbidden"}), 403
            
        data = request.json
        try:
            pid = patient_mgr.create_patient(
                name=data["name"],
                age=int(data["age"]),
                gender=data["gender"],
                contact=data.get("contact", ""),
                notes=data.get("notes", ""),
                doctor_id=session["doctor_id"]
            )
            return jsonify({"success": True, "patient_id": pid})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400
    else:
        try:
            role = session.get("role", "doctor")
            if role in ("admin", "superadmin"):
                pts = patient_mgr.list_all_patients(session["doctor_id"], role)
            else:
                pts = patient_mgr.get_patients_by_doctor(session["doctor_id"])
            return jsonify({"success": True, "patients": pts})
        except Exception as e:
            logger.error(f"Error fetching patients: {str(e)}")
            return jsonify({"success": False, "error": str(e)}), 500
@app.route("/api/upload", methods=["POST"])
@audit_action("upload_radiograph")
def upload_file():
    if "doctor_id" not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    if "image" not in request.files:
        return jsonify({"success": False, "error": "No image"}), 400
        
    file = request.files["image"]
    upload_id = uuid.uuid4().hex
    
    is_dcm = file.filename.lower().endswith('.dcm')
    suffix = ".dcm" if is_dcm else ".png"
    fd, temp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    file.save(temp_path)
    
    # Validate file type using magic bytes
    try:
        with open(temp_path, "rb") as f:
            header = f.read(132)
        is_png = header.startswith(b"\x89PNG\r\n\x1a\n")
        is_jpg = header.startswith(b"\xff\xd8\xff")
        is_dicom_sig = len(header) >= 132 and header[128:132] == b"DICM"
        
        if not (is_png or is_jpg or is_dicom_sig):
            os.remove(temp_path)
            return jsonify({"success": False, "error": "Invalid file type. Only PNG, JPG, and DICOM are allowed."}), 400
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify({"success": False, "error": f"File validation failed: {str(e)}"}), 400
        
    TEMP_UPLOADS[upload_id] = temp_path
    
    # If DICOM, we also want to parse metadata immediately for the frontend to confirm
    metadata = None
    if _is_dicom_file(temp_path, file.filename):
        is_dcm = True
        try:
            metadata = _read_dicom_metadata(temp_path)
        except Exception:
            metadata = None
                
    return jsonify({"success": True, "upload_id": upload_id, "is_dcm": is_dcm, "metadata": metadata})

@app.route("/api/dicom-metadata/<upload_id>", methods=["GET"])
@audit_action("view_dicom_metadata")
def dicom_metadata(upload_id):
    if upload_id not in TEMP_UPLOADS:
        return jsonify({"success": False, "error": "Upload not found"}), 404
        
    path = TEMP_UPLOADS[upload_id]
    if not _is_dicom_file(path):
        return jsonify({"success": False, "error": "Not a valid DICOM file"}), 400
        
    try:
        meta = _read_dicom_metadata(path)
        return jsonify({"success": True, "metadata": meta})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route("/api/analyze", methods=["POST"])
@limiter.limit("10 per minute")
@audit_action("analyze_radiograph")
def analyze():
    if "doctor_id" not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    upload_id = request.form.get("upload_id")
    patient_id = request.form.get("patient_id")

    if not patient_id:
        return jsonify({"success": False, "error": "Invalid input"}), 400
        
    temp_path = None
    dicom_meta = None
    
    if upload_id and upload_id in TEMP_UPLOADS:
        temp_path = TEMP_UPLOADS[upload_id]
    elif "image" in request.files:
        file = request.files["image"]
        if file.filename != '':
            fd, temp_path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            file.save(temp_path)
            
    if not temp_path:
        return jsonify({"success": False, "error": "No image provided"}), 400

    if temp_path:
        try:
            # If it's a DICOM file, convert to PNG and store metadata
            if temp_path.endswith('.dcm'):
                ds = pydicom.dcmread(temp_path)
                dicom_meta = {
                    "PatientName": str(ds.get("PatientName", "")),
                    "PatientID": str(ds.get("PatientID", "")),
                    "StudyDate": str(ds.get("StudyDate", "")),
                    "Modality": str(ds.get("Modality", ""))
                }
                arr = ds.pixel_array
                arr = arr - np.min(arr)
                if np.max(arr) > 0:
                    arr = arr / np.max(arr)
                arr = (arr * 255).astype(np.uint8)
                
                png_path = temp_path + ".png"
                cv2.imwrite(png_path, arr)
                temp_path = png_path # Models will use this PNG

            current_date_str = datetime.now().strftime("%Y-%m-%d")

            # Stage 1: Preprocessing
            processed_img = preprocess_for_analysis(temp_path)
            if processed_img is None:
                processed_img = np.zeros((512, 512), dtype=np.uint8)

            # Stage 2: Detection & bone loss
            detections = td_model.detect_teeth(temp_path)
            landmarks = ld_model.detect_landmarks(detections, processed_img)
            bone_loss_results = compute_bone_loss(landmarks)
            
            pixels_per_mm, calib_conf, calib_status = _aligner.calibrate_pixels_per_mm(processed_img, detections)

            # Stage 3: Landmark data assembly
            past_xrays = xray_mgr.get_records_by_patient(patient_id)
            landmark_data = build_longitudinal_landmark_dict(
                current_landmarks=landmarks,
                current_date=current_date_str,
                patient_history=past_xrays,
                bone_loss_results=bone_loss_results,
                pixels_per_mm=pixels_per_mm,
                calib_conf=calib_conf,
                calib_status=calib_status
            )

            # Stage 4: TALPA velocity & grading
            patient = patient_mgr.get_patient(patient_id)
            age = patient.get("age", 40) if patient else 40
            risk_factors = {
                "smoker_cpd": int(request.form.get("smoker_cpd", 0) or 0),
                "hba1c": float(request.form.get("hba1c", 0.0) or 0.0),
            }

            talpa_results = _talpa_calculator.compute_full_mouth_velocity_profile(
                landmark_data=landmark_data,
                visit_dates={},
                risk_factors=risk_factors if any(risk_factors.values()) else None,
            )

            progression_table = analyze_progression(past_xrays, bone_loss_results)

            # Stage 5: Future escalation risk
            risk_profile = _talpa_calculator.estimate_future_grade_risk(
                talpa_results["per_site_results"]
            )

            predictions = {}
            for bl_data in progression_table:
                tid = bl_data["tooth_id"]
                feat = {
                    "current_bl": bl_data.get("current_bl", 0),
                    "velocity": bl_data.get("delta", 0),
                    "age": age,
                    "pos": tid,
                    "prev_bl": bl_data.get("current_bl", 0) - bl_data.get("delta", 0),
                    "years": 1,
                }
                predictions[tid] = rp_model.predict_tooth_risk(feat)

            # Stage 6: Visualization
            annotated_img = draw_findings_on_image(processed_img, detections, landmarks, bone_loss_results)
            ann_filename = f"{patient_id}_{uuid.uuid4().hex[:8]}_annotated.png"
            os.makedirs("storage/annotated_results", exist_ok=True)
            ann_path = os.path.join("storage/annotated_results", ann_filename)
            cv2.imwrite(ann_path, annotated_img)

            # Build per-tooth TALPA grade lookup from per_site_results
            talpa_grade_lookup = {}
            velocity_lookup = {}
            for sr in talpa_results.get("per_site_results", []):
                tid = sr.get("tooth_id")
                grade = sr.get("grade_result", {}).get("grade")
                vel = sr.get("velocity_result", {}).get("velocity_mm_per_year")
                if tid is not None:
                    talpa_grade_lookup[tid] = f"Grade {grade}" if grade else "Insufficient Data"
                    if vel is not None:
                        velocity_lookup[tid] = vel

            # Format final frontend payload
            analysis_dict = {
                "teeth": [],
                "full_mouth_summary": talpa_results.get("full_mouth_summary", {}),
                "escalation_risk": risk_profile,
            }

            for det_obj in detections:
                tid = det_obj.get("tooth_number")
                bl_pct = bone_loss_results.get(tid, {}).get("bone_loss_pct", 0)
                sev = bone_loss_results.get(tid, {}).get("severity", "Unknown")
                risk_lvl = predictions.get(tid, {}).get("risk_level", "Unknown")
                talpa_grade = talpa_grade_lookup.get(tid, "Insufficient Data")
                velocity = velocity_lookup.get(tid, 0.0)
                
                rel_flag = det_obj.get("reliability_flag", "none")
                h_agree = det_obj.get("heatmap_agreement", 1.0)

                analysis_dict["teeth"].append({
                    "tooth_id": tid,
                    "bone_loss_pct": bl_pct,
                    "severity": sev,
                    "velocity_per_year": velocity,
                    "talpa_grade": talpa_grade,
                    "risk_level": risk_lvl,
                    "reliability_flag": rel_flag,
                    "heatmap_agreement": h_agree,
                })

            # Stage 7: Persist & respond
            record_id = f"REC_{uuid.uuid4().hex[:6]}"
            bone_loss_results_str = _stringify_keys(bone_loss_results)
            predictions_str = _stringify_keys(predictions)
            xray_mgr.create_record(
                record_id=record_id,
                patient_id=patient_id,
                image_path=temp_path,
                analysis_date=current_date_str,
                bone_loss_results=bone_loss_results_str,
                predictions=predictions_str,
                annotated_path=ann_path,
                dicom_metadata=dicom_meta,
                analysis_payload=analysis_dict,
            )
            
            # Update record with DICOM metadata if available
            if dicom_meta:
                db_record = xray_mgr.collection.find_one({"record_id": record_id})
                if db_record:
                    xray_mgr.collection.update_one({"record_id": record_id}, {"$set": {"dicom_metadata": dicom_meta}})

            os.remove(temp_path)

            logger.info(
                f"TALPA analysis complete for patient {patient_id}: "
                f"overall_grade={talpa_results['full_mouth_summary'].get('overall_grade')}, "
                f"high_risk_teeth={risk_profile.get('high_risk_tooth_count', 0)}"
            )

            return jsonify({
                "success": True,
                "record_id": record_id,
                "analysis": analysis_dict,
                "annotated_path": ann_path.replace(os.path.sep, '/'),
            })

        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            logger.exception("Analysis failed")
            import pymongo.errors
            if isinstance(e, pymongo.errors.ConnectionFailure):
                return jsonify({"success": False, "error": "Database service unavailable"}), 503
            return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/report/<record_id>", methods=["GET"])
@audit_action("download_report")
def download_report(record_id):
    if "doctor_id" not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        xray_record = xray_mgr.get_record(
            record_id,
            requester_id=session["doctor_id"],
            requester_role=session.get("role", "doctor"),
        )
        if not xray_record:
            return jsonify({"success": False, "error": "Record not found"}), 404

        pdf_bytes = generate_clinical_report(record_id, session["doctor_id"])
        report_dir = os.path.join(ROOT_DIR, "storage", "reports")
        os.makedirs(report_dir, exist_ok=True)
        report_path = os.path.join(report_dir, f"{record_id}.pdf")
        with open(report_path, "wb") as report_file:
            report_file.write(pdf_bytes)

        verifier = ModelIntegrityVerifier()
        verifier.sign_model(report_path)
        xray_mgr.update_record_fields(
            record_id,
            {
                "report_path": report_path,
                "report_generated_at": datetime.now().isoformat(),
            },
        )
        return send_file(
            report_path,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"PerioVision_Report_{record_id}.pdf"
        )
    except OSError as oe:
        if oe.errno == 28:
            return jsonify({"success": False, "error": "Insufficient storage space on disk"}), 507
        return jsonify({"success": False, "error": str(oe)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route("/api/image", methods=["GET"])
def get_image():
    path = request.args.get("path")
    if not path:
        return jsonify({"error": "Path required"}), 400
        
    # Block directory traversal
    abs_path = os.path.abspath(path)
    allowed_dir_1 = os.path.abspath(os.path.join(ROOT_DIR, "storage"))
    allowed_dir_2 = os.path.abspath(os.path.join(ROOT_DIR, "web"))
    allowed_dir_3 = os.path.abspath(os.path.join(ROOT_DIR, "temp")) # allow temp files if needed
    
    if not (abs_path.startswith(allowed_dir_1) or abs_path.startswith(allowed_dir_2) or abs_path.startswith(allowed_dir_3) or "tempfile" in abs_path):
        # Allow temp files or enforce absolute path check:
        # Let's check: if ".." in path or any parent dir reference:
        if ".." in path or path.startswith("/") or path.startswith("\\") or ":" in path:
            if not (abs_path.startswith(allowed_dir_1) or abs_path.startswith(allowed_dir_2) or abs_path.startswith(allowed_dir_3)):
                return jsonify({"error": "Path traversal blocked"}), 400
                
    if not os.path.exists(path):
        return jsonify({"error": "Image not found"}), 404
    return send_file(path, mimetype='image/png')

@app.route("/api/audit-log", methods=["GET"])
def get_audit_log():
    if "doctor_id" not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    from security.rbac import RBACEnforcer
    rbac = RBACEnforcer()
    doc = doctor_mgr.collection.find_one({"doctor_id": session["doctor_id"]})
    if not doc or not rbac.can_access(doc.get("role", "doctor"), "superadmin"):
        return jsonify({"success": False, "error": "Forbidden"}), 403
        
    audit_log = MerkleAuditLog()
    logs = list(audit_log.logs.find({}, {"_id": 0}).sort("sequence_number", -1).limit(50))
    return jsonify({"success": True, "logs": logs})

@app.route("/api/audit-log/verify", methods=["GET"])
def verify_audit_log():
    if "doctor_id" not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    from security.rbac import RBACEnforcer
    rbac = RBACEnforcer()
    doc = doctor_mgr.collection.find_one({"doctor_id": session["doctor_id"]})
    if not doc or not rbac.can_access(doc.get("role", "doctor"), "superadmin"):
        return jsonify({"success": False, "error": "Forbidden"}), 403
        
    audit_log = MerkleAuditLog()
    res = audit_log.verify_chain_integrity()
    return jsonify({
        "success": True, 
        "chain_valid": res["chain_intact"], 
        "record_count": res["entries_verified"],
        "verification": {
            "chain_intact": res["chain_intact"],
            "entries_verified": res["entries_verified"]
        }
    })

@app.route("/admin/stats", methods=["GET"])
@audit_action("view_admin_stats")
def get_admin_stats():
    if "doctor_id" not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    from security.rbac import RBACEnforcer
    rbac = RBACEnforcer()
    doc = doctor_mgr.collection.find_one({"doctor_id": session["doctor_id"]})
    if not doc or not rbac.can_access(doc.get("role", "doctor"), "superadmin"):
        return jsonify({"success": False, "error": "Forbidden"}), 403
        
    total_doctors = doctor_mgr.collection.count_documents({})
    total_patients = patient_mgr.collection.count_documents({})
    total_xrays = xray_mgr.collection.count_documents({})
    
    return jsonify({
        "success": True,
        "stats": {
            "total_doctors": total_doctors,
            "total_patients": total_patients,
            "total_xrays": total_xrays
        }
    })

@app.route("/admin/dashboard", methods=["GET"])
def admin_dashboard():
    # Render an admin dashboard page (stub)
    if "doctor_id" not in session:
        return "Unauthorized", 401
    from security.rbac import RBACEnforcer
    rbac = RBACEnforcer()
    doc = doctor_mgr.collection.find_one({"doctor_id": session["doctor_id"]})
    if not doc or not rbac.can_access(doc.get("role", "doctor"), "superadmin"):
        return "Forbidden", 403
    return "<h1>SuperAdmin Dashboard</h1><p>Welcome to global operations.</p>"

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
