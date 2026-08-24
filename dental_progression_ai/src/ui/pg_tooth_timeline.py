import datetime
import html

import plotly.graph_objects as go
import streamlit as st

from database.xrays import XrayRecordManager
from ui.styles import empty_state_container, page_header


UPPER_ARCH = [18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28]
LOWER_ARCH = [48, 47, 46, 45, 44, 43, 42, 41, 31, 32, 33, 34, 35, 36, 37, 38]


def _go_to_patients():
    """Send the user back to the Patients page."""
    st.session_state.nav_page = "Patients"
    st.rerun()


def _parse_date(value):
    """Parse an ISO-like date string into a datetime object."""
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


def _normalized_teeth(record):
    """Normalize a stored X-ray analysis payload into a tooth dictionary."""
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


def _bone_loss_color(bone_loss_pct):
    """Map bone loss percentage to a severity color."""
    if bone_loss_pct < 15:
        return "#22c55e"
    if bone_loss_pct <= 30:
        return "#f59e0b"
    return "#ef4444"


def _tooth_series(records, tooth_id):
    """Build a time series for a single tooth from historical records."""
    points = []
    for record in records:
        record_date = _parse_date(record.get("analysis_date"))
        tooth_data = _normalized_teeth(record).get(str(tooth_id), {})
        if record_date and tooth_data:
            points.append((record_date, float(tooth_data.get("bone_loss_pct", 0.0) or 0.0), float(tooth_data.get("velocity_per_year", 0.0) or 0.0)))
    return sorted(points, key=lambda item: item[0])


def _render_arch_html(current_selection, latest_record):
    """Render a clickable SVG arch that uses query params for tooth selection."""
    latest_teeth = _normalized_teeth(latest_record)
    cells = []

    def tooth_svg(tooth_number, x, y):
        tooth_data = latest_teeth.get(str(tooth_number), {})
        bone_loss_pct = float(tooth_data.get("bone_loss_pct", 0.0) or 0.0)
        fill = _bone_loss_color(bone_loss_pct)
        selected = str(tooth_number) == str(current_selection)
        stroke = "#ffffff" if selected else "rgba(255,255,255,0.25)"
        stroke_width = 4 if selected else 1.5
        label_y = y + 48
        return f'''
            <a href="?selected_tooth={tooth_number}" target="_top" style="text-decoration:none;">
                <g>
                    <rect x="{x}" y="{y}" rx="10" ry="10" width="42" height="42" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>
                    <text x="{x + 21}" y="{label_y}" text-anchor="middle" fill="#e2e8f0" font-size="11" font-family="Space Grotesk, Arial, sans-serif">{tooth_number}</text>
                </g>
            </a>
        '''

    for index, tooth in enumerate(UPPER_ARCH):
        x = 24 + index * 46
        cells.append(tooth_svg(tooth, x, 24))
    for index, tooth in enumerate(LOWER_ARCH):
        x = 24 + index * 46
        cells.append(tooth_svg(tooth, x, 96))

    html_markup = f"""
    <div style="padding: 10px 0 4px 0;">
      <svg viewBox="0 0 760 180" width="100%" height="180" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="archGlow" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stop-color="#38bdf8" stop-opacity="0.15" />
            <stop offset="50%" stop-color="#22d3ee" stop-opacity="0.45" />
            <stop offset="100%" stop-color="#a855f7" stop-opacity="0.15" />
          </linearGradient>
        </defs>
        <rect x="10" y="12" width="740" height="156" rx="24" fill="url(#archGlow)" opacity="0.18" />
        <text x="30" y="18" fill="#94a3b8" font-size="12">Upper arch</text>
        <text x="30" y="90" fill="#94a3b8" font-size="12">Lower arch</text>
        {''.join(cells)}
      </svg>
    </div>
    """
    st.components.v1.html(html_markup, height=200, scrolling=False)


