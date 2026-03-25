"""
PerioVision AI — Main Application Entry Point
Orchestrates auth flow and all page modules.
Run with: streamlit run web_app/streamlit_app.py
"""
import sys, os
# Ensure the project root (dental_progression_ai/) is always in sys.path,
# regardless of whether Streamlit was launched from the root or the web_app dir.
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import streamlit as st
import os
import cv2
import datetime
import uuid
import pandas as pd
from PIL import Image
from io import BytesIO

# ─── Page config (must be first) ───
st.set_page_config(
    page_title="PerioVision AI",
    page_icon="🦷",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ─── Shared styles ───
from web_app.ui_styles import GLOBAL_CSS, BRAND_HTML, page_header, empty_state_container
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# ─── Database managers ───
from database.patient_manager import PatientManager
from database.xray_record_manager import XrayRecordManager
from database.doctor_manager import DoctorManager
from database.audit_logger import AuditLogger
from database.appointment_manager import AppointmentManager
from database.notification_manager import NotificationManager

# ─── AI / Analysis modules ───
from utilities.generate_patient_id import generate_next_patient_id
from utilities.dataset_loader import ensure_storage_directories
from image_processing.preprocess_xray import preprocess_for_analysis
from image_processing.radiograph_alignment import align_radiographs
from models.tooth_detection_model.inference import ToothDetectionModel
from models.landmark_detection_model.inference import LandmarkDetectionModel
from analysis.calculate_bone_loss import compute_bone_loss
from analysis.progression_analysis import analyze_progression
from analysis.risk_prediction import RiskPredictor
from analysis.landmark_detection import LandmarkDetector
from analysis.radiograph_alignment import RadiographAligner
from analysis.progression_velocity_calculator import ProgressionVelocityCalculator
from prediction.tooth_risk_prediction import ToothRiskPredictor
from visualization.draw_annotations import draw_findings_on_image
from visualization.progression_map_generator import generate_progression_map
from report_generation.generate_dental_report import generate_pdf_report, generate_csv_report

# ─── Page renderers ───
from web_app.pg_auth import render_login, render_register, render_2fa
from web_app.pg_dashboard import render_dashboard, render_admin
from web_app.pg_patients import render_patients
from web_app.pg_appointments import render_appointments
from web_app.pg_analytics import render_analytics
from web_app.pg_profile import render_profile
from web_app.pg_notifications import render_notifications

# ─── Init ───
ensure_storage_directories()

@st.cache_resource
def load_ai_models():
    return ToothDetectionModel(), LandmarkDetectionModel(), RiskPredictor()

@st.cache_resource
def get_db_managers():
    return (PatientManager(), XrayRecordManager(), DoctorManager(),
            AuditLogger(), AppointmentManager(), NotificationManager())

td_model, ld_model, rp_model = load_ai_models()
patient_mgr, xray_mgr, doctor_mgr, audit_log, appt_mgr, notif_mgr = get_db_managers()
landmark_detector = LandmarkDetector()
aligner           = RadiographAligner(method="affine")
velocity_calc     = ProgressionVelocityCalculator()
risk_predictor    = ToothRiskPredictor()

# ─── Session defaults ───
for k, v in [("logged_in", False), ("doctor", None), ("auth_mode", "login"), ("pending_2fa", None)]:
    if k not in st.session_state:
        st.session_state[k] = v

# ═══════════════════════════════════════════
#  AUTH GATE (3D REDESIGN)
# ═══════════════════════════════════════════
if not st.session_state.logged_in:
    # Hide sidebar via CSS when not logged in
    st.markdown("<style>[data-testid='stSidebar'] { display: none !important; }</style>", unsafe_allow_html=True)
    
    mode = st.session_state.auth_mode
    if mode == "login":
        render_login(doctor_mgr, audit_log)
    elif mode == "2fa":
        render_2fa(doctor_mgr, audit_log)
    else:
        render_register(doctor_mgr)
    st.stop()

# ── Render Header only when logged in ──
st.markdown(BRAND_HTML, unsafe_allow_html=True)

# ═══════════════════════════════════════════
#  AUTHENTICATED APP
# ═══════════════════════════════════════════
doctor = st.session_state.doctor

# ── Sidebar ──
with st.sidebar:
    unread_count = notif_mgr.unread_count(doctor["doctor_id"])
    badge = f" 🔴{unread_count}" if unread_count else ""
    st.markdown(f"""
    <div style="text-align:center;padding:20px 0 10px;">
        <div style="font-size:3rem;">👨‍⚕️</div>
        <h3 style="color:white!important;margin:8px 0 2px;">Dr. {doctor['name']}</h3>
        <p style="color:#90CAF9!important;font-size:.8rem;margin:0;">{doctor.get('clinic','') or 'No clinic'}</p>
        <p style="color:#64B5F6!important;font-size:.75rem;">🌆 {doctor.get('city','') or '—'}
        {'&nbsp;&nbsp;👑 Admin' if doctor.get('role')=='admin' else ''}</p>
    </div>
    <hr style="border-color:rgba(255,255,255,.15);margin:12px 0;">
    """, unsafe_allow_html=True)
    st.caption(f"🏅 License: {doctor.get('license_number','—')}")
    st.caption(f"📧 {doctor.get('email','')}")
    st.caption(f"🔐 2FA: {'✅ On' if doctor.get('totp_enabled') else '⚠️ Off'}")
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button(f"🔔 Notifications{badge}", use_container_width=True, type="secondary"):
        st.session_state["active_page"] = "notifications"
        st.rerun()
    if st.button("🚪 Logout", use_container_width=True):
        audit_log.log(doctor["doctor_id"], "LOGOUT", f"Dr. {doctor['name']} logged out")
        for k in ["logged_in", "doctor", "auth_mode", "pending_2fa"]:
            st.session_state[k] = False if k == "logged_in" else None
        st.session_state["auth_mode"] = "login"
        st.rerun()

# ── Helper ──
def my_patients():
    pts = patient_mgr.get_patients_by_doctor(doctor["doctor_id"])
    if not pts:
        all_p = patient_mgr.get_all_patients()
        pts = [p for p in all_p if p.get("doctor_id") is None]
    return pts

def p_map(pts):
    return {f"{p['patient_id']} — {p['patient_name']}": p["patient_id"] for p in pts}

# ── Direct page override (from sidebar buttons) ──
if st.session_state.get("active_page") == "notifications":
    render_notifications(doctor, notif_mgr)
    if st.button("← Back to Dashboard", type="secondary"):
        st.session_state.pop("active_page", None)
        st.rerun()
    st.stop()

# ─── Tab definitions ───
is_admin = doctor.get("role") == "admin"
tab_names = ["🏠 Dashboard", "👥 Patients", "👤 Add Patient",
             "🔬 Analyze X-Ray", "📊 TALPA Analysis", "📂 Records",
             "🗓️ Appointments", "📈 Analytics", "🔄 Transfer",
             "⚙️ Profile"]
if is_admin:
    tab_names.insert(1, "🏥 Admin")

tabs = st.tabs(tab_names)
t = 0  # tab offset

def next_tab():
    global t
    idx = t; t += 1; return idx

# ═══ TAB: DASHBOARD ═══
with tabs[next_tab()]:
    render_dashboard(doctor, patient_mgr, xray_mgr, appt_mgr, notif_mgr)

# ═══ TAB: ADMIN (conditional) ═══
if is_admin:
    with tabs[next_tab()]:
        render_admin(doctor, doctor_mgr, patient_mgr, xray_mgr, audit_log)

# ═══ TAB: PATIENT MANAGEMENT ═══
with tabs[next_tab()]:
    render_patients(doctor, patient_mgr, xray_mgr, notif_mgr)

# ═══ TAB: REGISTER PATIENT ═══
with tabs[next_tab()]:
    st.markdown(page_header("👤 Register New Patient", "Add a new patient to your practice"), unsafe_allow_html=True)
    with st.container(border=True):
        with st.form("add_patient_form"):
            st.markdown("#### 📋 Patient Details")
            c1, c2 = st.columns(2)
            with c1:
                p_name    = st.text_input("Full Name *", placeholder="e.g. Priya Singh")
                p_age     = st.number_input("Age *", min_value=1, max_value=120, value=35)
                p_contact = st.text_input("Contact / Email", placeholder="patient@email.com")
            with c2:
                p_gender = st.radio("Gender", ["Male", "Female", "Other"], horizontal=True)
                p_notes  = st.text_area("Clinical Notes", height=107, placeholder="Allergies, past procedures...")
            submitted = st.form_submit_button("✅ Register Patient", use_container_width=True)
        if submitted:
            if p_name:
                new_pid = generate_next_patient_id()
                patient_mgr.create_patient(new_pid, p_name, p_age, p_gender, p_contact, p_notes, doctor_id=doctor["doctor_id"])
                audit_log.log(doctor["doctor_id"], "PATIENT_CREATED", f"Patient {p_name} ID:{new_pid}")
                st.success(f"✅ **{p_name}** registered! ID: **{new_pid}**")
                st.balloons()
            else:
                st.warning("Patient name is required.")

# ═══ TAB: UPLOAD & ANALYZE ═══
with tabs[next_tab()]:
    st.markdown(page_header("🔬 Upload & Analyze X-Ray", "AI-powered periodontal bone loss measurement with TALPA"), unsafe_allow_html=True)
    pts = my_patients()
    pm  = p_map(pts)
    if not pm:
        st.info("Register a patient first.")
    else:
        col_l, col_r = st.columns([1, 1.8])
        with col_l:
            with st.container(border=True):
                st.markdown("#### ⚙️ Settings")
                sel_str = st.selectbox("Patient", list(pm.keys()))
                sel_pid = pm[sel_str]
                uploaded = st.file_uploader("Upload X-Ray", type=["png","jpg","jpeg"], label_visibility="collapsed")
                if uploaded:
                    st.image(Image.open(uploaded), caption="Uploaded", use_container_width=True)
                run_btn = st.button("🚀 Run AI Analysis", use_container_width=True, type="primary", disabled=(uploaded is None))

        with col_r:
            if uploaded and run_btn:
                with st.spinner("🧠 Running AI Pipeline..."):
                    ext = uploaded.name.split(".")[-1]
                    uid = uuid.uuid4().hex[:8]
                    raw_fn  = f"{sel_pid}_{datetime.datetime.now().strftime('%Y%m%d')}_{uid}.{ext}"
                    raw_path = os.path.join("storage","xrays",raw_fn)
                    with open(raw_path,"wb") as f: f.write(uploaded.getbuffer())

                    proc_img   = preprocess_for_analysis(raw_path)
                    past_xrays = xray_mgr.get_records_by_patient(sel_pid)
                    aligned    = proc_img
                    if past_xrays:
                        last_img = cv2.imread(past_xrays[-1]["xray_image_path"])
                        if last_img is not None:
                            aligned = align_radiographs(last_img, proc_img)

                    detections  = td_model.detect_teeth(raw_path)
                    landmarks   = ld_model.detect_landmarks(aligned, detections)
                    bl_results  = compute_bone_loss(landmarks)
                    prog_table  = analyze_progression(past_xrays, bl_results)
                    pat_data    = patient_mgr.get_patient(sel_pid)
                    predictions = rp_model.evaluate_all_teeth(prog_table, pat_data["age"])

                    # TALPA
                    talpa_lm = landmark_detector.extract_landmarks(aligned, detections)
                    talpa_bl = velocity_calc.calculate_bone_loss(talpa_lm)
                    prev_bl  = past_xrays[-1].get("bone_loss_metrics",{}) if past_xrays else {}
                    time_diff = 1.0
                    if past_xrays:
                        try:
                            pd_ = datetime.datetime.strptime(past_xrays[-1]["analysis_date"],"%Y-%m-%d")
                            time_diff = max(0.01,(datetime.datetime.now()-pd_).days/365.0)
                        except Exception: pass
                    velocity     = velocity_calc.calculate_progression_velocity(prev_bl, talpa_bl, time_diff)
                    talpa_preds  = risk_predictor.predict_all_teeth(talpa_bl, velocity, pat_data)
                    annotated    = draw_findings_on_image(aligned, detections, landmarks, bl_results)
                    annot_path   = os.path.join("storage","annotated_results",raw_fn)
                    cv2.imwrite(annot_path, annotated)
                    map_fn   = f"{uid}_map.jpg"
                    map_path = os.path.join("storage","annotated_results",map_fn)
                    prog_map = generate_progression_map(aligned, detections, talpa_bl, velocity, talpa_preds)
                    cv2.imwrite(map_path, prog_map)

                    record_id = f"XR{datetime.datetime.now().strftime('%Y%m%d')}{uid}"
                    xray_mgr.create_record(record_id=record_id, patient_id=sel_pid,
                        xray_image_path=raw_path, bone_loss_results=bl_results, risk_prediction=predictions,
                        landmark_coordinates=talpa_lm, bone_loss_metrics=talpa_bl,
                        progression_velocity=velocity, prediction_results=talpa_preds)

                    # Auto notification for high-risk teeth
                    high_risk = [tk for tk, pi in talpa_preds.items()
                                 if (pi.get("risk_level") if isinstance(pi,dict) else pi) == "High Risk"]
                    if high_risk:
                        notif_mgr.auto_risk_alert(doctor["doctor_id"], pat_data["patient_name"], sel_pid, high_risk)

                    audit_log.log(doctor["doctor_id"], "ANALYSIS", f"Analyzed patient {sel_pid} record {record_id}")

                st.success("✅ Analysis Complete!")
                st.image(cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB), caption="Annotated Output", use_container_width=True)
                for row in prog_table:
                    row["Risk"] = predictions.get(row["Tooth"],"—")
                st.dataframe(pd.DataFrame(prog_table), use_container_width=True, hide_index=True)

                pdf_path = f"storage/annotated_results/{record_id}_report.pdf"
                csv_path = f"storage/annotated_results/{record_id}_report.csv"
                generate_pdf_report(pat_data, {"analysis_date": datetime.datetime.now().strftime("%Y-%m-%d"), "record_id": record_id, "bone_loss_results": bl_results},
                                    prog_table, predictions, pdf_path, velocity_metrics=velocity, talpa_map_image_path=map_path)
                generate_csv_report(pat_data, {"analysis_date": datetime.datetime.now().strftime("%Y-%m-%d"), "record_id": record_id, "bone_loss_results": bl_results},
                                    prog_table, predictions, csv_path, velocity_metrics=velocity)
                d1, d2 = st.columns(2)
                with d1:
                    with open(pdf_path,"rb") as pf: st.download_button("📄 PDF Report", pf, f"{pat_data['patient_name']}_Report.pdf","application/pdf",use_container_width=True)
                with d2:
                    with open(csv_path,"rb") as cf: st.download_button("📊 CSV Data", cf, f"{pat_data['patient_name']}_Data.csv","text/csv",use_container_width=True)
            elif not uploaded:
                st.markdown(empty_state_container("📁", "Upload an X-Ray to Begin", "Select a patient and drop a JPEG/PNG radiograph"), unsafe_allow_html=True)

