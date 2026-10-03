"""Convert TL-pano (Zenodo 10.5281/zenodo.18715533) expert outlines into CEJ / apex / crest keypoints.

TL-pano gives, per panoramic film, instance polygons for enamel (class 1), whole tooth with FDI quadrant
and tooth type (class 4), and upper / lower alveolar bone (classes 5 / 6). From them, per tooth:
  * apex  = the root tip: the tooth-outline points furthest from the occlusal plane (mean of the tips)
  * CEJ   = where the enamel ends, on the mesial and on the distal side of the tooth
  * crest = where the alveolar-bone outline meets the tooth surface, on the same side
The tooth's keypoints come from its WORST side (largest bone loss), as in convert_denpar.py, so the
labels match the app's per-tooth bone loss. Output: YOLO-pose crops (tooth plus neighbours, like the app's
panoramic crop path) with 1 class and 3 keypoints (CEJ, apex, crest); split by FILM into train / val / test
so no patient appears in two splits.

Check the result before training: --preview N writes N images with the derived points drawn.

Usage (from backend/):
    python scripts/convert_tlpano.py --src ~/Downloads/TL-pano --out ~/Downloads/TL-pano/pose --preview 10
NOTE: written from the format described on the Zenodo page ("annotations" list of objects with class_id,
quadrant_id, tooth_type_id and "coordinates"); if the downloaded files differ, adjust load_film().
"""
import argparse
import glob
import json
import os
import random

import cv2
import numpy as np

ENAMEL, TOOTH, UPPER_BONE, LOWER_BONE = 1, 4, 5, 6
QUADRANT_TO_FDI = {0: 1, 1: 2, 2: 3, 3: 4}      # Upper right, upper left, lower left, lower right (Zenodo page)


def load_film(path: str) -> dict:
    d = json.load(open(path, encoding="utf-8"))
    objs = d.get("annotations", d if isinstance(d, list) else [])
    out = {"image": d.get("filename") or d.get("image") or os.path.splitext(os.path.basename(path))[0], "teeth": [],
           "enamel": [], "bone_upper": [], "bone_lower": []}
    for o in objs:
        pts = np.asarray(o.get("coordinates") or o.get("points"), float).reshape(-1, 2)
        if len(pts) < 3:
            continue
        c = int(o["class_id"])
        if c == TOOTH:
            q, t = o.get("quadrant_id"), o.get("tooth_type_id")
            fdi = f"{QUADRANT_TO_FDI.get(int(q), 0)}{int(t) + 1}" if q is not None and t is not None else None
            out["teeth"].append({"poly": pts, "fdi": fdi, "upper": q is not None and int(q) in (0, 1)})
        elif c == ENAMEL:
            out["enamel"].append(pts)
        elif c == UPPER_BONE:
            out["bone_upper"].append(pts)
        elif c == LOWER_BONE:
            out["bone_lower"].append(pts)
    return out


def _mask(poly, shape):
    m = np.zeros(shape, np.uint8)
    cv2.fillPoly(m, [np.round(poly).astype(np.int32)], 1)
    return m.astype(bool)


def densify(poly: np.ndarray, step: float = 2.0) -> np.ndarray:
    """Points every `step` px along the closed outline (annotation vertices alone are too sparse)."""
    out = []
    for a, b in zip(poly, np.roll(poly, -1, axis=0)):
        k = max(1, int(np.ceil(np.linalg.norm(b - a) / step)))
        out.extend(a + (b - a) * t for t in np.arange(k) / k)
    return np.asarray(out)


