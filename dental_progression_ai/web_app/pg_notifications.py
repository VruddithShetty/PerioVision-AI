"""Notifications page."""
import sys as _sys, os as _os
_wd = _os.path.dirname(_os.path.abspath(__file__))
for _p in [_os.path.dirname(_wd), _wd]:
    if _p not in _sys.path: _sys.path.insert(0, _p)
import streamlit as st
from ui_styles import section_title, page_header


def render_notifications(doctor, notif_mgr):
    st.markdown(page_header("🔔 Notifications & Alerts", "Risk alerts and system messages"), unsafe_allow_html=True)

    unread = notif_mgr.get_unread(doctor["doctor_id"])
    all_n  = notif_mgr.get_all(doctor["doctor_id"])

    c1, c2 = st.columns(2)
    c1.metric("🔴 Unread", len(unread))
    c2.metric("📋 Total",  len(all_n))

    if unread:
        if st.button("✅ Mark All as Read", use_container_width=True, type="secondary"):
            notif_mgr.mark_read(doctor["doctor_id"])
            st.rerun()

    st.markdown("---")
    st.markdown(section_title("📬 All Notifications"), unsafe_allow_html=True)

    if not all_n:
        st.info("🎉 No notifications yet. Notifications appear after analyzing high-risk cases.")
        return

    level_map = {"danger": ("🔴", "rgba(220, 38, 38, 0.1)", "#F87171"),
                 "warning": ("🟠", "rgba(251, 191, 36, 0.1)", "#FBBF24"),
                 "info":    ("🔵", "rgba(56, 189, 248, 0.1)", "#38BDF8")}

    for n in all_n:
        icon, bg, border = level_map.get(n.get("level", "info"), ("🔵", "rgba(56, 189, 248, 0.1)", "#38BDF8"))
        read_mark = "" if n.get("read") else " 🆕"
        with st.expander(f"{icon} {n['title']}{read_mark}  —  {n.get('created_at', '')}"):
            st.markdown(f"""
            <div style="background:{bg}; border-left:4px solid {border}; border-radius:0 12px 12px 0; padding:16px 20px; color:var(--text-primary); backdrop-filter:blur(10px);">
                {n['message']}
            </div>""", unsafe_allow_html=True)

            if n.get("patient_id"):
                st.caption(f"Patient ID: {n['patient_id']}")
