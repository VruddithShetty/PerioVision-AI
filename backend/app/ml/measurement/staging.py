"""Periodontitis stage and grade *suggestions* aligned with the 2017 AAP/EFP classification
(Tonetti, Greenwell & Kornman, J Clin Periodontol 2018;45 Suppl 20:S149-S161).

This is decision support, not a diagnosis. Radiographic bone loss is used as the
severity measure because clinical attachment loss is not available from an image.

Stage (severity, from the worst tooth's radiographic bone loss):
  I   < 15 % (coronal third)
  II  15-33 %
  III > 33 % (middle third or beyond)
  IV  as III, plus >= 5 teeth lost to periodontitis (only if the clinician enters it)
Grade (rate), in priority order:
  1. direct evidence: observed bone-loss velocity from previous radiographs
  2. indirect evidence: % bone loss / age  (A < 0.25, B 0.25-1.0, C > 1.0)
  3. risk modifiers can raise the grade: smoking >= 10/day or HbA1c >= 7.0 % -> C;
     smoking < 10/day or diabetes with HbA1c < 7.0 % -> at least B
"""
from __future__ import annotations

from app import config

STAGE_BANDS = {"I": (0.0, 15.0), "II": (15.0, 33.0), "III": (33.0, 100.0)}
GRADE_ORDER = {"A": 0, "B": 1, "C": 2}


def stage_for_pct(pct: float | None, teeth_lost_perio: int | None = None) -> str | None:
    if pct is None:
        return None
    t = config.THRESHOLDS["staging"]
    if pct < t["stage_ii_min_pct"]:
        return "I"
    if pct <= t["stage_iii_min_pct"]:
        return "II"
    if teeth_lost_perio is not None and teeth_lost_perio >= t["stage_iv_min_teeth_lost"]:
        return "IV"
    return "III"


def stages_overlapping(low: float, high: float) -> list[str]:
    """Stages whose bone-loss band intersects [low, high] (used for conformal prediction sets)."""
    t = config.THRESHOLDS["staging"]
    bands = {"I": (0.0, t["stage_ii_min_pct"]), "II": (t["stage_ii_min_pct"], t["stage_iii_min_pct"]),
             "III": (t["stage_iii_min_pct"], 100.0)}
    return [s for s, (a, b) in bands.items() if high >= a and low <= b]


def grade_suggestion(max_bl_pct: float | None, age: int | None, clinical: dict | None = None,
                     velocity_pct_per_year: float | None = None) -> dict:
    """Return {grade, basis, reasons} or grade None when inputs are insufficient."""
    t = config.THRESHOLDS["staging"]
    clinical = clinical or {}
    reasons: list[str] = []
    grade, basis = None, None

    if velocity_pct_per_year is not None:
        # Direct evidence expressed per year of radiographic bone loss (% of root length).
        # 5-year loss of ~2 mm is roughly 10-15 % of an average root; we use %/year bands.
        basis = "direct (observed progression)"
        if velocity_pct_per_year <= 0.5:
            grade = "A"
        elif velocity_pct_per_year <= 2.0:
            grade = "B"
        else:
            grade = "C"
        reasons.append(f"Observed bone-loss rate {velocity_pct_per_year:.1f} %/year.")
    elif max_bl_pct is not None and age:
        basis = "indirect (% bone loss / age)"
        ratio = max_bl_pct / max(int(age), 1)
        grade = "A" if ratio < t["grade_b_min_ratio"] else ("B" if ratio <= t["grade_c_min_ratio"] else "C")
        reasons.append(f"Bone loss / age ratio = {ratio:.2f}.")

    if grade is None:
        return {"grade": None, "basis": None, "reasons": ["Not enough information (needs age or a previous visit)."]}

    cigs = clinical.get("cigarettes_per_day")
    smoker = clinical.get("smoking_status") == "current"
    hba1c = clinical.get("hba1c")
    diabetic = bool(clinical.get("diabetic"))

    def raise_to(target: str, why: str):
        nonlocal grade
        if GRADE_ORDER[target] > GRADE_ORDER[grade]:
            grade = target
            reasons.append(why)

    if smoker and cigs is not None and cigs >= 10:
        raise_to("C", "Smoking 10 or more cigarettes a day raises the grade to C.")
    elif smoker:
        raise_to("B", "Current smoking (under 10 a day) raises the grade to at least B.")
    if hba1c is not None and hba1c >= 7.0:
        raise_to("C", "HbA1c of 7.0 % or higher raises the grade to C.")
    elif diabetic:
        raise_to("B", "Diabetes with HbA1c under 7.0 % raises the grade to at least B.")

    return {"grade": grade, "basis": basis, "reasons": reasons}
