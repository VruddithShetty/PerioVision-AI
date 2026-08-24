import csv
import datetime
import html
import io
import os

import streamlit as st

from database.patients import PatientManager
from database.xrays import XrayRecordManager
from security.integrity import ModelIntegrityVerifier
from ui.styles import empty_state_container, page_header


def _parse_date(value):
    """Parse a stored analysis date into a datetime object."""
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
    """Normalize a stored analysis payload into a per-tooth dictionary."""
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
    """Map a TALPA grade to a numeric rank."""
    value = str(grade or "").replace("Grade ", "").strip().upper()
    return {"A": 1, "B": 2, "C": 3}.get(value, 0)


def _worst_grade(record):
    """Return the worst grade found in a record."""
    worst = 0
    for tooth in _normalize_teeth(record).values():
        worst = max(worst, _grade_rank(tooth.get("talpa_grade") or tooth.get("grade")))
    return {1: "A", 2: "B", 3: "C"}.get(worst)


def _badge(text, color):
    """Render an inline HTML badge."""
    return f"<span style='display:inline-block;padding:4px 10px;border-radius:999px;background:{color};color:#fff;font-size:12px;font-weight:700;'>{html.escape(str(text))}</span>"


def _row_status(report_path, cache, record_id):
    """Return the cached or verified signing status for a report."""
    if record_id in cache:
        return cache[record_id]
    if not report_path or not os.path.exists(report_path):
        return "Unverified"
    sig_path = f"{report_path}.sig"
    if not os.path.exists(sig_path):
        return "Unverified"
    verifier = ModelIntegrityVerifier()
    result = verifier.verify_model(report_path)
    return "Verified" if result.get("verified") else "Tampered"


def _export_csv(rows):
    """Build a CSV export for report metadata."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Report ID", "Patient name", "Date generated", "TALPA grade", "Signing status", "Report path"])
    for row in rows:
        writer.writerow([row["record_id"], row["patient_name"], row["date_generated"], row["talpa_grade"], row["signing_status"], row.get("report_path", "")])
    return buffer.getvalue().encode("utf-8")


def render_report_vault():
    """Render the searchable signed report archive."""
    if not st.session_state.get("logged_in") or not st.session_state.get("doctor"):
        st.warning("Please log in as a doctor to access this page.")
        return

    doctor = st.session_state.doctor
    patient_mgr = PatientManager()
    xray_mgr = XrayRecordManager()
    verifier = ModelIntegrityVerifier()

    st.markdown(page_header("Report vault", "Archive, verify, and export signed clinical reports"), unsafe_allow_html=True)

    top_left, top_right = st.columns([3, 1])
    with top_left:
        search_text = st.text_input("Search by patient name or report date", placeholder="Type a patient name or YYYY-MM-DD")
    with top_right:
    filter_col1, filter_col2 = st.columns([1, 1])
    with filter_col1:
        grade_filter = st.selectbox("TALPA grade", ["All", "A", "B", "C"], index=0)
    with filter_col2:
        range_filter = st.selectbox("Date range", ["Last 30 days", "Last 90 days", "Last 365 days", "All time"], index=0)

    patients = patient_mgr.list_all_patients(requester_id=doctor["doctor_id"], requester_role=doctor.get("role", "doctor"))
    patient_names = {str(patient["patient_id"]): patient.get("patient_name", "Unknown") for patient in patients}
    records = xray_mgr.get_records_with_report_path(requester_id=doctor["doctor_id"], requester_role=doctor.get("role", "doctor"))

    today = datetime.datetime.now(datetime.timezone.utc)
    cutoff_map = {
        "Last 30 days": today - datetime.timedelta(days=30),
        "Last 90 days": today - datetime.timedelta(days=90),
        "Last 365 days": today - datetime.timedelta(days=365),
        "All time": None,
    }
    cutoff = cutoff_map[range_filter]
    filtered_rows = []
    for record in records:
        record_date = _parse_date(record.get("report_generated_at") or record.get("analysis_date"))
        if cutoff and record_date and record_date < cutoff:
            continue
        patient_name = patient_names.get(str(record.get("patient_id")), "Unknown")
        talpa_grade = _worst_grade(record) or record.get("talpa_grade") or "Unknown"
        signing_status = _row_status(record.get("report_path"), st.session_state.get("report_signing_cache", {}), record.get("record_id"))
        row = {
            "record_id": record.get("record_id"),
            "patient_name": patient_name,
            "date_generated": record_date.strftime("%Y-%m-%d") if record_date else "Unknown",
            "talpa_grade": talpa_grade,
            "signing_status": signing_status,
            "report_path": record.get("report_path"),
            "analysis_date": record_date,
        }
        if grade_filter != "All" and row["talpa_grade"] != grade_filter:
            continue
        if search_text:
            search_lower = search_text.lower().strip()
            if search_lower not in row["patient_name"].lower() and search_lower not in row["date_generated"].lower():
                continue
        filtered_rows.append(row)

    export_data = _export_csv(filtered_rows)
    with top_right:
        st.download_button(
            "Export audit log",
            data=export_data,
            file_name="report_vault_audit_log.csv",
            mime="text/csv",
            use_container_width=True,
        )

    if not filtered_rows:
        st.markdown(empty_state_container("📚", "No signed reports found", "Generate reports from the analysis workflow to populate the vault."), unsafe_allow_html=True)
        return

    for index, row in enumerate(filtered_rows):
        with st.container(border=True):
            columns = st.columns([2, 2, 1.2, 1, 1.4, 1.2, 1.2])
            columns[0].markdown(f"**{html.escape(row['record_id'])}**")
            columns[1].markdown(html.escape(row["patient_name"]), unsafe_allow_html=True)
            columns[2].markdown(row["date_generated"])
            columns[3].markdown(_badge(row["talpa_grade"], "#38bdf8" if row["talpa_grade"] == "A" else "#f59e0b" if row["talpa_grade"] == "B" else "#ef4444"), unsafe_allow_html=True)
            status_color = {"Verified": "#22c55e", "Tampered": "#ef4444", "Unverified": "#94a3b8"}.get(row["signing_status"], "#94a3b8")
            columns[4].markdown(_badge(row["signing_status"], status_color), unsafe_allow_html=True)

            verify_key = f"verify_{row['record_id']}_{index}"
            download_key = f"download_{row['record_id']}_{index}"
            if columns[5].button("Verify signature", key=verify_key, use_container_width=True):
                if row["report_path"] and os.path.exists(row["report_path"]):
                    result = verifier.verify_model(row["report_path"])
                    status = "Verified" if result.get("verified") else "Tampered"
                    st.session_state.setdefault("report_signing_cache", {})[row["record_id"]] = status
                    st.rerun()
                else:
                    st.session_state.setdefault("report_signing_cache", {})[row["record_id"]] = "Unverified"
                    st.rerun()

            if row["report_path"] and os.path.exists(row["report_path"]):
                with open(row["report_path"], "rb") as report_file:
                    report_bytes = report_file.read()
                columns[6].download_button(
                    "Download",
                    data=report_bytes,
                    file_name=os.path.basename(row["report_path"]),
                    mime="application/pdf",
                    key=download_key,
                    use_container_width=True,
                )
            else:
                columns[6].button("Download", key=download_key, disabled=True, use_container_width=True)


if __name__ == "__main__":
    render_report_vault()