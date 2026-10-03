"""Chairside clinical tools: periodontal chart analysis, clinical-radiographic concordance,
care planning (EFP S3 step therapy), per-tooth prognosis and risk-based recall.

Clinical references (the cut-offs below are simplified for decision support, not a substitute
for clinical judgement):
* Staging by interdental clinical attachment loss (CAL): 1-2 mm Stage I, 3-4 mm Stage II,
  >= 5 mm Stage III (Tonetti, Greenwell & Kornman 2018; Papapanou et al. 2018).
* Step-wise therapy for Stage I-III periodontitis: EFP S3 guideline (Sanz et al. 2020).
* Per-tooth prognosis categories after Kwok & Caton (2007): favourable, questionable,
  unfavourable, hopeless, using bone loss, mobility and furcation involvement.
* Risk-based supportive care intervals (3 / 4 / 6 months), as commonly used in periodontal
  risk assessment (Lang & Tonetti 2003).
"""
from __future__ import annotations

import datetime as dt

from app.ml.measurement.staging import grade_suggestion
from app.services.progression_service import usable_velocities

SITES = ("DB", "B", "MB", "DL", "L", "ML")          # six probing sites per tooth
INTERDENTAL = (0, 2, 3, 5)                        # DB, MB, DL, ML
STAGE_RANK = {None: 0, "I": 1, "II": 2, "III": 3, "IV": 4}


def _stage_for_cal(cal: float | None) -> str | None:
    if cal is None or cal <= 0:
        return None
    if cal <= 2:
        return "I"
    if cal <= 4:
        return "II"
    return "III"


def summarize_chart(chart: dict) -> dict:
    """Per-tooth and whole-mouth indices from a 6-point probing chart."""
    teeth_out = {}
    all_sites = bop_sites = plaque_sites = sites_4 = sites_6 = 0
    cal_values = []
    for tooth_id, t in (chart.get("teeth") or {}).items():
        if t.get("missing"):
            teeth_out[tooth_id] = {"missing": True}
            continue
        pd = [int(v) for v in t.get("pd", [0] * 6)]
        rec = [int(v) for v in t.get("rec", [0] * 6)]
        bop = [bool(v) for v in t.get("bop", [False] * 6)]
        plaque = [bool(v) for v in t.get("plaque", [False] * 6)]
        cal = [max(0, p + r) for p, r in zip(pd, rec)]     # CAL = probing depth + recession
        interdental_cal = max(cal[i] for i in INTERDENTAL)
        all_sites += 6
        bop_sites += sum(bop)
        plaque_sites += sum(plaque)
        sites_4 += sum(1 for p in pd if p >= 4)
        sites_6 += sum(1 for p in pd if p >= 6)
        cal_values.extend(cal)
        teeth_out[tooth_id] = {
            "missing": False,
            "cal": cal,
            "max_pd": max(pd),
            "max_cal": max(cal),
            "interdental_cal": interdental_cal,
            "bop_sites": sum(bop),
            "deep_pockets": sum(1 for p in pd if p >= 5),
            "mobility": int(t.get("mobility", 0) or 0),
            "furcation": int(t.get("furcation", 0) or 0),
            "clinical_stage": _stage_for_cal(interdental_cal),
        }
    present = [v for v in teeth_out.values() if not v.get("missing")]
    worst = max((v["clinical_stage"] for v in present), key=lambda s: STAGE_RANK[s], default=None)
    return {
        "teeth": teeth_out,
        "teeth_present": len(present),
        "teeth_missing": sum(1 for v in teeth_out.values() if v.get("missing")),
        "bop_pct": round(100 * bop_sites / all_sites, 1) if all_sites else None,
        "plaque_pct": round(100 * plaque_sites / all_sites, 1) if all_sites else None,
        "sites_pd_4_plus": sites_4,
        "sites_pd_6_plus": sites_6,
        "mean_cal": round(sum(cal_values) / len(cal_values), 2) if cal_values else None,
        "clinical_stage": worst,
        "gingival_status": _gingival_status(bop_sites, all_sites, worst),
    }