# ═══ TAB: TALPA PROGRESSION ANALYSIS ═══
with tabs[next_tab()]:
    st.markdown(page_header("📊 TALPA Progression Analysis", "Landmark-based temporal alignment and bone loss velocity"), unsafe_allow_html=True)
    pts = my_patients(); pm = p_map(pts)
    if not pm:
        st.info("Register patients and analyze X-rays first.")
    else:
        pa_str = st.selectbox("Patient", list(pm.keys()), key="talpa_pt")
        pa_pid = pm[pa_str]
        records = xray_mgr.get_records_by_patient(pa_pid)
        if not records:
            st.info("No records for this patient. Upload and analyze first.")
        else:
            rec_labels = [f"📅 {r['analysis_date']}  |  {r['record_id']}" for r in records]
            sel_lbl = st.selectbox("Session", rec_labels, key="talpa_rec")
            sel_rec = records[rec_labels.index(sel_lbl)]
            idx     = records.index(sel_rec)

            ca, cb = st.columns(2)
            img_p = sel_rec.get("xray_image_path","")
            with ca:
                st.markdown("#### 📸 Current Session")
                if img_p and os.path.exists(img_p):
                    st.image(img_p, caption=f"Date: {sel_rec['analysis_date']}", use_container_width=True)
            with cb:
                if idx > 0:
                    prev_rec = records[idx-1]
                    prev_p   = prev_rec.get("xray_image_path","")
                    st.markdown("#### 🕐 Previous (Aligned)")
                    if prev_p and os.path.exists(prev_p) and img_p and os.path.exists(img_p):
                        c_cv = cv2.imread(img_p); p_cv = cv2.imread(prev_p)
                        cl = sel_rec.get("landmark_coordinates",{}); pl = prev_rec.get("landmark_coordinates",{})
                        if c_cv is not None and p_cv is not None and cl and pl:
                            aln = aligner.align_images(p_cv, c_cv, pl, cl)
                            st.image(cv2.cvtColor(aln, cv2.COLOR_BGR2RGB), caption=f"Aligned: {prev_rec['analysis_date']}", use_container_width=True)
                        else:
                            st.image(prev_p, use_container_width=True)
                else:
                    st.info("🏁 Baseline — no previous session.")

            bl_m = sel_rec.get("bone_loss_metrics",{}); vm = sel_rec.get("progression_velocity",{}); tp = sel_rec.get("prediction_results",{})
            if bl_m:
                st.markdown("---"); st.markdown("### 🦴 Bone Loss & Risk Table")
                rows = []
                for tk, loss in bl_m.items():
                    vel = vm.get(tk); pred = tp.get(tk,{}); risk = pred.get("risk_level","—") if isinstance(pred,dict) else str(pred)
                    sev = "Healthy" if loss<15 else ("Mild" if loss<30 else ("Moderate" if loss<50 else "Severe"))
                    rows.append({"🦷 Tooth": tk.replace("tooth_",""), "Bone Loss (%)": loss, "Severity": sev,
                                 "Velocity (%/yr)": f"{vel:+.2f}" if isinstance(vel,(int,float)) else "Baseline", "Risk": risk})
                df = pd.DataFrame(rows)
                def cr(v):
                    c = {"Low Risk":"#1B5E20","Medium Risk":"#E65100","High Risk":"#B71C1C","Healthy":"#1B5E20","Mild":"#F57F17","Moderate":"#E65100","Severe":"#B71C1C"}
                    return f"color:{c.get(v,'#0D2137')};font-weight:700"
                st.dataframe(df.style.applymap(cr,subset=["Severity","Risk"]), use_container_width=True, hide_index=True)

            if vm:
                vd = {k.replace("tooth_","T"): v for k,v in vm.items() if isinstance(v,(int,float))}
                if vd:
                    st.markdown("---"); st.markdown("### 📈 Velocity Chart")
                    st.bar_chart(pd.DataFrame({"Tooth":list(vd.keys()),"Vel":list(vd.values())}).set_index("Tooth"))

            if img_p and os.path.exists(img_p) and bl_m:
                raw_cv = cv2.imread(img_p)
                if raw_cv is not None:
                    st.markdown("---"); st.markdown("### 🗺️ Disease Map")
                    det_map = td_model.detect_teeth(img_p)
                    ov = generate_progression_map(raw_cv, det_map, bl_m, vm, tp)
                    st.image(cv2.cvtColor(ov, cv2.COLOR_BGR2RGB), caption="Color-coded severity overlay", use_container_width=True)
                    buf = BytesIO(); Image.fromarray(cv2.cvtColor(ov, cv2.COLOR_BGR2RGB)).save(buf, format="PNG")
                    st.download_button("📥 Download Map", buf.getvalue(), f"{sel_rec['record_id']}_map.png","image/png",use_container_width=True)

