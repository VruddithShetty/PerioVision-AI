"""Verification of the LIVE pipeline with the real trained weights (docs/VERIFICATION_REPORT.md).

Every test feeds real radiographs through the real models and checks that outputs are computed
from the input (they change when the input changes) and that nothing is reported as a measurement
unless a model produced it. Run from backend/:  python -m pytest tests_live -q
"""
import io
import json

import cv2
import numpy as np
import pytest

from tests_live.conftest import UA, needs_weights

pytestmark = needs_weights


def _gray(path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    return img.reshape(img.shape[:2])


def _png(gray: np.ndarray) -> bytes:
    return cv2.imencode(".png", gray)[1].tobytes()


@pytest.fixture(scope="module")
def services(app):
    from app.services import container
    from app.services.analysis_service import locate_teeth, run_analysis

    pm = container.patient_manager()
    user = {"id": "live-verifier", "role": "dentist", "name": "Verifier"}

    def new_patient(**clinical):
        p = pm.create_patient({"name": "Verification Patient", "age": 50, "sex": "female", "smoking_status": "never",
                               "diabetic": False, **clinical}, owner_id=user["id"])
        return pm.get_raw(p["patient_id"])

    def analyse(gray, patient, date):
        return run_analysis(_png(gray), patient, user, visit_date=date)

    return {"locate": locate_teeth, "analyse": analyse, "new_patient": new_patient, "container": container}


# ---------- models are real, signed and loaded ----------
def test_real_signed_models_are_loaded(services):
    services["container"].tooth_detector(), services["container"].landmark_detector()
    status = {s["name"]: s for s in services["container"].registry().status()}
    for name in ("tooth_detector", "landmarks"):
        assert status[name]["signature_valid"] and status[name]["loaded"], status[name]


def test_detector_boxes_come_from_the_image(services, panoramic_images):
    a = services["locate"](_gray(panoramic_images[0]))
    b = services["locate"](_gray(panoramic_images[1]))
    assert a["live"] and a["detections"] and b["detections"]
    assert all(d["tooth_id_source"] == "model_fdi_class" for d in a["detections"])
    boxes_a = sorted(tuple(d["bbox"]) for d in a["detections"])
    boxes_b = sorted(tuple(d["bbox"]) for d in b["detections"])
    assert boxes_a != boxes_b
    # shifting the image shifts the boxes by the same amount (they are computed, not fixed)
    g = _gray(panoramic_images[0])
    shifted = np.zeros_like(g)
    shifted[:, 40:] = g[:, :-40]
    s = services["locate"](shifted)
    common = {d["tooth_id"]: d for d in a["detections"]}
    dx = [d["bbox"][0] - common[d["tooth_id"]]["bbox"][0] for d in s["detections"]
          if d["tooth_id"] in common and common[d["tooth_id"]]["bbox"][0] > 60]
    assert dx and abs(float(np.median(dx)) - 40) < 8


# ---------- preprocessing ----------
def test_clahe_runs_and_changes_the_image(panoramic_images):
    from app.ml.preprocessing.clahe import apply_clahe

    g = _gray(panoramic_images[0])
    e = apply_clahe(g)
    assert e.shape == g.shape and not np.array_equal(e, g)
    # local contrast goes up (mean 32x32 tile standard deviation)
    def tile_std(img):
        h, w = (img.shape[0] // 32) * 32, (img.shape[1] // 32) * 32
        return img[:h, :w].reshape(h // 32, 32, w // 32, 32).std(axis=(1, 3)).mean()
    assert tile_std(e) > tile_std(g)


def test_quality_gate_rejects_degraded_radiographs(services, denpar_images):
    from app.ml.preprocessing.quality_check import assess_quality

    g = _gray(denpar_images[0])
    assert assess_quality(g)["verdict"] in ("pass", "warn")
    assert assess_quality(cv2.GaussianBlur(g, (0, 0), 12))["verdict"] == "reject"
    assert assess_quality(cv2.resize(g, (200, 150)))["verdict"] == "reject"
    assert assess_quality(np.full_like(g, 128))["verdict"] == "reject"


def test_non_radiograph_is_never_auto_cleared(services):
    from app.services.analysis_service import QualityRejected

    page = np.full((900, 1200), 245, np.uint8)                     # a scanned text document
    for i in range(30):
        cv2.putText(page, "Lorem ipsum dolor sit amet consectetur " * 2, (20, 30 + 28 * i),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, 20, 1)
    with pytest.raises(QualityRejected) as exc:
        services["analyse"](page, services["new_patient"](), "2026-01-01")
    assert exc.value.quality["verdict"] == "reject"
    noise = cv2.GaussianBlur(np.random.default_rng(1).integers(0, 255, (900, 1200), dtype=np.uint8), (0, 0), 2)
    with pytest.raises(QualityRejected):
        services["analyse"](noise, services["new_patient"](), "2026-01-01")


# ---------- landmarks and bone loss ----------
def test_landmarks_and_bone_loss_are_computed_from_the_image(services, denpar_images):
    from app.ml.measurement.bone_loss import bone_loss_for_tooth

    r = services["locate"](_gray(denpar_images[0]))
    assert r["image_type"] == "periapical"
    lms = [r["landmarks"][d["tooth_id"]] for d in r["detections"]]
    assert lms and all(lm["landmark_source"] == "keypoint_model" for lm in lms)
    pcts = [bone_loss_for_tooth(lm)["bone_loss_pct"] for lm in lms]
    assert len(set(pcts)) == len(pcts), "every tooth got the same value"
    # move the radiograph down by 30 px: the landmarks move with it
    g = _gray(denpar_images[0])
    moved = np.zeros_like(g)
    moved[30:] = g[:-30]
    r2 = services["locate"](moved)
    dy = [b["cej"][1] - a["cej"][1] for a, b in zip(lms, [r2["landmarks"][d["tooth_id"]] for d in r2["detections"]])
          if abs(b["cej"][0] - a["cej"][0]) < 15]
    assert dy and abs(float(np.median(dy)) - 30) < 6


def test_teeth_without_model_landmarks_get_no_number(services, panoramic_images):
    r = services["analyse"](_gray(panoramic_images[0]), services["new_patient"](), "2026-01-01")
    assert r["mode"] == "live" and r["source"] == "uploaded_radiograph"
    assert r["image_type"] == "panoramic" and r["teeth"]
    # landmarks are validated on periapical films only: a panoramic film gets detection + FDI numbers, no numbers
    for t in r["teeth"]:
        assert t["bone_loss_pct"] is None and t["stage"] is None and t["cej"] is None
        assert t["roi_attention"] is None and t["uncertainty"]["interval"] is None
        assert t["landmark_source"] in ("not_measured", "not_validated_on_panoramic")
    reasons = {x["code"]: x for x in r["review"]["reasons"]}
    assert "not_validated_image_type" in reasons
    assert r["summary"]["teeth_measured"] == 0 and r["summary"]["stage"] is None


def test_stage_follows_the_documented_bands(services, denpar_images):
    from app.ml.measurement.staging import stage_for_pct

    r = services["analyse"](_gray(denpar_images[1]), services["new_patient"](), "2026-01-01")
    for t in r["teeth"]:
        if t["bone_loss_pct"] is not None:
            p = t["bone_loss_pct"]
            assert t["stage"] == ("I" if p < 15 else "II" if p <= 33 else "III") == stage_for_pct(p)


# ---------- explainability ----------
def test_gradcam_is_computed_from_the_model_that_made_the_detection(services, denpar_images, panoramic_images):
    from app.services.analysis_service import locate_teeth

    maps = []
    for path in (denpar_images[0], denpar_images[1]):
        r = locate_teeth(_gray(path))
        assert r["explain_model_name"] == "landmark (pose) model"
        hm = r["explain_model"].gradcam_heatmap(r["bgr"], r["detections"])
        assert hm is not None and hm.shape == r["bgr"].shape[:2] and hm.max() > 0
        maps.append(cv2.resize(hm, (256, 256)))
    assert float(np.abs(maps[0] - maps[1]).mean()) > 0.01, "heatmap does not depend on the image"
    pan = locate_teeth(_gray(panoramic_images[0]))
    assert pan["explain_model_name"] == "tooth detector"


def test_roi_attention_is_measured_per_tooth(services, denpar_images):
    r = services["analyse"](_gray(denpar_images[2]), services["new_patient"](), "2026-01-01")
    att = [t["roi_attention"] for t in r["teeth"] if t["roi_attention"] is not None]
    assert len(att) >= 2 and len(set(att)) > 1, att
    for t in r["teeth"]:
        if t["roi_attention"] is not None:
            assert t["flags"]["low_attention_validity"] == (t["roi_attention"] < 0.25)


# ---------- uncertainty ----------
def test_conformal_intervals_use_the_calibrated_q(services, denpar_images):
    from app.ml.uncertainty import calibration

    q = calibration.current_q()
    assert q is not None and 0 < q < 50
    r = services["analyse"](_gray(denpar_images[3]), services["new_patient"](), "2026-01-01")
    widths = []
    for t in r["teeth"]:
        if t["bone_loss_pct"] is None:
            continue
        lo, hi = t["uncertainty"]["interval"]
        # half-width = q * sigma(mirrored-pass disagreement of THIS tooth) (sigma = 1 for fixed-width calibration)
        half = q * calibration.scale_for(t)
        assert t["uncertainty"]["half_width"] == pytest.approx(half, abs=0.01)
        assert lo == pytest.approx(max(0.0, t["bone_loss_pct"] - half), abs=0.01)
        assert hi == pytest.approx(min(100.0, t["bone_loss_pct"] + half), abs=0.01)
        widths.append(round(half, 2))
    if (calibration.load() or {}).get("sigma"):
        assert len(set(widths)) > 1, "adaptive calibration but every tooth got the same width"
    trust = calibration.report()
    assert trust["calibrated"] and trust["levels"]["0.9"]["empirical_coverage_other_half"] is not None


# ---------- longitudinal ----------
def test_unrelated_radiographs_are_not_compared_as_progression(services, denpar_images):
    patient = services["new_patient"]()
    services["analyse"](_gray(denpar_images[0]), patient, "2025-01-01")
    second = services["analyse"](_gray(denpar_images[1]), patient, "2026-01-01")   # a different person's film
    assert second["alignment"]["status"] == "failed"
    assert second["progression"] and not any(c["reliable"] for c in second["progression"])
    assert second["summary"]["max_velocity_pct_per_year"] is None
    assert second["summary"]["grade"]["basis"] != "direct (observed progression)"


def test_same_film_rotated_registers_and_matches_the_same_teeth(services, denpar_images):
    g = _gray(denpar_images[4])
    h, w = g.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), 4.0, 1.03)
    m[:, 2] += (25, -10)
    later = cv2.warpAffine(g, m, (w, h), borderValue=int(np.median(g)))
    patient = services["new_patient"]()
    first = services["analyse"](g, patient, "2025-01-01")
    second = services["analyse"](later, patient, "2026-01-01")
    assert second["alignment"]["status"] == "success", second["alignment"]
    comps = second["progression"]
    assert comps, "no teeth were matched across the visits"
    by_prev = {t["tooth_id"]: t for t in first["teeth"]}
    for c in comps:
        prev_box = by_prev[c["previous_tooth_id"]]["bbox"]
        cx, cy = (prev_box[0] + prev_box[2]) / 2, (prev_box[1] + prev_box[3]) / 2
        px, py = m @ np.array([cx, cy, 1.0])                         # where that tooth went in the later film
        cur = next(t for t in second["teeth"] if t["tooth_id"] == c["tooth_id"])["bbox"]
        assert cur[0] - 20 <= px <= cur[2] + 20 and cur[1] - 20 <= py <= cur[3] + 20, c
        # same anatomy -> any difference is measurement noise, never "progression"
        assert c["label"] in ("no change beyond measurement error", "unreliable comparison")


def test_films_sharing_imaging_plate_artefacts_are_not_compared(services):
    """DenPAR test films 152 and 269 are different patients taken on the same imaging plate: identical scratches
    and frame marks fooled feature matching (47 RANSAC inliers, NCC 0.75). The tooth-overlap check must refuse them."""
    from tests_live.conftest import DENPAR_DIR

    a, b = DENPAR_DIR / "images" / "test" / "152.jpg", DENPAR_DIR / "images" / "test" / "269.jpg"
    if not (a.exists() and b.exists()):
        pytest.skip("DenPAR test films 152 / 269 not available")
    patient = services["new_patient"]()
    services["analyse"](_gray(a), patient, "2025-01-01")
    second = services["analyse"](_gray(b), patient, "2026-01-01")
    assert second["alignment"]["status"] == "failed"
    assert second["alignment"]["reason"] == "teeth do not line up after registration"
    assert not any(c["reliable"] for c in second["progression"])


def test_mirrored_film_is_not_matched_tooth_for_tooth(services, denpar_images):
    g = _gray(denpar_images[4])
    patient = services["new_patient"]()
    services["analyse"](g, patient, "2025-01-01")
    second = services["analyse"](cv2.flip(g, 1), patient, "2026-01-01")
    assert second["alignment"]["status"] == "failed"
    assert not any(c["reliable"] for c in second["progression"])


def test_velocity_uses_the_real_visit_dates(app):
    from app.services.progression_service import compare_visits

    tooth = lambda bl: {"tooth_id": "11", "tooth_id_source": "model_fdi_class", "bbox": [0, 0, 10, 10],  # noqa: E731
                        "bone_loss_pct": bl}
    base = {"image_size": [100, 100], "mode": "live", "image_type": "periapical",
            "alignment": {"status": "success", "confidence": 0.9}}
    prev = {**base, "analysis_id": "a", "visit_date": "2024-01-01", "teeth": [tooth(10.0)]}
    one = compare_visits(prev, {**base, "analysis_id": "b", "visit_date": "2025-01-01", "teeth": [tooth(60.0)]})[0]
    two = compare_visits(prev, {**base, "analysis_id": "c", "visit_date": "2026-01-01", "teeth": [tooth(60.0)]})[0]
    assert one["interval_days"] == 366 and two["interval_days"] == 731
    assert one["velocity_pct_per_year"] == pytest.approx(50 / (366 / 365.25), abs=0.01)
    assert two["velocity_pct_per_year"] == pytest.approx(50 / (731 / 365.25), abs=0.01)


# ---------- risk ----------
def test_risk_changes_with_clinical_inputs_on_a_real_analysis(services, denpar_images):
    g = _gray(denpar_images[5])
    base = services["analyse"](g, services["new_patient"](), "2026-01-01")["risk"]
    smoker = services["analyse"](g, services["new_patient"](smoking_status="current", cigarettes_per_day=20,
                                                            diabetic=True, hba1c=9.1), "2026-01-01")["risk"]
    assert base["model_type"] == smoker["model_type"] == "logistic regression trained on NHANES"
    assert smoker["probability"] > base["probability"]
    assert {f["factor"] for f in smoker["top_factors"]} != {f["factor"] for f in base["top_factors"]}


# ---------- tampering ----------
def test_a_one_byte_change_to_the_weights_is_refused_and_logged(services, denpar_images):
    from app import config
    from app.security.audit_log import audit

    container = services["container"]
    path = config.WEIGHTS_DIR / "dental_landmark_yolov8n-pose.pt"      # the TEMPORARY copy, never the real file
    original = path.read_bytes()
    try:
        tampered = bytearray(original)
        tampered[len(tampered) // 2] ^= 0x01
        path.write_bytes(bytes(tampered))
        container.reset_models()
        assert container.landmark_detector().available is False
        refusals = audit().recent(limit=5, action="MODEL_LOAD_REFUSED")
        assert any(e.get("resource") == path.name for e in refusals)
        status = {s["name"]: s for s in container.registry().status()}["landmarks"]
        assert not status["signature_valid"] and not status["loaded"]
    finally:
        path.write_bytes(original)
        container.reset_models()
    assert container.landmark_detector().available


# ---------- API: live responses are tagged live and never synthetic ----------
def test_live_api_response_is_live_and_not_synthetic(client, dentist, denpar_images):
    pid = client.post("/api/patients", headers=dentist, json={"name": "API Live", "age": 60,
                                                              "smoking_status": "former"}).get_json()["data"]["patient_id"]
    up = client.post("/api/radiographs", headers=dentist, content_type="multipart/form-data",
                     data={"image": (io.BytesIO(_png(_gray(denpar_images[6]))), "film.png")})
    assert up.status_code == 201, up.get_json()
    r = client.post("/api/analyses", headers=dentist, json={"upload_id": up.get_json()["data"]["upload_id"],
                                                            "patient_id": pid, "visit_date": "2026-02-01"})
    assert r.status_code == 201, r.get_json()
    body = r.get_json()
    assert body["data"]["mode"] == "live" and body["data"]["source"] != "synthetic_demo"
    prog = client.get(f"/api/patients/{pid}/progression", headers={**dentist, **UA}).get_json()
    assert prog["error"] is None


# ---------- whole-film panoramic estimate ----------
def test_panoramic_films_get_a_validated_whole_film_estimate(services, panoramic_images):
    from app import config

    if not (config.WEIGHTS_DIR / "panoramic_severity.pt").exists():
        pytest.skip("panoramic whole-film models not installed")
    a = services["analyse"](_gray(panoramic_images[0]), services["new_patient"](), "2026-01-01")
    b = services["analyse"](_gray(panoramic_images[1]), services["new_patient"](), "2026-01-01")
    pa = a["panoramic_assessment"]
    assert pa and pa["level"].startswith("patient")
    metrics = json.loads((config.WEIGHTS_DIR / "panoramic_severity_metrics.json").read_text())
    wt = pa["worst_tooth"]
    q = metrics["conformal_q90_from_val"]
    assert wt["interval_90"][0] == pytest.approx(max(0, wt["bone_loss_pct"] - q), abs=0.11)
    assert wt["interval_90"][1] == pytest.approx(min(100, wt["bone_loss_pct"] + q), abs=0.11)
    assert wt["test"]["test_MAE"] == metrics["test_MAE"]             # accuracy shown is read from the metrics file
    for jaw in ("maxilla", "mandible"):
        p = pa["screen"][jaw]
        assert 0.0 <= p["probability"] <= 1.0 and p["bone_loss_suggested"] == (p["probability"] >= p["threshold"])
    pb = b["panoramic_assessment"]
    assert (pa["worst_tooth"]["bone_loss_pct"], pa["screen"]["maxilla"]["probability"]) !=         (pb["worst_tooth"]["bone_loss_pct"], pb["screen"]["maxilla"]["probability"]), "output does not depend on the film"
    # per-tooth numbers stay withheld on panoramic films
    assert all(t["bone_loss_pct"] is None for t in a["teeth"])


def test_periapical_films_get_no_panoramic_estimate(services, denpar_images):
    r = services["analyse"](_gray(denpar_images[0]), services["new_patient"](), "2026-01-01")
    assert r["image_type"] == "periapical" and r["panoramic_assessment"] is None


def test_tampered_panoramic_model_is_refused(services, panoramic_images):
    from app import config
    from app.ml.panoramic.whole_film import whole_film

    path = config.WEIGHTS_DIR / "panoramic_severity.pt"
    if not path.exists():
        pytest.skip("panoramic whole-film models not installed")
    original = path.read_bytes()
    try:
        data = bytearray(original)
        data[len(data) // 2] ^= 0x01
        path.write_bytes(bytes(data))
        services["container"].reset_models()
        out = whole_film().assess(_gray(panoramic_images[0]))
        assert out is None or "worst_tooth" not in out
    finally:
        path.write_bytes(original)
        services["container"].reset_models()
