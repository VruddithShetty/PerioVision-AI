import sys
import os
import streamlit as st

# Ensure project root and src/ are in path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "src"))

from security.headers import inject_security_headers
from security.honeypot import HoneypotManager
from ui.styles import GLOBAL_CSS, BRAND_HTML
from ui.pg_auth import render_login, render_register
from ui.pg_dashboard import render_dashboard, render_admin
from ui.pg_patients import render_patients
from ui.pg_analytics import render_analytics
from ui.pg_tooth_timeline import render_tooth_timeline
from ui.pg_risk_watchlist import render_risk_watchlist
from ui.pg_xray_comparison import render_xray_comparison
from ui.pg_report_vault import render_report_vault


def _nav_button(label, page_name):
    """Render a navigation button and update the active page state on click."""
    if st.sidebar.button(label, use_container_width=True, key=f"nav_{page_name}"):
        st.session_state.nav_page = page_name
        st.rerun()


def render_settings(doctor):
    """Render a lightweight account/settings view."""
    st.markdown("## ⚙️ Settings", unsafe_allow_html=True)
    st.write("**Doctor ID:**", doctor.get("doctor_id", "Unknown"))
    st.write("**Name:**", doctor.get("name", "Unknown"))
    st.write("**Email:**", doctor.get("email", "Unknown"))
    st.write("**Role:**", doctor.get("role", "doctor"))
    st.info("Account preferences and security settings can be extended here.")

# 1. Security First
inject_security_headers()
HoneypotManager().create_honeypot_patient()

# 2. Page Config
st.set_page_config(page_title="PerioVision AI", page_icon="🦷", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# 3. Session State
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "doctor" not in st.session_state:
    st.session_state.doctor = None
if "nav_page" not in st.session_state:
    st.session_state.nav_page = "Dashboard"

# 4. App Flow
if not st.session_state.logged_in:
    st.markdown(BRAND_HTML, unsafe_allow_html=True)
    tab_l, tab_r = st.tabs(["Login", "Register"])
    with tab_l: render_login()
    with tab_r: render_register()
else:
    st.markdown(BRAND_HTML, unsafe_allow_html=True)
    doctor_role = st.session_state.doctor.get("role", "doctor")

    # Sidebar Navigation
    with st.sidebar:
        st.markdown("### 🧭 Navigation")
        st.markdown("#### Clinical")
        _nav_button("Dashboard", "Dashboard")
        _nav_button("Tooth timeline", "Tooth timeline")
        _nav_button("X-ray comparison", "X-ray comparison")

        st.markdown("#### Practice")
        _nav_button("Risk watchlist", "Risk watchlist")
        _nav_button("Patients", "Patients")

        st.markdown("#### Reports")
        _nav_button("Analytics", "Analytics")
        _nav_button("Report vault", "Report vault")

        st.markdown("#### Account")
        _nav_button("Settings", "Settings")
        if doctor_role == "admin":
            _nav_button("Administration", "Administration")

        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.doctor = None
            st.session_state.nav_page = "Dashboard"
            st.rerun()

    # Database Managers (Lazy Init)
    from database.patients import PatientManager
    patient_mgr = PatientManager()
    page = st.session_state.get("nav_page", "Dashboard")

    if page == "Dashboard":
        render_dashboard(st.session_state.doctor, patient_mgr)
    elif page == "Tooth timeline":
        render_tooth_timeline()
    elif page == "X-ray comparison":
        render_xray_comparison()
    elif page == "Risk watchlist":
        render_risk_watchlist()
    elif page == "Patients":
        render_patients(patient_mgr, st.session_state.doctor)
    elif page == "Analytics":
        render_analytics(st.session_state.doctor)
    elif page == "Report vault":
        render_report_vault()
    elif page == "Settings":
        render_settings(st.session_state.doctor)
    elif page == "Administration":
        if st.session_state.doctor.get("role") == "admin":
            render_admin(st.session_state.doctor)
        else:
            st.error("Admin Access Required")