def _gingival_status(bop_sites: int, all_sites: int, stage: str | None) -> str:
    if not all_sites:
        return "not charted"
    bop = bop_sites / all_sites
    if stage is None:
        return "gingival health" if bop < 0.10 else "gingivitis"
    return "periodontitis with active inflammation" if bop >= 0.10 else "periodontitis, currently stable"


def concordance(summary: dict, analysis: dict | None) -> list[dict]:
    """Compare the clinical stage (probing) with the radiographic stage (AI) tooth by tooth."""
    if not analysis:
        return []
    radiographic = {t["tooth_id"]: t for t in analysis.get("teeth", [])
                    if t.get("tooth_id_source") in ("model_fdi_class", "demo_fdi_estimate")}
    out = []
    for tooth_id, c in summary["teeth"].items():
        r = radiographic.get(tooth_id)
        if c.get("missing") or r is None or r.get("stage") is None:  # unmeasured teeth cannot be compared
            continue
        cs, rs = c["clinical_stage"], r.get("stage")
        gap = STAGE_RANK[cs] - STAGE_RANK[rs]
        status = "agree" if abs(gap) == 0 else ("clinical worse" if gap > 0 else "radiograph worse")
        hint = None
        if gap >= 1:
            hint = ("Probing shows more attachment loss than the X-ray. Consider an angular (vertical) defect, "
                    "overlapping structures or a landmark error; a periapical view may help.")
        elif gap <= -1:
            hint = ("The X-ray shows more bone loss than probing suggests. Check for a probing error, recession not "
                    "recorded, or a long junctional epithelium after previous therapy.")
        out.append({"tooth_id": tooth_id, "clinical_stage": cs, "radiographic_stage": rs,
                    "interdental_cal_mm": c["interdental_cal"], "bone_loss_pct": r.get("bone_loss_pct"),
                    "status": status, "hint": hint})
    return sorted(out, key=lambda x: (x["status"] == "agree", x["tooth_id"]))


def tooth_prognosis(bone_loss_pct: float | None, mobility: int = 0, furcation: int = 0) -> dict:
    """Simplified per-tooth prognosis (after Kwok & Caton 2007).

    An unmeasured tooth (bone_loss_pct None) is never assumed healthy: unless mobility or
    furcation already decide the category, its prognosis is "not assessable".
    """
    bl = bone_loss_pct if bone_loss_pct is not None else -1.0
    if bl > 75 or mobility >= 3:
        cat = "hopeless"
    elif bl > 50 or furcation >= 3 or mobility == 2:
        cat = "unfavourable"
    elif bl >= 25 or furcation == 2 or mobility == 1:
        cat = "questionable"
    elif bone_loss_pct is None:
        cat = "not assessable"
    else:
        cat = "favourable"
    reasons = [] if bone_loss_pct is not None else ["bone loss not measured on the radiograph"]
    if bl > 0:
        reasons.append(f"{bl:.0f}% radiographic bone loss")
    if mobility:
        reasons.append(f"mobility grade {mobility}")
    if furcation:
        reasons.append(f"furcation class {furcation}")
    return {"category": cat, "reasons": reasons}


def recall_interval(grade: str | None, risk_category: str | None, bop_pct: float | None,
                    rapid_progression: bool) -> dict:
    reasons = []
    months = 6
    if grade == "C" or risk_category == "high" or (bop_pct is not None and bop_pct >= 30) or rapid_progression:
        months = 3
        reasons.append("high risk: grade C, high risk score, BOP ≥ 30 % or rapid progression")
    elif grade == "B" or risk_category == "moderate" or (bop_pct is not None and bop_pct >= 10):
        months = 4
        reasons.append("moderate risk: grade B, moderate risk score or BOP ≥ 10 %")
    else:
        reasons.append("low risk")
    return {"months": months, "reasons": reasons}


