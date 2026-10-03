"""Clinical periodontitis risk: a logistic model TRAINED on NHANES (US CDC, public domain).

Model file: app/ml/fusion/risk_model_nhanes.json, produced by scripts/train_risk_model_nhanes.py.
Outcome: moderate or severe periodontitis by the CDC/AAP case definition (Eke et al. 2012), from
full-mouth probing of adults aged 30+. Fitted on NHANES 2009-2012, validated on 2013-2014
(temporal hold-out): ROC AUC ~0.65; predictions ran a few points high on the newer cycle because
prevalence fell between cycles (both recorded in the file and returned with every result).

What the number means: among people with the same age, sex, smoking and diabetes / HbA1c profile,
the share who have moderate or severe periodontitis. It does NOT use the radiograph (no dataset
links radiographs to outcomes, so no image weight could be learned) and does NOT predict future
progression. The radiograph's own evidence is the stage and grade.

Missing inputs are never replaced by a typical value: without age, sex (male / female), smoking
status and, for current smokers, cigarettes per day, the result is status "insufficient_data" with
no probability. HbA1c is optional: without it the validated model that omits HbA1c is used.

Because the model is linear in the log-odds, each factor's contribution (relative to a reference
person: female, never smoker, no diabetes, HbA1c 5.4 %, same age) is exact and is reported as an
odds ratio in plain language.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

from app import config

MODEL_FILE = Path(__file__).with_name("risk_model_nhanes.json")
MODEL_TYPE = "logistic regression trained on NHANES"
MODEL_VERSION = "nhanes-perio-1.0"
REFERENCE = {"male": 0.0, "current_smoker": 0.0, "former_smoker": 0.0, "log_cigs": 0.0, "diabetic": 0.0, "hba1c": 5.4}
LABELS = {
    "male": "Male sex", "current_smoker": "Current smoker", "former_smoker": "Former smoker",
    "log_cigs": "Cigarettes per day", "diabetic": "Diabetes", "hba1c": "HbA1c level",
}


@lru_cache(maxsize=1)
def load_model() -> dict | None:
    if not MODEL_FILE.exists():
        return None
    with open(MODEL_FILE, encoding="utf-8") as f:
        return json.load(f)


def missing_required(clinical: dict) -> list[str]:
    """Inputs without which no score is produced (never filled in with a 'typical' value)."""
    missing = []
    if clinical.get("age") in (None, ""):
        missing.append("age")
    elif int(clinical["age"]) < 30:
        missing.append("age 30 or over (the model was trained on adults aged 30+)")
    if clinical.get("sex") not in ("male", "female"):
        missing.append("sex (male / female)")
    if clinical.get("smoking_status") in (None, "", "unknown"):
        missing.append("smoking status")
    elif clinical["smoking_status"] == "current" and clinical.get("cigarettes_per_day") is None:
        missing.append("cigarettes per day")
    return missing


def features(clinical: dict) -> dict:
    current = clinical["smoking_status"] == "current"
    return {
        "age": float(clinical["age"]),
        "male": 1.0 if clinical["sex"] == "male" else 0.0,
        "current_smoker": 1.0 if current else 0.0,
        "former_smoker": 1.0 if clinical["smoking_status"] == "former" else 0.0,
        "log_cigs": math.log1p(float(clinical.get("cigarettes_per_day") or 0)) if current else 0.0,
        "diabetic": 1.0 if clinical.get("diabetic") else 0.0,
        "hba1c": None if clinical.get("hba1c") is None else float(clinical["hba1c"]),
    }


def predict_patient_risk(clinical: dict, image: dict | None = None) -> dict:
    """`image` is accepted for API compatibility; the trained model does not use radiograph features."""
    model = load_model()
    base = {"model_type": MODEL_TYPE, "model_version": MODEL_VERSION}
    if model is None:
        return {**base, "status": "unavailable", "category": None, "probability": None, "top_factors": [],
                "missing_inputs": [], "disclaimer": "No risk score: the risk model file is not installed."}
    missing = missing_required(clinical)
    if missing:
        return {**base, "status": "insufficient_data", "category": None, "probability": None, "top_factors": [],
                "missing_inputs": missing,
                "disclaimer": "No risk score: required inputs are missing (" + ", ".join(missing) + ")."}
    x = features(clinical)
    variant = "with_hba1c" if x["hba1c"] is not None else "without_hba1c"
    m = model["models"][variant]
    coef = m["coefficients"]
    logit = m["intercept"] + sum(coef[k] * x[k] for k in m["features"])
    prob = 1.0 / (1.0 + math.exp(-logit))
    t = config.THRESHOLDS["risk"]
    category = "high" if prob >= t["high_min_probability"] else (
        "moderate" if prob >= t["moderate_min_probability"] else "low")
    # contributions to the log-odds relative to the reference person of the same age
    contrib = {k: coef[k] * (x[k] - REFERENCE[k]) for k in m["features"] if k != "age"}
    ranked = sorted(((c, k) for k, c in contrib.items() if c > 0.05), reverse=True)[:3]
    factors = [{"factor": LABELS[k], "contribution": round(c, 3),
                "text": f"{LABELS[k]} raises the odds about {math.exp(c):.1f}×"} for c, k in ranked]
    test = m["test"]
    return {
        **base,
        "status": "ok",
        "category": category,
        "probability": round(prob, 3),
        "top_factors": factors,
        "missing_inputs": [] if x["hba1c"] is not None else ["HbA1c (optional; model without HbA1c used)"],
        "variant": variant,
        "validation": {"source": model["source"], "outcome": model["outcome"], "test_n": test["n"],
                       "roc_auc": test["roc_auc"], "brier": test["brier"]},
        "disclaimer": (f"Share of US adults with this age, sex, smoking and diabetes profile who have moderate or "
                       f"severe periodontitis (CDC/AAP), from NHANES; validated AUC {test['roc_auc']:.2f}. "
                       "It does not use the radiograph and does not predict future progression."),
    }
