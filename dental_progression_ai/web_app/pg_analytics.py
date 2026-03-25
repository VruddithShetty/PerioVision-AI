"""Analytics page: system-wide charts and bone loss trends."""
import sys as _sys, os as _os
_wd = _os.path.dirname(_os.path.abspath(__file__))
for _p in [_os.path.dirname(_wd), _wd]:
    if _p not in _sys.path: _sys.path.insert(0, _p)
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from ui_styles import section_title, page_header


def render_analytics(doctor, patient_mgr, xray_mgr, appt_mgr):
    st.markdown(page_header("📈 Practice Analytics", "Visualize bone loss trends, risk distribution and appointment activity"), unsafe_allow_html=True)

    pts  = patient_mgr.get_patients_by_doctor(doctor["doctor_id"])
    if not pts:
        st.info("No data yet. Register patients and run analyses to see charts.")
        return

    all_records, all_bl, risk_counts = [], [], {"Low Risk": 0, "Medium Risk": 0, "High Risk": 0}
    for p in pts:
        recs = xray_mgr.get_records_by_patient(p["patient_id"])
        for rec in recs:
            all_records.append(rec)
            for tk, bl in rec.get("bone_loss_metrics", rec.get("bone_loss_results", {})).items():
                if isinstance(bl, (int, float)):
                    all_bl.append({"Date": rec["analysis_date"], "Patient": p["patient_name"],
                                   "Tooth": str(tk).replace("tooth_", "T"), "Bone Loss %": bl})
            for v in rec.get("prediction_results", {}).values():
                rl = v.get("risk_level") if isinstance(v, dict) else str(v)
                if rl in risk_counts:
                    risk_counts[rl] += 1

    tab1, tab2, tab3 = st.tabs(["🦴 Bone Loss Trends", "🔬 Risk Distribution", "🗓️ Appointment Stats"])

    with tab1:
        st.markdown(section_title("Bone Loss Over Time"), unsafe_allow_html=True)
        if all_bl:
            df_bl = pd.DataFrame(all_bl)
            # Allow filtering by patient
            sel_pt = st.multiselect("Filter by Patient", options=df_bl["Patient"].unique().tolist(),
                                    default=df_bl["Patient"].unique().tolist()[:5])
            df_filt = df_bl[df_bl["Patient"].isin(sel_pt)] if sel_pt else df_bl
            fig = px.box(df_filt, x="Date", y="Bone Loss %", color="Patient",
                         points="all", title="Bone Loss Distribution per Session")
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font_family="Outfit", font_color="#F8FAFC", margin=dict(t=30, b=10))
            st.plotly_chart(fig, use_container_width=True)

            fig2 = px.scatter(df_filt, x="Date", y="Bone Loss %", color="Tooth",
                              size="Bone Loss %", hover_data=["Patient"],
                              title="Per-Tooth Bone Loss Scatter")
            fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_family="Outfit", font_color="#F8FAFC")
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Run analyses on patients to generate bone loss data.")

    with tab2:
        st.markdown(section_title("Risk Level Distribution"), unsafe_allow_html=True)
        if any(risk_counts.values()):
            c1, c2 = st.columns(2)
            with c1:
                fig = px.pie(names=list(risk_counts.keys()), values=list(risk_counts.values()),
                             color=list(risk_counts.keys()),
                             color_discrete_map={"Low Risk":"#43A047","Medium Risk":"#FB8C00","High Risk":"#E53935"},
                             hole=0.5, title="Tooth-Level Risk Counts")
                fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_family="Outfit", font_color="#F8FAFC")
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                fig2 = go.Figure(go.Bar(
                    x=list(risk_counts.keys()), y=list(risk_counts.values()),
                    marker_color=["#43A047","#FB8C00","#E53935"],
                    text=list(risk_counts.values()), textposition="outside"
                ))
                fig2.update_layout(title="Risk Count Bar Chart", paper_bgcolor="rgba(0,0,0,0)",
                                   plot_bgcolor="rgba(0,0,0,0)", font_family="Outfit", font_color="#F8FAFC")
                st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Run analyses to generate risk data.")

    with tab3:
        st.markdown(section_title("Appointment Activity"), unsafe_allow_html=True)
        appts = appt_mgr.get_by_doctor(doctor["doctor_id"])
        if appts:
            df_appt = pd.DataFrame(appts)
            status_counts = df_appt["status"].value_counts()
            fig = px.bar(x=status_counts.index, y=status_counts.values,
                         labels={"x": "Status", "y": "Count"}, title="Appointments by Status",
                         color=status_counts.index,
                         color_discrete_map={"Scheduled":"#1565C0","Completed":"#43A047",
                                             "Cancelled":"#E53935","No-Show":"#9E9E9E"})
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_family="Inter")
            st.plotly_chart(fig, use_container_width=True)

            if "type" in df_appt.columns:
                type_counts = df_appt["type"].value_counts()
                fig2 = px.pie(names=type_counts.index, values=type_counts.values, title="Appointments by Type", hole=0.4)
                fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_family="Inter")
                st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No appointment data yet.")
