"""Head-to-head bone-loss evaluation of landmark models on the SAME films against the SAME reference.

Reference: the 3-keypoint DenPAR labels from scripts/convert_denpar.py (each tooth's worst site), i.e. exactly
what every published PerioVision number is measured against. Models:
  * 3-keypoint model (deployed): bone loss from CEJ / apex / crest, measured when all three confidences >= 0.3
  * 5-keypoint two-site model (scripts/convert_denpar_twosite.py): bone loss at the left and right sites, the
    worse CONFIDENT site is reported. The site confidence cut-off is chosen on the VALIDATION split only.

Both get the app's mirrored test-time augmentation (--tta, on by default): the film is also read mirrored, matched
teeth get averaged keypoints (left / right swapped back for the 5-keypoint model). Matching to reference teeth:
box IoU >= 0.5, greedy, as in scripts/evaluate_landmarks.py.

Usage (Colab, GPU; or CPU for a small --limit smoke test):
  python -m research.compare_landmark_models predict --model old.pt --kpts 3 --images <pose3>/images/val \
      --labels <pose3>/labels/val --out old_val.csv
  python -m research.compare_landmark_models summary --val new_val.csv --test new_test.csv --kpts 5 \
      [--baseline-test old_test.csv] --out compare.json
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))  # backend/

import numpy as np  # noqa: E402

from research import stats  # noqa: E402

MIN_KPT_CONF = 0.3                      # app threshold (config/thresholds.json landmarks.min_keypoint_confidence)
SWAP5 = [2, 3, 0, 1, 4]                 # mirror: left <-> right sites


def pct(cej, apex, crest) -> float | None:
    """Identical to app/ml/measurement/bone_loss.py."""
    cej, apex, crest = (np.asarray(p, float) for p in (cej, apex, crest))
    root = apex - cej
    L2 = float(root @ root)
    if L2 <= 1e-6:
        return None
    return max(0.0, min(100.0, float((crest - cej) @ root) / L2 * 100.0))


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - ix * iy
    return ix * iy / u if u > 0 else 0.0


def read_ref(path, w, h):
    teeth = []
    for line in open(path, encoding="utf-8"):
        v = list(map(float, line.split()))
        if len(v) < 14:
            continue
        cx, cy, bw, bh = v[1] * w, v[2] * h, v[3] * w, v[4] * h
        kp = [(v[5 + 3 * i] * w, v[6 + 3 * i] * h, v[7 + 3 * i]) for i in range(3)]
        if min(k[2] for k in kp) <= 0:
            continue                                     # no reference bone loss for this tooth
        teeth.append({"bbox": [cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2],
                      "ref": pct(kp[0][:2], kp[1][:2], kp[2][:2])})
    return teeth


def run_model(model, img, imgsz, kpts: int, tta: bool):
    """[(box, keypoints[k, 3], disagreement or None)] with mirrored TTA as in the app."""
    def raw(im):
        r = model.predict(im, imgsz=imgsz, conf=0.05, verbose=False)[0]
        if r.boxes is None or r.keypoints is None or not len(r.boxes):
            return np.zeros((0, 4)), np.zeros((0, kpts, 3))
        return r.boxes.xyxy.cpu().numpy().copy(), r.keypoints.data.cpu().numpy().copy()

    boxes, kp = raw(img)
    dis = [None] * len(boxes)
    if tta and len(boxes):
        w = img.shape[1]
        mb, mk = raw(np.ascontiguousarray(img[:, ::-1]))
        if len(mb):
            mb = np.stack([w - mb[:, 2], mb[:, 1], w - mb[:, 0], mb[:, 3]], 1)
            mk[:, :, 0] = w - mk[:, :, 0]
            if kpts == 5:
                mk = mk[:, SWAP5]
            used = set()
            for i in range(len(boxes)):
                j, best = max(((j, iou(boxes[i], mb[j])) for j in range(len(mb)) if j not in used),
                              key=lambda t: t[1], default=(None, 0.0))
                if j is None or best < 0.5:
                    continue
                used.add(j)
                a, b = tooth_pct(kp[i], kpts, 0.0), tooth_pct(mk[j], kpts, 0.0)
                kp[i] = (kp[i] + mk[j]) / 2.0
                dis[i] = abs(a - b) if a is not None and b is not None else None
    return list(zip(boxes, kp, dis))


def tooth_pct(k, kpts: int, site_conf: float) -> float | None:
    """Bone loss of one predicted tooth. 3 keypoints: CEJ, apex, crest. 5: worst confident site."""
    if kpts == 3:
        if min(k[:, 2]) < MIN_KPT_CONF:
            return None
        return pct(k[0, :2], k[1, :2], k[2, :2])
    if k[4, 2] < MIN_KPT_CONF:
        return None
    vals = [pct(k[c, :2], k[4, :2], k[r, :2]) for c, r in ((0, 1), (2, 3))
            if min(k[c, 2], k[r, 2]) >= site_conf]
    vals = [v for v in vals if v is not None]
    return max(vals) if vals else None


def predict(args) -> int:
    import cv2
    from ultralytics import YOLO

    model = YOLO(args.model)
    imgsz = args.imgsz or int(model.overrides.get("imgsz", 1024))
    files = sorted(glob.glob(os.path.join(args.images, "*.jpg")) + glob.glob(os.path.join(args.images, "*.png")))
    files = files[: args.limit] if args.limit else files
    rows = []
    for n, f in enumerate(files, 1):
        stem = os.path.splitext(os.path.basename(f))[0]
        lab = os.path.join(args.labels, stem + ".txt")
        img = cv2.imread(f)
        if img is None or not os.path.exists(lab):
            continue
        h, w = img.shape[:2]
        preds, used = run_model(model, img, imgsz, args.kpts, not args.no_tta), set()
        for t_idx, ref in enumerate(read_ref(lab, w, h)):
            j, best = max(((j, iou(ref["bbox"], p[0])) for j, p in enumerate(preds) if j not in used),
                          key=lambda t: t[1], default=(None, 0.0))
            row = {"image": os.path.basename(f), "tooth_index": t_idx, "ref_pct": round(ref["ref"], 4), "iou": round(best, 4)}
            if j is None or best < 0.5:
                rows.append({**row, "matched": 0})
                continue
            used.add(j)
            k = preds[j][1]
            row.update({"matched": 1, "tta_disagreement": preds[j][2]})
            row.update({f"k{i}_{c}": round(float(k[i, ci]), 3) for i in range(args.kpts) for ci, c in enumerate("xyc")})
            rows.append(row)
        if n % 20 == 0 or n == len(files):
            print(f"[{n}/{len(files)}]", flush=True)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        cols = sorted({c for r in rows for c in r}, key=lambda c: (not c.startswith(("image", "tooth", "ref", "iou", "matched")), c))
        wr = csv.DictWriter(fh, fieldnames=cols)
        wr.writeheader()
        wr.writerows(rows)
    print(f"wrote {len(rows)} reference teeth to {args.out}")
    return 0


# ------------------------------------------------------------------ summary
def _load(path, kpts):
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        k = None
        if r["matched"] == "1":
            k = np.array([[float(r[f"k{i}_{c}"]) for c in "xyc"] for i in range(kpts)])
        out.append({"image": r["image"], "ref": float(r["ref_pct"]), "k": k})
    return out


def score(rows, kpts, site_conf, boot=2000) -> dict:
    found = [r for r in rows if r["k"] is not None]
    meas = [(r, tooth_pct(r["k"], kpts, site_conf)) for r in found]
    meas = [(r, p) for r, p in meas if p is not None]
    ref = np.array([r["ref"] for r, _ in meas])
    pred = np.array([p for _, p in meas])
    films = np.array([r["image"] for r, _ in meas])
    out = {"reference_teeth": len(rows), "matched": len(found), "measured": len(meas),
           "measured_share_of_reference": len(meas) / len(rows) if rows else None}
    out.update(stats.mae_report(ref, pred, films, boot))
    out["staging"] = stats.stage_report(ref, pred, films, boot)
    out["bias_pred_minus_ref"] = float(np.mean(pred - ref))
    return out


def summary(args) -> int:
    val, test = _load(args.val, args.kpts), _load(args.test, args.kpts)
    chosen = None
    if args.kpts == 5:
        # choose the site-confidence cut-off on VALIDATION only: lowest MAE among cut-offs that still measure
        # at least as large a share of teeth as the 3-keypoint rule would need (>= --min-share)
        grid = [round(x, 2) for x in np.arange(0.1, 0.95, 0.05)]
        cands = []
        for c in grid:
            found = [r for r in val if r["k"] is not None]
            m = [(r["ref"], tooth_pct(r["k"], 5, c)) for r in found]
            m = [(a, b) for a, b in m if b is not None]
            if not m:
                continue
            share = len(m) / len(val)
            mae = float(np.mean([abs(a - b) for a, b in m]))
            cands.append({"site_conf": c, "val_mae": mae, "val_share": share})
        ok = [c for c in cands if c["val_share"] >= args.min_share] or cands
        chosen = min(ok, key=lambda c: c["val_mae"])
        print("validation grid:", json.dumps(cands))
    cut = chosen["site_conf"] if chosen else MIN_KPT_CONF
    report = {"kpts": args.kpts, "site_conf_chosen_on_val": chosen, "val": score(val, args.kpts, cut, args.boot),
              "test": score(test, args.kpts, cut, args.boot)}
    if args.baseline_test:
        base = _load(args.baseline_test, 3)
        report["baseline_3kpt_test"] = score(base, 3, MIN_KPT_CONF, args.boot)
        # paired comparison on teeth both models measured
        nb = {(r["image"], i): r for i, r in enumerate(base)}
        nt = {(r["image"], i): r for i, r in enumerate(test)}
        pairs = []
        for key in nb.keys() & nt.keys():
            a, b = nb[key], nt[key]
            if a["k"] is None or b["k"] is None:
                continue
            pa, pb = tooth_pct(a["k"], 3, MIN_KPT_CONF), tooth_pct(b["k"], args.kpts, cut)
            if pa is not None and pb is not None:
                pairs.append((key[0], abs(pa - a["ref"]), abs(pb - b["ref"])))
        if pairs:
            films = np.array([p[0] for p in pairs])
            diff = np.array([p[2] - p[1] for p in pairs])
            report["paired_test"] = {
                "teeth": len(pairs), "mae_old": float(np.mean([p[1] for p in pairs])),
                "mae_new": float(np.mean([p[2] for p in pairs])), "mae_new_minus_old": float(diff.mean()),
                "mae_new_minus_old_ci95": stats.bootstrap_ci(lambda i: float(diff[i].mean()), len(diff), films, args.boot),
                "note": "negative = the new model's error is lower; CI excluding 0 = a real difference"}
    json.dump(report, open(args.out, "w", encoding="utf-8"), indent=2, default=float)
    t = report["test"]
    print(f"TEST: measured {t['measured']}/{t['reference_teeth']}, MAE {t['mae']:.2f} {t['mae_ci95']}, "
          f"stage {t['staging']['exact_stage_accuracy']:.3f}")
    if "paired_test" in report:
        p = report["paired_test"]
        print(f"PAIRED: old {p['mae_old']:.2f} vs new {p['mae_new']:.2f}, diff {p['mae_new_minus_old']:.2f} "
              f"CI {p['mae_new_minus_old_ci95']}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("predict")
    p.add_argument("--model", required=True)
    p.add_argument("--kpts", type=int, choices=(3, 5), required=True)
    p.add_argument("--images", required=True)
    p.add_argument("--labels", required=True, help="3-keypoint REFERENCE labels (convert_denpar.py)")
    p.add_argument("--out", required=True)
    p.add_argument("--imgsz", type=int)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--no-tta", action="store_true")
    s = sub.add_parser("summary")
    s.add_argument("--val", required=True)
    s.add_argument("--test", required=True)
    s.add_argument("--kpts", type=int, choices=(3, 5), required=True)
    s.add_argument("--baseline-test")
    s.add_argument("--min-share", type=float, default=0.95, help="5-kpt: keep at least this share of teeth measured (val)")
    s.add_argument("--boot", type=int, default=2000)
    s.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    return predict(args) if args.cmd == "predict" else summary(args)


if __name__ == "__main__":
    sys.exit(main())
