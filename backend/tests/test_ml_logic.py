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
from app.services.progression_service import compare_visits, label_for_velocity, usable_velocities


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


def test_adaptive_interval_scales_with_difficulty(monkeypatch):
    from app.ml.uncertainty import calibration

    spec = {"intercept": 4.0, "slope": 0.5, "floor": 2.0, "missing_sigma": 12.0}
    monkeypatch.setattr(calibration, "load", lambda: {"scores": [1.0] * 50, "sigma": spec})
    assert calibration.scale_for({"tta_disagreement_pct": 0.0}) == 4.0
    assert calibration.scale_for({"tta_disagreement_pct": 10.0}) == 9.0
    assert calibration.scale_for({"tta_disagreement_pct": None}) == 12.0      # unseen in the mirror: widest
    easy, hard = predict_interval(30.0, 2.0, 4.0), predict_interval(30.0, 2.0, 9.0)
    assert easy["half_width"] == 8.0 and hard["half_width"] == 18.0 and easy["set_size"] < hard["set_size"]
    monkeypatch.setattr(calibration, "load", lambda: {"scores": [1.0] * 50})       # standard calibration
    assert calibration.scale_for({"tta_disagreement_pct": 10.0}) == 1.0


def test_progression_uses_each_readings_own_error_bound(monkeypatch):
    from app.ml.uncertainty import calibration

    monkeypatch.setattr(calibration, "current_q", lambda coverage=None: 2.0)
    def tooth(bl, hw):
        return {"tooth_id": "11", "tooth_id_source": "model_fdi_class", "bbox": [0, 0, 10, 10], "bone_loss_pct": bl,
                "uncertainty": {"half_width": hw}}
    base = {"image_size": [100, 100], "mode": "live", "image_type": "periapical",
            "alignment": {"status": "success", "confidence": 0.9}}
    prev = {**base, "analysis_id": "a", "visit_date": "2024-01-01", "teeth": [tooth(10.0, 5.0)]}
    small = compare_visits(prev, {**base, "analysis_id": "b", "visit_date": "2025-01-01", "teeth": [tooth(20.0, 6.0)]})[0]
    big = compare_visits(prev, {**base, "analysis_id": "c", "visit_date": "2025-01-01", "teeth": [tooth(22.0, 6.0)]})[0]
    assert small["measurement_error_pct"] == 11.0 and not small["change_detectable"]     # 10 < 5 + 6
    assert big["change_detectable"]                                                    # 12 > 11


def test_review_router_flags():
    tooth = {"tooth_id": "11", "uncertainty": {"calibrated": True, "set_size": 1}, "flags": {},
             "landmark_source": "keypoint_model", "bone_loss_pct": 10.0}
    assert route([tooth], {"verdict": "pass"}, {"is_ood": False}, False)["status"] == "auto_cleared"
    ambiguous = {**tooth, "uncertainty": {"calibrated": True, "set_size": 2}}
    res = route([ambiguous], {"verdict": "pass"}, {"is_ood": False}, False)
    assert res["status"] == "review_required" and res["reasons"][0]["code"] == "ambiguous_stage"
    attention = {**tooth, "flags": {"low_attention_validity": True}}
    codes = [r["code"] for r in route([attention], {"verdict": "warn", "reasons": []}, {"is_ood": True, "reasons": ["x"]},
                                      True)["reasons"]]
    assert {"demo_mode", "low_quality", "out_of_distribution", "low_attention_validity"} <= set(codes)
    unmeasured = {**tooth, "bone_loss_pct": None}
    res = route([unmeasured], {"verdict": "pass"}, {"is_ood": False}, False)
    assert [r["code"] for r in res["reasons"]] == ["not_measured"]


def test_review_router_flags_landmarks_used_outside_their_validated_image_type():
    tooth = {"tooth_id": "36", "uncertainty": {"calibrated": True, "set_size": 1}, "flags": {},
             "landmark_source": "keypoint_model_crop", "bone_loss_pct": 10.0}
    ok = {"verdict": "pass"}
    same = route([tooth], ok, {"is_ood": False}, False, image_type="periapical", validated_image_type="periapical")
    assert same["status"] == "auto_cleared"
    other = route([tooth], ok, {"is_ood": False}, False, image_type="panoramic", validated_image_type="periapical")
    assert [r["code"] for r in other["reasons"]] == ["landmarks_not_validated"]
    unvalidated = route([tooth], ok, {"is_ood": False}, False, image_type="panoramic", validated_image_type=None)
    assert [r["code"] for r in unvalidated["reasons"]] == ["landmarks_not_validated"]


