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
from app.services.progression_service import compare_visits, usable_velocities

logger = logging.getLogger(__name__)
STAGE_ORDER = {"I": 1, "II": 2, "III": 3, "IV": 4}
MIN_PANORAMIC_TEETH = 4   # fewer teeth from the panoramic detector -> try the periapical path


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


def tooth_overlap(prev_teeth: list[dict], curr_teeth: list[dict], matrix) -> float | None:
    """Anatomical check of a registration: map the earlier film's tooth boxes into the current film and
    return the median best IoU with the current teeth. The same mouth gives high overlap; two different
    mouths do not, even when films share imaging-plate scratches or frame marks that fool feature matching."""
    if not prev_teeth or not curr_teeth or matrix is None:
        return None
    from app.ml.landmarks.cej_abc_extractor import _iou

    m = np.asarray(matrix, float)
    best = []
    for t in prev_teeth:
        x1, y1, x2, y2 = t["bbox"]
        corners = np.array([[x1, y1, 1], [x2, y1, 1], [x1, y2, 1], [x2, y2, 1]], float) @ m.T
        box = [corners[:, 0].min(), corners[:, 1].min(), corners[:, 0].max(), corners[:, 1].max()]
        best.append(max(_iou(box, c["bbox"]) for c in curr_teeth))
    return float(np.median(best))


def _register_with_previous(prev: dict | None, gray: np.ndarray, teeth: list[dict] | None = None) -> dict | None:
    """Align the previous visit's radiograph to this one; report how well it worked."""
    if not prev or not prev.get("blobs", {}).get("radiograph"):
        return None
    try:
        prev_gray = _decode(storage_service.get(prev["blobs"]["radiograph"], "radiograph"))
    except Exception as exc:
        return {"confidence": 0.0, "status": "previous image unavailable", "detail": type(exc).__name__}
    return register_images(prev_gray, gray, prev.get("teeth", []), teeth or [])


def register_images(prev_gray: np.ndarray, gray: np.ndarray, prev_teeth: list[dict], teeth: list[dict]) -> dict:
    """Feature registration (ORB + RANSAC + plausibility + NCC) followed by the tooth-overlap check."""
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
              "metal_artifact_detected": bool(info.get("metal_artifact_detected", False)),
              "reason": info.get("reason"),
              "evidence": {k: info.get(k) for k in ("ransac_inliers", "inlier_ratio", "scale", "rotation_deg",
                                                    "ncc_after_warp")}}
    if status == "success":
        # Convert the small-image affine (prev_small -> cur_small) into full-resolution coordinates.
        s_prev = np.diag([1024.0 / pw, 1024.0 / pw, 1.0])
        s_cur_inv = np.diag([1.0 / scale, 1.0 / scale, 1.0])
        m = np.vstack([np.asarray(matrix, float), [0, 0, 1]])
        result["matrix_prev_to_curr"] = (s_cur_inv @ m @ s_prev)[:2].round(6).tolist()
        overlap = tooth_overlap(prev_teeth, teeth, result["matrix_prev_to_curr"])
        result["evidence"]["tooth_overlap"] = None if overlap is None else round(overlap, 3)
        min_overlap = config.THRESHOLDS["progression"].get("min_tooth_overlap", 0.5)
        if overlap is None or overlap < min_overlap:
            # Image features lined up but the teeth do not: not the same anatomy in the same place.
            result.update({"status": "failed", "confidence": 0.0,
                           "reason": "teeth do not line up after registration" if overlap is not None
                           else "no teeth to check the registration against"})
            result.pop("matrix_prev_to_curr")
    return result


def demo_landmarks(gray: np.ndarray, det: dict) -> dict:
    """DEMO ONLY: geometric CEJ/apex plus an image-based crest estimate (see app/ml/synthetic.py)."""
    from app.ml.synthetic import demo_crest_y

    lm = heuristic_landmarks(det["bbox"])
    crest = demo_crest_y(gray, det["bbox"], lm["cej"][1])
    if crest is None:  # no crest found in the image: nothing was measured, so report nothing
        return {**lm, "landmark_source": "demo_unmeasured"}
    lm["bone_crest"] = [lm["cej"][0], round(crest, 1)]
    lm["landmark_source"] = "demo"
    return lm


