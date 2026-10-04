"""Re-measure the live pipeline's bone-loss accuracy and conformal coverage on a labelled split.

Runs the SAME code path as the app (analysis_service.locate_teeth: panoramic detector, then the
periapical keypoint path, the same "measured" rule) on every image, matches each labelled tooth to
a predicted one (box IoU >= 0.5), and compares bone loss computed from predicted vs labelled
CEJ / apex / crest keypoints. Nothing is written to the weights folder; results go to --out.

Use it to check the numbers in weights/*_metrics.json and on the Model Trust page instead of
trusting them. The calibration q comes from weights/conformal_calibration.json, so run this on a
split that was NOT used to compute q (for DenPAR, q came from the validation split; use test).

Usage (from backend/):
    python scripts/evaluate_landmarks.py --images <pose>/images/test --labels <pose>/labels/test --out eval.json
    add --per-tooth-csv teeth.csv to keep one row per labelled tooth (needed for confidence intervals,
    confusion matrices and error analysis: python -m research.compute_ci).
Label format per line: class cx cy w h  cej_x cej_y v  apex_x apex_y v  crest_x crest_y v (normalised).
"""
import argparse
import csv
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))  # backend/

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from app import config  # noqa: E402
from app.ml.landmarks.cej_abc_extractor import _iou  # noqa: E402
from app.ml.measurement.bone_loss import bone_loss_for_tooth  # noqa: E402
from app.ml.measurement.staging import stage_for_pct  # noqa: E402
from app.ml.uncertainty import calibration  # noqa: E402
from app.ml.uncertainty.conformal import predict_interval  # noqa: E402
from app.services.analysis_service import locate_teeth, measured  # noqa: E402

KEYS = ("cej", "root_apex", "bone_crest")


def read_labels(path, w, h):
    teeth = []
    for line in open(path, encoding="utf-8"):
        p = line.split()
        if len(p) < 14:
            continue
        cx, cy, bw, bh = float(p[1]) * w, float(p[2]) * h, float(p[3]) * w, float(p[4]) * h
        kp = [(float(p[5 + 3 * i]) * w, float(p[6 + 3 * i]) * h, float(p[7 + 3 * i])) for i in range(3)]
        if min(k[2] for k in kp) <= 0:  # a keypoint is missing: no reference bone loss for this tooth
            continue
        teeth.append({"bbox": [cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2],
                      **{name: [k[0], k[1]] for name, k in zip(KEYS, kp)}})
    return teeth


