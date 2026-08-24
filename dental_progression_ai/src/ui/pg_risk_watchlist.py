import datetime
import html

import streamlit as st

from database.patients import PatientManager
from database.xrays import XrayRecordManager
from ui.styles import empty_state_container, page_header


def _go_to_patient(patient_id):
    """Set the active patient and navigate to the Patients page."""
    st.session_state.current_patient_id = patient_id
    st.session_state.nav_page = "Patients"
    st.rerun()


def _parse_date(value):
    """Parse an ISO-like string into a datetime object."""
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


def _normalize_teeth(record):
    """Normalize the stored analysis payload to a tooth dictionary."""
    analysis = record.get("analysis_result", {}) if record else {}
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
    """Map a TALPA grade to a sortable rank."""
    value = str(grade or "").replace("Grade ", "").strip().upper()
    return {"A": 1, "B": 2, "C": 3}.get(value, 0)


def _risk_rank(risk_level):
    """Map risk levels to a numeric rank."""
    return {"Low": 0, "Medium": 1, "High": 2}.get(str(risk_level).title(), 0)


def _badge(text, color):
    """Render a compact HTML badge for inline display."""
    return f'<span style="display:inline-block;padding:4px 10px;border-radius:999px;background:{color};color:#fff;font-size:12px;font-weight:700;">{html.escape(str(text))}</span>'


def _days_overdue(record, today):
    """Calculate the days since the most recent X-ray."""
    record_date = _parse_date(record.get("analysis_date"))
    if not record_date:
        return None
    return (today - record_date).days


def _is_overdue(record, today):
    """Determine if a patient should be flagged for recall."""
    days = _days_overdue(record, today)
    if days is None:
        return False
    worst_grade = _worst_grade(record)
    if worst_grade == "C" and days > 180:
        return True
    if worst_grade == "B" and days > 365:
        return True
    return False


def _worst_grade(record):
    """Extract the worst TALPA grade from the stored tooth analysis."""
    worst = 0
    for tooth in _normalize_teeth(record).values():
        worst = max(worst, _grade_rank(tooth.get("talpa_grade") or tooth.get("grade")))
    return {1: "A", 2: "B", 3: "C"}.get(worst)


def _flatten_rows(patients, xray_mgr, doctor):
    """Flatten the latest record for each patient into per-tooth risk rows."""
    rows = []
    today = datetime.datetime.now(datetime.timezone.utc)
    for patient in patients:
        record = xray_mgr.get_latest_record_for_patient(
            patient.get("patient_id"),
            requester_id=doctor["doctor_id"],
            requester_role=doctor.get("role", "doctor"),
        )
        if not record:
            continue

        record_date = _parse_date(record.get("analysis_date"))
        days_since = _days_overdue(record, today)
        teeth = _normalize_teeth(record)
        for tooth_id, tooth in teeth.items():
            risk = str(tooth.get("risk_level") or tooth.get("risk") or "").title()
            if risk not in {"Medium", "High"}:
                continue
            bone_loss_pct = float(tooth.get("bone_loss_pct", 0.0) or 0.0)
            velocity = float(tooth.get("velocity_per_year", 0.0) or 0.0)
            rows.append({
                "patient_id": patient.get("patient_id"),
                "patient_name": patient.get("patient_name", "Unknown"),
                "tooth_id": tooth_id,
                "risk_level": risk,
                "bone_loss_pct": bone_loss_pct,
                "velocity": velocity,
                "last_xray_date": record_date,
                "days_overdue": days_since,
                "grade": tooth.get("talpa_grade") or tooth.get("grade") or _worst_grade(record),
                "risk_score": _risk_rank(risk) * 100 + int(bone_loss_pct) + int(abs(velocity) * 10),
                "overdue": _is_overdue(record, today),
            })
    return rows


