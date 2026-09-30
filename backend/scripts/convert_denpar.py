"""Convert the DenPAR periapical dataset to the YOLO-pose format PerioVision trains on.

DenPAR (Zenodo record 16645076, CC BY 4.0): 1000 periapical radiographs with, per image,
tooth boxes, tooth-wise masks, CEJ points, apex points and alveolar bone-level polylines,
annotated in Labelbox and verified by dental specialists. Points are NOT grouped per tooth,
so this script assigns them:

* each CEJ / apex point goes to the tooth whose mask is nearest (within MAX_DIST px);
* a tooth's apex = mean of its apex points (multi-rooted teeth have several);
* for each CEJ site (mesial / distal) the bone level = the deepest bone-line vertex that
  touches the tooth surface on that side, i.e. where bone meets the root;
* the tooth's keypoints come from its WORST site (largest bone loss), which is what
  periodontal staging uses.

Output per tooth line: 0 cx cy w h  cej_x cej_y v  apex_x apex_y v  crest_x crest_y v
(normalised; v = 2 visible, 0 missing). The official Training / Validation / Testing split is kept.

Usage (from backend/):
    python scripts/convert_denpar.py --src <folder containing Dataset/> --out <output folder>
"""
import argparse
import glob
import json
import os
import shutil

import cv2
import numpy as np

MAX_DIST = 25.0      # px: how far a point may lie from a tooth mask and still belong to it
SPLITS = {"Training": "train", "Validation": "val", "Testing": "test"}


def load_masks(folder):
    masks = []
    for f in sorted(glob.glob(os.path.join(folder, "*.png")), key=lambda p: int("".join(c for c in os.path.basename(p) if c.isdigit()) or 0)):
        m = cv2.imread(f, cv2.IMREAD_GRAYSCALE)
        if m is not None and m.max() > 0:
            masks.append(m > 127)
    return masks


def dist_map(mask):
    # distance (px) from every pixel to the nearest mask pixel
    return cv2.distanceTransform((~mask).astype(np.uint8), cv2.DIST_L2, 5)


def at(dm, p):
    h, w = dm.shape
    x, y = int(round(min(max(p[0], 0), w - 1))), int(round(min(max(p[1], 0), h - 1)))
    return float(dm[y, x])


def convert_image(kp, bone, masks):
    teeth = []
    dms = [dist_map(m) for m in masks]
    for m in masks:
        ys, xs = np.nonzero(m)
        teeth.append({"box": [xs.min(), ys.min(), xs.max(), ys.max()], "cej": [], "apex": []})

    def nearest(p):
        d = [at(dm, p) for dm in dms]
        i = int(np.argmin(d)) if d else -1
        return i if i >= 0 and d[i] <= MAX_DIST else -1

    for name, key in (("CEJ_Points", "cej"), ("Apex_Points", "apex")):
        for p in kp.get(name, []):
            i = nearest(p)
            if i >= 0:
                teeth[i][key].append(np.asarray(p, float))
    vertices = [np.asarray(v, float) for line in bone.get("Bone_Lines", []) for v in line]

    rows = []
    for i, t in enumerate(teeth):
        if not t["cej"] or not t["apex"]:
            continue                      # cannot define the root axis: skip the tooth entirely
        apex = np.mean(t["apex"], axis=0)
        cx_mid = np.mean([c[0] for c in t["cej"]])
        best = None
        for cej in t["cej"]:
            axis = apex - cej
            L2 = float(axis @ axis)
            if L2 < 1:
                continue
            side = np.sign(cej[0] - cx_mid) if len(t["cej"]) > 1 else 0
            cands = [v for v in vertices if at(dms[i], v) <= MAX_DIST
                     and (side == 0 or np.sign(v[0] - cx_mid) == side)]
            crest = max(cands, key=lambda v: float((v - cej) @ axis)) if cands else None
            ratio = float((crest - cej) @ axis) / L2 if crest is not None else -1
            if best is None or ratio > best[0]:
                best = (ratio, cej, crest)
        if best is None:
            continue
        rows.append({"box": t["box"], "cej": best[1], "apex": apex, "crest": best[2]})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="folder that contains Dataset/")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    root = os.path.join(args.src, "Dataset")
    stats = {}
    for split, short in SPLITS.items():
        os.makedirs(os.path.join(args.out, "images", short), exist_ok=True)
        os.makedirs(os.path.join(args.out, "labels", short), exist_ok=True)
        n_img = n_teeth = n_crest = 0
        for kp_path in sorted(glob.glob(os.path.join(root, split, "Key Points Annotations", "*.json"))):
            stem = os.path.splitext(os.path.basename(kp_path))[0]
            img_path = os.path.join(root, split, "Images", stem + ".jpg")
            bone_path = os.path.join(root, split, "Bone Level Annotations", stem + ".json")
            mask_dir = os.path.join(root, split, "Masks (Tooth-wise)", stem)
            if not (os.path.exists(img_path) and os.path.isdir(mask_dir)):
                continue
            img = cv2.imread(img_path)
            H, W = img.shape[:2]
            kp = json.load(open(kp_path))
            bone = json.load(open(bone_path)) if os.path.exists(bone_path) else {}
            rows = convert_image(kp, bone, load_masks(mask_dir))
            lines = []
            for r in rows:
                x1, y1, x2, y2 = r["box"]
                vals = [0, (x1 + x2) / 2 / W, (y1 + y2) / 2 / H, (x2 - x1) / W, (y2 - y1) / H]
                for p in (r["cej"], r["apex"], r["crest"]):
                    vals += [p[0] / W, p[1] / H, 2] if p is not None else [0, 0, 0]
                lines.append(" ".join(f"{v:.6f}" if isinstance(v, float) else str(v) for v in vals))
                n_crest += r["crest"] is not None
            if not lines:
                continue
            shutil.copy(img_path, os.path.join(args.out, "images", short, stem + ".jpg"))
            open(os.path.join(args.out, "labels", short, stem + ".txt"), "w").write("\n".join(lines) + "\n")
            n_img += 1
            n_teeth += len(lines)
        stats[short] = {"images": n_img, "teeth": n_teeth, "teeth_with_crest": n_crest}
    open(os.path.join(args.out, "pose.yaml"), "w").write(
        f"path: {os.path.abspath(args.out)}\ntrain: images/train\nval: images/val\ntest: images/test\n"
        "kpt_shape: [3, 3]\nflip_idx: [0, 1, 2]\nnames:\n  0: tooth\n")
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
