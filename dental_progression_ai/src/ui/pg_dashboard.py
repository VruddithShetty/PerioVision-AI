import streamlit as st
import datetime
import os
from collections import defaultdict
import plotly.graph_objects as go
from ui.styles import stat_card, section_title, page_header
from security.threat_intel import ThreatIntelligenceCollector
from security.governance import GovernanceReporter
from security.readiness import ProductionReadinessChecker
from database.audit import AuditLogger
from database.doctors import DoctorManager
from database.xrays import XrayRecordManager

# Initialize
threat_intel = ThreatIntelligenceCollector()
gov_reporter = GovernanceReporter()
readiness_checker = ProductionReadinessChecker()
audit_log = AuditLogger()
doctor_mgr = DoctorManager()


def _parse_record_date(value):
    """Parse an ISO-like analysis date into a datetime object."""
    if not value:
        return None
    if isinstance(value, datetime.datetime):
        return value
    try:
        parsed = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        try:
            return datetime.datetime.strptime(str(value), "%Y-%m-%d")
        except ValueError:
            return None


def _snapshot_metrics(patient_ids, xray_mgr, cutoff_date, requester_id, requester_role):
    """Build a snapshot of the latest record per patient up to a cutoff date."""
    snapshot = {}
    for patient_id in patient_ids:
        records = xray_mgr.get_records_by_patient(patient_id, requester_id=requester_id, requester_role=requester_role)
        eligible = []
        for record in records:
            record_date = _parse_record_date(record.get("analysis_date"))
            if record_date and record_date <= cutoff_date:
                eligible.append((record_date, record))
        if eligible:
            snapshot[patient_id] = sorted(eligible, key=lambda item: item[0])[-1][1]
    return snapshot


def _extract_teeth(record):
    """Return a normalized tooth mapping from a stored X-ray record."""
    if not record:
        return {}
    analysis = record.get("analysis_result", {})
    if isinstance(analysis, dict):
        return analysis
    if isinstance(analysis, list):
        normalized = {}
        for tooth in analysis:
            tooth_id = tooth.get("tooth_id")
            if tooth_id is not None:
                normalized[str(tooth_id)] = tooth
        return normalized
    return {}


def _grade_rank(grade):
    """Map a TALPA grade to a numeric rank for comparisons."""
    return {"A": 1, "B": 2, "C": 3}.get(str(grade).replace("Grade ", "").strip(), 0)


def _worst_grade(record):
    """Compute the worst grade present in a record."""
    worst = 0
    for tooth in _extract_teeth(record).values():
        grade = tooth.get("talpa_grade") or tooth.get("grade")
        worst = max(worst, _grade_rank(grade))
    return {1: "A", 2: "B", 3: "C"}.get(worst)


def _high_risk_count(record):
    """Count high-risk teeth in a record."""
    count = 0
    for tooth in _extract_teeth(record).values():
        risk = str(tooth.get("risk_level") or tooth.get("risk") or "").title()
        if risk == "High":
            count += 1
    return count


def _overdue_flag(record, current_date):
    """Return whether a patient is overdue for recall based on grade and age of last X-ray."""
    if not record:
        return False
    record_date = _parse_record_date(record.get("analysis_date"))
    if not record_date:
        return False
    days_since = (current_date - record_date).days
    worst_grade = _worst_grade(record)
    if worst_grade == "C" and days_since > 180:
        return True
    if worst_grade == "B" and days_since > 365:
        return True
    return False