def locate_teeth(gray: np.ndarray, force_demo: bool = False) -> dict:
    """Detect teeth and their CEJ / apex / crest landmarks: the same path for the app and for evaluation.

    Returns {live, image_type, detections, landmarks, explain_model}. `explain_model` is the model whose
    predictions produced the boxes, so Grad-CAM explains the model that actually made the detection.
    """
    enhanced = apply_clahe(gray)
    bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)  # models were trained on unenhanced radiographs
    detector = lm_model = None
    if not force_demo:
        detector, lm_model = container.tooth_detector(), container.landmark_detector()
    live = detector is not None and detector.available
    detections = detector.detect_teeth(bgr) if live else demo_detections(enhanced)
    image_type = "panoramic"
    landmarks = None
    explain_model, explain_name = (detector, "tooth detector") if live else (None, None)
    if live and lm_model.available and len(detections) < MIN_PANORAMIC_TEETH:
        # A periapical film: the panoramic detector sees too little, so the keypoint model
        # (trained on periapical films) finds the teeth and their landmarks itself.
        periapical = lm_model.detect_teeth(bgr)
        if len(periapical) > len(detections):
            image_type = "periapical"
            detections = [d for d, _ in periapical]
            landmarks = {d["tooth_id"]: lm for d, lm in periapical}
            explain_model, explain_name = lm_model, "landmark (pose) model"
    if landmarks is None:
        landmarks = lm_model.detect_landmarks(detections, bgr) if (live and lm_model.available) \
            else {d["tooth_id"]: demo_landmarks(gray, d) for d in detections}
    return {"live": live, "image_type": image_type, "detections": detections, "landmarks": landmarks,
            "explain_model": explain_model, "explain_model_name": explain_name, "enhanced": enhanced, "bgr": bgr}


def measured(lm: dict | None) -> bool:
    """True only for landmarks that came from a model (or, in demo mode, from the image itself).

    The geometric fallback places CEJ and crest at fixed fractions of the box, which always gives
    the same ~17 % "bone loss" whatever the image shows, so it never produces a measurement.
    """
    return bool(lm) and lm.get("landmark_source") not in ("heuristic_fallback", "demo_unmeasured")