def test_review_router_uses_the_panoramic_conformal_interval():
    ok, clean = {"verdict": "pass"}, {"is_ood": False}
    tooth = {"tooth_id": "36", "uncertainty": {"calibrated": True, "set_size": 0}, "flags": {},
             "landmark_source": "not_validated_on_panoramic", "measurement_status": "not_validated_on_panoramic",
             "bone_loss_pct": None}
    wide = {"worst_tooth": {"interval_90": [0.0, 52.3], "stage_set": ["I", "II", "III"]}}
    codes = [r["code"] for r in route([tooth], ok, clean, False, "panoramic", "periapical", wide)["reasons"]]
    assert "panoramic_stage_ambiguous" in codes and "not_validated_image_type" in codes
    narrow = {"worst_tooth": {"interval_90": [0.0, 12.0], "stage_set": ["I"]}}
    codes = [r["code"] for r in route([tooth], ok, clean, False, "panoramic", "periapical", narrow)["reasons"]]
    assert "panoramic_stage_ambiguous" not in codes
    no_model = [r["code"] for r in route([tooth], ok, clean, False, "panoramic", "periapical", {"screen": {}})["reasons"]]
    assert "panoramic_estimate_unavailable" in no_model
    extra = route([], ok, clean, False, extra_reasons=[{"code": "film_shape_not_panoramic", "message": "x"}])
    assert extra["status"] == "review_required"


