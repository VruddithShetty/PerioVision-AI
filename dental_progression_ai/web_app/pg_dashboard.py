"""Dashboard and Admin Dashboard pages."""
import sys as _sys, os as _os
_wd = _os.path.dirname(_os.path.abspath(__file__))
for _p in [_os.path.dirname(_wd), _wd]:
    if _p not in _sys.path: _sys.path.insert(0, _p)
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from ui_styles import stat_card, section_title, page_header
import datetime


def render_dashboard(doctor, patient_mgr, xray_mgr, appt_mgr, notif_mgr):
    st.markdown(page_header(f"🏠 Dashboard — Dr. {doctor['name']}", datetime.datetime.now().strftime('%A, %B %d %Y')), unsafe_allow_html=True)

    pts       = patient_mgr.get_patients_by_doctor(doctor["doctor_id"])
    rec_count = sum(len(xray_mgr.get_records_by_patient(p["patient_id"])) for p in pts)
    upcoming  = appt_mgr.get_upcoming(doctor["doctor_id"], days=7)
    unread    = notif_mgr.unread_count(doctor["doctor_id"])

    # Premium stat row
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(stat_card("👥", len(pts),       "My Patients",       "#0D47A1"), unsafe_allow_html=True)
    c2.markdown(stat_card("📷", rec_count,      "X-Rays Analyzed",   "#1565C0"), unsafe_allow_html=True)
    c3.markdown(stat_card("🗓️", len(upcoming),  "Upcoming This Week", "#059669"), unsafe_allow_html=True)
    c4.markdown(stat_card("🔔", unread,         "Unread Alerts",     "#DC2626" if unread else "#64748B"), unsafe_allow_html=True)

    # Quick Actions
    st.markdown(section_title("⚡ Quick Actions"), unsafe_allow_html=True)
    qa1, qa2, qa3, qa4 = st.columns(4)
    for col, icon, title, desc, color in [
        (qa1, "👤", "Add Patient",      "Register a new patient",         "#0D47A1"),
        (qa2, "🔬", "Analyze X-Ray",    "Run AI bone loss detection",      "#1565C0"),
        (qa3, "📊", "TALPA Analysis",   "Temporal progression tracking",   "#7C3AED"),
        (qa4, "🔄", "Transfer Patient", "Move patient to another doctor",  "#059669"),
    ]:
        col.markdown(f"""
        <div style="background:var(--glass-bg); border:1px solid var(--glass-border); border-radius:var(--radius-md); padding:20px;
            text-align:center; box-shadow:0 8px 32px 0 rgba(0, 0, 0, 0.3);
            transition:transform 0.3s cubic-bezier(0.4, 0, 0.2, 1); cursor:pointer; backdrop-filter:blur(10px);">
            <div style="background:linear-gradient(135deg,{color}33,{color}11);
                width:56px; height:56px; border-radius:16px; display:flex; align-items:center;
                justify-content:center; margin:0 auto 12px; font-size:1.8rem;
                border:1px solid {color}44; box-shadow:0 0 15px {color}22;">{icon}</div>
            <div style="font-weight:700; color:var(--text-primary); font-size:1rem; margin-bottom:4px; font-family:'Space Grotesk';">{title}</div>
            <div style="color:var(--text-muted); font-size:0.8rem; line-height:1.4;">{desc}</div>
        </div>""", unsafe_allow_html=True)


    col_l, col_r = st.columns([1.6, 1])

    with col_l:
        st.markdown(section_title("📅 Upcoming Appointments (7 days)"), unsafe_allow_html=True)
        if upcoming:
            rows = [{"Date": a["date"], "Time": a["time"], "Patient": a["patient_id"],
                     "Type": a["type"], "Status": a["status"]} for a in upcoming]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("No upcoming appointments this week.")

    with col_r:
        st.markdown(section_title("🔔 Recent Alerts"), unsafe_allow_html=True)
        alerts = notif_mgr.get_unread(doctor["doctor_id"], limit=5)
        if alerts:
            for a in alerts:
                icon = "🔴" if a["level"] == "danger" else ("🟠" if a["level"] == "warning" else "🔵")
                with st.container(border=True):
                    st.markdown(f"**{icon} {a['title']}**")
                    st.caption(a["message"])
            if st.button("✅ Mark All Read", use_container_width=True, type="secondary"):
                notif_mgr.mark_read(doctor["doctor_id"])
                st.rerun()
        else:
            st.success("✅ All caught up — no unread alerts!")

    # Risk distribution chart
    if pts:
        st.markdown("---")
        st.markdown(section_title("📊 Risk Distribution Across My Patients"), unsafe_allow_html=True)
        risk_counts = {"Low Risk": 0, "Medium Risk": 0, "High Risk": 0}
        for p in pts:
            for rec in xray_mgr.get_records_by_patient(p["patient_id"]):
                for v in rec.get("prediction_results", {}).values():
                    rl = v.get("risk_level") if isinstance(v, dict) else str(v)
                    if rl in risk_counts:
                        risk_counts[rl] += 1

        if any(risk_counts.values()):
            fig = px.pie(
                names=list(risk_counts.keys()),
                values=list(risk_counts.values()),
                color=list(risk_counts.keys()),
                color_discrete_map={"Low Risk": "#43A047", "Medium Risk": "#FB8C00", "High Risk": "#E53935"},
                hole=0.45,
            )
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font_family="Inter", margin=dict(t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)


