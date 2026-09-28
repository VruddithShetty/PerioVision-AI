"""The radiograph analysis pipeline (objective O1 to O5 in one place).

  upload guard (already done by the API) -> quality gate -> CLAHE
  -> tooth detection (FDI numbers) + Grad-CAM -> CEJ/ABC landmarks
  -> bone loss % + stage per tooth -> conformal interval + stage set
  -> periodontal-ROI attention check -> adversarial + out-of-distribution checks
  -> registration against the previous visit -> progression -> grade -> risk
  -> review routing -> encrypted storage of images -> analysis record + audit entry

If no verified model is available the pipeline still runs end to end in DEMO
MODE: teeth are located by a simple intensity heuristic, every tooth is marked
`source = "demo"`, the response says `"mode": "demo"`, and the case is always
routed to clinician review. The real inference path is unchanged, so signing
and dropping in weights switches to live results.
"""
from __future__ import annotations

import datetime as dt
import logging

import cv2
import numpy as np

from app import config
from app.ml.explainability import overlay
from app.ml.explainability.gradcam import periodontal_roi, roi_attention
from app.ml.landmarks.cej_abc_extractor import heuristic_landmarks
from app.ml.measurement.bone_loss import bone_loss_for_tooth
from app.ml.measurement.staging import grade_suggestion, stage_for_pct
from app.ml.preprocessing.clahe import apply_clahe, compute_phash
from app.ml.preprocessing.quality_check import assess_quality
from app.ml.uncertainty import calibration
from app.ml.uncertainty.conformal import predict_interval
from app.ml.uncertainty.ood import ood_check
from app.ml.uncertainty.review_router import route
from app.security.adversarial import AdversarialInputDetector
from app.security.audit_log import audit
from app.services import container, storage_service
from app.services.progression_service import compare_visits

logger = logging.getLogger(__name__)
STAGE_ORDER = {"I": 1, "II": 2, "III": 3, "IV": 4}


class QualityRejected(Exception):
    def __init__(self, quality: dict):
        super().__init__("Radiograph rejected by the quality gate")
        self.quality = quality