def _build_progression_chart(records, tooth_id):
    """Build the tooth progression chart with bone loss and velocity traces, linear trend overlays, and safety signals."""
    time_series = []
    for r in records:
        date_str = r.get("analysis_date")
        if date_str:
            if "T" in date_str:
                date_str = date_str.split("T")[0]
            elif " " in date_str:
                date_str = date_str.split(" ")[0]
                
            tooth_data = _normalized_teeth(r).get(str(tooth_id), {})
            if tooth_data:
                # Get alignment confidence from metadata if present
                align_conf = 0.95
                if isinstance(r.get("dicom_metadata"), dict):
                    align_conf = r["dicom_metadata"].get("alignment_confidence", 0.95)
                elif isinstance(r.get("analysis_result"), dict):
                    # Fallback to visual check if present
                    align_conf = r["analysis_result"].get(str(tooth_id), {}).get("alignment_confidence", 0.95)

                time_series.append({
                    "date": date_str,
                    "bone_loss_percentage": float(tooth_data.get("bone_loss_pct", 0.0) or 0.0),
                    "landmark_confidence": float(tooth_data.get("landmark_confidence", 0.95)),
                    "alignment_confidence": float(align_conf)
                })

    if len(time_series) < 2:
        st.info("Add another X-ray visit to see progression trends.")
        return

    from analysis.progression_velocity_calculator import ProgressionVelocityCalculator
    calc = ProgressionVelocityCalculator()
    profile = calc.compute_talpa_profile(time_series)

    # Render Statistical Honesty Layer (Stage 3)
    conf = profile["confidence"]
    qual_conf = conf["qualitative_confidence"].upper()
    flags = conf["data_quality_flags"]

    col1, col2 = st.columns([1, 2])
    with col1:
        if qual_conf == "HIGH":
            st.success(f"Confidence: **HIGH** 🟢")
        elif qual_conf == "MODERATE":
            st.warning(f"Confidence: **MODERATE** 🟡")
        else:
            st.error(f"Confidence: **LOW** 🔴")
    with col2:
        if flags:
            st.caption(f"⚠️ Quality flags: {', '.join(flags)}")
        else:
            st.caption("✨ Optimal landmark accuracy and alignment registration.")

    dates = [m["date"] for m in time_series]
    bone_loss_values = [m["bone_loss_percentage"] for m in time_series]

    fig = go.Figure()
    
    # 1. Main bone loss trajectory trace
    fig.add_trace(go.Scatter(
        x=dates,
        y=bone_loss_values,
        mode="lines+markers",
        name="Bone loss %",
        line=dict(color="#38bdf8", width=3),
        marker=dict(size=8, color="#38bdf8"),
    ))

    # 2. Linear regression overlay (Stage 2 trend fitting for 3+ points)
    if len(time_series) >= 3:
        # Reconstruct linear fit points
        trend_res = calc.fit_multi_interval_trend(time_series)
        if trend_res["status"] == "success":
            x_years = trend_res["x_years"]
            slope = trend_res["linear_slope"]
            intercept = trend_res["linear_intercept"]
            
            # Convert x_years back to dates for plotting
            import datetime
            def parse_date(m):
                d = m.get("date") or m.get("radiograph_date")
                return datetime.date.fromisoformat(d)
                
            sorted_ts = sorted(time_series, key=parse_date)
            start_date = parse_date(sorted_ts[0])
            
            fit_dates = []
            for y_yr in x_years:
                dt = start_date + datetime.timedelta(days=int(y_yr * 365.25))
                fit_dates.append(dt.isoformat())
                
            fit_values = [slope * y_yr + intercept for y_yr in x_years]
            
            fig.add_trace(go.Scatter(
                x=fit_dates,
                y=fit_values,
                mode="lines",
                name=f"Fitted Trend ({trend_res['trend_classification']})",
                line=dict(color="#22d3ee", width=2, dash="dash"),
            ))
            
            # Show warning if accelerated episodes detected
            if trend_res["is_accelerating"]:
                st.error("⚠️ **ACCELERATING PERIODONTITIS EPISODE DETECTED** on this site!")

    fig.add_hline(y=15, line_dash="dash", line_color="#f59e0b", annotation_text="Gingivitis threshold", annotation_position="top left")
    fig.add_hline(y=30, line_dash="dash", line_color="#ef4444", annotation_text="Periodontitis threshold", annotation_position="top left")
    fig.update_layout(
        title=f"Tooth {tooth_id} — bone loss progression (Velocity: {profile['velocity']:.3f} %/yr)",
        xaxis_title="Visit date",
        yaxis=dict(title="Bone loss %", range=[0, 100]),
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=60, b=40),
        height=480,
    )
    st.plotly_chart(fig, use_container_width=True)


def render_tooth_timeline():
    """Render the per-tooth longitudinal bone loss timeline page."""
    if not st.session_state.get("logged_in") or not st.session_state.get("doctor"):
        st.warning("Please log in as a doctor to access this page.")
        return

    doctor = st.session_state.doctor
    patient_id = st.session_state.get("current_patient_id")
    if not patient_id:
        st.markdown(page_header("Tooth timeline", "Track per-tooth periodontal progression over time"), unsafe_allow_html=True)
        st.warning("Select a patient first to view the tooth timeline.")
        if st.button("Go to Patients"):
            _go_to_patients()
        return

    xray_mgr = XrayRecordManager()
    records = xray_mgr.get_records_by_patient(patient_id, requester_id=doctor["doctor_id"], requester_role=doctor.get("role", "doctor"))
    if not records:
        st.markdown(page_header("Tooth timeline", "Track per-tooth periodontal progression over time"), unsafe_allow_html=True)
        st.markdown(empty_state_container("🦷", "No X-ray records yet", "Upload an image to start tracking longitudinal change."), unsafe_allow_html=True)
        return

    st.markdown(page_header("Tooth timeline", "Track per-tooth periodontal progression over time"), unsafe_allow_html=True)

    query_params = getattr(st, "query_params", {})
    selected_from_query = query_params.get("selected_tooth") if hasattr(query_params, "get") else None
    if isinstance(selected_from_query, list):
        selected_from_query = selected_from_query[0] if selected_from_query else None

    if selected_from_query:
        st.session_state.selected_tooth = str(selected_from_query)
    elif "selected_tooth" not in st.session_state:
        current_latest = _normalized_teeth(records[-1])
        st.session_state.selected_tooth = str(next(iter(current_latest.keys()), 11))

    current_selected = str(st.session_state.get("selected_tooth", "11"))
    latest_record = records[-1]
    _render_arch_html(current_selected, latest_record)

    st.caption("Click any tooth block to update the selection.")
    _build_progression_chart(records, current_selected)

    # Category 4: Validation status & inter-observer disclosure
    st.info("ℹ️ **Validation Status:** Validated on synthetic Gaussian noise cohort (n=100). Clinical correlation not established. | **Inter-Observer Variability:** Not measured — single annotator dataset.")


if __name__ == "__main__":
    render_tooth_timeline()