# ═══ TAB: PATIENT RECORDS ═══
with tabs[next_tab()]:
    st.markdown(page_header("📂 Patient Records", "Historical analysis and longitudinal data"), unsafe_allow_html=True)
    pts = my_patients(); pm = p_map(pts)
    if not pm:
        st.info("No patients found.")
    else:
        rec_str = st.selectbox("Patient", list(pm.keys()), key="rec_sel")
        rec_pid = pm[rec_str]; pat = patient_mgr.get_patient(rec_pid)
        records = xray_mgr.get_records_by_patient(rec_pid)
        pc1,pc2,pc3,pc4 = st.columns(4)
        pc1.metric("Name", pat["patient_name"]); pc2.metric("Age", pat["age"]); pc3.metric("Gender", pat["gender"]); pc4.metric("Sessions", len(records))
        st.markdown("---")
        if not records:
            st.info("No X-ray records for this patient.")
        else:
            for rec in reversed(records):
                with st.expander(f"📁 {rec['analysis_date']}  |  {rec['record_id']}"):
                    e1,e2 = st.columns(2)
                    with e1:
                        st.markdown("**🦴 Bone Loss**"); st.json(rec.get("bone_loss_results",{}))
                    with e2:
                        st.markdown("**📈 Velocity**"); st.json(rec.get("progression_velocity",{}))
                    if rec.get("prediction_results"):
                        rd = {k: (v.get("risk_level") if isinstance(v,dict) else v) for k,v in rec["prediction_results"].items()}
                        st.markdown("**🔬 Risk**"); st.json(rd)

