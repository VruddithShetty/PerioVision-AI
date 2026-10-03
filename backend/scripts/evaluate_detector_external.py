"""External test of the tooth detector (FDI numbering) on panoramic films from another hospital.

Ground truth: LabelMe JSON polygons, one per tooth, FDI number in `group_id` (format of the Aga Khan
University OPG dataset, Zenodo 10.5281/zenodo.10538750, CC BY 4.0). Polygons cover crown AND root.

Reports, at IoU >= 0.5:
  * tooth detection recall / precision (any number)
  * numbering accuracy of the detected teeth (predicted FDI == true FDI)
  * tooth-level F1 with the right number (the app's real behaviour)

Usage (from backend/):
    python scripts/evaluate_detector_external.py --data ~/Downloads/OPG-AKU/Niihhaa-Dataset-4ac91db/dataset \\
        --out ../docs/evidence/detector_external_aku.json
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))  # backend/

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from app.ml.landmarks.cej_abc_extractor import _iou  # noqa: E402
from app.services import container  # noqa: E402

FDI = {f"{q}{n}" for q in (1, 2, 3, 4) for n in range(1, 9)}


def ground_truth(path: str) -> list[dict]:
    teeth = []
    for s in json.load(open(path, encoding="utf-8"))["shapes"]:
        fdi = str(s.get("group_id"))
        if fdi not in FDI or s.get("shape_type") != "polygon":
            continue
        p = np.asarray(s["points"], float)
        teeth.append({"fdi": fdi, "bbox": [p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()], "poly": p})
    return teeth


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    det = container.tooth_detector()
    if not det.available:
        print("ERROR: tooth detector not available")
        return 2
    tp = fp = fn = right = 0
    for n, ann in enumerate(sorted(glob.glob(os.path.join(os.path.expanduser(args.data), "*", "annotations", "*.json"))), 1):
        stem = os.path.splitext(os.path.basename(ann))[0]
        imgs = glob.glob(os.path.join(os.path.dirname(ann), "..", "OPGs", stem + ".*"))
        img = cv2.imread(imgs[0]) if imgs else None
        if img is None:
            continue
        gt = ground_truth(ann)
        pred = det.detect_teeth(img)
        used = set()
        for g in gt:
            best = max(((i, _iou(g["bbox"], p["bbox"])) for i, p in enumerate(pred) if i not in used),
                       key=lambda x: x[1], default=(None, 0.0))
            if best[0] is None or best[1] < 0.5:
                fn += 1
                continue
            used.add(best[0])
            tp += 1
            right += pred[best[0]]["tooth_id"] == g["fdi"]
        fp += len(pred) - len(used)
        if n % 20 == 0:
            print(f"[{n}] tp {tp} fp {fp} fn {fn}", flush=True)
    out = {
        "dataset": "Aga Khan University OPG teeth segmentation & numbering (Zenodo 10538750, CC BY 4.0)",
        "teeth_ground_truth": tp + fn, "detected_iou50": tp,
        "detection_recall": round(tp / (tp + fn), 4), "detection_precision": round(tp / (tp + fp), 4),
        "numbering_accuracy_of_detected": round(right / tp, 4) if tp else None,
        "tooth_level_F1_with_correct_number": round(2 * right / (2 * right + (tp - right) * 2 + fp + fn), 4),
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
