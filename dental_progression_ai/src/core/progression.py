import datetime
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from analysis.progression_velocity_calculator import ProgressionVelocityCalculator

_calculator = ProgressionVelocityCalculator()


def analyze_progression(past_xrays, current_bl_results):
    """
    Thin adapter: compares current bone loss against historical records and
    delegates grading to ProgressionVelocityCalculator (AAP/EFP 2017).

    Returns insufficient_temporal_data=True for single timepoints.
    See docs/TALPA.md for design decisions and grading criteria.
    """
    progression_table = []
    current_date = datetime.datetime.now()

    for tooth_id, current in current_bl_results.items():
        history = []
        for xr in past_xrays:
            bl_val = xr.get("analysis_result", {}).get(str(tooth_id), {}).get("bone_loss_pct", 0.0)

            dt_str = xr.get("analysis_date", current_date.strftime("%Y-%m-%d"))
            try:
                dt_obj = datetime.datetime.strptime(dt_str, "%Y-%m-%d")
            except ValueError:
                dt_obj = current_date

            history.append({"date": dt_obj, "bl_pct": bl_val})

        velocity_per_year = None
        grade_result = None
        insufficient_temporal = False

        if len(history) >= 1:
            history_sorted = sorted(history, key=lambda x: x["date"])
            prev_record = history_sorted[-1]
            prev_bl = prev_record["bl_pct"]
            delta = current["bone_loss_pct"] - prev_bl

            days_diff = (current_date - prev_record["date"]).days
            years_diff = max(days_diff / 365.25, 0.01)
            velocity_per_year = delta / years_diff

            # Proxy: bone_loss_pct / 10 ≈ mm until RadiographAligner emits true mm.
            # See docs/TALPA.md for the full landmark wire-up plan.
            grade_result = _calculator.classify_aap_efp_grade(
                velocity_mm_per_year=velocity_per_year * 0.1,
                time_span_years=years_diff,
            )
        else:
            delta = 0.0
            insufficient_temporal = True

        progression_table.append({
            "tooth_id": tooth_id,
            "current_bl": current["bone_loss_pct"],
            "delta": round(delta, 2),
            "velocity_per_year": round(velocity_per_year, 2) if velocity_per_year is not None else None,
            "history_count": len(history),
            "insufficient_temporal_data": insufficient_temporal,
            "aap_efp_grade": grade_result["grade"] if grade_result else None,
            "grade_label": grade_result["grade_label"] if grade_result else "Insufficient Temporal Data",
            "trend": (
                "Stable" if velocity_per_year is not None and velocity_per_year <= 0
                else ("Progressing" if velocity_per_year and velocity_per_year > 0 else "Unknown")
            ),
        })

    return progression_table
