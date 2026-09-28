"""Image-quality gate: warns about or rejects radiographs that are too blurry, flat or small.

Thresholds live in app/config.py (THRESHOLDS["quality"]) so they can be tuned without code changes.
"""
from __future__ import annotations

import cv2
import numpy as np

from app import config


def assess_quality(gray: np.ndarray) -> dict:
    """Return metrics, a verdict (pass | warn | reject) and plain-language reasons."""
    t = config.THRESHOLDS["quality"]
    h, w = gray.shape[:2]
    # Sharpness is resolution-dependent, so it is measured at a fixed 1024 px width.
    norm = cv2.resize(gray, (1024, max(1, int(1024 * h / w))), interpolation=cv2.INTER_AREA)
    blur = float(cv2.Laplacian(norm, cv2.CV_64F).var())
    contrast = float(gray.std())
    mean = float(gray.mean())
    clipped = float(((gray <= 2) | (gray >= 253)).mean())

    reasons, verdict = [], "pass"

    severity = {"pass": 0, "warn": 1, "reject": 2}

    def flag(level: str, message: str):
        nonlocal verdict
        reasons.append({"level": level, "message": message})
        if severity[level] > severity[verdict]:
            verdict = level

    if min(h, w) < t["min_side_reject"]:
        flag("reject", f"Resolution too low ({w}x{h}); at least {t['min_side_reject']} px on the short side is needed.")
    elif min(h, w) < t["min_side_warn"]:
        flag("warn", f"Low resolution ({w}x{h}); measurements may be less precise.")
    if blur < t["blur_reject"]:
        flag("reject", "Image is too blurry to find tooth landmarks reliably.")
    elif blur < t["blur_warn"]:
        flag("warn", "Image looks slightly blurry.")
    if contrast < t["contrast_reject"]:
        flag("reject", "Contrast is too low (image looks flat or washed out).")
    elif contrast < t["contrast_warn"]:
        flag("warn", "Contrast is low.")
    if clipped > t["clipped_warn"]:
        flag("warn", "Large areas are pure black or white (over/under-exposed).")

    return {
        "verdict": verdict,
        "reasons": reasons,
        "metrics": {"width": int(w), "height": int(h), "sharpness": round(blur, 1), "contrast": round(contrast, 1),
                    "mean_intensity": round(mean, 1), "clipped_fraction": round(clipped, 3)},
    }
