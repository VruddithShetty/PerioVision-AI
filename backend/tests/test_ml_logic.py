"""Measurement, staging, conformal coverage, progression, quality gate, adversarial check, risk."""
import datetime as dt

import cv2
import numpy as np
import pytest

from app.ml.fusion.multimodal_risk import predict_patient_risk
from app.ml.measurement.bone_loss import bone_loss_for_tooth
from app.ml.measurement.staging import grade_suggestion, stage_for_pct
from app.ml.preprocessing.quality_check import assess_quality
from app.ml.uncertainty.conformal import conformal_quantile, empirical_coverage, predict_interval
from app.ml.uncertainty.review_router import route
from app.security.adversarial import AdversarialInputDetector
from app.services.progression_service import compare_visits, label_for_velocity


# ---------- measurement ----------
def test_bone_loss_geometry():
    pts = {"cej": [100, 100], "root_apex": [100, 300], "bone_crest": [100, 150]}
    assert bone_loss_for_tooth(pts)["bone_loss_pct"] == 25.0
    pts["bone_crest"] = [100, 90]   # crest above CEJ: no loss
    assert bone_loss_for_tooth(pts)["bone_loss_pct"] == 0.0
    pts["bone_crest"] = [120, 200]  # sideways jitter is ignored by the projection
    assert bone_loss_for_tooth(pts)["bone_loss_pct"] == 50.0
    assert bone_loss_for_tooth(pts, pixel_spacing_mm=0.1)["cej_to_crest_mm"] == pytest.approx(10.2, abs=0.1)
    assert bone_loss_for_tooth({"cej": [1, 1], "root_apex": [1, 1], "bone_crest": [1, 2]})["bone_loss_pct"] is None


def test_staging_bands():
    assert [stage_for_pct(v) for v in (5, 14.9, 15, 33, 33.1, 80)] == ["I", "I", "II", "II", "III", "III"]
    assert stage_for_pct(60, teeth_lost_perio=5) == "IV"
    assert stage_for_pct(None) is None


def test_grade_indirect_and_modifiers():
    assert grade_suggestion(10, 60)["grade"] == "A"          # 0.17
    assert grade_suggestion(30, 40)["grade"] == "B"          # 0.75
    assert grade_suggestion(60, 35)["grade"] == "C"          # 1.7
    heavy = grade_suggestion(10, 60, {"smoking_status": "current", "cigarettes_per_day": 15})
    assert heavy["grade"] == "C" and any("10 or more" in r for r in heavy["reasons"])
    assert grade_suggestion(10, 60, {"diabetic": True, "hba1c": 6.5})["grade"] == "B"
    assert grade_suggestion(None, None)["grade"] is None


# ---------- conformal ----------
def test_conformal_quantile_formula():
    scores = np.arange(1, 11)          # n = 10
    assert conformal_quantile(scores, 0.8) == 9   # ceil(11 * 0.8) = 9th smallest
    assert conformal_quantile(scores, 0.95) == float("inf")


def test_conformal_coverage_holds_on_exchangeable_data():
    rng = np.random.default_rng(1)
    truth = rng.uniform(0, 80, 4000)
    pred = truth + rng.normal(0, 5, 4000)
    scores = np.abs(pred - truth)
    q = conformal_quantile(scores[:2000], 0.9)
    cov = empirical_coverage(pred[2000:], truth[2000:], q)
    assert 0.88 <= cov <= 0.93


def test_prediction_sets():
    assert predict_interval(10.0, 2.0)["stage_set"] == ["I"]
    wide = predict_interval(15.0, 4.0)
    assert wide["stage_set"] == ["I", "II"] and wide["set_size"] == 2
    uncal = predict_interval(20.0, None)
    assert uncal["calibrated"] is False and uncal["set_size"] == 3


def test_review_router_flags():
    tooth = {"tooth_id": "11", "uncertainty": {"calibrated": True, "set_size": 1}, "flags": {},
             "landmark_source": "keypoint_model"}
    assert route([tooth], {"verdict": "pass"}, {"is_ood": False}, False)["status"] == "auto_cleared"
    ambiguous = {**tooth, "uncertainty": {"calibrated": True, "set_size": 2}}
    res = route([ambiguous], {"verdict": "pass"}, {"is_ood": False}, False)
    assert res["status"] == "review_required" and res["reasons"][0]["code"] == "ambiguous_stage"
    attention = {**tooth, "flags": {"low_attention_validity": True}}
    codes = [r["code"] for r in route([attention], {"verdict": "warn", "reasons": []}, {"is_ood": True, "reasons": ["x"]},
                                      True)["reasons"]]
    assert {"demo_mode", "low_quality", "out_of_distribution", "low_attention_validity"} <= set(codes)


