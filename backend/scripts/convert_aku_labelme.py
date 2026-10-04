"""Aga Khan University OPG dataset (Zenodo 10.5281/zenodo.10538750, CC BY 4.0) -> YOLO detect, FDI classes.

LabelMe polygons (crown + root) with the FDI number in `group_id` become boxes whose class index matches
the PerioVision tooth detector exactly: 11-18 -> 0-7, 21-28 -> 8-15, 31-38 -> 16-23, 41-48 -> 24-31.
Films are split 70 / 15 / 15 (seeded) so no film appears in two splits; the test split is kept for the
before / after comparison and never used for training. All three folders are used (folder 2 spells its label
folder "annnotations"; versions before 2026-10-04 missed it, so the first fine-tune saw folders 1 and 3 only).

Usage:  python convert_aku_labelme.py --src <.../dataset> --out <folder>
"""
import argparse
import glob
import json
import os
import random
import shutil

FDI = [f"{q}{n}" for q in (1, 2, 3, 4) for n in range(1, 9)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    src = os.path.expanduser(args.src)
    # folder 2 of the published archive spells its label folder "annnotations" (three n)
    anns = sorted(glob.glob(os.path.join(src, "*", "annotations", "*.json")) +
                  glob.glob(os.path.join(src, "*", "annnotations", "*.json")))
    random.Random(0).shuffle(anns)  # audit-ok: seeded film-level split
    n = len(anns)
    counts = {"train": 0, "val": 0, "test": 0}
    for i, ann in enumerate(anns):
        split = "train" if i < 0.7 * n else "val" if i < 0.85 * n else "test"
        d = json.load(open(ann, encoding="utf-8"))
        stem = os.path.splitext(os.path.basename(ann))[0]
        imgs = glob.glob(os.path.join(os.path.dirname(ann), "..", "OPGs", stem + ".*"))
        if not imgs:
            continue
        w, h = d["imageWidth"], d["imageHeight"]
        lines = []
        for s in d["shapes"]:
            fdi = str(s.get("group_id"))
            if fdi not in FDI or s.get("shape_type") != "polygon":
                continue
            xs, ys = [p[0] for p in s["points"]], [p[1] for p in s["points"]]
            x1, x2, y1, y2 = max(0, min(xs)), min(w, max(xs)), max(0, min(ys)), min(h, max(ys))
            lines.append(f"{FDI.index(fdi)} {(x1 + x2) / 2 / w:.6f} {(y1 + y2) / 2 / h:.6f} {(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}")
        if not lines:
            continue
        name = f"{os.path.basename(os.path.dirname(os.path.dirname(ann))).replace(' ', '_')}_{stem}"
        for sub in ("images", "labels"):
            os.makedirs(os.path.join(args.out, sub, split), exist_ok=True)
        shutil.copy(imgs[0], os.path.join(args.out, "images", split, name + os.path.splitext(imgs[0])[1]))
        with open(os.path.join(args.out, "labels", split, name + ".txt"), "w") as f:
            f.write("\n".join(lines) + "\n")
        counts[split] += 1
    with open(os.path.join(args.out, "aku.yaml"), "w") as f:
        f.write(f"path: {os.path.abspath(args.out)}\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n"
                + "".join(f"  {i}: '{c}'\n" for i, c in enumerate(FDI)))
    print(counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
