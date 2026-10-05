"""Split-conformal prediction for per-tooth bone-loss %.

Calibration (offline, scripts/calibrate_conformal.py): run the pipeline on a
held-out calibration set with known landmarks, and record the nonconformity
score |predicted % - reference %| for every tooth. For coverage 1 - alpha the
threshold q is the ceil((n + 1)(1 - alpha))-th smallest score
(Vovk et al.; Angelopoulos & Bates 2021).

Normalised (adaptive) variant: the score is |predicted - reference| / sigma(x), where sigma(x) grows
with the tooth's test-time-augmentation disagreement (calibration.scale_for), so the interval is
pred +/- q * sigma(x): wider for teeth the model reads inconsistently, narrower for stable ones.

Prediction: interval = [pred - q, pred + q] clipped to 0-100, and the stage
*prediction set* is every stage whose band overlaps that interval. A set with
more than one stage means the model cannot tell the stages apart at the chosen
coverage, which sends the tooth to clinician review.

Without a calibration file nothing is invented: q is unknown, the interval is
the whole 0-100 % range, every stage is in the set, and the case is routed to
review with the reason "uncalibrated".
"""
from __future__ import annotations

import math

import numpy as np

from app.ml.measurement.staging import stages_overlapping


def conformal_quantile(scores, coverage: float) -> float:
    scores = np.sort(np.asarray(scores, dtype=float))
    n = len(scores)
    if n == 0:
        raise ValueError("No calibration scores.")
    k = math.ceil((n + 1) * coverage)
    if k > n:
        return float("inf")  # too few calibration points for this coverage level
    return float(scores[k - 1])


def predict_interval(pred_pct: float | None, q: float | None, scale: float = 1.0, q_upper: float | None = None) -> dict:
    """Interval [pred - q * scale, pred + q_upper * scale] (q_upper = q when not given: symmetric).

    scale = 1 for standard split conformal; for normalised (adaptive) conformal it is the tooth's difficulty
    sigma(x), and q was calibrated on |error| / sigma(x). With an asymmetric calibration q is the lower and
    q_upper the upper margin, each from its own tail (alpha / 2 each), so coverage stays >= 1 - alpha while
    the interval can reach further up than down for a model that underestimates severe bone loss."""
    if pred_pct is None:
        return {"interval": None, "stage_set": [], "set_size": 0, "calibrated": q is not None, "half_width": None}
    if q is None or not math.isfinite(q):
        return {"interval": [0.0, 100.0], "stage_set": ["I", "II", "III"], "set_size": 3, "calibrated": False,
                "half_width": None}
    up = q if q_upper is None or not math.isfinite(q_upper) else q_upper
    low, high = max(0.0, pred_pct - q * scale), min(100.0, pred_pct + up * scale)
    stage_set = stages_overlapping(low, high)
    return {"interval": [round(low, 2), round(high, 2)], "stage_set": stage_set, "set_size": len(stage_set),
            "calibrated": True, "half_width": round(max(q, up) * scale, 3),   # conservative bound for progression
            "lower_margin": round(q * scale, 3), "upper_margin": round(up * scale, 3)}


def empirical_coverage(preds, refs, q: float) -> float:
    preds, refs = np.asarray(preds, float), np.asarray(refs, float)
    return float(np.mean(np.abs(preds - refs) <= q)) if len(preds) else float("nan")
