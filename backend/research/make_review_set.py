"""Build a review pack for a dentist: tooth images plus a form, in the format research.agreement reads.

Two modes:
  label-check  Shows the REFERENCE CEJ (blue), crest (orange) and apex (green) points that the converted DenPAR labels
               use. The dentist marks whether the points are right and, if not, gives their own bone loss % or stage.
               This measures how good the "ground truth" is.
  blind        Plain tooth crop with only a box around the tooth, no points and no numbers. The dentist grades bone
               loss % (or stage). Two dentists grading the same pack independently give the human-vs-human agreement
               the model is compared against.

Teeth are sampled stratified by reference stage (equal numbers of I / II / III when available), fixed seed, from a
per-tooth CSV written by scripts/evaluate_landmarks.py --per-tooth-csv. The model's predictions go into a separate
file (answers_do_not_share.csv) so the pack stays blind.

Usage (from backend/):
    python -m research.make_review_set --per-tooth ../docs/evidence/predictions/denpar_test_per_tooth.csv \
        --images ~/Downloads/DenPAR/pose_dataset/images/test --labels ~/Downloads/DenPAR/pose_dataset/labels/test \
        --mode blind --n 60 --out ../review/blind_pack
Then give the dentist the pack folder; each fills review_form.csv (keep a copy per dentist, set the `rater` column).
Combine the filled forms with answers_do_not_share.csv and run python -m research.agreement.
"""
from __future__ import annotations

import argparse
import csv
import os
import random
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))  # backend/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import cv2  # noqa: E402

from evaluate_landmarks import read_labels  # noqa: E402

COLORS = {"cej": (255, 120, 0), "bone_crest": (0, 140, 255), "root_apex": (0, 200, 0)}   # BGR


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--per-tooth", required=True)
    ap.add_argument("--images", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--mode", choices=("label-check", "blind"), required=True)
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    images, labels = os.path.expanduser(args.images), os.path.expanduser(args.labels)
    rows = [r for r in csv.DictReader(open(args.per_tooth, encoding="utf-8")) if r["status"] == "measured"]
    rng = random.Random(args.seed)  # audit-ok: seeded sampling of review items
    by_stage = {s: [r for r in rows if r["ref_stage"] == s] for s in ("I", "II", "III")}
    for v in by_stage.values():
        rng.shuffle(v)
    per = args.n // 3
    pick = [r for s in ("I", "II", "III") for r in by_stage[s][:per]]
    rng.shuffle(pick)                                            # stages mixed, so order gives nothing away
    os.makedirs(os.path.join(args.out, "teeth"), exist_ok=True)
    form, answers = [], []
    for i, r in enumerate(pick, 1):
        img = cv2.imread(os.path.join(images, r["image"]))
        h, w = img.shape[:2]
        tooth = read_labels(os.path.join(labels, os.path.splitext(r["image"])[0] + ".txt"), w, h)[int(r["tooth_index"])]
        x1, y1, x2, y2 = map(int, tooth["bbox"])
        pad = int(0.35 * max(x2 - x1, y2 - y1))
        cx1, cy1, cx2, cy2 = max(0, x1 - pad), max(0, y1 - pad), min(w, x2 + pad), min(h, y2 + pad)
        crop = img[cy1:cy2, cx1:cx2].copy()
        cv2.rectangle(crop, (x1 - cx1, y1 - cy1), (x2 - cx1, y2 - cy1), (255, 255, 255), 1)
        if args.mode == "label-check":
            for name, color in COLORS.items():
                px, py = tooth[name]
                cv2.circle(crop, (int(px - cx1), int(py - cy1)), max(4, crop.shape[1] // 80), color, -1)
        item = f"T{i:03d}"
        cv2.imwrite(os.path.join(args.out, "teeth", f"{item}.png"), crop)
        row = {"item": item, "image_file": f"teeth/{item}.png", "film": r["image"], "tooth": r["tooth_index"],
               "rater": "", "bone_loss_pct": "", "stage": "", "notes": ""}
        if args.mode == "label-check":
            row = {**row, "points_correct_yes_no": ""}
        form.append(row)
        answers += [{"film": r["image"], "tooth": r["tooth_index"], "rater": "reference_labels",
                     "bone_loss_pct": r["ref_pct"], "stage": r["ref_stage"]},
                    {"film": r["image"], "tooth": r["tooth_index"], "rater": "model",
                     "bone_loss_pct": r["pred_pct"], "stage": r["pred_stage"]}]
    for name, data in (("review_form.csv", form), ("answers_do_not_share.csv", answers)):
        with open(os.path.join(args.out, name), "w", newline="", encoding="utf-8") as f:
            wr = csv.DictWriter(f, fieldnames=list(data[0]))
            wr.writeheader()
            wr.writerows(data)
    guide = ("Blind grading: for each image, estimate radiographic bone loss at the WORST interproximal site of the boxed "
             "tooth as % of root length (CEJ to apex), or give the stage (I < 15 %, II 15-33 %, III > 33 %). "
             "Fill bone_loss_pct and/or stage and your name in `rater`. Do not look at other raters' forms."
             if args.mode == "blind" else
             "Label check: blue = CEJ, orange = bone crest, green = root apex used as the reference for the boxed tooth. "
             "Write yes in points_correct_yes_no if all three are where you would place them for the worst site; "
             "otherwise write no and give your own bone_loss_pct and/or stage.")
    open(os.path.join(args.out, "INSTRUCTIONS.txt"), "w", encoding="utf-8").write(guide + "\n")
    print(f"{len(form)} teeth ({ {s: sum(1 for r in pick if r['ref_stage'] == s) for s in ('I', 'II', 'III')} }) -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
