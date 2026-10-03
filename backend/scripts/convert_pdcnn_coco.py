"""PDCNN panoramic periodontitis dataset (github.com/PuckBlink/PDCNN, 1,747 films) -> YOLO detect.

The dataset ships COCO exports from the VIA annotator: `via_export_coco_BL.json` (per-tooth boxes labelled for
periodontal bone loss) and `via_export_coco_FI.json` (furcation involvement). This converts ONE of them
(--json) into YOLO boxes, keeping the categories found in the file (printed with their counts so the
meaning of each class can be checked), and splits films 80 / 10 / 10 (seeded) into train / val / test.

Usage:  python convert_pdcnn_coco.py --json via_export_coco_BL.json --images <folder with the films> --out <folder>
"""
import argparse
import collections
import glob
import json
import os
import random
import shutil

import cv2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    ap.add_argument("--images", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    coco = json.load(open(args.json, encoding="utf-8"))
    cats = sorted(coco.get("categories", []), key=lambda c: c["id"])
    if not cats:   # VIA sometimes omits categories: fall back to the ids used
        cats = [{"id": i, "name": f"class_{i}"} for i in sorted({a["category_id"] for a in coco["annotations"]})]
    index = {c["id"]: i for i, c in enumerate(cats)}
    print("categories:", [(c["id"], c["name"]) for c in cats])
    print("boxes per category:", collections.Counter(a["category_id"] for a in coco["annotations"]))
    files = {os.path.basename(p).lower(): p for p in glob.glob(os.path.join(args.images, "**", "*"), recursive=True)
             if p.lower().endswith((".jpg", ".jpeg", ".png"))}
    by_image = collections.defaultdict(list)
    for a in coco["annotations"]:
        by_image[a["image_id"]].append(a)
    images = [im for im in coco["images"] if os.path.basename(im["file_name"]).lower() in files and by_image[im["id"]]]
    random.Random(0).shuffle(images)  # audit-ok: seeded film-level split
    n, counts = len(images), collections.Counter()
    for i, im in enumerate(images):
        split = "train" if i < 0.8 * n else "val" if i < 0.9 * n else "test"
        src = files[os.path.basename(im["file_name"]).lower()]
        w, h = im.get("width"), im.get("height")
        if not w or not h:
            h, w = cv2.imread(src, cv2.IMREAD_GRAYSCALE).shape[:2]
        lines = []
        for a in by_image[im["id"]]:
            x, y, bw, bh = a["bbox"]
            if bw <= 1 or bh <= 1:
                continue
            lines.append(f"{index[a['category_id']]} {(x + bw / 2) / w:.6f} {(y + bh / 2) / h:.6f} {bw / w:.6f} {bh / h:.6f}")
        if not lines:
            continue
        for sub in ("images", "labels"):
            os.makedirs(os.path.join(args.out, sub, split), exist_ok=True)
        stem = f"pdcnn_{im['id']}"
        shutil.copy(src, os.path.join(args.out, "images", split, stem + os.path.splitext(src)[1]))
        with open(os.path.join(args.out, "labels", split, stem + ".txt"), "w") as f:
            f.write("\n".join(lines) + "\n")
        counts[split] += 1
    with open(os.path.join(args.out, "pdcnn.yaml"), "w") as f:
        f.write(f"path: {os.path.abspath(args.out)}\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n"
                + "".join(f"  {i}: '{c['name']}'\n" for i, c in enumerate(cats)))
    print("films per split:", dict(counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
