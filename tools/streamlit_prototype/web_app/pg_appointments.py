"""Appointments scheduling and management page."""
import sys as _sys, os as _os
_wd = _os.path.dirname(_os.path.abspath(__file__))
for _p in [_os.path.dirname(_wd), _wd]:
    if _p not in _sys.path: _sys.path.insert(0, _p)
import streamlit as st
import pandas as pd
import datetime
from database.appointment_manager import APPOINTMENT_TYPES, APPOINTMENT_STATUS
from ui_styles import section_title, page_header


def render_appointments(doctor, patient_mgr, appt_mgr, audit_log):
    st.markdown(page_header("🗓️ Appointments", "Schedule, view, and manage patient appointments"), unsafe_allow_html=True)

    pts   = patient_mgr.get_patients_by_doctor(doctor["doctor_id"])
    p_map = {f"{p['patient_id']} — {p['patient_name']}": p["patient_id"] for p in pts}

    tab_sched, tab_view = st.tabs(["➕ Schedule New", "📋 View All"])

    with tab_sched:
        if not p_map:
            st.info("Register a patient first.")
        else:
            with st.container(border=True):
                with st.form("appt_form"):
                    st.markdown("#### 📝 New Appointment")
                    sel_pt = st.selectbox("Patient *", list(p_map.keys()))
                    c1, c2 = st.columns(2)
                    appt_date = c1.date_input("Date *", min_value=datetime.date.today())
                    appt_time = c2.time_input("Time *", value=datetime.time(10, 0))
                    appt_type = st.selectbox("Type *", APPOINTMENT_TYPES)
                    appt_notes = st.text_area("Notes / Reason", height=80)
                    sub = st.form_submit_button("✅ Schedule Appointment", use_container_width=True)

                if sub:
                    pid = p_map[sel_pt]
                    appt_mgr.create(pid, doctor["doctor_id"],
                                    appt_date.isoformat(), appt_time.strftime("%H:%M"),
                                    appt_type, appt_notes)
                    audit_log.log(doctor["doctor_id"], "APPT_CREATED",
                                  f"Appointment for patient {pid} on {appt_date}")
                    st.success(f"✅ Appointment scheduled for {appt_date.strftime('%B %d, %Y')} at {appt_time.strftime('%H:%M')}")
                    st.rerun()

    with tab_view:
        status_filter = st.selectbox("Filter Status", ["All"] + APPOINTMENT_STATUS, key="appt_filter")
        sf = None if status_filter == "All" else status_filter
        appts = appt_mgr.get_by_doctor(doctor["doctor_id"], status=sf)

        if not appts:
            st.info("No appointments found.")
        else:
            # Build patient name lookup
            pt_lookup = {p["patient_id"]: p["patient_name"] for p in pts}

            # Summary counts
            counts = {s: sum(1 for a in appts if a["status"] == s) for s in APPOINTMENT_STATUS}
            sc1, sc2, sc3, sc4 = st.columns(4)
            sc1.metric("📅 Scheduled",  counts.get("Scheduled", 0))
            sc2.metric("✅ Completed",  counts.get("Completed", 0))
            sc3.metric("❌ Cancelled",  counts.get("Cancelled", 0))
            sc4.metric("🚫 No-Show",    counts.get("No-Show", 0))

            st.markdown("---")
            for appt in appts:
                pname = pt_lookup.get(appt["patient_id"], f"ID:{appt['patient_id']}")
                status_icon = {"Scheduled": "📅", "Completed": "✅", "Cancelled": "❌", "No-Show": "🚫"}.get(appt["status"], "📋")
                with st.expander(f"{status_icon} {appt['date']} {appt['time']}  |  {pname}  |  {appt['type']}"):
                    a1, a2 = st.columns([2, 1])
                    a1.markdown(f"**Patient:** {pname}  \n**Type:** {appt['type']}  \n**Notes:** {appt.get('notes') or '—'}")
                    a2.markdown(f"**Status:** {appt['status']}  \n**ID:** `{appt['appointment_id']}`")

                    if appt["status"] == "Scheduled":
                        b1, b2, b3 = st.columns(3)
                        with b1:
                            if st.button("✅ Complete", key=f"done_{appt['appointment_id']}", use_container_width=True):
                                appt_mgr.update_status(appt["appointment_id"], "Completed")
                                st.rerun()
                        with b2:
                            if st.button("❌ Cancel", key=f"cancel_{appt['appointment_id']}", use_container_width=True, type="secondary"):
                                appt_mgr.update_status(appt["appointment_id"], "Cancelled")
                                st.rerun()
                        with b3:
                            if st.button("🚫 No-Show", key=f"noshow_{appt['appointment_id']}", use_container_width=True, type="secondary"):
                                appt_mgr.update_status(appt["appointment_id"], "No-Show")
                                st.rerun()
