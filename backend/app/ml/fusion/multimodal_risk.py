"""Multimodal periodontal-progression risk: clinical factors + image-derived features.

HONESTY NOTE: no labelled outcome dataset (patients followed over time) is
available to this project, so this is NOT a trained model. It is a
**rule-assisted demo**: a small logistic model whose weights were set by hand
to follow the *direction* of well-known risk factors (smoking, diabetes/HbA1c,
existing bone loss, observed progression; e.g. Tonetti et al. 2018, Genco &
Borgnakke 2013). The probability it returns is a relative score for ranking and
explanation, not a calibrated clinical risk. Every response carries
`model_type = "rule-assisted demo"` so the UI and reports say so.

Because it is linear, each factor's contribution to the log-odds is exact, and
the top contributions are turned into plain-language reasons (the same idea as
SHAP values for a linear model).
"""
from __future__ import annotations

import math

from app import config

MODEL_TYPE = "rule-assisted demo"
MODEL_VERSION = "risk-rules-1.0"
INTERCEPT = -3.0

# (feature key, weight per unit, unit description, plain-language template)
WEIGHTS = {
    "age_decades_over_30": (0.15, "Age"),
    "current_smoker": (0.8, "Current smoker"),
    "heavy_smoker": (0.4, "Smokes 10 or more cigarettes a day"),
    "former_smoker": (0.2, "Former smoker"),
    "diabetic": (0.5, "Diabetes"),
    "hba1c_over_6_5": (0.3, "HbA1c above 6.5 %"),
    "mean_bone_loss_per_10pct": (0.5, "Average bone loss across teeth"),
    "max_bone_loss_per_10pct": (0.25, "Worst single-tooth bone loss"),
    "affected_teeth_per_4": (0.3, "Number of teeth with bone loss over 15 %"),
    "velocity_pct_per_year": (0.3, "Observed bone-loss progression"),
}


def build_features(clinical: dict, image: dict) -> dict:
    age = clinical.get("age")
    smoking = clinical.get("smoking_status") or "unknown"
    cigs = clinical.get("cigarettes_per_day") or 0
    hba1c = clinical.get("hba1c")
    velocity = image.get("max_velocity_pct_per_year")
    return {
        "age_decades_over_30": max(0.0, ((age or 30) - 30) / 10.0),
        "current_smoker": 1.0 if smoking == "current" else 0.0,
        "heavy_smoker": 1.0 if smoking == "current" and cigs >= 10 else 0.0,
        "former_smoker": 1.0 if smoking == "former" else 0.0,
        "diabetic": 1.0 if clinical.get("diabetic") else 0.0,
        "hba1c_over_6_5": max(0.0, (hba1c - 6.5)) if hba1c is not None else 0.0,
        "mean_bone_loss_per_10pct": (image.get("mean_bone_loss_pct") or 0.0) / 10.0,
        "max_bone_loss_per_10pct": (image.get("max_bone_loss_pct") or 0.0) / 10.0,
        "affected_teeth_per_4": (image.get("affected_teeth") or 0) / 4.0,
        "velocity_pct_per_year": min(max(velocity, 0.0), 10.0) if velocity is not None else 0.0,
    }


def predict_patient_risk(clinical: dict, image: dict) -> dict:
    t = config.THRESHOLDS["risk"]
    feats = build_features(clinical, image)
    contributions = {k: WEIGHTS[k][0] * v for k, v in feats.items()}
    logit = INTERCEPT + sum(contributions.values())
    prob = 1.0 / (1.0 + math.exp(-logit))
    category = "high" if prob >= t["high_min_probability"] else (
        "moderate" if prob >= t["moderate_min_probability"] else "low")

    ranked = sorted(((c, k) for k, c in contributions.items() if c > 0.05), reverse=True)[:3]
    reasons = [{"factor": WEIGHTS[k][1], "contribution": round(c, 2),
                "text": f"{WEIGHTS[k][1]} increases the risk score"} for c, k in ranked]
    missing = [name for name, val in (("age", clinical.get("age")), ("smoking status", clinical.get("smoking_status")),
                                      ("HbA1c", clinical.get("hba1c"))) if val in (None, "", "unknown")]
    return {
        "category": category,
        "probability": round(prob, 3),
        "top_factors": reasons,
        "missing_inputs": missing,
        "model_type": MODEL_TYPE,
        "model_version": MODEL_VERSION,
        "disclaimer": "Rule-assisted demo score for decision support, not a calibrated clinical risk.",
    }