def render_admin(doctor, doctor_mgr, patient_mgr, xray_mgr, audit_log):
    if doctor.get("role") != "admin":
        st.error("⛔ Access Denied — Admin only area.")
        return

    st.markdown(page_header("🏥 Admin Dashboard", "System-wide management and analytics"), unsafe_allow_html=True)

    sys_stats = doctor_mgr.get_system_stats()
    all_pts   = patient_mgr.get_all_patients()
    all_drs   = doctor_mgr.get_all_doctors()
    audit_stats = audit_log.get_stats()

    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(stat_card("👨‍⚕️", sys_stats["total"],    "Total Doctors"),    unsafe_allow_html=True)
    c2.markdown(stat_card("✅",    sys_stats["active"],   "Active Accounts"),  unsafe_allow_html=True)
    c3.markdown(stat_card("👥",    len(all_pts),          "Total Patients"),   unsafe_allow_html=True)
    c4.markdown(stat_card("🔐",    sys_stats["with_2fa"], "2FA Enrolled"),     unsafe_allow_html=True)

    st.markdown("---")
    # Doctors management table
    st.markdown(section_title("👨‍⚕️ Doctor Accounts"), unsafe_allow_html=True)
    if all_drs:
        for dr in all_drs:
            with st.expander(f"{'👑 ' if dr['role']=='admin' else '👨‍⚕️ '}  Dr. {dr['name']}  |  {dr['email']}  |  {dr.get('city','—')}"):
                dc1, dc2, dc3 = st.columns(3)
                dc1.info(f"**Role:** {dr['role'].capitalize()}")
                dc2.info(f"**Status:** {dr.get('status','active').capitalize()}")
                dc3.info(f"**2FA:** {'✅ Active' if dr.get('totp_enabled') else '⚠️ Not Set'}")
                st.caption(f"License: {dr.get('license_number','—')} | Clinic: {dr.get('clinic','—')} | Last login: {dr.get('last_login','Never')}")

                if dr["doctor_id"] != doctor["doctor_id"]:
                    b1, b2, b3 = st.columns(3)
                    with b1:
                        is_active = dr.get("status", "active") == "active"
                        btn_label = "🚫 Deactivate" if is_active else "✅ Activate"
                        new_status = "inactive" if is_active else "active"
                        if st.button(btn_label, key=f"status_{dr['doctor_id']}", use_container_width=True, type="secondary"):
                            doctor_mgr.set_status(dr["doctor_id"], new_status)
                            audit_log.log(doctor["doctor_id"], "ADMIN_STATUS",
                                          f"Set Dr.{dr['name']} status={new_status}", level="WARNING")
                            st.rerun()
                    with b2:
                        if dr["role"] != "admin":
                            if st.button("👑 Make Admin", key=f"admin_{dr['doctor_id']}", use_container_width=True, type="secondary"):
                                doctor_mgr.set_role(dr["doctor_id"], "admin")
                                audit_log.log(doctor["doctor_id"], "ADMIN_ROLE", f"Promoted Dr.{dr['name']} to admin")
                                st.rerun()

    st.markdown("---")
    # Audit log
    st.markdown(section_title("📋 Audit Log"), unsafe_allow_html=True)
    ca, cb, cc = st.columns(3)
    ca.metric("Total Events", audit_stats["total"])
    cb.metric("⚠️ Warnings",  audit_stats["warnings"])
    cc.metric("🚨 Critical",   audit_stats["critical"])

    recent_logs = audit_log.get_recent(n=30)
    if recent_logs:
        level_filter = st.selectbox("Filter by Level", ["All", "INFO", "WARNING", "CRITICAL"], key="log_level")
        filtered = [l for l in recent_logs if level_filter == "All" or l["level"] == level_filter]
        df_log = pd.DataFrame(filtered)
        if not df_log.empty:
            def color_level(val):
                c = {"INFO": "#1565C0", "WARNING": "#E65100", "CRITICAL": "#C62828"}
                return f"color:{c.get(val,'#0D2137')};font-weight:700"
            st.dataframe(df_log.style.applymap(color_level, subset=["level"]),
                         use_container_width=True, hide_index=True)
    else:
        st.info("No audit events recorded yet.")