def _add_months(d: dt.date, months: int) -> dt.date:
    y, m = divmod(d.month - 1 + months, 12)
    day = min(d.day, [31, 29 if (d.year + y) % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m])
    return dt.date(d.year + y, m + 1, day)


def care_plan(patient: dict, analysis: dict | None, chart: dict | None, progression_latest: list[dict]) -> dict:
    summary = summarize_chart(chart) if chart else None
    radio_stage = (analysis or {}).get("summary", {}).get("stage")
    clin_stage = summary["clinical_stage"] if summary else None
    stage = max([radio_stage, clin_stage], key=lambda s: STAGE_RANK[s])
    if stage == "III" and (patient.get("teeth_lost_perio") or 0) >= 5:
        stage = "IV"

    velocities = usable_velocities(progression_latest)
    max_bl = (analysis or {}).get("summary", {}).get("max_bone_loss_pct")
    grade = grade_suggestion(max_bl, patient.get("age"), patient, max(velocities) if velocities else None)
    risk = (analysis or {}).get("risk", {})
    rapid = any(c.get("label") == "rapidly progressing" for c in progression_latest)  # reliable, detectable only
    recall = recall_interval(grade.get("grade"), risk.get("category"), summary["bop_pct"] if summary else None, rapid)

    deep = summary["sites_pd_4_plus"] if summary else 0
    very_deep = summary["sites_pd_6_plus"] if summary else 0
    steps = [
        {"step": 1, "title": "Guide behaviour and control risk factors",
         "items": ["Oral hygiene instruction (interdental cleaning)", "Supragingival plaque and calculus removal",
                   *(["Smoking cessation support"] if patient.get("smoking_status") == "current" else []),
                   *(["Coordinate diabetes control with the physician (HbA1c target < 7 %)"]
                     if patient.get("diabetic") or (patient.get("hba1c") or 0) >= 6.5 else [])],
         "indicated": True},
        {"step": 2, "title": "Cause-related therapy",
         "items": ["Subgingival instrumentation of pockets ≥ 4 mm", "Re-evaluate after 6–8 weeks"],
         "indicated": stage is not None and (deep > 0 or summary is None)},
        {"step": 3, "title": "Treat residual pockets",
         "items": ["Re-instrument or consider access flap / regenerative surgery for residual pockets ≥ 6 mm",
                   "Specialist referral for complex defects"],
         "indicated": stage in ("III", "IV") or very_deep > 0},
        {"step": 4, "title": "Supportive periodontal care",
         "items": [f"Recall every {recall['months']} months", "Re-chart and compare with the previous visit"],
         "indicated": True},
    ]

    chart_teeth = (summary or {}).get("teeth", {})
    prognosis = []
    for t in (analysis or {}).get("teeth", []):
        c = chart_teeth.get(t["tooth_id"], {})
        prognosis.append({"tooth_id": t["tooth_id"], **tooth_prognosis(t.get("bone_loss_pct"), c.get("mobility", 0),
                                                                       c.get("furcation", 0))})

    last_visit = max([d for d in ((analysis or {}).get("visit_date"), (chart or {}).get("exam_date")) if d],
                     default=None)
    next_due = _add_months(dt.date.fromisoformat(last_visit[:10]), recall["months"]).isoformat() if last_visit else None
    referral = stage in ("III", "IV") or grade.get("grade") == "C" or any(
        c["status"] != "agree" for c in concordance(summary, analysis)) if summary else stage in ("III", "IV")

    return {
        "stage": stage, "radiographic_stage": radio_stage, "clinical_stage": clin_stage,
        "grade": grade, "risk": risk.get("category"), "recall": recall, "last_visit": last_visit,
        "next_recall_due": next_due, "steps": steps, "prognosis": prognosis,
        "referral_suggested": bool(referral), "chart_summary": summary,
        "disclaimer": "Decision support based on the 2017 AAP/EFP classification and the EFP S3 guideline; "
                      "confirm every step clinically.",
    }