def _build_month_comparison(patient_ids, xray_mgr, now, requester_id, requester_role):
    """Build current and previous month clinical snapshot counts."""
    month_start = datetime.datetime(now.year, now.month, 1, tzinfo=now.tzinfo)
    previous_month_end = month_start - datetime.timedelta(seconds=1)
    previous_month_start = (month_start - datetime.timedelta(days=1)).replace(day=1)
    current_snapshot = _snapshot_metrics(patient_ids, xray_mgr, now, requester_id, requester_role)
    previous_snapshot = _snapshot_metrics(patient_ids, xray_mgr, previous_month_end, requester_id, requester_role)

    current_high_risk = sum(_high_risk_count(record) for record in current_snapshot.values())
    previous_high_risk = sum(_high_risk_count(record) for record in previous_snapshot.values())
    current_overdue = sum(1 for record in current_snapshot.values() if _overdue_flag(record, now))
    previous_overdue = sum(1 for record in previous_snapshot.values() if _overdue_flag(record, previous_month_end))

    current_month_records = 0
    previous_month_records = 0
    for patient_id in patient_ids:
        records = xray_mgr.get_records_by_patient(patient_id, requester_id=requester_id, requester_role=requester_role)
        for record in records:
            record_date = _parse_record_date(record.get("analysis_date"))
            if not record_date:
                continue
            if month_start <= record_date <= now:
                current_month_records += 1
            elif previous_month_start <= record_date <= previous_month_end:
                previous_month_records += 1

    return {
        "current_high_risk": current_high_risk,
        "previous_high_risk": previous_high_risk,
        "current_overdue": current_overdue,
        "previous_overdue": previous_overdue,
        "current_month_records": current_month_records,
        "previous_month_records": previous_month_records,
    }

def render_dashboard(doctor, patient_mgr):
    st.markdown(page_header(f"👋 Welcome, Dr. {doctor['name']}", "Clinical Overview & Security Metrics"), unsafe_allow_html=True)

    xray_mgr = XrayRecordManager()
    patients = patient_mgr.get_patients_by_doctor(doctor["doctor_id"])
    patient_ids = [patient.get("patient_id") for patient in patients if patient.get("patient_id") is not None]
    now = datetime.datetime.now(datetime.timezone.utc)
    snapshot = _build_month_comparison(patient_ids, xray_mgr, now, doctor["doctor_id"], doctor.get("role", "doctor"))

    c1, c2, c3 = st.columns(3)
    c1.metric(
        "High risk teeth",
        snapshot["current_high_risk"],
        snapshot["current_high_risk"] - snapshot["previous_high_risk"],
        delta_color="inverse",
    )
    c2.metric(
        "Overdue recalls",
        snapshot["current_overdue"],
        snapshot["current_overdue"] - snapshot["previous_overdue"],
        delta_color="inverse",
    )
    c3.metric(
        "New this month",
        snapshot["current_month_records"],
        snapshot["current_month_records"] - snapshot["previous_month_records"],
        delta_color="normal",
    )
    
    # Summary Stats
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(stat_card("👥", len(patients), "Total Patients"), unsafe_allow_html=True)
    c2.markdown(stat_card("🦷", "128", "Analyses Run"), unsafe_allow_html=True)
    c3.markdown(stat_card("🚨", "2", "Risk Alerts"), unsafe_allow_html=True)
    c4.markdown(stat_card("🛡️", "Active", "Security Mode", "#4ade80"), unsafe_allow_html=True)

def render_admin(doctor):
    st.markdown(page_header("🏥 System Administration", "Governance, Security, and Audit Logs"), unsafe_allow_html=True)
    
    t_sec, t_drs, t_threat, t_audit, t_gov = st.tabs([
        "🛡️ Security Control", "👨‍⚕️ User Management", "📡 Threat Intelligence", "📋 Audit Trail", "📜 Governance"
    ])
    
    with t_threat:
        st.markdown("### 📡 Real-Time Threat Intel")
        metrics = threat_intel.get_security_metrics()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Adversarial Hits", metrics["adversarial_hits"])
        m2.metric("Honeypot Breaches", metrics["honeypot_breaches"])
        m3.metric("Failed Logins", metrics["failed_logins"])
        m4.metric("Verified States", metrics["verified_states"])

    with t_gov:
        st.markdown("### 📜 Governance & Compliance")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### 🚀 Production Readiness")
            check = readiness_checker.run_preflight_check()
            if check["is_ready"]: st.success("🏆 SYSTEM PRODUCTION READY")
            else: st.error("❌ READINESS CHECK FAILED")
        
        with c2:
            st.markdown("#### 📄 Signed Reports")
            if st.button("🏗️ Generate & Sign Audit Report"):
                report_path = "storage/reports/audit_signed.pdf"
                os.makedirs("storage/reports", exist_ok=True)
                gov_reporter.generate_signed_audit_report(report_path, doctor["doctor_id"])
                st.success("Report generated and digitally signed.")