def _half_cov(rows, harder: bool):
    if not rows:
        return None
    med = float(np.median([r["half_width"] for r in rows]))
    part = [r for r in rows if (r["half_width"] > med) == harder]
    return round(float(np.mean([r["covered"] for r in part])), 4) if part else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--per-tooth-csv", help="write one row per labelled tooth (found or missed) to this CSV")
    ap.add_argument("--metrics-out", help="also write the result as the deployed-pipeline metrics file "
                                          "(e.g. weights/pipeline_test_metrics.json) shown on the About page")
    args = ap.parse_args()

    q = calibration.current_q()
    files = sorted(glob.glob(os.path.join(args.images, "*.jpg")) + glob.glob(os.path.join(args.images, "*.png")))
    files = files[:args.limit] if args.limit else files
    labelled = found = 0
    rows, kp_err, types, t0 = [], {k: [] for k in KEYS}, {}, time.time()
    per_tooth = []
    for n, img_path in enumerate(files, 1):
        label = os.path.join(args.labels, os.path.splitext(os.path.basename(img_path))[0] + ".txt")
        gray = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
        if gray is None or not os.path.exists(label):
            continue
        gray = gray.reshape(gray.shape[:2])  # some JPEGs decode as (h, w, 1)
        h, w = gray.shape
        truth = read_labels(label, w, h)
        res = locate_teeth(gray)
        if not res["live"]:
            print("ERROR: no verified model loaded; this script only evaluates live models.")
            return 2
        types[res["image_type"]] = types.get(res["image_type"], 0) + 1
        dets, lms, used = res["detections"], res["landmarks"], set()
        labelled += len(truth)
        for t_idx, ref in enumerate(truth):
            best = max(((i, _iou(d["bbox"], ref["bbox"])) for i, d in enumerate(dets) if i not in used),
                       key=lambda x: x[1], default=(None, 0.0))
            ref_pct = bone_loss_for_tooth(ref)["bone_loss_pct"]
            base = {"image": os.path.basename(img_path), "tooth_index": t_idx, "image_type": res["image_type"],
                    "image_w": w, "image_h": h, "ref_pct": ref_pct, "iou": round(best[1], 4)}
            if best[0] is None or best[1] < 0.5:
                per_tooth.append({**base, "status": "missed"})
                continue
            used.add(best[0])
            found += 1
            lm = lms.get(dets[best[0]]["tooth_id"])
            if not measured(lm):
                rows.append({"measured": False})
                per_tooth.append({**base, "status": "not_measured", "tooth_id": dets[best[0]].get("tooth_id")})
                continue
            p = bone_loss_for_tooth(lm)["bone_loss_pct"]
            r = bone_loss_for_tooth(ref)["bone_loss_pct"]
            if p is None or r is None:
                continue
            root = float(np.linalg.norm(np.subtract(ref["root_apex"], ref["cej"])))
            kp_row = {}
            for k in KEYS:
                kp_err[k].append(100.0 * float(np.linalg.norm(np.subtract(lm[k], ref[k]))) / max(root, 1e-6))
                kp_row[f"{k}_err_pct_root"] = round(kp_err[k][-1], 3)
                kp_row[f"{k}_dx_px"] = round(float(lm[k][0] - ref[k][0]), 2)
                kp_row[f"{k}_dy_px"] = round(float(lm[k][1] - ref[k][1]), 2)
            unc = predict_interval(p, q, calibration.scale_for(lm))
            per_tooth.append({**base, "status": "measured", "tooth_id": dets[best[0]].get("tooth_id"),
                              "pred_pct": round(p, 3), "abs_err": round(abs(p - ref_pct), 3),
                              "ref_stage": stage_for_pct(ref_pct), "pred_stage": stage_for_pct(p),
                              "root_length_px": round(root, 2), "det_confidence": dets[best[0]].get("confidence"),
                              "kpt_conf_min": min((lm.get("keypoint_confidences") or {"_": None}).values(), key=lambda v: v or 0),
                              "landmark_confidence": lm.get("landmark_confidence"),
                              "tta_disagreement_pct": lm.get("tta_disagreement_pct"),
                              "half_width": unc["half_width"], "set_size": unc["set_size"],
                              "stage_set": "|".join(unc["stage_set"]),
                              "covered": None if q is None else abs(p - ref_pct) <= unc["half_width"], **kp_row})
            rows.append({"measured": True, "pred": p, "ref": r, "err": abs(p - r),
                         "stage_ok": stage_for_pct(p) == stage_for_pct(r),
                         "half_width": unc["half_width"], "disagreement": lm.get("tta_disagreement_pct"),
                         "covered": None if q is None else abs(p - r) <= unc["half_width"],
                         "set_size": unc["set_size"], "ref_stage_in_set": stage_for_pct(r) in unc["stage_set"]})
        if n % 20 == 0 or n == len(files):
            print(f"[{n}/{len(files)}] {found} teeth matched, {time.time() - t0:.0f}s")

    m = [r for r in rows if r["measured"]]
    err = np.array([r["err"] for r in m]) if m else np.array([])
    out = {
        "images": len(files), "image_types_detected": types,
        "teeth_labelled_with_all_keypoints": labelled, "teeth_matched_iou50": found,
        "tooth_recall": round(found / labelled, 4) if labelled else None,
        "teeth_measured": len(m), "teeth_not_measured": sum(1 for r in rows if not r["measured"]),
        "bone_loss_MAE_pct_points": round(float(err.mean()), 3) if len(err) else None,
        "bone_loss_median_abs_error": round(float(np.median(err)), 3) if len(err) else None,
        "within_5_points": round(float((err <= 5).mean()), 4) if len(err) else None,
        "within_10_points": round(float((err <= 10).mean()), 4) if len(err) else None,
        "stage_agreement": round(float(np.mean([r["stage_ok"] for r in m])), 4) if m else None,
        "landmark_error_pct_of_root_length_mean": {k: round(float(np.mean(v)), 2) for k, v in kp_err.items() if v},
        "conformal": None if q is None else {
            "target_coverage": config.THRESHOLDS["uncertainty"]["coverage"], "q": round(q, 3),
            "empirical_interval_coverage": round(float(np.mean([r["covered"] for r in m])), 4) if m else None,
            "reference_stage_in_prediction_set": round(float(np.mean([r["ref_stage_in_set"] for r in m])), 4) if m else None,
            "set_size_counts": {str(s): sum(1 for r in m if r["set_size"] == s) for s in (1, 2, 3)},
            "adaptive": bool((calibration.load() or {}).get("sigma")),
            "mean_half_width_pct": round(float(np.mean([r["half_width"] for r in m])), 3) if m else None,
            # coverage separately for the easier and harder half of teeth (by interval width)
            "coverage_easier_half": _half_cov(m, False), "coverage_harder_half": _half_cov(m, True),
        },
        "calibration_file_source": (calibration.load() or {}).get("source"),
    }
    if args.per_tooth_csv and per_tooth:
        cols = sorted({k for r in per_tooth for k in r}, key=lambda k: (k not in per_tooth[-1], k))
        with open(args.per_tooth_csv, "w", newline="", encoding="utf-8") as f:
            wr = csv.DictWriter(f, fieldnames=cols)
            wr.writeheader()
            wr.writerows(per_tooth)
    for path in filter(None, (args.out, args.metrics_out)):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
