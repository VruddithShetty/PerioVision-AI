"""Patient management page with search, details, and edit."""
import sys as _sys, os as _os
_wd = _os.path.dirname(_os.path.abspath(__file__))
for _p in [_os.path.dirname(_wd), _wd]:
    if _p not in _sys.path: _sys.path.insert(0, _p)
import streamlit as st
import pandas as pd
import plotly.express as px
from ui_styles import section_title, page_header


def render_patients(doctor, patient_mgr, xray_mgr, notif_mgr):
    st.markdown(page_header("👥 Patient Management", "Search, view, and manage your patient records"), unsafe_allow_html=True)

    pts = patient_mgr.get_patients_by_doctor(doctor["doctor_id"])
    if not pts:
        st.info("No patients yet. Register one in the 'Register Patient' tab.")
        return

    # Search bar
    search = st.text_input("🔍 Search patients by name, ID, or gender", placeholder="Type to filter...")
    if search:
        s = search.lower()
        pts = [p for p in pts if s in p["patient_name"].lower()
               or s in str(p["patient_id"])
               or s in p.get("gender", "").lower()]

    st.markdown(f"**{len(pts)} patient(s) found**")
    st.markdown("---")

    if not pts:
        st.warning("No patients match your search.")
        return

    # Patient list
    for p in pts:
        recs = xray_mgr.get_records_by_patient(p["patient_id"])
        # determine highest risk
        worst = "Low Risk"
        for rec in recs:
            for v in rec.get("prediction_results", {}).values():
                rl = v.get("risk_level") if isinstance(v, dict) else str(v)
                if rl == "High Risk":
                    worst = "High Risk"; break
                elif rl == "Medium Risk" and worst != "High Risk":
                    worst = "Medium Risk"
        badge = {"High Risk": "badge-danger", "Medium Risk": "badge-warn", "Low Risk": "badge-success"}[worst]
        badge_icon = {"High Risk": "🔴", "Medium Risk": "🟠", "Low Risk": "🟢"}[worst]

        with st.expander(f"👤 {p['patient_name']}  |  ID: {p['patient_id']}  |  Age: {p['age']}  |  Records: {len(recs)}"):
            pc1, pc2, pc3, pc4 = st.columns(4)
            pc1.metric("Name",   p["patient_name"])
            pc2.metric("Age",    p["age"])
            pc3.metric("Gender", p["gender"])
            pc4.metric("Sessions", len(recs))
            st.markdown(f"**Overall Risk:** <span class='{badge}'>{badge_icon} {worst}</span>",
                        unsafe_allow_html=True)
            if p.get("contact_number"):
                st.caption(f"📞 {p['contact_number']}")
            if p.get("notes"):
                st.info(f"📝 **Notes:** {p['notes']}")

            st.markdown(section_title("📈 Bone Loss Trend"), unsafe_allow_html=True)
            if recs:
                trend_data = []
                for rec in recs:
                    for tk, bl in rec.get("bone_loss_metrics", rec.get("bone_loss_results", {})).items():
                        if isinstance(bl, (int, float)):
                            trend_data.append({"Date": rec["analysis_date"],
                                               "Tooth": str(tk).replace("tooth_", "T"), "Bone Loss %": bl})
                if trend_data:
                    df_t = pd.DataFrame(trend_data)
                    fig = px.line(df_t, x="Date", y="Bone Loss %", color="Tooth", markers=True,
                                  color_discrete_sequence=px.colors.qualitative.Set2)
                    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                      font_family="Inter", margin=dict(t=10, b=10, l=0, r=0))
                    st.plotly_chart(fig, use_container_width=True)

            # Inline edit
            with st.form(f"edit_{p['patient_id']}"):
                st.markdown("**✏️ Edit Patient Info**")
                e1, e2 = st.columns(2)
                new_name    = e1.text_input("Name",    value=p["patient_name"], key=f"en_{p['patient_id']}")
                new_age     = e1.number_input("Age",   value=p["age"], min_value=1, max_value=120, key=f"ea_{p['patient_id']}")
                new_contact = e2.text_input("Contact", value=p.get("contact_number",""), key=f"ec_{p['patient_id']}")
                new_notes   = e2.text_area("Notes",    value=p.get("notes",""), key=f"enotes_{p['patient_id']}", height=70)
                if st.form_submit_button("💾 Save", use_container_width=True):
                    patient_mgr.update_patient(p["patient_id"], patient_name=new_name, age=new_age,
                                               contact_number=new_contact, notes=new_notes)
                    st.success("✅ Patient updated!")
                    st.rerun()
