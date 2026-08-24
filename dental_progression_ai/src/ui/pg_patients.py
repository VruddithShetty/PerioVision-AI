import streamlit as st
import plotly.graph_objects as go
from database.xrays import XrayRecordManager
from ui.styles import page_header, empty_state_container


def _parse_analysis_date(value):
    """Parse an X-ray analysis date into a datetime object."""
    import datetime

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


def _average_bone_loss_series(records):
    """Build a date-sorted average bone loss series from patient X-ray records."""
    series = []
    for record in records or []:
        teeth = record.get("analysis_result", {})
        values = []
        if isinstance(teeth, dict):
            for tooth in teeth.values():
                try:
                    values.append(float(tooth.get("bone_loss_pct", 0.0) or 0.0))
                except (TypeError, ValueError):
                    continue
        elif isinstance(teeth, list):
            for tooth in teeth:
                try:
                    values.append(float(tooth.get("bone_loss_pct", 0.0) or 0.0))
                except (TypeError, ValueError):
                    continue
        if values:
            series.append((
                _parse_analysis_date(record.get("analysis_date")),
                sum(values) / len(values),
            ))
    return [(dt, value) for dt, value in sorted(series, key=lambda item: item[0]) if dt is not None]


def _sparkline_figure(series):
    """Render a compact trend sparkline for patient card use."""
    if not series:
        return go.Figure()
    x_values = [point[0] for point in series]
    y_values = [point[1] for point in series]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x_values, y=y_values, mode="lines+markers", line=dict(color="#38BDF8", width=2), marker=dict(size=4)))
    fig.update_layout(
        height=120,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    return fig

def render_patients(patient_mgr, doctor):
    st.markdown(page_header("👥 Patient Management", "View and manage clinical records"), unsafe_allow_html=True)
    
    patients = patient_mgr.get_patients_by_doctor(doctor["doctor_id"])
    if not patients:
        st.markdown(empty_state_container("👥", "No Patients Found", "Start by adding a new patient record."), unsafe_allow_html=True)
    else:
        xray_mgr = XrayRecordManager()
        for patient in patients:
            with st.expander(f"{patient.get('patient_name', 'Unknown')}  •  ID {patient.get('patient_id', '-')}"):
                left, right = st.columns([2, 1])
                with left:
                    st.write(f"**Age:** {patient.get('age', '-')}")
                    st.write(f"**Gender:** {patient.get('gender', '-')}")
                    st.write(f"**Doctor ID:** {patient.get('doctor_id', '-')}")
                records = xray_mgr.get_records_by_patient(patient.get("patient_id"), requester_id=doctor["doctor_id"], requester_role=doctor.get("role", "doctor"))
                series = _average_bone_loss_series(records)
                with right:
                    if series:
                        st.plotly_chart(_sparkline_figure(series), use_container_width=True, config={"displayModeBar": False})
                    else:
                        st.info("No X-ray history yet.")
