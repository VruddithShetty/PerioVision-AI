"""Validate visit-to-visit registration on REAL radiograph pairs.

Input: a CSV with columns  image_a, image_b, same_patient  (1 = the same patient's films taken at different
visits, 0 = films of two different patients), paths relative to the CSV. The script runs the exact
registration the app uses (analysis_service.register_images: features, RANSAC, plausibility, image
correlation, then the tooth-overlap check with the app's own tooth detections) and reports:
  * acceptance rate on same-patient pairs     (should be high: comparable follow-ups get compared)
  * false-acceptance rate on different-patient pairs (must be ~0: unrelated films are never compared)
  * the evidence (inliers, inlier ratio, scale, rotation, NCC) per pair, to re-tune the thresholds in
    app/ml/preprocessing/alignment.py if needed.

Usage (from backend/):
    python scripts/evaluate_registration.py --pairs pairs.csv --out ../docs/evidence/registration_eval.json
If no different-patient pairs are listed, --make-negatives N pairs random films of different patients.
Where to get same-patient pairs: a partner clinic (de-identified) or PhysioNet "Multimodal dental dataset"
(registration + data use agreement; non-commercial).
"""
import argparse
import csv
import json
import os
import random
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))  # backend/

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from app.services.analysis_service import locate_teeth, register_images  # noqa: E402


_teeth_cache: dict = {}


def teeth_of(path: str, gray: np.ndarray) -> list[dict]:
    if path not in _teeth_cache:
        _teeth_cache[path] = locate_teeth(gray)["detections"]
    return _teeth_cache[path]


def register(a: np.ndarray, b: np.ndarray, pa: str, pb: str) -> dict:
    """Exactly the app's registration (analysis_service.register_images), a = earlier film, b = later film."""
    return register_images(a, b, teeth_of(pa, a), teeth_of(pb, b))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--make-negatives", type=int, default=0)
    args = ap.parse_args()
    base = os.path.dirname(os.path.abspath(args.pairs))
    with open(args.pairs, newline="", encoding="utf-8") as f:
        pairs = [(r["image_a"], r["image_b"], int(r["same_patient"])) for r in csv.DictReader(f)]
    if args.make_negatives:
        imgs = sorted({p for a, b, _ in pairs for p in (a, b)})
        owner = {p: i for i, (a, b, s) in enumerate(pairs) if s == 1 for p in (a, b)}
        rng = random.Random(0)  # audit-ok: seeded choice of negative pairs
        while sum(1 for *_, s in pairs if s == 0) < args.make_negatives and len(imgs) > 2:
            a, b = rng.sample(imgs, 2)
            if owner.get(a) != owner.get(b) or a not in owner:
                pairs.append((a, b, 0))
    results = []
    for a, b, same in pairs:
        ia = cv2.imread(os.path.join(base, a), cv2.IMREAD_GRAYSCALE)
        ib = cv2.imread(os.path.join(base, b), cv2.IMREAD_GRAYSCALE)
        if ia is None or ib is None:
            print(f"skipped (unreadable): {a} / {b}")
            continue
        info = register(ia.reshape(ia.shape[:2]), ib.reshape(ib.shape[:2]), a, b)
        results.append({"image_a": a, "image_b": b, "same_patient": same, **info})
    pos = [r for r in results if r["same_patient"] == 1]
    neg = [r for r in results if r["same_patient"] == 0]
    rate = lambda rows: round(sum(r["status"] == "success" for r in rows) / len(rows), 4) if rows else None  # noqa: E731
    summary = {"same_patient_pairs": len(pos), "acceptance_rate_same_patient": rate(pos),
               "different_patient_pairs": len(neg), "false_acceptance_rate_different_patients": rate(neg),
               "pairs": results}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print({k: v for k, v in summary.items() if k != "pairs"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