def test_review_router_flags_landmarks_used_outside_their_validated_image_type():
    tooth = {"tooth_id": "36", "uncertainty": {"calibrated": True, "set_size": 1}, "flags": {},
             "landmark_source": "keypoint_model_crop"}
    ok = {"verdict": "pass"}
    same = route([tooth], ok, {"is_ood": False}, False, image_type="periapical", validated_image_type="periapical")
    assert same["status"] == "auto_cleared"
    other = route([tooth], ok, {"is_ood": False}, False, image_type="panoramic", validated_image_type="periapical")
    assert [r["code"] for r in other["reasons"]] == ["landmarks_not_validated"]
    unvalidated = route([tooth], ok, {"is_ood": False}, False, image_type="panoramic", validated_image_type=None)
    assert [r["code"] for r in unvalidated["reasons"]] == ["landmarks_not_validated"]


# ---------- progression ----------
def _analysis(date, teeth, source="model_fdi_class", align=0.9):
    return {"analysis_id": date, "visit_date": date, "image_size": [1000, 500], "alignment": {"confidence": align},
            "teeth": [{"tooth_id": tid, "tooth_id_source": source, "bbox": box, "bone_loss_pct": bl,
                       "landmark_source": "keypoint_model"} for tid, box, bl in teeth]}


def test_labels_from_velocity():
    assert label_for_velocity(0.2) == "stable"
    assert label_for_velocity(3.0) == "progressing"
    assert label_for_velocity(8.0) == "rapidly progressing"
    assert label_for_velocity(-2.0) == "improved"


def test_compare_visits_by_tooth_number():
    prev = _analysis("2025-01-01", [("11", [100, 100, 150, 300], 10.0), ("21", [200, 100, 250, 300], 20.0)])
    curr = _analysis("2026-01-01", [("11", [110, 100, 160, 300], 16.0), ("21", [210, 100, 260, 300], 20.2)])
    res = {c["tooth_id"]: c for c in compare_visits(prev, curr)}
    assert res["11"]["match_method"] == "tooth_number" and res["11"]["label"] == "rapidly progressing"
    assert res["21"]["label"] == "stable" and res["21"]["reliable"]


def test_unreliable_comparisons_are_flagged_not_silently_computed():
    prev = _analysis("2025-01-01", [("T1", [100, 100, 150, 300], 10.0)], source="positional_estimate")
    curr = _analysis("2026-01-01", [("T1", [105, 100, 155, 300], 20.0)], source="positional_estimate", align=0.2)
    c = compare_visits(prev, curr)[0]
    assert c["match_method"] == "spatial" and not c["reliable"]
    assert c["label"] == "unreliable comparison" and len(c["reliability_reasons"]) >= 2


# ---------- quality + adversarial ----------
def _texture(seed=0):
    rng = np.random.default_rng(seed)
    img = cv2.GaussianBlur(rng.integers(40, 200, (700, 1400)).astype(np.uint8), (0, 0), 3)
    for i in range(12):
        cv2.rectangle(img, (70 + i * 105, 180), (140 + i * 105, 540), 200, 3)
    return img


def test_quality_gate():
    assert assess_quality(_texture())["verdict"] in ("pass", "warn")
    flat = np.full((700, 1400), 128, np.uint8)
    assert assess_quality(flat)["verdict"] == "reject"
    assert assess_quality(cv2.resize(_texture(), (200, 100)))["verdict"] == "reject"


def test_adversarial_noise_is_detected():
    from tests.conftest import synthetic_radiograph

    img = cv2.imdecode(np.frombuffer(synthetic_radiograph(), np.uint8), cv2.IMREAD_GRAYSCALE)
    det = AdversarialInputDetector()
    assert not det.detect_adversarial(img)["is_suspicious"]
    noisy = np.clip(img.astype(np.int16) + np.random.default_rng(0).choice([-8, 8], img.shape), 0, 255).astype(np.uint8)
    assert det.detect_adversarial(noisy)["is_suspicious"]


# ---------- risk ----------
def test_risk_is_monotonic_and_explained():
    base = {"age": 45, "smoking_status": "never", "diabetic": False, "hba1c": 5.4}
    img = {"mean_bone_loss_pct": 10, "max_bone_loss_pct": 15, "affected_teeth": 1}
    low = predict_patient_risk(base, img)
    high = predict_patient_risk({**base, "smoking_status": "current", "cigarettes_per_day": 20, "diabetic": True,
                                 "hba1c": 9.0}, {**img, "mean_bone_loss_pct": 40, "max_bone_loss_pct": 60})
    assert high["probability"] > low["probability"]
    assert high["category"] in ("moderate", "high") and high["top_factors"]
    assert high["model_type"] == "rule-assisted demo"
    assert "not a calibrated clinical risk" in high["disclaimer"]


def test_visit_date_parsing_in_progression():
    assert compare_visits(_analysis("2025-01-01", []), _analysis(dt.date(2025, 6, 1).isoformat(), [])) == []