def demo_detections(gray: np.ndarray, max_teeth: int = 14) -> list[dict]:
    """DEMO ONLY: find bright vertical structures in the middle band of the image.

    Not a model and not clinically meaningful; it lets the full workflow be shown
    without weights. Every tooth it returns is labelled as demo output.
    """
    h, w = gray.shape
    blurred = cv2.GaussianBlur(gray, (0, 0), 5)
    band = blurred[int(0.2 * h):int(0.5 * h), :]          # crown band, above most alveolar bone
    profile = np.convolve(band.mean(axis=0), np.ones(25) / 25, mode="same")
    threshold = profile.mean() + 0.25 * profile.std()
    spans, inside, start = [], False, 0
    for x, v in enumerate(profile):
        if v > threshold and not inside:
            inside, start = True, x
        elif (v <= threshold or x == w - 1) and inside:
            inside = False
            if spans and start - spans[-1][1] < max(6, w // 200):   # re-join a tooth split by its canal
                spans[-1][1] = x
            else:
                spans.append([start, x])
    spans = [s for s in spans if s[1] - s[0] >= max(8, w // 80)]
    teeth = []
    for x1, x2 in sorted(spans, key=lambda s: -(s[1] - s[0]))[:max_teeth]:
        rows = blurred[:, x1:x2].mean(axis=1)
        row_thr = rows.min() + 0.6 * (rows.max() - rows.min())
        ys = np.nonzero(rows > row_thr)[0]
        y1, y2 = (int(ys[0]), int(ys[-1])) if len(ys) else (int(0.28 * h), int(0.78 * h))
        teeth.append([float(x1), float(y1), float(x2), float(y2)])
    teeth.sort(key=lambda b: b[0])
    # Demo numbering: the middle of a lower arch, left to right on screen (48 ... 41 | 31 ... 38).
    # Clearly marked as an estimate so progression matching never trusts it like a model class.
    arch = [f"4{n}" for n in range(8, 0, -1)] + [f"3{n}" for n in range(1, 9)]
    start = max(0, (len(arch) - len(teeth)) // 2)
    ids = arch[start:start + len(teeth)] if len(teeth) <= len(arch) else [f"D{i}" for i in range(1, len(teeth) + 1)]
    return [{"tooth_id": ids[i], "tooth_id_source": "demo_fdi_estimate", "class_index": 0,
             "bbox": [round(v, 1) for v in b], "confidence": None, "low_confidence": False}
            for i, b in enumerate(teeth)]


def _decode(png_bytes: bytes) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(png_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError("Could not decode the stored radiograph.")
    return img


def _register_with_previous(prev: dict | None, gray: np.ndarray) -> dict | None:
    """Align the previous visit's radiograph to this one; report how well it worked."""
    if not prev or not prev.get("blobs", {}).get("radiograph"):
        return None
    try:
        prev_gray = _decode(storage_service.get(prev["blobs"]["radiograph"], "radiograph"))
    except Exception as exc:
        return {"confidence": 0.0, "status": "previous image unavailable", "detail": type(exc).__name__}
    ph, pw = prev_gray.shape
    h, w = gray.shape
    scale = 1024.0 / max(w, 1)
    small_cur = cv2.resize(gray, (1024, max(1, int(h * scale))))
    small_prev = cv2.resize(prev_gray, (1024, max(1, int(1024 * ph / pw))))
    aligner = container.aligner()
    _aligned, matrix = aligner.align_by_features(small_cur, small_prev)
    info = getattr(aligner, "last_alignment_info", {}) or {}
    status = info.get("alignment_status", "failed")
    result = {"confidence": float(info.get("alignment_confidence", 0.0)), "status": status,
              "metal_artifact_detected": bool(info.get("metal_artifact_detected", False))}
    if status == "success":
        # Convert the small-image affine (prev_small -> cur_small) into full-resolution coordinates.
        s_prev = np.diag([1024.0 / pw, 1024.0 / pw, 1.0])
        s_cur_inv = np.diag([1.0 / scale, 1.0 / scale, 1.0])
        m = np.vstack([np.asarray(matrix, float), [0, 0, 1]])
        result["matrix_prev_to_curr"] = (s_cur_inv @ m @ s_prev)[:2].round(6).tolist()
    return result


def demo_landmarks(gray: np.ndarray, det: dict) -> dict:
    """DEMO ONLY: geometric CEJ/apex plus an image-based crest estimate (see app/ml/synthetic.py)."""
    from app.ml.synthetic import demo_crest_y

    lm = heuristic_landmarks(det["bbox"])
    crest = demo_crest_y(gray, det["bbox"], lm["cej"][1])
    if crest is not None:
        lm["bone_crest"] = [lm["cej"][0], round(crest, 1)]
    lm["landmark_source"] = "demo"
    return lm


def run_analysis(png_bytes: bytes, patient_doc: dict, user: dict, visit_date: str | None = None,
                 pixel_spacing_mm: float | None = None, upload_meta: dict | None = None,
                 force_demo: bool = False) -> dict:
    gray = _decode(png_bytes)
    h, w = gray.shape
    quality = assess_quality(gray)
    if quality["verdict"] == "reject":
        audit().record("ANALYSIS_REJECTED_QUALITY", outcome="rejected", actor=user["id"],
                       resource=patient_doc["pseudo_id"], details={"reasons": [r["message"] for r in quality["reasons"]]})
        raise QualityRejected(quality)

    enhanced = apply_clahe(gray)
    bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)  # models were trained on unenhanced radiographs

    detector = lm_model = None
    if not force_demo:
        detector, lm_model = container.tooth_detector(), container.landmark_detector()
    live = detector is not None and detector.available
    detections = detector.detect_teeth(bgr) if live else demo_detections(enhanced)
    landmarks = lm_model.detect_landmarks(detections, bgr) if (live and lm_model.available) \
        else {d["tooth_id"]: demo_landmarks(gray, d) for d in detections}
    heatmap = detector.gradcam_heatmap(bgr, detections) if live else None

    q = calibration.current_q()
    t_exp = config.THRESHOLDS["explainability"]
    clinical = container.patient_manager().clinical_profile(patient_doc)
    teeth = []
    for det in detections:
        lm = landmarks.get(det["tooth_id"], heuristic_landmarks(det["bbox"]))
        bl = bone_loss_for_tooth(lm, pixel_spacing_mm)
        pct = bl.get("bone_loss_pct")
        roi = periodontal_roi(det["bbox"], lm["cej"], lm["bone_crest"], t_exp["roi_margin_fraction"])
        attention = roi_attention(heatmap, det["bbox"], roi)
        unc = predict_interval(pct, q)
        teeth.append({
            "tooth_id": det["tooth_id"],
            "tooth_id_source": det["tooth_id_source"],
            "bbox": det["bbox"],
            "confidence": det["confidence"],
            "cej": lm["cej"],
            "abc": lm["bone_crest"],
            "root_apex": lm["root_apex"],
            "landmark_source": "demo" if not live else lm["landmark_source"],
            "landmark_confidence": lm.get("landmark_confidence"),
            "bone_loss_pct": pct,
            "cej_to_crest_mm": bl.get("cej_to_crest_mm"),
            "stage": stage_for_pct(pct, clinical.get("teeth_lost_perio")),
            "uncertainty": unc,
            "roi": list(roi),
            "roi_attention": attention,
            "flags": {
                "low_confidence": bool(det.get("low_confidence")),
                "low_attention_validity": attention is not None and attention < t_exp["min_roi_attention"],
                "heuristic_landmarks": lm.get("landmark_source") == "heuristic_fallback",
            },
        })

    adversarial = AdversarialInputDetector().detect_adversarial(gray)
    ood = ood_check(gray, len(teeth), adversarial)

    analyses = container.analysis_store()
    visit_date = str(visit_date or dt.date.today().isoformat())[:10]
    prev = analyses.latest_for_patient(patient_doc["patient_id"], before_date=visit_date)
    alignment = _register_with_previous(prev, gray)

    current = {"analysis_id": "pending", "visit_date": visit_date, "teeth": teeth, "image_size": [w, h],
               "alignment": alignment}
    progression = compare_visits(prev, current) if prev else []
    reliable_v = [c["velocity_pct_per_year"] for c in progression
                  if c["reliable"] and c["velocity_pct_per_year"] is not None]

    measured = [t["bone_loss_pct"] for t in teeth if t["bone_loss_pct"] is not None]
    worst = max(teeth, key=lambda t: STAGE_ORDER.get(t["stage"], 0), default=None)
    max_bl = max(measured) if measured else None
    patient_summary = {
        "teeth_detected": len(teeth),
        "mean_bone_loss_pct": round(float(np.mean(measured)), 2) if measured else None,
        "max_bone_loss_pct": max_bl,
        "affected_teeth": sum(1 for v in measured if v > config.THRESHOLDS["staging"]["stage_ii_min_pct"]),
        "stage": worst["stage"] if worst else None,
        "grade": grade_suggestion(max_bl, clinical.get("age"), clinical, max(reliable_v) if reliable_v else None),
        "max_velocity_pct_per_year": max(reliable_v) if reliable_v else None,
    }
    from app.ml.fusion.multimodal_risk import predict_patient_risk
    risk = predict_patient_risk(clinical, patient_summary)
    review = route(teeth, quality, ood, demo_mode=not live)

    blobs = {"radiograph": storage_service.put(png_bytes, "radiograph"),
             "annotated": storage_service.put(overlay.encode_png(overlay.annotated_image(enhanced, teeth)), "annotated")}
    if heatmap is not None:
        blobs["gradcam"] = storage_service.put(overlay.encode_png(overlay.heatmap_layer(heatmap)), "gradcam")

    record = analyses.create({
        "patient_id": patient_doc["patient_id"],
        "pseudo_id": patient_doc["pseudo_id"],
        "visit_date": visit_date,
        "mode": "live" if live else "demo",
        "created_by": user["id"],
        "image_size": [w, h],
        "image_phash": compute_phash(gray),
        "pixel_spacing_mm": pixel_spacing_mm,
        "upload": upload_meta or {},
        "quality": quality,
        "adversarial": adversarial,
        "ood": ood,
        "explainability": {"gradcam_available": heatmap is not None,
                           "method": "Grad-CAM over YOLOv8 neck layers P3-P5" if heatmap is not None else None},
        "teeth": teeth,
        "summary": patient_summary,
        "risk": risk,
        "alignment": alignment,
        "progression": progression,
        "previous_analysis_id": prev["analysis_id"] if prev else None,
        "calibration": {"calibrated": q is not None, "q": q,
                        "coverage": config.THRESHOLDS["uncertainty"]["coverage"]},
        "models": container.registry().status(),
        "review": {"status": review["status"], "label": review["label"], "reasons": review["reasons"],
                   "history": []},
        "blobs": blobs,
    })
    audit().record("PREDICTION", actor=user["id"], resource=patient_doc["pseudo_id"],
                   details={"analysis_id": record["analysis_id"], "mode": record["mode"], "teeth": len(teeth),
                            "review": review["status"]})
    return record
