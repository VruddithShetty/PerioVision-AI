"""DenPAR -> YOLO-pose with BOTH bone-loss sites per tooth (5 keypoints instead of 3).

Why: the 3-keypoint labels (scripts/convert_denpar.py) keep only each tooth's worst site, which is sometimes
the left and sometimes the right side of the tooth. The model cannot know in advance which side the annotator's
worst site will be, so it learns to put CEJ and crest between the two (the model card's "placed near the middle
of the tooth"). Here every tooth gets both sites, and the worst site is chosen AFTER prediction, by measuring
both. That is how staging is defined anyway.

Keypoints per tooth (image left / right, so a mirror flip just swaps them; flip_idx [2, 3, 0, 1, 4]):
  0 cej_left   1 crest_left   2 cej_right   3 crest_right   4 root_apex
A site with no annotated CEJ or bone line is marked missing (v = 0) and does not contribute to the loss.

Point-to-tooth matching, apex and crest rules are imported unchanged from convert_denpar.py, and the worse of
the two sites equals that script's 3-keypoint label (checked per tooth; mismatches are counted and printed).

Leakage: films that are copies of a film in another split (research.split_audit, docs/DATA_SPLITS.md) are left
out of val / test by default: test 166, 852; val 1028, 158, 899.

Usage (from backend/):
    python scripts/convert_denpar_twosite.py --src <folder containing Dataset/> --out <output folder>
"""
import argparse
import glob
import json
import os
import shutil
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from convert_denpar import MAX_DIST, SPLITS, at, dist_map, load_masks  # noqa: E402

LEAKED = {"test": {"166", "852"}, "val": {"1028", "158", "899"}}
KPT_NAMES = ("cej_left", "crest_left", "cej_right", "crest_right", "root_apex")


def ratio(cej, crest, apex) -> float:
    axis = apex - cej
    L2 = float(axis @ axis)
    return float((crest - cej) @ axis) / L2 if crest is not None and L2 >= 1 else -1.0


def convert_image(kp, bone, masks):
    """Per tooth: box, apex, a site per side {cej, crest, ratio}, and the 3-keypoint worst site for checking."""
    dms = [dist_map(m) for m in masks]
    teeth = []
    for m in masks:
        ys, xs = np.nonzero(m)
        teeth.append({"box": [xs.min(), ys.min(), xs.max(), ys.max()], "cx": float(xs.mean()), "cej": [], "apex": []})

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
            continue
        apex = np.mean(t["apex"], axis=0)
        cx_mid = np.mean([c[0] for c in t["cej"]])
        sites = {"left": None, "right": None}
        worst = None
        for cej in t["cej"]:
            if float((apex - cej) @ (apex - cej)) < 1:
                continue
            mid = cx_mid if len(t["cej"]) > 1 else t["cx"]                  # same rule as convert_denpar.py
            side = np.sign(cej[0] - mid)
            cands = [v for v in vertices if at(dms[i], v) <= MAX_DIST
                     and (side == 0 or np.sign(v[0] - mid) == side)]
            axis = apex - cej
            crest = max(cands, key=lambda v: float((v - cej) @ axis)) if cands else None
            r = ratio(cej, crest, apex)
            if worst is None or r > worst[0]:
                worst = (r, cej, crest)
            # which side of the tooth: by the CEJ's own x when there are several, else by the tooth centre
            name = "left" if side < 0 else "right"
            if sites[name] is None or r > sites[name]["ratio"]:
                sites[name] = {"cej": cej, "crest": crest, "ratio": r}
        if worst is None:
            continue
        rows.append({"box": t["box"], "apex": apex, "sites": sites, "worst": worst})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="folder that contains Dataset/")
    ap.add_argument("--out", required=True)
    ap.add_argument("--keep-leaked", action="store_true", help="keep the duplicated films in val / test")
    args = ap.parse_args()
    root = os.path.join(args.src, "Dataset")
    stats = {}
    for split, short in SPLITS.items():
        os.makedirs(os.path.join(args.out, "images", short), exist_ok=True)
        os.makedirs(os.path.join(args.out, "labels", short), exist_ok=True)
        n = {"images": 0, "teeth": 0, "both_sites": 0, "one_site": 0, "worst_site_mismatch": 0, "dropped_leaked": 0}
        for kp_path in sorted(glob.glob(os.path.join(root, split, "Key Points Annotations", "*.json"))):
            stem = os.path.splitext(os.path.basename(kp_path))[0]
            if not args.keep_leaked and stem in LEAKED.get(short, ()):
                n["dropped_leaked"] += 1
                continue
            img_path = os.path.join(root, split, "Images", stem + ".jpg")
            bone_path = os.path.join(root, split, "Bone Level Annotations", stem + ".json")
            mask_dir = os.path.join(root, split, "Masks (Tooth-wise)", stem)
            if not (os.path.exists(img_path) and os.path.isdir(mask_dir)):
                continue
            img = cv2.imread(img_path)
            H, W = img.shape[:2]
            kp = json.load(open(kp_path))
            bone = json.load(open(bone_path)) if os.path.exists(bone_path) else {}
            lines = []
            for r in convert_image(kp, bone, load_masks(mask_dir)):
                x1, y1, x2, y2 = r["box"]
                vals = [0, (x1 + x2) / 2 / W, (y1 + y2) / 2 / H, (x2 - x1) / W, (y2 - y1) / H]
                have = 0
                for side in ("left", "right"):
                    s = r["sites"][side]
                    ok = s is not None and s["crest"] is not None
                    have += ok
                    for p in ((s["cej"], s["crest"]) if ok else (None, None)):
                        vals += [p[0] / W, p[1] / H, 2] if p is not None else [0.0, 0.0, 0]
                vals += [r["apex"][0] / W, r["apex"][1] / H, 2]
                best = max((s["ratio"] for s in r["sites"].values() if s is not None and s["crest"] is not None),
                           default=None)
                if best is not None and abs(best - r["worst"][0]) > 1e-9:
                    n["worst_site_mismatch"] += 1
                n["both_sites" if have == 2 else "one_site" if have == 1 else "no_site"] = \
                    n.get("both_sites" if have == 2 else "one_site" if have == 1 else "no_site", 0) + 1
                lines.append(" ".join(f"{v:.6f}" if isinstance(v, float) else str(v) for v in vals))
            if not lines:
                continue
            shutil.copy(img_path, os.path.join(args.out, "images", short, stem + ".jpg"))
            open(os.path.join(args.out, "labels", short, stem + ".txt"), "w").write("\n".join(lines) + "\n")
            n["images"] += 1
            n["teeth"] += len(lines)
        stats[short] = n
    open(os.path.join(args.out, "pose.yaml"), "w").write(
        f"path: {os.path.abspath(args.out)}\ntrain: images/train\nval: images/val\ntest: images/test\n"
        "kpt_shape: [5, 3]\nflip_idx: [2, 3, 0, 1, 4]\nnames:\n  0: tooth\n"
        f"# keypoints: {', '.join(KPT_NAMES)}\n")
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
