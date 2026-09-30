"""Decides whether an analysis may be used directly or needs mandatory clinician review.

A case becomes "Mandatory clinician review" if ANY of these hold:
  * any tooth's conformal stage set has more than one stage, or uncertainty is uncalibrated
  * the image-quality gate returned a warning
  * the image looks out-of-distribution or adversarially perturbed
  * any tooth's Grad-CAM attention falls outside the periodontal region
  * any tooth used heuristic landmarks or had a low-confidence detection
  * the landmark model was validated on a different radiograph type (e.g. periapical vs panoramic)
  * the pipeline ran in demo mode (no verified model)
Such a case cannot become a final signed report until a dentist signs off.
"""
from __future__ import annotations


def route(teeth: list[dict], quality: dict, ood: dict, demo_mode: bool,
          image_type: str | None = None, validated_image_type: str | None = None) -> dict:
    reasons: list[dict] = []

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
    heuristic = [t["tooth_id"] for t in teeth if t.get("landmark_source") == "heuristic_fallback"]
    if heuristic:
        add("heuristic_landmarks", "Landmarks were estimated geometrically, not by the keypoint model.", heuristic)
    model_lms = [t["tooth_id"] for t in teeth if str(t.get("landmark_source", "")).startswith("keypoint_model")]
    if model_lms and validated_image_type and image_type and image_type != validated_image_type:
        add("landmarks_not_validated", f"The landmark model was validated on {validated_image_type} radiographs, "
            f"not {image_type} ones, so its accuracy on this image is unmeasured.", model_lms)
    low_conf = [t["tooth_id"] for t in teeth if t.get("flags", {}).get("low_confidence")]
    if low_conf:
        add("low_confidence", "Low detection confidence.", low_conf)

    needs_review = bool(reasons)
    return {
        "status": "review_required" if needs_review else "auto_cleared",
        "label": "Mandatory clinician review" if needs_review else "No automatic flags",
        "reasons": reasons,
    }
