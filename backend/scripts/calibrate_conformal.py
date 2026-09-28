"""Split-conformal calibration of per-tooth bone-loss % on a labelled held-out set.

For every image in the calibration split it runs the SAME detector + landmark
pipeline as the app, computes each tooth's predicted bone loss, matches it to the
labelled tooth (box IoU >= 0.3), computes the reference bone loss from the
labelled CEJ / apex / crest keypoints, and stores |predicted - reference|.
Half of the scores set the conformal threshold, the other half measure the
coverage actually achieved; both go into weights/conformal_calibration.json.

Usage (from backend/), pointing at a YOLO-pose dataset split:
    python scripts/calibrate_conformal.py --images <dataset>/pose/images/valid --labels <dataset>/pose/labels/valid
Label format per line: class cx cy w h  cej_x cej_y v  apex_x apex_y v  crest_x crest_y v (normalised).
IMPORTANT: coverage is only as meaningful as the labels. Write down where they came from with --source.
"""
import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))  # backend/

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from app.ml.landmarks.cej_abc_extractor import _iou  # noqa: E402
from app.ml.measurement.bone_loss import bone_loss_for_tooth  # noqa: E402
from app.ml.uncertainty import calibration  # noqa: E402
from app.services import container  # noqa: E402


def read_labels(path, w, h):
    teeth = []
    for line in open(path, encoding="utf-8"):
        p = line.split()
        if len(p) < 14:
            continue
        cx, cy, bw, bh = float(p[1]) * w, float(p[2]) * h, float(p[3]) * w, float(p[4]) * h
        kp = [(float(p[5 + 3 * i]) * w, float(p[6 + 3 * i]) * h) for i in range(3)]
        teeth.append({"bbox": [cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2],
                      "cej": kp[0], "root_apex": kp[1], "bone_crest": kp[2]})
    return teeth


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--source", default="YOLO-pose validation split (see docs/DATASETS.md)")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    detector, landmarks = container.tooth_detector(), container.landmark_detector()
    if not detector.available:
        print("ERROR: the tooth detector is not available (missing or unsigned weights). Run scripts/sign_model.py.")
        return 2
    files = sorted(glob.glob(os.path.join(args.images, "*.jpg")) + glob.glob(os.path.join(args.images, "*.png")))
    if args.limit:
        files = files[:args.limit]
    scores, preds, refs = [], [], []
    for n, img_path in enumerate(files, 1):
        label = os.path.join(args.labels, os.path.splitext(os.path.basename(img_path))[0] + ".txt")
        img = cv2.imread(img_path)
        if img is None or not os.path.exists(label):
            continue
        h, w = img.shape[:2]
        truth = read_labels(label, w, h)
        dets = detector.detect_teeth(img)
        lms = landmarks.detect_landmarks(dets, img) if landmarks.available else {}
        for d in dets:
            best = max(truth, key=lambda t: _iou(d["bbox"], t["bbox"]), default=None)
            if best is None or _iou(d["bbox"], best["bbox"]) < 0.3 or d["tooth_id"] not in lms:
                continue
            p = bone_loss_for_tooth(lms[d["tooth_id"]])["bone_loss_pct"]
            r = bone_loss_for_tooth(best)["bone_loss_pct"]
            if p is None or r is None:
                continue
            preds.append(p)
            refs.append(r)
            scores.append(abs(p - r))
        print(f"[{n}/{len(files)}] {os.path.basename(img_path)}: {len(scores)} matched teeth so far")
    if len(scores) < 20:
        print(f"ERROR: only {len(scores)} matched teeth; need at least 20 for a meaningful calibration.")
        return 1
    data = calibration.save(scores, preds, refs, source=args.source,
                            notes=f"{len(files)} images from {args.images}")
    print(f"Saved {len(scores)} scores. Mean absolute error {data['mean_absolute_error_pct']} percentage points.")
    for cov, lvl in data["levels"].items():
        print(f"  target {cov}: q = {lvl['q_from_half']}  coverage on the other half = {lvl['empirical_coverage_other_half']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
