"""perio-KPT (Zenodo 10.5281/zenodo.14711842, CC BY-NC-SA 2.0, access on request) -> PerioVision reference labels.

perio-KPT is an EXTERNAL periapical test set for PerioVision: other institutions (Peru, United Kingdom, India), other
devices, other annotators than DenPAR. Its YOLO-pose labels give, per tooth box, 11 keypoints in this order
(dataset description on Zenodo):

    0 CEJ-m   1 BL-m   2 RL-m   3 CEJ-d   4 BL-d   5 RL-d   6 RL-c   7 FA   8 FBL-m   9 FBL-d   10 ARR
    (m = mesial, d = distal, c = central; CEJ = cemento-enamel junction, BL = bone level, RL = root limit / apex)

and box classes 0 Single Root, 1 Double Root, 2 Triple Root, 3 ARR, 4 PLS (only classes 0-2 are teeth).

Each tooth becomes one PerioVision reference line, exactly like scripts/convert_denpar.py:
    0 cx cy w h  cej_x cej_y v  apex_x apex_y v  crest_x crest_y v       (normalised)
using the WORST of the mesial and distal sites (largest CEJ->bone-level distance along the root axis), with the
apex = mean of the visible root-limit points. Teeth without a complete site are written with missing keypoints
(v = 0), so evaluation skips them instead of guessing.

The keypoint order and class ids above are taken from the dataset description. Before trusting any number, this
script CHECKS them on the data: it reports how often each keypoint is visible and whether CEJ lies above the
bone level and the root limit below both on most teeth (a wrong order shows up immediately), and it draws
--check-images overlays to look at.

Usage (from backend/):
    python scripts/convert_periokpt.py --images <perio-KPT>/0_Baseline/images --labels <perio-KPT>/0_Baseline/labels \
        --out ~/Downloads/periokpt_ref --check-images 8
    DB_MODE=demo python scripts/evaluate_landmarks.py --images ~/Downloads/periokpt_ref/images \
        --labels ~/Downloads/periokpt_ref/labels --out ../docs/evidence/periokpt_external_eval.json \
        --per-tooth-csv ../docs/evidence/predictions/periokpt_external_per_tooth.csv
"""
import argparse
import glob
import json
import os
import shutil

import cv2
import numpy as np

TOOTH_CLASSES = {0, 1, 2}
CEJ_M, BL_M, RL_M, CEJ_D, BL_D, RL_D, RL_C = 0, 1, 2, 3, 4, 5, 6
N_KPT = 11


def parse(line: str, w: int, h: int):
    v = list(map(float, line.split()))
    if len(v) < 5 + 2 * N_KPT:
        return None
    cls = int(v[0])
    box = (v[1] * w, v[2] * h, v[3] * w, v[4] * h)
    step = 3 if len(v) >= 5 + 3 * N_KPT else 2          # with or without visibility flags
    kp = []
    for i in range(N_KPT):
        x, y = v[5 + step * i] * w, v[6 + step * i] * h
        vis = v[7 + step * i] if step == 3 else float(x > 0 or y > 0)
        kp.append((x, y, vis))
    return cls, box, np.array(kp)


