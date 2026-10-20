"""Agreement between raters (dentist vs dentist) and between the model and each rater, with 95 % CIs.

Answers "is 77 % stage agreement good?": the model is compared with the same yardstick as two dentists are
compared with each other. If model-vs-dentist agreement falls inside the dentist-vs-dentist range, the model is
about as consistent as a second dentist; if it falls below, the gap is quantified.

Input: one CSV, one row per (film, tooth, rater):
    film,tooth,rater,bone_loss_pct
    ext_001.jpg,1,dentist_A,22.5
    ext_001.jpg,1,dentist_B,18.0
    ext_001.jpg,1,model,20.1
`bone_loss_pct` is radiographic bone loss in % of root length (the stage follows from the 2017 AAP/EFP bands). A
rater may instead give `stage` (I / II / III) when no percentage was measured; those rows count for the stage
statistics only. Teeth are matched by (film, tooth). Films are the resampling unit of every bootstrap.

Usage (from backend/):
    python -m research.agreement --csv ratings.csv --out ../docs/evidence/agreement.json
The review packs from research.make_review_set produce rows in exactly this format.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))  # backend/

import numpy as np  # noqa: E402

from research import stats  # noqa: E402


def load(path: str) -> dict:
    """{rater: {(film, tooth): {"pct": float | None, "stage": str}}}"""
    out: dict = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        pct = r.get("bone_loss_pct", "").strip()
        pct = float(pct) if pct else None
        stage = (r.get("stage") or "").strip().upper() or (stats.stage_of(pct) if pct is not None else "")
        if stage not in stats.STAGES:
            continue
        out.setdefault(r["rater"].strip(), {})[(r["film"].strip(), r["tooth"].strip())] = {"pct": pct, "stage": stage}
    return out


def pair(a: dict, b: dict, boot: int) -> dict:
    keys = sorted(a.keys() & b.keys())
    if not keys:
        return {"teeth": 0}
    films = np.array([k[0] for k in keys])
    sa, sb = np.array([a[k]["stage"] for k in keys]), np.array([b[k]["stage"] for k in keys])
    ia, ib = (np.array([stats.STAGES.index(s) for s in x]) for x in (sa, sb))
    res = {"teeth": len(keys), "films": int(len(set(films))),
           "exact_stage": float(np.mean(ia == ib)),
           "exact_stage_ci95": stats.bootstrap_ci(lambda i: float(np.mean(ia[i] == ib[i])), len(keys), films, boot),
           "within_one_stage": float(np.mean(np.abs(ia - ib) <= 1)),
           "kappa_quadratic": stats.weighted_kappa(sa, sb),
           "kappa_quadratic_ci95": stats.bootstrap_ci(lambda i: stats.weighted_kappa(sa[i], sb[i]), len(keys), films, boot),
           "confusion_rows_first_cols_second": stats.confusion(sa, sb).tolist()}
    num = [k for k in keys if a[k]["pct"] is not None and b[k]["pct"] is not None]
    if num:
        d = np.array([a[k]["pct"] - b[k]["pct"] for k in num])
        nf = np.array([k[0] for k in num])
        res.update({"teeth_with_both_percentages": len(num),
                    "mean_abs_difference_pct": float(np.mean(np.abs(d))),
                    "mean_abs_difference_ci95": stats.bootstrap_ci(lambda i: float(np.mean(np.abs(d[i]))), len(d), nf, boot),
                    "bland_altman_bias": float(d.mean()),
                    "bland_altman_limits_95": [float(d.mean() - 1.96 * d.std(ddof=1)), float(d.mean() + 1.96 * d.std(ddof=1))]
                    if len(d) > 1 else None})
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model-rater", default="model", help="name of the model's rows (compared with every human)")
    ap.add_argument("--boot", type=int, default=2000)
    args = ap.parse_args(argv)
    raters = load(args.csv)
    humans = sorted(r for r in raters if r != args.model_rater)
    report = {"raters": {r: len(v) for r, v in raters.items()}, "human_vs_human": {}, "model_vs_human": {}}
    for a, b in itertools.combinations(humans, 2):
        report["human_vs_human"][f"{a} vs {b}"] = pair(raters[a], raters[b], args.boot)
    if args.model_rater in raters:
        for h in humans:
            report["model_vs_human"][f"{args.model_rater} vs {h}"] = pair(raters[args.model_rater], raters[h], args.boot)
    hh = [v["kappa_quadratic"] for v in report["human_vs_human"].values() if v.get("teeth")]
    mh = [v["kappa_quadratic"] for v in report["model_vs_human"].values() if v.get("teeth")]
    if hh and mh:
        report["verdict"] = ("model agrees with dentists about as well as dentists agree with each other"
                             if min(mh) >= min(hh) - 0.05 else
                             "model agrees with dentists less well than dentists agree with each other")
    json.dump(report, open(args.out, "w", encoding="utf-8"), indent=2, default=float)
    for name, v in {**report["human_vs_human"], **report["model_vs_human"]}.items():
        if v.get("teeth"):
            print(f"{name}: {v['teeth']} teeth, exact stage {v['exact_stage']:.3f} {tuple(round(x, 3) for x in v['exact_stage_ci95'])}, "
                  f"kappa {v['kappa_quadratic']:.3f}" + (f", |diff| {v['mean_abs_difference_pct']:.2f} points"
                                                       if "mean_abs_difference_pct" in v else ""))
    if "verdict" in report:
        print("VERDICT:", report["verdict"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
