"""Train the clinical periodontitis risk model on NHANES (US CDC, public domain) and validate it.

Data: NHANES 2009-10 (F), 2011-12 (G) and 2013-14 (H) full-mouth periodontal examinations of adults
aged 30+, with demographics (DEMO), smoking (SMQ), diabetes (DIQ) and HbA1c (GHB). Download the
.xpt files from https://wwwn.cdc.gov/nchs/nhanes/ into one folder.

Outcome: moderate or severe periodontitis by the CDC/AAP case definition (Eke et al., J Periodontol
2012;83:1449-54), from interproximal sites only (NHANES site codes D, S, P, A):
  severe   = >= 2 interproximal sites with CAL >= 6 mm on different teeth AND >= 1 with PD >= 5 mm
  moderate = >= 2 interproximal sites with CAL >= 4 mm on different teeth, OR
             >= 2 interproximal sites with PD >= 5 mm on different teeth
Features (all things a clinic records): age, sex, current / former smoking, cigarettes per day,
diabetes, HbA1c. Two models are fitted: with HbA1c, and without it (used when a non-diabetic
patient has no HbA1c on file).

Validation is temporal: fit on 2009-2012, test on 2013-2014 (never seen). Reported: ROC AUC,
Brier score, calibration in bins. Survey weights are not used, so probabilities describe the
NHANES examined sample, not the weighted US population.

Usage (from backend/):
    python scripts/train_risk_model_nhanes.py --data ~/Downloads/NHANES --out app/ml/fusion/risk_model_nhanes.json
The model file is plain JSON (coefficients only) and ships with the code.
"""
import argparse
import datetime as dt
import json
import os

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score

TEETH = [f"{t:02d}" for t in list(range(2, 16)) + list(range(18, 32))]   # NHANES universal numbering, no third molars
INTERPROXIMAL = ("D", "S", "P", "A")
FULL = ["age", "male", "current_smoker", "former_smoker", "log_cigs", "diabetic", "hba1c"]
NO_HBA1C = [f for f in FULL if f != "hba1c"]


def case_definition(per: pd.DataFrame) -> pd.Series:
    def teeth_with(measure: str, mm: float) -> pd.Series:
        hit = []
        for t in TEETH:
            cols = [f"OHX{t}{measure}{s}" for s in INTERPROXIMAL if f"OHX{t}{measure}{s}" in per]
            v = per[cols].where(per[cols] < 99)                 # 99 = cannot be assessed
            hit.append((v >= mm).any(axis=1))
        return pd.concat(hit, axis=1).sum(axis=1)                # number of DIFFERENT teeth with such a site

    def sites_with(measure: str, mm: float) -> pd.Series:
        cols = [f"OHX{t}{measure}{s}" for t in TEETH for s in INTERPROXIMAL if f"OHX{t}{measure}{s}" in per]
        v = per[cols].where(per[cols] < 99)
        return (v >= mm).sum(axis=1)

    severe = (teeth_with("LA", 6) >= 2) & (sites_with("PC", 5) >= 1)
    moderate = (teeth_with("LA", 4) >= 2) | (teeth_with("PC", 5) >= 2)
    return (severe | moderate).astype(int)


