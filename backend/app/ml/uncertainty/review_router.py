"""Decides whether an analysis may be used directly or needs mandatory clinician review.

A case becomes "Mandatory clinician review" if ANY of these hold:
  * any tooth's conformal stage set has more than one stage, or uncertainty is uncalibrated
  * the image-quality gate returned a warning
  * the image looks out-of-distribution or adversarially perturbed
  * any tooth's Grad-CAM attention falls outside the periodontal region
  * any tooth could not be measured (no model landmarks) or had a low-confidence detection
  * the landmark model was validated on a different radiograph type (e.g. periapical vs panoramic)
  * the whole-film panoramic estimate's conformal interval allows more than one stage, or its
    90 % interval is missing (the uncertainty system itself flags panoramic films, not only the film-type rule)
  * the pipeline ran in demo mode (no verified model)
Such a case cannot become a final signed report until a dentist signs off.
"""
from __future__ import annotations


def route(teeth: list[dict], quality: dict, ood: dict, demo_mode: bool,
          image_type: str | None = None, validated_image_type: str | None = None,
          panoramic_assessment: dict | None = None, extra_reasons: list[dict] | None = None) -> dict:
    reasons: list[dict] = list(extra_reasons or [])

    def add(code: str, message: str, teeth_ids=None):
        item = {"code": code, "message": message}
        if teeth_ids:
            item["teeth"] = teeth_ids
        reasons.append(item)

    if demo_mode:
        add("demo_mode", "No verified model was available; results are demo placeholders.")
    uncal = [t["tooth_id"] for t in teeth if not t.get("uncertainty", {}).get("calibrated", False)]
    if uncal:
        add("uncalibrated", "Uncertainty is not calibrated for this model yet.", uncal)
    ambiguous = [t["tooth_id"] for t in teeth
                 if t.get("uncertainty", {}).get("calibrated") and t["uncertainty"].get("set_size", 0) > 1]
    if ambiguous:
        add("ambiguous_stage", "More than one stage is plausible at the chosen coverage.", ambiguous)
    if quality.get("verdict") == "warn":
        add("low_quality", "Image quality is borderline: "
            + "; ".join(r["message"] for r in quality.get("reasons", [])))
    if ood.get("is_ood"):
        add("out_of_distribution", "; ".join(ood["reasons"]))
    attention = [t["tooth_id"] for t in teeth if t.get("flags", {}).get("low_attention_validity")]
    if attention:
        add("low_attention_validity", "Model attention fell outside the periodontal region.", attention)
    unvalidated = [t["tooth_id"] for t in teeth if str(t.get("measurement_status", "")).startswith("not_validated_on_")]
    if unvalidated:
        add("not_validated_image_type", f"Bone loss is not measured on {image_type} radiographs: the landmark model "
            "is only validated on periapical films. Take a periapical film of the teeth of interest to measure them.",
            unvalidated)
    unmeasured = [t["tooth_id"] for t in teeth if t.get("bone_loss_pct") is None and t["tooth_id"] not in unvalidated]
    if unmeasured:
        add("not_measured", "The landmark model could not place CEJ / crest / apex on these teeth, "
            "so no bone loss is reported for them; a clinician must assess them.", unmeasured)
    model_lms = [t["tooth_id"] for t in teeth if str(t.get("landmark_source", "")).startswith("keypoint_model")]
    if model_lms and image_type and validated_image_type is None:
        add("landmarks_not_validated", "The landmark model has no validation record (no calibration file), "
            "so the accuracy of its landmarks is unmeasured.", model_lms)
    elif model_lms and validated_image_type and image_type and image_type != validated_image_type:
        add("landmarks_not_validated", f"The landmark model was validated on {validated_image_type} radiographs, "
            f"not {image_type} ones, so its accuracy on this image is unmeasured.", model_lms)
    worst = (panoramic_assessment or {}).get("worst_tooth")
    if panoramic_assessment is not None and worst is None:
        add("panoramic_estimate_unavailable", "The whole-film worst-tooth model is not installed, so this "
            "panoramic film has no calibrated bone-loss estimate.")
    elif worst is not None and len(worst.get("stage_set") or []) != 1:
        lo, hi = worst["interval_90"]
        add("panoramic_stage_ambiguous", f"Whole-film estimate: the 90 % interval ({lo:.0f}-{hi:.0f} % bone loss) "
            f"allows stages {' / '.join(worst['stage_set'])}, so the stage cannot be decided from this film.")
    low_conf = [t["tooth_id"] for t in teeth if t.get("flags", {}).get("low_confidence")]
    if low_conf:
        add("low_confidence", "Low detection confidence.", low_conf)

    needs_review = bool(reasons)
    return {
        "status": "review_required" if needs_review else "auto_cleared",
        "label": "Mandatory clinician review" if needs_review else "No automatic flags",
        "reasons": reasons,
    }
