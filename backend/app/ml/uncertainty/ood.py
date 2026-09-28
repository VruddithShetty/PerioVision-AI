"""Out-of-distribution check: is this image unlike the radiographs the model was trained on?

Simple, explainable heuristics (not a learned detector): intensity range,
contrast, aspect ratio, whether any teeth were found, plus the adversarial
perturbation heuristics from app/security/adversarial.py.
"""
from __future__ import annotations

import numpy as np

from app import config


def ood_check(gray: np.ndarray, n_teeth: int, adversarial: dict | None = None) -> dict:
    t = config.THRESHOLDS["ood"]
    reasons = []
    mean = float(gray.mean())
    lo, hi = t["mean_intensity_range"]
    if not lo <= mean <= hi:
        reasons.append(f"Average brightness {mean:.0f} is outside the expected range {lo}-{hi}.")
    if float(gray.std()) < t["min_contrast"]:
        reasons.append("Contrast is far below typical radiographs.")
    h, w = gray.shape[:2]
    ar_lo, ar_hi = t["aspect_ratio_range"]
    if not ar_lo <= w / max(h, 1) <= ar_hi:
        reasons.append(f"Unusual image shape (width/height = {w / max(h, 1):.2f}).")
    if n_teeth < t["min_teeth_detected"]:
        reasons.append("No teeth were detected.")
    if adversarial and adversarial.get("is_suspicious"):
        reasons.extend(adversarial.get("triggers", []))
    return {"is_ood": bool(reasons), "reasons": reasons}