def load_cycle(folder: str, suffix: str) -> pd.DataFrame:
    rd = lambda name: pd.read_sas(os.path.join(folder, f"{name}_{suffix}.xpt"), format="xport")  # noqa: E731
    per = rd("OHXPER")
    per = per[per["OHDPDSTS"] == 1]                               # complete periodontal exam only
    out = pd.DataFrame({"SEQN": per["SEQN"], "perio": case_definition(per)})
    demo = rd("DEMO")[["SEQN", "RIDAGEYR", "RIAGENDR"]]
    smq = rd("SMQ")[["SEQN", "SMQ020", "SMQ040", "SMD650"]]
    diq = rd("DIQ")[["SEQN", "DIQ010"]]
    ghb = rd("GHB")[["SEQN", "LBXGH"]]
    d = out.merge(demo, on="SEQN").merge(smq, on="SEQN", how="left").merge(diq, on="SEQN", how="left") \
        .merge(ghb, on="SEQN", how="left")
    d = d[d["RIDAGEYR"] >= 30]
    current = d["SMQ040"].isin([1, 2])
    former = (d["SMQ020"] == 1) & (d["SMQ040"] == 3)
    never = d["SMQ020"] == 2
    cigs = d["SMD650"].where(d["SMD650"] < 777)                  # 777 / 999 = refused / don't know
    f = pd.DataFrame({
        "perio": d["perio"], "age": d["RIDAGEYR"], "male": (d["RIAGENDR"] == 1).astype(float),
        "current_smoker": current.astype(float), "former_smoker": former.astype(float),
        "log_cigs": np.log1p(cigs.where(current, 0.0)), "diabetic": (d["DIQ010"] == 1).astype(float),
        "hba1c": d["LBXGH"], "cycle": suffix,
    })
    known_smoking = current | former | never
    known_diabetes = d["DIQ010"].isin([1, 2, 3])
    f = f[known_smoking & known_diabetes & ~(current & cigs.isna())]
    return f


def fit(train: pd.DataFrame, test: pd.DataFrame, feats: list[str]) -> dict:
    tr, te = train.dropna(subset=feats), test.dropna(subset=feats)
    mu, sd = tr[feats].mean(), tr[feats].std().replace(0, 1)
    model = LogisticRegression(C=1.0, max_iter=2000).fit((tr[feats] - mu) / sd, tr["perio"])
    p = model.predict_proba((te[feats] - mu) / sd)[:, 1]
    y = te["perio"].to_numpy()
    bins = []
    for lo, hi in zip(np.linspace(0, 1, 6)[:-1], np.linspace(0, 1, 6)[1:]):
        m = (p >= lo) & ((p < hi) if hi < 1 else (p <= hi))
        if m.any():
            bins.append({"bin": [round(lo, 1), round(hi, 1)], "n": int(m.sum()),
                         "mean_predicted": round(float(p[m].mean()), 3), "observed_rate": round(float(y[m].mean()), 3)})
    coef = model.coef_[0] / sd.to_numpy()                          # back to per-unit coefficients
    intercept = float(model.intercept_[0] - np.sum(model.coef_[0] * mu.to_numpy() / sd.to_numpy()))
    return {
        "features": feats, "intercept": intercept, "coefficients": dict(zip(feats, map(float, coef))),
        "train": {"n": int(len(tr)), "prevalence": round(float(tr["perio"].mean()), 4)},
        "test": {"n": int(len(te)), "prevalence": round(float(y.mean()), 4),
                 "roc_auc": round(float(roc_auc_score(y, p)), 4), "brier": round(float(brier_score_loss(y, p)), 4),
                 "brier_of_prevalence_only": round(float(brier_score_loss(y, np.full_like(p, tr["perio"].mean()))), 4),
                 "calibration_bins": bins},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    folder = os.path.expanduser(args.data)
    train = pd.concat([load_cycle(folder, "F"), load_cycle(folder, "G")])
    test = load_cycle(folder, "H")
    models = {"with_hba1c": fit(train, test, FULL), "without_hba1c": fit(train, test, NO_HBA1C)}
    data = {
        "created": dt.datetime.now(dt.timezone.utc).isoformat(),
        "model_type": "logistic regression trained on NHANES",
        "outcome": "moderate or severe periodontitis, CDC/AAP case definition (Eke et al. 2012)",
        "source": "NHANES 2009-2012 (training) and 2013-2014 (temporal test), US CDC, public domain",
        "population": "US adults aged 30+ with a complete full-mouth periodontal exam (unweighted sample)",
        "models": models,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    for name, m in models.items():
        t = m["test"]
        print(f"{name}: train n={m['train']['n']} test n={t['n']} prevalence {t['prevalence']:.3f} "
              f"AUC {t['roc_auc']:.3f} Brier {t['brier']:.4f} (prevalence-only {t['brier_of_prevalence_only']:.4f})")
        print("   coef:", {k: round(v, 3) for k, v in m["coefficients"].items()}, "intercept", round(m["intercept"], 3))
        print("   calibration:", [(b["mean_predicted"], b["observed_rate"], b["n"]) for b in t["calibration_bins"]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
