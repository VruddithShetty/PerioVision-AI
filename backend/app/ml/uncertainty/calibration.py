"""Stores and reports the conformal calibration (weights/conformal_calibration.json).

The file records where the calibration data came from, the nonconformity
scores, and the resulting thresholds, so the Model Trust page can show real
coverage numbers, or say plainly that the model is uncalibrated.
"""
from __future__ import annotations

import datetime as dt
import json

import numpy as np

from app import config
from app.ml.uncertainty.conformal import conformal_quantile, empirical_coverage

_cache: dict | None = None


def load() -> dict | None:
    global _cache
    if _cache is None and config.CALIBRATION_FILE.exists():
        with open(config.CALIBRATION_FILE, encoding="utf-8") as f:
            _cache = json.load(f)
    return _cache


def reset_cache() -> None:
    global _cache
    _cache = None


def current_q(coverage: float | None = None) -> float | None:
    cal = load()
    if not cal or not cal.get("scores"):
        return None
    coverage = coverage or config.THRESHOLDS["uncertainty"]["coverage"]
    q = conformal_quantile(cal["scores"], coverage)
    return q if np.isfinite(q) else None


def save(scores, preds, refs, source: str, notes: str = "", split_seed: int = 0) -> dict:
    """Scores are split in half: one half sets q, the other half measures coverage honestly."""
    scores = np.asarray(scores, float)
    preds, refs = np.asarray(preds, float), np.asarray(refs, float)
    order = np.random.default_rng(split_seed).permutation(len(scores))
    half = len(order) // 2
    cal_idx, test_idx = order[:half], order[half:]
    levels = {}
    for cov in (0.8, 0.9, 0.95):
        q = conformal_quantile(scores[cal_idx], cov) if len(cal_idx) else float("inf")
        levels[str(cov)] = {
            "q_from_half": q if np.isfinite(q) else None,
            "empirical_coverage_other_half": empirical_coverage(preds[test_idx], refs[test_idx], q)
            if np.isfinite(q) and len(test_idx) else None,
        }
    data = {
        "created": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": source,
        "notes": notes,
        "n_scores": int(len(scores)),
        "scores": [round(float(s), 4) for s in scores],
        "levels": levels,
        "mean_absolute_error_pct": round(float(scores.mean()), 3) if len(scores) else None,
        "reliability_bins": _bins(preds, refs),
    }
    config.CALIBRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(config.CALIBRATION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    reset_cache()
    return data


def _bins(preds, refs, n_bins: int = 5) -> list[dict]:
    """Predicted vs reference bone loss per bin (data for the calibration plot)."""
    edges = np.linspace(0, 100, n_bins + 1)
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (preds >= lo) & ((preds < hi) if hi < 100 else (preds <= hi))
        if mask.any():
            out.append({"bin": [float(lo), float(hi)], "n": int(mask.sum()),
                        "mean_predicted": round(float(preds[mask].mean()), 2),
                        "mean_reference": round(float(refs[mask].mean()), 2)})
    return out


def report() -> dict:
    cal = load()
    coverage = config.THRESHOLDS["uncertainty"]["coverage"]
    if not cal:
        return {"calibrated": False, "target_coverage": coverage,
                "message": "No calibration file. Run scripts/calibrate_conformal.py on a held-out set. "
                           "Until then every case goes to clinician review."}
    return {"calibrated": True, "target_coverage": coverage, "q_current": current_q(coverage),
            **{k: v for k, v in cal.items() if k != "scores"}}
