"""Periodontitis risk: a clinical logistic model TRAINED on NHANES (US CDC, public domain), fused with the
radiograph's own measured evidence by a documented rule (fuse_with_radiograph, at the end of this file).

Model file: app/ml/fusion/risk_model_nhanes.json, produced by scripts/train_risk_model_nhanes.py.
Outcome: moderate or severe periodontitis by the CDC/AAP case definition (Eke et al. 2012), from
full-mouth probing of adults aged 30+. Fitted on NHANES 2009-2012, validated on 2013-2014
(temporal hold-out): ROC AUC ~0.65; predictions ran a few points high on the newer cycle because
prevalence fell between cycles (both recorded in the file and returned with every result).

What the number means: among people with the same age, sex, smoking and diabetes / HbA1c profile,
the share who have moderate or severe periodontitis. The logistic model itself does not use the
radiograph (no dataset links radiographs to outcomes, so no image weight could be learned) and does
NOT predict future progression. The radiograph's evidence (stage, panoramic whole-film estimate,
measurable progression) is combined with it afterwards by fuse_with_radiograph.

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
    """The coefficients, only if they match the signed manifest (otherwise no risk score: fail closed)."""
    if not MODEL_FILE.exists():
        return None
    from app.security.model_signing import Signer

    check = Signer().verify_weight_file(MODEL_FILE)
    if not check.get("verified"):
        import logging

        logging.getLogger(__name__).error("[SECURITY] Refusing the risk model: %s", check.get("reason"))
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
                "missing_inputs": [], "disclaimer": "No risk score: the risk model file is missing or failed its "
                                                    "signature check."}
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
                       f"severe periodontitis (CDC/AAP), from NHANES; AUC {test['roc_auc']:.2f} on a later cycle of the same survey "
                       "(predictions ran about 5 points high there: the high band, predicted about 70 %, had 55 %). "
                       "The clinical model does not read the radiograph; the radiograph's evidence is combined with it in the fused level. It does not predict future progression."),
    }


# ---------------------------------------------------------------- image + clinical fusion
LEVELS = ("low", "moderate", "high")
STAGE_LEVEL = {"I": "low", "II": "moderate", "III": "high", "IV": "high"}
FUSION_RULE = ("Combined level = the higher of the clinical level (NHANES model) and the radiographic level "
               "(stage I = low, II = moderate, III / IV = high; rapid, measurable progression = high). "
               "A documented decision rule, as in Lang & Tonetti's periodontal risk assessment, not a trained "
               "weight: no public dataset links radiographs to periodontitis outcomes.")


def _radiographic_evidence(summary: dict | None, panoramic: dict | None) -> dict | None:
    """The radiograph's own measured evidence, or None when the film gave no bone-loss evidence."""
    summary = summary or {}
    rapid = config.THRESHOLDS["progression"]["rapid_pct_per_year"]
    velocity = summary.get("max_velocity_pct_per_year")
    if summary.get("stage"):
        level, basis = STAGE_LEVEL[summary["stage"]], (
            f"per-tooth measurement: worst tooth stage {summary['stage']} "
            f"({summary.get('max_bone_loss_pct')} % bone loss), tested on held-out periapical films of the training dataset")
    elif (panoramic or {}).get("worst_tooth"):
        wt = panoramic["worst_tooth"]
        level, basis = STAGE_LEVEL[wt["stage"]], (
            f"whole-film panoramic estimate: worst tooth about {wt['bone_loss_pct']:.0f} % "
            f"(90 % interval {wt['interval_90'][0]:.0f}-{wt['interval_90'][1]:.0f} %, "
            f"possible stages {' / '.join(wt['stage_set'])})")
    else:
        return None
    if velocity is not None and velocity >= rapid:
        level, basis = "high", basis + f"; measurable progression {velocity:.1f} %/year"
    return {"level": level, "basis": basis}


def fuse_with_radiograph(risk: dict, summary: dict | None, panoramic: dict | None = None) -> dict:
    """Add a `fusion` block that combines the clinical risk with the radiograph's own evidence.

    The clinical part keeps its trained, validated probability unchanged (`category`, `probability`).
    The radiographic part is the measured stage (periapical per-tooth, or the whole-film panoramic estimate)
    and measurable progression. The combined level takes the higher of the two, so neither source can
    hide a warning from the other. Each part says where it came from, and a missing part is named.
    """
    image = _radiographic_evidence(summary, panoramic)
    clinical = risk.get("category")
    parts = [lvl for lvl in (clinical, image and image["level"]) if lvl]
    level = max(parts, key=LEVELS.index) if parts else None
    reasons = []
    if clinical:
        reasons.append(f"Clinical factors (age, sex, smoking, diabetes): {clinical}, "
                       f"probability {risk['probability']:.2f}.")
    else:
        reasons.append("Clinical risk not scored: " + (", ".join(risk.get("missing_inputs") or []) or "model unavailable") + ".")
    if image:
        reasons.append(f"Radiograph: {image['level']} ({image['basis']}).")
    else:
        reasons.append("Radiograph: no bone-loss measurement on this film, so it adds no evidence to the level.")
    return {**risk, "fusion": {"level": level, "clinical_level": clinical,
                               "radiographic_level": image and image["level"],
                               "radiographic_basis": image and image["basis"],
                               "rule": FUSION_RULE, "reasons": reasons}}
