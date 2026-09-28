"""Longitudinal progression: match teeth across visits, compute change and velocity, label each tooth.

Matching, per pair of consecutive visits:
  1. by FDI tooth number when both visits have model-assigned numbers
  2. otherwise by position: box centres (normalised to image size, after mapping
     the earlier visit through the registration transform when one exists) are
     paired to the nearest centre within `spatial_match_max_distance`
Every comparison carries a reliability verdict. It is marked unreliable (and
never silently trusted) when registration between the two radiographs was poor
or missing, a positional match was made without good registration, either
measurement used heuristic landmarks, or the visits are too close together to
measure a rate. Positional matches after a good registration are accepted.

Labels, from velocity in % of root length per year (thresholds in config):
  improved             velocity <= -stable band
  stable               within +/- stable band
  progressing          above the band
  rapidly progressing  >= rapid threshold
"""
from __future__ import annotations

import datetime as dt

import numpy as np

from app import config


def _parse_date(value) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value)[:10])


def _centre(tooth: dict, width: int, height: int, matrix=None) -> np.ndarray:
    x1, y1, x2, y2 = tooth["bbox"]
    pt = np.array([(x1 + x2) / 2.0, (y1 + y2) / 2.0, 1.0])
    if matrix is not None:
        pt = np.array([*(np.asarray(matrix, float) @ pt), 1.0])
    return np.array([pt[0] / max(width, 1), pt[1] / max(height, 1)])


def label_for_velocity(v_per_year: float | None) -> str | None:
    if v_per_year is None:
        return None
    t = config.THRESHOLDS["progression"]
    if v_per_year >= t["rapid_pct_per_year"]:
        return "rapidly progressing"
    if v_per_year > t["stable_band_pct_per_year"]:
        return "progressing"
    if v_per_year <= -t["stable_band_pct_per_year"]:
        return "improved"
    return "stable"


def match_teeth(prev: dict, curr: dict) -> list[tuple[dict, dict, str]]:
    """Pair teeth between two analyses. Returns (prev_tooth, curr_tooth, method)."""
    t = config.THRESHOLDS["progression"]
    pairs, used_prev, used_curr = [], set(), set()
    prev_teeth = [x for x in prev.get("teeth", []) if x.get("bone_loss_pct") is not None]
    curr_teeth = [x for x in curr.get("teeth", []) if x.get("bone_loss_pct") is not None]

    by_id = {x["tooth_id"]: x for x in prev_teeth if x.get("tooth_id_source") == "model_fdi_class"}
    for c in curr_teeth:
        p = by_id.get(c["tooth_id"]) if c.get("tooth_id_source") == "model_fdi_class" else None
        if p is not None:
            pairs.append((p, c, "tooth_number"))
            used_prev.add(id(p))
            used_curr.add(id(c))

    matrix = (curr.get("alignment") or {}).get("matrix_prev_to_curr")
    pw, ph = prev.get("image_size", [1, 1])
    cw, ch = curr.get("image_size", [1, 1])
    candidates = []
    for p in prev_teeth:
        if id(p) in used_prev:
            continue
        pc = _centre(p, cw if matrix else pw, ch if matrix else ph, matrix) if matrix else _centre(p, pw, ph)
        for c in curr_teeth:
            if id(c) in used_curr:
                continue
            d = float(np.linalg.norm(pc - _centre(c, cw, ch)))
            if d <= t["spatial_match_max_distance"]:
                candidates.append((d, p, c))
    for d, p, c in sorted(candidates, key=lambda x: x[0]):
        if id(p) in used_prev or id(c) in used_curr:
            continue
        pairs.append((p, c, "spatial"))
        used_prev.add(id(p))
        used_curr.add(id(c))
    return pairs


def compare_visits(prev: dict, curr: dict) -> list[dict]:
    t = config.THRESHOLDS["progression"]
    days = (_parse_date(curr["visit_date"]) - _parse_date(prev["visit_date"])).days
    alignment = curr.get("alignment") or {}
    align_score = alignment.get("confidence")
    results = []
    for p, c, method in match_teeth(prev, curr):
        delta = round(c["bone_loss_pct"] - p["bone_loss_pct"], 2)
        reasons = []
        if days < t["min_interval_days"]:
            reasons.append(f"Visits only {days} days apart; too short to measure a rate.")
        if align_score is not None and align_score < t["min_alignment_score"]:
            reasons.append(f"Radiographs could not be aligned well (score {align_score:.2f}).")
        if align_score is None:
            reasons.append("No image registration available between these visits.")
        registered = align_score is not None and align_score >= t["min_alignment_score"]
        if method == "spatial" and not registered:
            reasons.append("Tooth matched by position without a reliable image registration.")
        if "heuristic_fallback" in (p.get("landmark_source"), c.get("landmark_source")):
            reasons.append("At least one measurement used estimated (heuristic) landmarks.")
        reliable = not reasons
        velocity_year = round(delta / (days / 365.25), 2) if days >= t["min_interval_days"] else None
        results.append({
            "tooth_id": c["tooth_id"],
            "previous_tooth_id": p["tooth_id"],
            "match_method": method,
            "from_date": str(prev["visit_date"])[:10],
            "to_date": str(curr["visit_date"])[:10],
            "interval_days": days,
            "previous_bone_loss_pct": p["bone_loss_pct"],
            "current_bone_loss_pct": c["bone_loss_pct"],
            "delta_pct": delta,
            "velocity_pct_per_year": velocity_year,
            "velocity_pct_per_month": round(velocity_year / 12.0, 3) if velocity_year is not None else None,
            "label": label_for_velocity(velocity_year) if reliable else "unreliable comparison",
            "raw_label": label_for_velocity(velocity_year),
            "reliable": reliable,
            "reliability_reasons": reasons,
        })
    return results


def patient_progression(analyses: list[dict]) -> dict:
    """Build per-tooth time series and the latest comparison from a patient's analyses (any order)."""
    ordered = sorted(analyses, key=lambda a: (str(a["visit_date"]), a.get("created", "")))
    series: dict[str, list[dict]] = {}
    for a in ordered:
        for tooth in a.get("teeth", []):
            if tooth.get("bone_loss_pct") is None:
                continue
            series.setdefault(tooth["tooth_id"], []).append({
                "date": str(a["visit_date"])[:10], "analysis_id": a["analysis_id"],
                "bone_loss_pct": tooth["bone_loss_pct"], "stage": tooth.get("stage"),
            })
    comparisons = []
    for prev, curr in zip(ordered, ordered[1:]):
        comparisons.extend(compare_visits(prev, curr))
    latest = [c for c in comparisons if ordered and c["to_date"] == str(ordered[-1]["visit_date"])[:10]]
    reliable_v = [c["velocity_pct_per_year"] for c in latest if c["reliable"] and c["velocity_pct_per_year"] is not None]
    return {
        "visits": [{"analysis_id": a["analysis_id"], "visit_date": str(a["visit_date"])[:10],
                    "review_status": a.get("review", {}).get("status")} for a in ordered],
        "series": series,
        "comparisons": comparisons,
        "latest": latest,
        "summary": {
            "visits": len(ordered),
            "max_reliable_velocity_pct_per_year": max(reliable_v) if reliable_v else None,
            "unreliable_comparisons": sum(1 for c in comparisons if not c["reliable"]),
            "labels": {lbl: sum(1 for c in latest if c["label"] == lbl) for lbl in
                       ("stable", "progressing", "rapidly progressing", "improved", "unreliable comparison")},
        },
    }