def landmarks(tooth: dict, enamel: list, bones: list, shape) -> dict | None:
    """CEJ / crest per side and apex for one tooth; returns the worse side, or None if not derivable."""
    poly = densify(tooth["poly"])
    upper = tooth["upper"]
    sgn = -1.0 if upper else 1.0                        # +y points toward the apex for lower teeth
    ys = poly[:, 1] * sgn
    tips = poly[ys >= ys.max() - 0.03 * (ys.max() - ys.min())]   # extreme 3 %: the root tip(s)
    apex = tips.mean(axis=0)
    tmask = _mask(poly, shape)
    # enamel of this tooth = enamel polygons mostly inside the tooth outline
    own = [e for e in enamel if _mask(e, shape)[tmask].sum() > 0.6 * _mask(e, shape).sum()]
    if not own:
        return None
    emask = np.zeros(shape, bool)
    for e in own:
        emask |= _mask(e, shape)
    bmask = np.zeros(shape, bool)
    for b in bones:
        bmask |= _mask(b, shape)
    xs = poly[:, 0]
    mid = (xs.min() + xs.max()) / 2
    best = None
    for side in (-1, 1):                                  # left / right surface of the tooth
        surf = poly[(poly[:, 0] - mid) * side > 0.25 * (xs.max() - xs.min()) / 2]
        if len(surf) < 3:
            continue
        surf = surf[np.argsort(surf[:, 1] * sgn)]         # from the crown toward the apex
        on_enamel = [p for p in surf if emask[min(shape[0] - 1, int(p[1])), min(shape[1] - 1, int(p[0]))]
                     or emask[min(shape[0] - 1, int(p[1])), min(shape[1] - 1, max(0, int(p[0]) - 2 * side))]]
        if not on_enamel:
            continue
        cej = max(on_enamel, key=lambda p: p[1] * sgn)    # last enamel point going apically
        # crest: first point on this surface, apical to the CEJ, that touches the bone (sample just outside)
        crest = None
        for p in surf:
            if p[1] * sgn < cej[1] * sgn:
                continue
            x_out = int(np.clip(p[0] + 3 * side, 0, shape[1] - 1))
            if bmask[int(np.clip(p[1], 0, shape[0] - 1)), x_out]:
                crest = p
                break
        if crest is None:
            continue
        root = apex - cej
        loss = float(np.dot(crest - cej, root) / max(np.dot(root, root), 1e-6))
        if best is None or loss > best[0]:
            best = (loss, cej, crest)
    if best is None:
        return None
    return {"cej": best[1].tolist(), "root_apex": apex.tolist(), "bone_crest": best[2].tolist(),
            "bone_loss_pct": round(100 * max(0.0, min(1.0, best[0])), 2)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--preview", type=int, default=0)
    args = ap.parse_args()
    src, out = os.path.expanduser(args.src), os.path.expanduser(args.out)
    films = sorted(glob.glob(os.path.join(src, "**", "*.json"), recursive=True))
    random.Random(0).shuffle(films)  # audit-ok: seeded film-level split
    n = len(films)
    split = {f: ("train" if i < 0.7 * n else "val" if i < 0.85 * n else "test") for i, f in enumerate(films)}
    stats = {"films": 0, "teeth": 0, "with_landmarks": 0}
    previews = 0
    for f in films:
        film = load_film(f)
        imgs = glob.glob(os.path.join(os.path.dirname(f), "**", os.path.splitext(film["image"])[0] + ".*"), recursive=True)
        imgs = [p for p in imgs if p.lower().endswith((".jpg", ".jpeg", ".png"))]
        if not imgs or not film["teeth"]:
            continue
        img = cv2.imread(imgs[0], cv2.IMREAD_GRAYSCALE)
        H, W = img.shape
        stats["films"] += 1
        sp = split[f]
        os.makedirs(os.path.join(out, "images", sp), exist_ok=True)
        os.makedirs(os.path.join(out, "labels", sp), exist_ok=True)
        vis = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) if previews < args.preview else None
        for k, t in enumerate(film["teeth"]):
            stats["teeth"] += 1
            lm = landmarks(t, film["enamel"], film["bone_upper"] if t["upper"] else film["bone_lower"], (H, W))
            if lm is None:
                continue
            stats["with_landmarks"] += 1
            x1, y1 = t["poly"].min(0)
            x2, y2 = t["poly"].max(0)
            bw, bh = x2 - x1, y2 - y1
            cx1, cx2 = int(max(0, x1 - 0.9 * bw)), int(min(W, x2 + 0.9 * bw))     # same crop as the app
            cy1, cy2 = int(max(0, y1 - 0.15 * bh)), int(min(H, y2 + 0.15 * bh))
            crop = img[cy1:cy2, cx1:cx2]
            cw, ch = cx2 - cx1, cy2 - cy1
            name = f"{os.path.splitext(os.path.basename(f))[0]}_{k}"
            cv2.imwrite(os.path.join(out, "images", sp, name + ".png"), crop)
            kp = " ".join(f"{(p[0] - cx1) / cw:.6f} {(p[1] - cy1) / ch:.6f} 2" for p in (lm["cej"], lm["root_apex"], lm["bone_crest"]))
            box = f"{((x1 + x2) / 2 - cx1) / cw:.6f} {((y1 + y2) / 2 - cy1) / ch:.6f} {bw / cw:.6f} {bh / ch:.6f}"
            with open(os.path.join(out, "labels", sp, name + ".txt"), "w") as fh:
                fh.write(f"0 {box} {kp}\n")
            if vis is not None:
                for p, c in ((lm["cej"], (255, 255, 0)), (lm["bone_crest"], (0, 0, 255)), (lm["root_apex"], (255, 0, 255))):
                    cv2.circle(vis, tuple(int(v) for v in p), 6, c, -1)
        if vis is not None:
            os.makedirs(os.path.join(out, "preview"), exist_ok=True)
            cv2.imwrite(os.path.join(out, "preview", os.path.basename(f) + ".jpg"), vis)
            previews += 1
    with open(os.path.join(out, "pose.yaml"), "w") as fh:
        fh.write(f"path: {out}\ntrain: images/train\nval: images/val\ntest: images/test\nkpt_shape: [3, 3]\n"
                 "flip_idx: [0, 1, 2]\nnames:\n  0: tooth\n")
    print(stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
