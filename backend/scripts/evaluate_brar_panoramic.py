"""External panoramic evaluation on the BRAR dataset (figshare 10.6084/m9.figshare.30155974, CC BY 4.0).

BRAR gives, per patient, the expert-consensus bone loss of the WORST tooth as a fraction of root length
(CEJ -> crest over CEJ -> apex, interproximal, measured by 3 junior + 2 senior periodontists) and the
patient's age, but not which tooth it was. So this evaluates what a clinician uses from a panoramic film:
  * the worst measured tooth's bone loss vs the expert worst tooth (error, bias)
  * the patient-level stage (I < 15 %, II 15-33 %, III > 33 %) agreement
  * the indirect grade (bone loss % / age: A < 0.25, B 0.25-1.0, C > 1.0), the same ratio BRAR grades on
  * how many teeth per film the app could measure at all
Input: per-film JSON written by running analysis_service.locate_teeth on the films (see --predictions),
plus BRAR's meta_data.csv. Output: a JSON summary (and per-level breakdown).

Usage (from backend/):
    python scripts/evaluate_brar_panoramic.py --meta ~/Downloads/BRAR/data/meta_data.csv \\
        --predictions preds_*.json --out ../docs/evidence/brar_panoramic_eval.json
"""
import argparse
import glob
import json
import os

import numpy as np
import pandas as pd


def stage(p):
    return None if p is None else ("I" if p < 15 else "II" if p <= 33 else "III")


def grade(p, age):
    if p is None or not age:
        return None
    r = p / age
    return "A" if r < 0.25 else "B" if r <= 1.0 else "C"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--meta", required=True)
    ap.add_argument("--predictions", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    meta = pd.read_csv(os.path.expanduser(args.meta)).set_index("File name")
    preds = {}
    for pattern in args.predictions:
        for path in glob.glob(os.path.expanduser(pattern)):
            for r in json.load(open(path, encoding="utf-8")):
                preds[r["file"]] = r
    rows = []
    for f, r in preds.items():
        if f not in meta.index:
            continue
        m = meta.loc[f]
        ref = float(m["Bone resorption"]) * 100.0
        measured = [t["pct"] for t in r["teeth"] if t["pct"] is not None]
        app = max(measured) if measured else None
        rows.append({"file": f, "level": int(m["Level"]), "age": int(m["Age"]), "ref": ref, "app": app,
                     "n_measured": len(measured), "n_detected": r["n_detected"], "image_type": r["image_type"]})
    df = pd.DataFrame(rows)

    def summarise(d: pd.DataFrame) -> dict:
        has = d[d["app"].notna()]
        err = has["app"] - has["ref"]
        return {
            "films": int(len(d)),
            "films_with_a_measured_tooth": int(len(has)),
            "mean_teeth_detected": round(float(d["n_detected"].mean()), 1) if len(d) else None,
            "mean_teeth_measured": round(float(d["n_measured"].mean()), 1) if len(d) else None,
            "worst_tooth_MAE_pct_points": round(float(err.abs().mean()), 2) if len(has) else None,
            "worst_tooth_median_abs_error": round(float(err.abs().median()), 2) if len(has) else None,
            "worst_tooth_bias_app_minus_expert": round(float(err.mean()), 2) if len(has) else None,
            "within_10_points": round(float((err.abs() <= 10).mean()), 3) if len(has) else None,
            "stage_agreement": round(float(np.mean([stage(a) == stage(b) for a, b in zip(has["app"], has["ref"])])), 3)
            if len(has) else None,
            "grade_agreement_vs_BRAR": round(float(np.mean([grade(a, g) == grade(b, g) for a, b, g in
                                                            zip(has["app"], has["ref"], has["age"])])), 3)
            if len(has) else None,
        }

    out = {"dataset": "BRAR (figshare 10.6084/m9.figshare.30155974), CC BY 4.0, single centre, DEXIS OC200D",
           "reference": "expert-consensus worst-tooth bone loss / root length (interproximal), one tooth per patient",
           "overall": summarise(df),
           "by_BRAR_level": {str(lv): summarise(df[df["level"] == lv]) for lv in sorted(df["level"].unique())}}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
