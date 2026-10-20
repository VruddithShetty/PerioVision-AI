"""Asymmetric split-conformal interval for the panoramic worst-tooth bone-loss estimate.

The whole-film model regresses towards the mean: on BRAR test films it underestimates stage III cases by about
18 points, so a symmetric +/- q interval covered only 74 % of them although it covered 91 % overall. Here each
side gets its own quantile at 1 - alpha / 2 from the VALIDATION films' signed errors (reference - predicted),
which keeps coverage >= 1 - alpha (union bound) and lets the interval reach further up than down.

Input: the per-film predictions written by
    python -m research.export_predictions brar-severity --data ~/Downloads/BRAR/data --out ../docs/evidence/predictions/brar_severity_per_film.csv
(rows with split=val calibrate, rows with split=test only measure). Writes conformal_q90_lower / _upper and the
test coverage per reference stage into weights/panoramic_severity_metrics.json, then re-signs the manifest.

Usage (from backend/):
    python scripts/calibrate_panoramic_interval.py --predictions ../docs/evidence/predictions/brar_severity_per_film.csv
"""
import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))  # backend/

import numpy as np  # noqa: E402

from app import config  # noqa: E402
from app.ml.uncertainty.conformal import conformal_quantile  # noqa: E402


def stage(p):
    return np.where(p < 15, "I", np.where(p <= 33, "II", "III"))


def coverage(pred, ref, lo_m, up_m) -> dict:
    lo, hi = np.clip(pred - lo_m, 0, 100), np.clip(pred + up_m, 0, 100)
    inside = (ref >= lo) & (ref <= hi)
    st = stage(ref)
    return {"coverage": round(float(inside.mean()), 4),
            "coverage_by_reference_stage": {s: round(float(inside[st == s].mean()), 4) for s in ("I", "II", "III")},
            "mean_width_pct": round(float((hi - lo).mean()), 2)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--predictions", required=True)
    ap.add_argument("--coverage", type=float, default=0.9)
    ap.add_argument("--dry-run", action="store_true", help="print, do not change the metrics file")
    args = ap.parse_args()
    rows = list(csv.DictReader(open(args.predictions, encoding="utf-8")))
    val = [r for r in rows if r["split"] == "val"]
    test = [r for r in rows if r["split"] == "test"]
    if len(val) < 50 or not test:
        print(f"ERROR: need >= 50 validation films and some test films (got {len(val)} / {len(test)}).")
        return 1
    vp, vr = np.array([float(r["pred_pct"]) for r in val]), np.array([float(r["ref_pct"]) for r in val])
    tp, tr = np.array([float(r["pred_pct"]) for r in test]), np.array([float(r["ref_pct"]) for r in test])
    tail = 1 - (1 - args.coverage) / 2
    q_up = max(0.0, conformal_quantile(vr - vp, tail))
    q_dn = max(0.0, conformal_quantile(vp - vr, tail))
    q_sym = conformal_quantile(np.abs(vr - vp), args.coverage)
    result = {"asymmetric": {"q_lower": round(q_dn, 3), "q_upper": round(q_up, 3), **coverage(tp, tr, q_dn, q_up)},
              "symmetric": {"q": round(q_sym, 3), **coverage(tp, tr, q_sym, q_sym)},
              "validation_films": len(val), "test_films": len(test)}
    print(json.dumps(result, indent=2))
    if args.dry_run:
        return 0
    path = config.WEIGHTS_DIR / "panoramic_severity_metrics.json"
    metrics = json.loads(path.read_text(encoding="utf-8"))
    metrics.update({"conformal_q90_lower_from_val": result["asymmetric"]["q_lower"],
                    "conformal_q90_upper_from_val": result["asymmetric"]["q_upper"],
                    "test_interval_coverage_asymmetric": result["asymmetric"]["coverage"],
                    "test_interval_coverage_by_stage_asymmetric": result["asymmetric"]["coverage_by_reference_stage"],
                    "test_interval_coverage_by_stage_symmetric": result["symmetric"]["coverage_by_reference_stage"],
                    "interval_note": "Asymmetric split conformal (alpha/2 per side, from validation films' signed "
                                     "errors); scripts/calibrate_panoramic_interval.py"})
    path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    from app.security.model_signing import Signer

    Signer().sign_manifest(config.WEIGHTS_DIR)
    print(f"Updated {path.name} and re-signed the manifest.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