def run_analysis(png_bytes: bytes, patient_doc: dict, user: dict, visit_date: str | None = None,
                 pixel_spacing_mm: float | None = None, upload_meta: dict | None = None,
                 force_demo: bool = False, source: str = "uploaded_radiograph") -> dict:
    gray = _decode(png_bytes)
    h, w = gray.shape
    quality = assess_quality(gray)
    if quality["verdict"] == "reject":
        audit().record("ANALYSIS_REJECTED_QUALITY", outcome="rejected", actor=user["id"],
                       resource=patient_doc["pseudo_id"], details={"reasons": [r["message"] for r in quality["reasons"]]})
        raise QualityRejected(quality)

    found = locate_teeth(gray, force_demo)
    live, image_type, detections, landmarks = found["live"], found["image_type"], found["detections"], found["landmarks"]
    if live and not detections:
        # Neither the panoramic detector nor the periapical keypoint model found a single tooth:
        # this is not a dental radiograph we can analyse, so nothing is stored or reported.
        quality = {**quality, "verdict": "reject", "reasons": quality["reasons"] + [
            {"level": "reject", "message": "No teeth were found. Upload a dental panoramic or periapical radiograph."}]}
        audit().record("ANALYSIS_REJECTED_QUALITY", outcome="rejected", actor=user["id"],
                       resource=patient_doc["pseudo_id"], details={"reasons": ["no teeth found"]})
        raise QualityRejected(quality)
    enhanced, bgr = found["enhanced"], found["bgr"]
    heatmap = found["explain_model"].gradcam_heatmap(bgr, detections) if found["explain_model"] else None

    q = calibration.current_q()
    t_exp = config.THRESHOLDS["explainability"]
    clinical = container.patient_manager().clinical_profile(patient_doc)
    teeth = []
    # Landmarks are only trusted on the film type they were validated on (calibration file "image_type").
    # On BRAR's 988 expert-graded panoramic films the per-tooth readings disagreed widely with the experts
    # (docs/evidence/brar_panoramic_eval_*.json), so other film types get detection and numbering only.
    validated_type = (calibration.load() or {}).get("image_type")
    measure_this_type = (not live or validated_type is None or image_type == validated_type
                         or config.THRESHOLDS["landmarks"].get("measure_unvalidated_image_types", False))
    for det in detections:
        lm = landmarks.get(det["tooth_id"])
        if measured(lm) and not measure_this_type:
            bl, roi, attention = {"bone_loss_pct": None, "status": f"not_validated_on_{image_type}"}, None, None
            lm, lm_source = {}, f"not_validated_on_{image_type}"
        elif measured(lm):
            bl = bone_loss_for_tooth(lm, pixel_spacing_mm)
            roi = periodontal_roi(det["bbox"], lm["cej"], lm["bone_crest"], t_exp["roi_margin_fraction"])
            attention = roi_attention(heatmap, det["bbox"], roi)
            lm_source = "demo" if not live else lm["landmark_source"]
        else:
            # No model landmarks for this tooth: report it as found but NOT measured, never as a number.
            bl, roi, attention = {"bone_loss_pct": None, "status": "not_measured"}, None, None
            lm, lm_source = {}, "not_measured"
        pct = bl.get("bone_loss_pct")
        teeth.append({
            "tooth_id": det["tooth_id"],
            "tooth_id_source": det["tooth_id_source"],
            "bbox": det["bbox"],
            "confidence": det["confidence"],
            "cej": lm.get("cej"),
            "abc": lm.get("bone_crest"),
            "root_apex": lm.get("root_apex"),
            "landmark_source": lm_source,
            "landmark_confidence": lm.get("landmark_confidence"),
            "tta_disagreement_pct": lm.get("tta_disagreement_pct"),
            "measurement_status": bl.get("status"),
            "bone_loss_pct": pct,
            "cej_to_crest_mm": bl.get("cej_to_crest_mm"),
            "stage": stage_for_pct(pct, clinical.get("teeth_lost_perio")),
            "uncertainty": predict_interval(pct, q, calibration.scale_for(lm) if pct is not None else 1.0),
            "roi": list(roi) if roi else None,
            "roi_attention": attention,
            "flags": {
                "low_confidence": bool(det.get("low_confidence")),
                "low_attention_validity": attention is not None and attention < t_exp["min_roi_attention"],
                "not_measured": pct is None,
            },
        })

    adversarial = AdversarialInputDetector().detect_adversarial(gray)
    ood = ood_check(gray, len(teeth), adversarial)

    analyses = container.analysis_store()
    visit_date = str(visit_date or dt.date.today().isoformat())[:10]
    prev = analyses.latest_for_patient(patient_doc["patient_id"], before_date=visit_date)
    alignment = _register_with_previous(prev, gray, teeth)

    current = {"analysis_id": "pending", "visit_date": visit_date, "teeth": teeth, "image_size": [w, h],
               "alignment": alignment, "mode": "live" if live else "demo", "image_type": image_type}
    progression = compare_visits(prev, current) if prev else []
    reliable_v = usable_velocities(progression)

    measured_pct = [t["bone_loss_pct"] for t in teeth if t["bone_loss_pct"] is not None]
    worst = max(teeth, key=lambda t: STAGE_ORDER.get(t["stage"], 0), default=None)
    max_bl = max(measured_pct) if measured_pct else None
    patient_summary = {
        "teeth_detected": len(teeth),
        "teeth_measured": len(measured_pct),
        "mean_bone_loss_pct": round(float(np.mean(measured_pct)), 2) if measured_pct else None,
        "max_bone_loss_pct": max_bl,
        "affected_teeth": sum(1 for v in measured_pct if v > config.THRESHOLDS["staging"]["stage_ii_min_pct"]),
        "stage": worst["stage"] if worst else None,
        "grade": grade_suggestion(max_bl, clinical.get("age"), clinical, max(reliable_v) if reliable_v else None),
        "max_velocity_pct_per_year": max(reliable_v) if reliable_v else None,
    }
    from app.ml.fusion.multimodal_risk import predict_patient_risk
    risk = predict_patient_risk(clinical, patient_summary)
    cal_info = calibration.load() or {}
    review = route(teeth, quality, ood, demo_mode=not live, image_type=image_type,
                   validated_image_type=cal_info.get("image_type"))

    blobs = {"radiograph": storage_service.put(png_bytes, "radiograph"),
             "annotated": storage_service.put(overlay.encode_png(overlay.annotated_image(enhanced, teeth)), "annotated")}
    if heatmap is not None:
        blobs["gradcam"] = storage_service.put(overlay.encode_png(overlay.heatmap_layer(heatmap)), "gradcam")

    record = analyses.create({
        "patient_id": patient_doc["patient_id"],
        "pseudo_id": patient_doc["pseudo_id"],
        "visit_date": visit_date,
        "mode": "live" if live else "demo",
        # Where the image came from. The demo seeder passes "synthetic_demo"; a live-mode record must never carry it.
        "source": source,
        "created_by": user["id"],
        "image_size": [w, h],
        "image_type": image_type,
        "image_phash": compute_phash(gray),
        "pixel_spacing_mm": pixel_spacing_mm,
        "upload": upload_meta or {},
        "quality": quality,
        "adversarial": adversarial,
        "ood": ood,
        "explainability": {"gradcam_available": heatmap is not None,
                           "model": found["explain_model_name"] if heatmap is not None else None,
                           "method": "Grad-CAM over the YOLO neck layers feeding the detection head (P3-P5)" if heatmap is not None else None},
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