def render_risk_watchlist():
    """Render the practice-wide medium/high risk triage page."""
    if not st.session_state.get("logged_in") or not st.session_state.get("doctor"):
        st.warning("Please log in as a doctor to access this page.")
        return

    doctor = st.session_state.doctor
    patient_mgr = PatientManager()
    xray_mgr = XrayRecordManager()

    st.markdown(page_header("Risk watchlist", "Practice-wide triage for medium and high risk teeth"), unsafe_allow_html=True)

    patients = patient_mgr.list_all_patients(requester_id=doctor["doctor_id"], requester_role=doctor.get("role", "doctor"))
    rows = _flatten_rows(patients, xray_mgr, doctor)
    if not rows:
        st.markdown(empty_state_container("🚦", "No medium/high risk teeth found", "The current doctor's patient list does not yet contain active risk cases."), unsafe_allow_html=True)
        return

    high_risk_count = sum(1 for row in rows if row["risk_level"] == "High")
    medium_risk_count = sum(1 for row in rows if row["risk_level"] == "Medium")
    overdue_count = len({row["patient_id"] for row in rows if row["overdue"]})

    m1, m2, m3 = st.columns(3)
    m1.metric("High-risk teeth", high_risk_count)
    m2.metric("Medium-risk teeth", medium_risk_count)
    m3.metric("Patients overdue for recall", overdue_count)

    filter_col1, filter_col2, filter_col3 = st.columns([1, 1, 2])
    with filter_col1:
        risk_filter = st.selectbox("Risk level", ["All", "Medium", "High"], index=0)
    with filter_col2:
        sort_by = st.selectbox("Sort by", ["Risk score desc", "Days since last X-ray desc", "Patient name A-Z"], index=0)
    with filter_col3:
        search_text = st.text_input("Search patient", placeholder="Type a patient name")

    filtered_rows = rows
    if risk_filter != "All":
        filtered_rows = [row for row in filtered_rows if row["risk_level"] == risk_filter]
    if search_text:
        search_lower = search_text.lower().strip()
        filtered_rows = [row for row in filtered_rows if search_lower in row["patient_name"].lower()]

    if sort_by == "Risk score desc":
        filtered_rows.sort(key=lambda row: (row["risk_score"], row["days_overdue"] or -1, row["patient_name"]), reverse=True)
    elif sort_by == "Days since last X-ray desc":
        filtered_rows.sort(key=lambda row: (row["days_overdue"] or -1, row["risk_score"], row["patient_name"]), reverse=True)
    else:
        filtered_rows.sort(key=lambda row: row["patient_name"].lower())

    for index, row in enumerate(filtered_rows):
        with st.container(border=True):
            left, right = st.columns([5, 1])
            with left:
                row_cols = st.columns([2, 1, 1, 1, 1, 1])
                row_cols[0].markdown(f"**{html.escape(row['patient_name'])}**")
                row_cols[1].markdown(str(row["tooth_id"]))
                row_cols[2].markdown(_badge(row["risk_level"], "#ef4444" if row["risk_level"] == "High" else "#f59e0b"), unsafe_allow_html=True)
                row_cols[3].markdown(f"{row['bone_loss_pct']:.1f}%")
                row_cols[4].markdown(f"{row['velocity']:.2f}")
                date_text = row["last_xray_date"].strftime("%Y-%m-%d") if row["last_xray_date"] else "N/A"
                row_cols[5].markdown(date_text)

                overdue_text = "N/A" if row["days_overdue"] is None else str(row["days_overdue"])
                overdue_color = "#ef4444" if row["overdue"] else "#94a3b8"
                st.markdown(
                    f"<div style='margin-top:0.4rem;color:{overdue_color};font-weight:700;'>Days overdue: {html.escape(overdue_text)}</div>",
                    unsafe_allow_html=True,
                )
            with right:
                if st.button("View patient", key=f"watchlist_view_{index}_{row['patient_id']}_{row['tooth_id']}", use_container_width=True):
                    _go_to_patient(row["patient_id"])


if __name__ == "__main__":
    render_risk_watchlist()