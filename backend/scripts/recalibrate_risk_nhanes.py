"""Temporal recalibration of the NHANES risk models (intercept only), fitted and checked on separate people.

Why: the models were fitted on NHANES 2009-2012 (prevalence 44 %), but the later 2013-2014 cycle has 38 %, so every
probability ran about 5 points high (calibration in the large +0.05; the "high" band, mean predicted 0.70, had 55 %).

How: the 2013-2014 people are split once at random (seed 0) into two halves. On half A a single intercept shift
delta is fitted by maximum likelihood with the model's linear predictor held fixed (logistic recalibration in the
large). Half B, which played no part in the fit, measures calibration before and after. Ranking (AUC) cannot change:
only the probabilities move. The shift is written into each model of app/ml/fusion/risk_model_nhanes.json under
"recalibration", and the manifest is re-signed (the file is signed as external/risk_model_nhanes.json).

Usage (from backend/):  python scripts/recalibrate_risk_nhanes.py --data ~/Downloads/NHANES [--dry-run]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))  # backend/
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np  # noqa: E402

from train_risk_model_nhanes import load_cycle  # noqa: E402

MODEL_FILE = os.path.join(os.path.dirname(__file__), "..", "app", "ml", "fusion", "risk_model_nhanes.json")
SEED = 0


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def fit_shift(z: np.ndarray, y: np.ndarray) -> float:
    """MLE of delta in P(y=1) = sigmoid(z + delta), by Newton's method (concave, converges in a few steps)."""
    d = 0.0
    for _ in range(50):
        p = sigmoid(z + d)
        step = (y - p).sum() / max((p * (1 - p)).sum(), 1e-9)
        d += step
        if abs(step) < 1e-10:
            break
    return float(d)


def calib(y: np.ndarray, p: np.ndarray) -> dict:
    high = p >= 0.65
    return {"n": int(len(y)), "observed": round(float(y.mean()), 4), "mean_predicted": round(float(p.mean()), 4),
            "calibration_in_the_large": round(float(p.mean() - y.mean()), 4),
            "brier": round(float(((p - y) ** 2).mean()), 4),
            "high_band_n": int(high.sum()),
            "high_band_mean_predicted": round(float(p[high].mean()), 4) if high.any() else None,
            "high_band_observed": round(float(y[high].mean()), 4) if high.any() else None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="folder with the NHANES .xpt files")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    model = json.load(open(MODEL_FILE, encoding="utf-8"))
    test = load_cycle(os.path.expanduser(args.data), "H")
    rng = np.random.default_rng(SEED)  # audit-ok: seeded split of the recalibration cycle
    half_a = set(rng.permutation(np.sort(test.index.to_numpy()))[: len(test) // 2].tolist())
    for name, m in model["models"].items():
        d = test.dropna(subset=m["features"])
        z = m["intercept"] + sum(d[f].to_numpy() * c for f, c in m["coefficients"].items())
        y = d["perio"].to_numpy().astype(float)
        in_a = np.array([s in half_a for s in d.index])
        delta = fit_shift(z[in_a], y[in_a])
        before, after = calib(y[~in_a], sigmoid(z[~in_a])), calib(y[~in_a], sigmoid(z[~in_a] + delta))
        m["recalibration"] = {
            "intercept_shift": round(delta, 6),
            "method": "logistic recalibration in the large (intercept only; coefficients and ranking unchanged)",
            "fitted_on": f"random half of NHANES 2013-2014 (seed {SEED}), n = {int(in_a.sum())}",
            "evaluated_on": f"the other half, n = {int((~in_a).sum())}",
            "half_b_before": before, "half_b_after": after,
        }
        print(f"{name}: shift {delta:+.4f} | half B calibration-in-the-large {before['calibration_in_the_large']:+.3f}"
              f" -> {after['calibration_in_the_large']:+.3f} | Brier {before['brier']:.4f} -> {after['brier']:.4f}"
              f" | high band predicted {before['high_band_mean_predicted']} observed {before['high_band_observed']}"
              f" -> predicted {after['high_band_mean_predicted']} observed {after['high_band_observed']}"
              f" (n {before['high_band_n']} -> {after['high_band_n']})")
    if args.dry_run:
        return 0
    with open(MODEL_FILE, "w", encoding="utf-8") as f:
        json.dump(model, f, indent=2)
    from app.security.model_signing import Signer
    from app import config

    Signer().sign_manifest(config.WEIGHTS_DIR)
    print("Saved the shifts into risk_model_nhanes.json and re-signed the manifest. Run scripts/sign_model.py to "
          "re-record the self-check outputs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