# ═══ TAB: APPOINTMENTS ═══
with tabs[next_tab()]:
    render_appointments(doctor, patient_mgr, appt_mgr, audit_log)

# ═══ TAB: ANALYTICS ═══
with tabs[next_tab()]:
    render_analytics(doctor, patient_mgr, xray_mgr, appt_mgr)

# ═══ TAB: TRANSFER PATIENT ═══
with tabs[next_tab()]:
    st.markdown(page_header("🔄 Transfer Patient", "Move a patient to another doctor's care"), unsafe_allow_html=True)
    pts = my_patients(); pm_tr = p_map(pts)
    other_drs = [d for d in doctor_mgr.get_all_doctors() if d["doctor_id"] != doctor["doctor_id"]]
    if not pm_tr:
        st.info("No patients to transfer.")
    elif not other_drs:
        st.warning("No other registered doctors found. The destination doctor must register first.")
    else:
        with st.container(border=True):
            tr_pt  = st.selectbox("Patient to Transfer", list(pm_tr.keys()), key="tr_p")
            tr_pid = pm_tr[tr_pt]; tr_patient = patient_mgr.get_patient(tr_pid)
            tc1,tc2,tc3 = st.columns(3)
            tc1.info(f"👤 **{tr_patient['patient_name']}**"); tc2.info(f"🎂 Age: {tr_patient['age']}"); tc3.info(f"📷 {len(xray_mgr.get_records_by_patient(tr_pid))} records")
            dr_opts = {f"Dr. {d['name']} — {d.get('clinic','') or '?'} ({d.get('city','—')})": d["doctor_id"] for d in other_drs}
            dest_str = st.selectbox("Destination Doctor", list(dr_opts.keys()), key="tr_dr")
            dest_id  = dr_opts[dest_str]
            st.warning(f"⚠️ **{tr_patient['patient_name']}** will be moved to **{dest_str}** immediately and removed from your list.")
            b1,b2 = st.columns(2)
            with b1:
                if st.button("✅ Confirm Transfer", type="primary", use_container_width=True, key="confirm_tr"):
                    patient_mgr.transfer_patient(tr_pid, dest_id)
                    audit_log.log(doctor["doctor_id"], "PATIENT_TRANSFER",
                                  f"Patient {tr_pid} → Dr.{dest_id}", level="WARNING")
                    st.success(f"✅ **{tr_patient['patient_name']}** transferred successfully!")
                    st.balloons()
            with b2:
                st.button("✖️ Cancel", type="secondary", use_container_width=True, key="cancel_tr")

# ═══ TAB: MY PROFILE ═══
with tabs[next_tab()]:
    render_profile(doctor, doctor_mgr, audit_log)