# ---------- progression ----------
def _analysis(date, teeth, source="model_fdi_class", align=0.9):
    return {"analysis_id": date, "visit_date": date, "image_size": [1000, 500], "alignment": {"confidence": align, "status": "success" if align >= 0.5 else "failed"},
            "mode": "demo",
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


def _live(a):
    return {**a, "mode": "live", "image_type": "periapical"}


def test_live_change_within_measurement_error_is_not_called_progression(monkeypatch):
    from app.ml.uncertainty import calibration

    monkeypatch.setattr(calibration, "current_q", lambda coverage=None: 18.6)
    prev = _live(_analysis("2025-01-01", [("11", [100, 100, 150, 300], 10.0), ("21", [200, 100, 250, 300], 10.0)]))
    curr = _live(_analysis("2026-01-01", [("11", [110, 100, 160, 300], 30.0), ("21", [210, 100, 260, 300], 60.0)]))
    res = {c["tooth_id"]: c for c in compare_visits(prev, curr)}
    # +20 points is within 2q = 37.2 of measurement error: no claim of progression, not usable for grading
    assert res["11"]["reliable"] and not res["11"]["change_detectable"]
    assert res["11"]["label"] == "no change beyond measurement error"
    assert res["21"]["change_detectable"] and res["21"]["label"] == "rapidly progressing"
    assert usable_velocities(list(res.values())) == [res["21"]["velocity_pct_per_year"]]


def test_live_comparison_without_calibration_or_registration_is_unreliable(monkeypatch):
    from app.ml.uncertainty import calibration

    monkeypatch.setattr(calibration, "current_q", lambda coverage=None: None)
    prev = _live(_analysis("2025-01-01", [("11", [100, 100, 150, 300], 10.0)]))
    curr = _live(_analysis("2026-01-01", [("11", [110, 100, 160, 300], 60.0)]))
    c = compare_visits(prev, curr)[0]
    assert not c["reliable"] and any("uncalibrated" in r for r in c["reliability_reasons"])

    monkeypatch.setattr(calibration, "current_q", lambda coverage=None: 5.0)
    # a score above the threshold is not enough: the registration itself must have succeeded
    failed = {**curr, "alignment": {"confidence": 0.55, "status": "failed", "reason": "registered images do not look alike"}}
    c = compare_visits(prev, failed)[0]
    assert not c["reliable"] and any("could not be registered" in r for r in c["reliability_reasons"])
    other_type = {**curr, "image_type": "panoramic"}
    c = compare_visits(prev, other_type)[0]
    assert not c["reliable"] and any("Different radiograph types" in r for r in c["reliability_reasons"])


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
    base = {"age": 45, "sex": "female", "smoking_status": "never", "diabetic": False, "hba1c": 5.4}
    low = predict_patient_risk(base)
    high = predict_patient_risk({**base, "sex": "male", "smoking_status": "current", "cigarettes_per_day": 20,
                                 "diabetic": True, "hba1c": 9.0})
    assert high["probability"] > low["probability"]
    assert high["top_factors"] and not low["top_factors"]            # the reference person has no raising factors
    assert high["model_type"] == "logistic regression trained on NHANES"
    assert high["validation"]["roc_auc"] > 0.6 and high["validation"]["test_n"] > 1000
    assert "does not read the radiograph" in high["disclaimer"]


def test_risk_fuses_clinical_and_radiograph_evidence():
    from app.ml.fusion.multimodal_risk import fuse_with_radiograph

    clinical = predict_patient_risk({"age": 45, "sex": "female", "smoking_status": "never", "diabetic": False,
                                     "hba1c": 5.4})
    assert clinical["category"] == "low"
    # a measured stage III radiograph raises the combined level; the trained probability is unchanged
    fused = fuse_with_radiograph(clinical, {"stage": "III", "max_bone_loss_pct": 41.0})
    assert fused["fusion"]["level"] == "high" and fused["fusion"]["radiographic_level"] == "high"
    assert fused["probability"] == clinical["probability"] and fused["category"] == "low"
    # panoramic: the whole-film estimate is the radiographic evidence
    pano = {"worst_tooth": {"bone_loss_pct": 25.7, "stage": "II", "interval_90": [0.0, 52.3],
                            "stage_set": ["I", "II", "III"]}}
    assert fuse_with_radiograph(clinical, {"stage": None}, pano)["fusion"]["level"] == "moderate"
    # measurable rapid progression is high whatever the stage
    rapid = fuse_with_radiograph(clinical, {"stage": "I", "max_bone_loss_pct": 10.0, "max_velocity_pct_per_year": 9.0})
    assert rapid["fusion"]["level"] == "high"
    # no measurement on the film: the radiograph adds nothing and says so
    none = fuse_with_radiograph(clinical, {"stage": None})
    assert none["fusion"]["level"] == "low" and none["fusion"]["radiographic_level"] is None
    assert "no bone-loss measurement" in none["fusion"]["reasons"][-1]
    # missing clinical inputs: the radiograph alone sets the level
    missing = fuse_with_radiograph(predict_patient_risk({"age": 45}), {"stage": "II", "max_bone_loss_pct": 20.0})
    assert missing["probability"] is None and missing["fusion"]["level"] == "moderate"


def test_grade_message_names_the_missing_measurement():
    assert "No per-tooth bone-loss measurement" in grade_suggestion(None, 50)["reasons"][0]
    assert "age" in grade_suggestion(30.0, None)["reasons"][0]


def test_risk_comes_from_the_trained_coefficients():
    import math

    from app.ml.fusion.multimodal_risk import load_model

    m = load_model()["models"]["with_hba1c"]
    c = {"age": 50, "sex": "male", "smoking_status": "current", "cigarettes_per_day": 9, "diabetic": True, "hba1c": 7.0}
    x = {"age": 50, "male": 1, "current_smoker": 1, "former_smoker": 0, "log_cigs": math.log1p(9), "diabetic": 1, "hba1c": 7.0}
    expected = 1 / (1 + math.exp(-(m["intercept"] + sum(m["coefficients"][k] * x[k] for k in m["features"]))))
    assert predict_patient_risk(c)["probability"] == round(expected, 3)
    no_lab = predict_patient_risk({**c, "hba1c": None})
    assert no_lab["variant"] == "without_hba1c" and no_lab["probability"] is not None


def test_risk_responds_to_each_clinical_toggle():
    base = {"age": 45, "sex": "female", "smoking_status": "never", "diabetic": False, "hba1c": 5.4}
    p0 = predict_patient_risk(base)
    for change, factor in (({"smoking_status": "current", "cigarettes_per_day": 5}, "Current smoker"),
                           ({"sex": "male"}, "Male sex"),
                           ({"hba1c": 9.5}, "HbA1c level")):
        r = predict_patient_risk({**base, **change})
        assert r["probability"] > p0["probability"], change
        assert factor in [f["factor"] for f in r["top_factors"]], change
    assert predict_patient_risk({**base, "age": 70})["probability"] > p0["probability"]


@pytest.mark.parametrize("clinical, missing", [
    ({"sex": "female", "smoking_status": "never"}, "age"),
    ({"age": 25, "sex": "female", "smoking_status": "never"}, "age 30 or over (the model was trained on adults aged 30+)"),
    ({"age": 50, "smoking_status": "never"}, "sex (male / female)"),
    ({"age": 50, "sex": "other", "smoking_status": "never"}, "sex (male / female)"),
    ({"age": 50, "sex": "male"}, "smoking status"),
    ({"age": 50, "sex": "male", "smoking_status": "current"}, "cigarettes per day"),
])
def test_risk_is_withheld_not_defaulted_when_inputs_are_missing(clinical, missing):
    r = predict_patient_risk(clinical)
    assert r["status"] == "insufficient_data" and r["probability"] is None and r["category"] is None
    assert missing in r["missing_inputs"]


def test_visit_date_parsing_in_progression():
    assert compare_visits(_analysis("2025-01-01", []), _analysis(dt.date(2025, 6, 1).isoformat(), [])) == []



def test_tampered_risk_coefficients_are_refused(tmp_path, monkeypatch):
    """The risk model's coefficients are part of the signed manifest: an edited copy gives no score at all."""
    import json as _json

    from app.ml.fusion import multimodal_risk
    from app.security import model_signing

    copy = tmp_path / "risk_model_nhanes.json"
    data = _json.loads(multimodal_risk.MODEL_FILE.read_text(encoding="utf-8"))
    data["models"]["with_hba1c"]["intercept"] += 2.0                  # silently raise every risk
    copy.write_text(_json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(multimodal_risk, "MODEL_FILE", copy)
    monkeypatch.setitem(model_signing.EXTERNAL_FILES, "external/risk_model_nhanes.json", copy)
    multimodal_risk.load_model.cache_clear()
    try:
        r = predict_patient_risk({"age": 50, "sex": "male", "smoking_status": "never", "diabetic": False, "hba1c": 5.5})
        assert r["status"] == "unavailable" and r["probability"] is None
    finally:
        multimodal_risk.load_model.cache_clear()


def test_interval_margins_can_be_asymmetric():
    up = predict_interval(20.0, 10.0, 1.0, 25.0)
    assert up["interval"] == [10.0, 45.0] and up["lower_margin"] == 10.0 and up["upper_margin"] == 25.0
    assert up["half_width"] == 25.0 and "III" in up["stage_set"]
    assert predict_interval(20.0, 10.0)["interval"] == [10.0, 30.0]      # symmetric when no upper margin is given


def test_film_type_routing_uses_count_shape_and_arches():
    from app.services.analysis_service import _route_film

    class Pose:
        def __init__(self, n):
            self.n = n

        def detect_teeth(self, _bgr):
            return [({"tooth_id": f"P{i}"}, {}) for i in range(self.n)]

    def dets(ids):
        return [{"tooth_id": i, "tooth_id_source": "model_fdi_class", "bbox": [0, 0, 1, 1]} for i in ids]

    pano = np.zeros((1000, 2000), np.uint8)      # panoramic proportions
    peri = np.zeros((900, 1200), np.uint8)       # periapical proportions
    assert _route_film(pano, dets(["11", "12", "21", "31", "41"]), Pose(0), None)[:2] == ("panoramic", None)
    assert _route_film(peri, dets([str(10 + i) for i in range(12)]), Pose(5), None)[0] == "panoramic"  # squashed pano
    assert _route_film(peri, dets(["11", "12", "21", "31", "41", "42"]), Pose(3), None)[:2] == ("panoramic", None)
    # the case the count-only rule misrouted: 3 detector teeth, 3 periapical teeth, periapical shape
    assert _route_film(peri, dets(["36", "37", "35"]), Pose(3), None)[:2] == ("periapical", None)
    # ambiguous: 5 teeth from one arch on a periapical-shaped film -> periapical, but flagged
    decision, reason, _ = _route_film(peri, dets(["34", "35", "36", "37", "38"]), Pose(4), None)
    assert decision == "periapical" and reason
    # few teeth on a panoramic-shaped film: flagged whichever way it goes
    assert _route_film(pano, dets(["11"]), Pose(0), None)[1]