def worst_site(kp):
    vis = lambda i: kp[i, 2] > 0  # noqa: E731
    roots = [kp[i, :2] for i in (RL_M, RL_D, RL_C) if vis(i)]
    if not roots:
        return None
    apex = np.mean(roots, axis=0)
    best = None
    for cej_i, bl_i in ((CEJ_M, BL_M), (CEJ_D, BL_D)):
        if not (vis(cej_i) and vis(bl_i)):
            continue
        cej, bl = kp[cej_i, :2], kp[bl_i, :2]
        axis = apex - cej
        L2 = float(axis @ axis)
        if L2 < 1:
            continue
        r = float((bl - cej) @ axis) / L2
        if best is None or r > best[0]:
            best = (r, cej, bl)
    return None if best is None else (best[1], apex, best[2])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--check-images", type=int, default=8)
    args = ap.parse_args()
    out = os.path.expanduser(args.out)
    os.makedirs(os.path.join(out, "images"), exist_ok=True)
    os.makedirs(os.path.join(out, "labels"), exist_ok=True)
    os.makedirs(os.path.join(out, "check"), exist_ok=True)
    stats = {"images": 0, "tooth_boxes": 0, "teeth_with_reference": 0, "visible_per_keypoint": [0] * N_KPT,
             "order_check_cej_above_bone": 0, "order_check_root_below_cej": 0, "order_checked": 0}
    imgs = sorted(p for p in glob.glob(os.path.join(os.path.expanduser(args.images), "*"))
                  if p.lower().endswith((".png", ".jpg", ".jpeg")))
    drawn = 0
    for p in imgs:
        stem = os.path.splitext(os.path.basename(p))[0]
        lab = os.path.join(os.path.expanduser(args.labels), stem + ".txt")
        img = cv2.imread(p)
        if img is None or not os.path.exists(lab):
            continue
        h, w = img.shape[:2]
        lines, vis_img = [], img.copy()
        for line in open(lab, encoding="utf-8"):
            parsed = parse(line, w, h)
            if parsed is None or parsed[0] not in TOOTH_CLASSES:
                continue
            cls, (cx, cy, bw, bh), kp = parsed
            stats["tooth_boxes"] += 1
            for i in range(N_KPT):
                stats["visible_per_keypoint"][i] += int(kp[i, 2] > 0)
            for cej_i, bl_i in ((CEJ_M, BL_M), (CEJ_D, BL_D)):
                if kp[cej_i, 2] > 0 and kp[bl_i, 2] > 0 and kp[RL_C, 2] + kp[RL_M, 2] + kp[RL_D, 2] > 0:
                    root = np.mean([kp[i, :2] for i in (RL_M, RL_D, RL_C) if kp[i, 2] > 0], axis=0)
                    d_bl = np.linalg.norm(kp[bl_i, :2] - root)
                    d_cej = np.linalg.norm(kp[cej_i, :2] - root)
                    stats["order_checked"] += 1
                    stats["order_check_cej_above_bone"] += int(d_cej >= d_bl)   # CEJ is farther from the apex
                    stats["order_check_root_below_cej"] += int(d_cej > 0.3 * bh)
            ws = worst_site(kp)
            vals = [0, cx / w, cy / h, bw / w, bh / h]
            if ws is None:
                vals += [0.0, 0.0, 0] * 3
            else:
                stats["teeth_with_reference"] += 1
                for q in (ws[0], ws[1], ws[2]):                     # cej, apex, crest (PerioVision order)
                    vals += [q[0] / w, q[1] / h, 2]
                for q, col in zip(ws, ((255, 120, 0), (0, 200, 0), (0, 140, 255))):
                    cv2.circle(vis_img, (int(q[0]), int(q[1])), max(4, w // 150), col, -1)
            lines.append(" ".join(f"{x:.6f}" if isinstance(x, float) else str(x) for x in vals))
        if not lines:
            continue
        shutil.copy(p, os.path.join(out, "images", os.path.basename(p)))
        open(os.path.join(out, "labels", stem + ".txt"), "w").write("\n".join(lines) + "\n")
        stats["images"] += 1
        if drawn < args.check_images:
            cv2.imwrite(os.path.join(out, "check", stem + "_reference.png"), vis_img)
            drawn += 1
    n = max(1, stats["order_checked"])
    stats["share_cej_farther_from_apex_than_bone"] = round(stats["order_check_cej_above_bone"] / n, 3)
    stats["share_root_far_below_cej"] = round(stats["order_check_root_below_cej"] / n, 3)
    ok = stats["share_cej_farther_from_apex_than_bone"] > 0.8 and stats["share_root_far_below_cej"] > 0.8
    stats["keypoint_order_plausible"] = ok
    json.dump(stats, open(os.path.join(out, "conversion_report.json"), "w"), indent=2)
    print(json.dumps(stats, indent=2))
    if not ok:
        print("WARNING: the keypoint order does not look like CEJ / bone level / root limit. Check the overlays in "
              f"{os.path.join(out, 'check')} and the dataset's README before evaluating.")
        return 3
    print(f"Look at the overlays in {os.path.join(out, 'check')} (blue CEJ, orange bone level, green apex), then evaluate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
