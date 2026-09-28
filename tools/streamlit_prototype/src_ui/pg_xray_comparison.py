import datetime
import html

import numpy as np
import pandas as pd
import streamlit as st

from core.preprocessing import preprocess_for_analysis
from database.xrays import XrayRecordManager
from ui.styles import empty_state_container, page_header


def _go_to_patients():
    """Navigate the app to the Patients page."""
    st.session_state.nav_page = "Patients"
    st.rerun()


def _parse_date(value):
    """Parse an analysis date into a datetime object."""
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
    """Normalize a stored record into a per-tooth dictionary."""
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


def _render_image(record, show_overlay):
    """Render the annotated or CLAHE-preprocessed image for a record."""
    if show_overlay and record.get("annotated_path"):
        st.image(record["annotated_path"], use_container_width=True)
        return

    preprocessed = preprocess_for_analysis(record.get("image_path"))
    if preprocessed is None:
        st.info("Preprocessed image not available for this visit.")
        return
    display_image = np.clip(preprocessed * 255.0, 0, 255).astype(np.uint8)
    st.image(display_image, use_container_width=True, clamp=True)


def _comparison_table(record_a, record_b):
    """Render a color-coded tooth comparison table between two visits."""
    teeth_a = _normalize_teeth(record_a)
    teeth_b = _normalize_teeth(record_b)
    all_teeth = sorted({*teeth_a.keys(), *teeth_b.keys()}, key=lambda value: int(str(value)))

    rows = []
    for tooth_id in all_teeth:
        loss_a = float(teeth_a.get(tooth_id, {}).get("bone_loss_pct", 0.0) or 0.0)
        loss_b = float(teeth_b.get(tooth_id, {}).get("bone_loss_pct", 0.0) or 0.0)
        delta = loss_b - loss_a
        if delta > 0:
            delta_style = "color:#ef4444;"
        elif delta < 0:
            delta_style = "color:#22c55e;"
        else:
            delta_style = "color:#94a3b8;"
        rows.append(
            f"<tr>"
            f"<td style='padding:8px 10px;border-bottom:1px solid rgba(255,255,255,0.08);'>{html.escape(str(tooth_id))}</td>"
            f"<td style='padding:8px 10px;border-bottom:1px solid rgba(255,255,255,0.08);'>{loss_a:.1f}%</td>"
            f"<td style='padding:8px 10px;border-bottom:1px solid rgba(255,255,255,0.08);'>{loss_b:.1f}%</td>"
            f"<td style='padding:8px 10px;border-bottom:1px solid rgba(255,255,255,0.08);font-weight:700;{delta_style}'>{delta:+.1f}%</td>"
            f"</tr>"
        )

    table_html = f"""
    <table style="width:100%;border-collapse:collapse;background:rgba(15,23,42,0.35);border-radius:16px;overflow:hidden;">
      <thead>
        <tr>
          <th style='text-align:left;padding:10px;border-bottom:1px solid rgba(255,255,255,0.08);'>Tooth</th>
          <th style='text-align:left;padding:10px;border-bottom:1px solid rgba(255,255,255,0.08);'>Visit A</th>
          <th style='text-align:left;padding:10px;border-bottom:1px solid rgba(255,255,255,0.08);'>Visit B</th>
          <th style='text-align:left;padding:10px;border-bottom:1px solid rgba(255,255,255,0.08);'>Delta (B - A)</th>
        </tr>
      </thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>
    """
    st.markdown(table_html, unsafe_allow_html=True)


def render_xray_comparison():
    """Render the side-by-side X-ray comparison page."""
    if not st.session_state.get("logged_in") or not st.session_state.get("doctor"):
        st.warning("Please log in as a doctor to access this page.")
        return

    doctor = st.session_state.doctor
    patient_id = st.session_state.get("current_patient_id")
    st.markdown(page_header("X-ray comparison", "Compare two visits side by side"), unsafe_allow_html=True)

    if not patient_id:
        st.warning("Select a patient first to compare X-rays.")
        if st.button("Go to Patients"):
            _go_to_patients()
        return

    xray_mgr = XrayRecordManager()
    records = xray_mgr.get_records_by_patient(patient_id, requester_id=doctor["doctor_id"], requester_role=doctor.get("role", "doctor"))
    if len(records) < 2:
        st.info("Add another X-ray visit to compare two studies.")
        st.selectbox("Visit A", ["Unavailable"], disabled=True)
        st.selectbox("Visit B", ["Unavailable"], disabled=True)
        return

    sorted_records = sorted(records, key=lambda record: _parse_date(record.get("analysis_date")) or datetime.datetime.min)
    labels = [f"{_parse_date(record.get('analysis_date')).strftime('%Y-%m-%d')} • {record.get('record_id', '')}" for record in sorted_records]

    visit_a_default = max(0, len(sorted_records) - 2)
    visit_b_default = len(sorted_records) - 1

    left_col, right_col = st.columns([1, 1])
    with left_col:
        visit_a_label = st.selectbox("Visit A", labels, index=visit_a_default, disabled=False)
    with right_col:
        visit_b_label = st.selectbox("Visit B", labels, index=visit_b_default, disabled=False)

    index_a = labels.index(visit_a_label)
    index_b = labels.index(visit_b_label)
    record_a = sorted_records[index_a]
    record_b = sorted_records[index_b]

    show_overlay = st.checkbox("Show annotation overlay", value=True)

    img_col_a, img_col_b = st.columns([1, 1])
    with img_col_a:
        st.caption(f"Visit A: {visit_a_label}")
        _render_image(record_a, show_overlay)
    with img_col_b:
        st.caption(f"Visit B: {visit_b_label}")
        _render_image(record_b, show_overlay)

    st.markdown("### Tooth-level comparison")
    _comparison_table(record_a, record_b)


if __name__ == "__main__":
    render_xray_comparison()