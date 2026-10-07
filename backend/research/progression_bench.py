"""Progression bench: how well does PerioVision tell real bone-loss change from measurement noise?

No public dataset has follow-up radiographs of the same patients with a measured amount of bone-loss change, so the
bench builds the two things a change detector must get right, from DenPAR films with specialist bone-level labels:

  1. NO-CHANGE pairs: the same film "re-taken" with a realistic acquisition change (rotation, scale, shift, a slight
     projective tilt that mimics a different beam angle, exposure / gamma / contrast, sensor noise, blur, JPEG).
     Every tooth in such a pair has a true change of 0. A good detector stays silent (specificity).
  2. CHANGE pairs: the same, but one site of one tooth first gets simulated extra bone loss of a known size: the
     alveolar crest at that site is moved apically along the root by DELTA % of root length, and the bone between the
     old and the new crest is replaced by soft-tissue density in an angular (crater-shaped) defect, the way bone
     loss shows on a radiograph. A good detector flags it (sensitivity). All other teeth in the pair are no-change.

This is a TECHNICAL (bench) validation in the sense of subtraction-radiography studies: it measures repeatability
and the response to a known, simulated lesion. It is not a clinical validation; that needs real follow-up pairs
(scripts/evaluate_registration.py and research/progression_bench.py --pairs for those, once they exist).

Every film goes through the app's own path: locate_teeth (two-site landmarks, mirrored reading), register_images
(ORB + RANSAC + plausibility + NCC + tooth overlap) and progression_service.match_teeth.

Usage (from backend/; CPU works, one film pair takes about 10-15 s):
    python -m research.progression_bench run --split val  --films 80  --out ../docs/evidence/predictions/progression_val.csv
    python -m research.progression_bench run --split test --films 100 --out ../docs/evidence/predictions/progression_test.csv
    python -m research.progression_bench summary --val ../docs/evidence/predictions/progression_val.csv \
        --test ../docs/evidence/predictions/progression_test.csv --out ../docs/evidence/progression_bench.json
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import random
import sys

os.environ.setdefault("DB_MODE", "demo")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))           # backend/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

DELTAS = (5.0, 10.0, 15.0, 20.0)
FIELDS = ["film", "variant", "kind", "tooth", "site", "prev_pct", "curr_pct", "delta", "tooth_delta", "edited_tooth",
          "edited_site", "true_delta", "registered", "match", "tta_prev", "tta_curr"]
SPLITS = {"train": "Training", "val": "Validation", "test": "Testing"}
LEAKED = {"166", "852", "1028", "158", "899"}            # films duplicated across DenPAR splits (docs/DATA_SPLITS.md)


# ------------------------------------------------------------------ acquisition change ("re-take")
def retake(gray: np.ndarray, rng: random.Random) -> np.ndarray:
    h, w = gray.shape
    ang, sc = rng.uniform(-4, 4), rng.uniform(0.93, 1.07)
    m = cv2.getRotationMatrix2D((w / 2, h / 2), ang, sc)
    m[:, 2] += (rng.uniform(-0.04, 0.04) * w, rng.uniform(-0.04, 0.04) * h)
    img = cv2.warpAffine(gray, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    # slight projective tilt: a different vertical / horizontal beam angle
    d = 0.025
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[rng.uniform(-d, d) * w, rng.uniform(-d, d) * h] for _ in range(4)]) + src
    img = cv2.warpPerspective(img, cv2.getPerspectiveTransform(src, dst), (w, h), borderMode=cv2.BORDER_REFLECT)
    x = img.astype(np.float32) / 255.0
    x = np.power(np.clip(x, 0, 1), rng.uniform(0.8, 1.25))                       # exposure / processing curve
    x = x * rng.uniform(0.9, 1.1) + rng.uniform(-0.06, 0.06)                      # contrast / brightness
    x = x * 255.0 + np.random.default_rng(rng.randrange(2**31)).normal(0, rng.uniform(1.5, 5.0), x.shape)
    sigma = rng.uniform(0, 1.0)
    if sigma > 0.2:
        x = cv2.GaussianBlur(x, (0, 0), sigma)
    out = np.clip(x, 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, rng.randint(70, 95)])
    dec = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
    return dec.reshape(dec.shape[:2])


# ------------------------------------------------------------------ simulated bone loss at one site
def simulate_loss(gray: np.ndarray, mask: np.ndarray, cej, crest, apex, side: str, delta_pct: float,
                  all_teeth: np.ndarray | None = None) -> np.ndarray | None:
    """Move the crest apically by delta_pct % of root length at one site; fill the defect with soft-tissue density."""
    cej, crest, apex = (np.asarray(p, float) for p in (cej, crest, apex))
    axis = apex - cej
    L = float(np.linalg.norm(axis))
    if L < 20:
        return None
    u = axis / L
    t0 = float((crest - cej) @ u)
    t1 = t0 + delta_pct / 100.0 * L
    if t1 > 0.9 * L:
        return None
    h, w = gray.shape
    ys, xs = np.nonzero(mask)
    cx, tooth_w = xs.mean(), xs.max() - xs.min()
    dist_out = cv2.distanceTransform((~mask).astype(np.uint8), cv2.DIST_L2, 5)        # distance from the tooth
    teeth = mask if all_teeth is None else (all_teeth | mask)
    no_tooth = ~cv2.dilate(teeth.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)  # never paint on a tooth
    yy, xx = np.mgrid[0:h, 0:w]
    t = (xx - cej[0]) * u[0] + (yy - cej[1]) * u[1]
    on_side = (xx < cx) if side == "left" else (xx > cx)
    W = max(6.0, 0.35 * tooth_w)
    frac = np.clip((t - t0) / max(t1 - t0, 1e-6), 0, 1)
    width = W * (1.0 - 0.85 * frac)                                                    # crater narrows apically
    defect = on_side & no_tooth & (t >= t0 - 0.01 * L) & (t <= t1) & (dist_out <= width)
    if defect.sum() < 20:
        return None
    # soft-tissue level: the interdental area just coronal to the old crest on the same side (no bone there)
    soft = on_side & no_tooth & (t >= t0 - 0.12 * L) & (t < t0 - 0.02 * L) & (dist_out <= W)
    if soft.sum() < 20:
        return None
    g = gray.astype(np.float32)
    level = float(np.median(g[soft]))
    local = cv2.GaussianBlur(g, (0, 0), 2)
    filled = level + (g - local)                                                       # keep the film's grain
    alpha = cv2.GaussianBlur(defect.astype(np.float32), (0, 0), 2.5)                  # no hard edges
    out = g * (1 - alpha) + np.minimum(filled, g) * alpha                             # loss only darkens
    return np.clip(out, 0, 255).astype(np.uint8)


# ------------------------------------------------------------------ DenPAR films with masks and site labels
def films(root: str, split: str) -> list[dict]:
    import convert_denpar_twosite as cv2site
    from convert_denpar import load_masks

    base = os.path.join(root, SPLITS[split])
    out = []
    for kp_path in sorted(glob.glob(os.path.join(base, "Key Points Annotations", "*.json"))):
        stem = os.path.splitext(os.path.basename(kp_path))[0]
        if stem in LEAKED:
            continue
        img = os.path.join(base, "Images", stem + ".jpg")
        md = os.path.join(base, "Masks (Tooth-wise)", stem)
        bp = os.path.join(base, "Bone Level Annotations", stem + ".json")
        if not (os.path.exists(img) and os.path.isdir(md)):
            continue
        masks = load_masks(md)
        rows = cv2site.convert_image(json.load(open(kp_path)), json.load(open(bp)) if os.path.exists(bp) else {}, masks)
        teeth = []
        for r in rows:
            box = [int(v) for v in r["box"]]
            m = next((mk for mk in masks if [int(v) for v in (np.nonzero(mk)[1].min(), np.nonzero(mk)[0].min(),
                                                                  np.nonzero(mk)[1].max(), np.nonzero(mk)[0].max())] == box), None)
            sites = {k: v for k, v in r["sites"].items() if v is not None and v["crest"] is not None}
            if m is not None and sites:
                teeth.append({"box": box, "mask": m, "apex": r["apex"], "sites": sites})
        if teeth:
            union = np.zeros_like(masks[0])
            for mk in masks:
                union |= mk
            out.append({"film": stem + ".jpg", "path": img, "teeth": teeth, "all_teeth": union})
    return out


# ------------------------------------------------------------------ app path
def analyse(gray: np.ndarray) -> dict:
    from app.ml.measurement.bone_loss import bone_loss_for_tooth
    from app.services.analysis_service import locate_teeth, measured

    res = locate_teeth(gray)
    teeth = []
    for det in res["detections"]:
        lm = res["landmarks"].get(det["tooth_id"])
        if not measured(lm):
            continue
        teeth.append({"tooth_id": det["tooth_id"], "tooth_id_source": det.get("tooth_id_source"), "bbox": det["bbox"],
                      "bone_loss_pct": bone_loss_for_tooth(lm)["bone_loss_pct"],
                      "site_bone_loss_pct": lm.get("site_bone_loss_pct") or {},
                      "tta_disagreement_pct": lm.get("tta_disagreement_pct")})
    return {"teeth": teeth, "image_size": [gray.shape[1], gray.shape[0]], "image_type": res["image_type"]}


def compare(prev_gray, prev, gray, curr) -> tuple[dict, list]:
    from app.services.analysis_service import register_images
    from app.services.progression_service import match_teeth

    alignment = register_images(prev_gray, gray, prev["teeth"], curr["teeth"])
    curr = {**curr, "alignment": alignment}
    return alignment, match_teeth(prev, curr)


def run(args) -> int:
    from app.ml.landmarks.cej_abc_extractor import _iou

    rng = random.Random(args.seed)  # audit-ok: seeded bench construction
    root = os.path.expanduser(args.denpar)
    fl = films(root, args.split)
    rng.shuffle(fl)
    fl = fl[: args.films]
    if args.shard is not None:
        k, n = map(int, args.shard.split("/"))
        fl = fl[k::n]
    done = set()
    if os.path.exists(args.out):                      # resume: films already written are skipped
        done = {r["film"] for r in csv.DictReader(open(args.out, encoding="utf-8"))}
    total = 0
    for i, f in enumerate(fl, 1):
        if f["film"] in done:
            continue
        rng = random.Random(f"{args.seed}:{f['film']}")  # audit-ok: per-film seed, identical after a resume
        rows = []
        gray = cv2.imread(f["path"], cv2.IMREAD_GRAYSCALE)
        gray = gray.reshape(gray.shape[:2])                    # some JPEGs decode as (h, w, 1)
        prev = analyse(gray)
        variants = [("nochange", None, 0.0)] * args.nochange + \
                   ([("change", d, d) for d in DELTAS] if args.split != "val" or args.val_changes else [])
        for v_i, (kind, d, true_delta) in enumerate(variants):
            img, edited = gray, None
            if kind == "change":
                for _ in range(10):
                    tooth = rng.choice(f["teeth"])
                    side = rng.choice(sorted(tooth["sites"]))
                    s = tooth["sites"][side]
                    sim = simulate_loss(gray, tooth["mask"], s["cej"], s["crest"], tooth["apex"], side, d, f["all_teeth"])
                    if sim is not None:
                        img, edited = sim, (tooth, side)
                        break
                if edited is None:
                    continue
            follow = retake(img, rng)
            curr = analyse(follow)
            alignment, pairs = compare(gray, prev, follow, curr)
            for p, c, method in pairs:
                is_edited = edited is not None and _iou(p["bbox"], edited[0]["box"]) >= 0.5
                for side in ("left", "right"):
                    a, b = p["site_bone_loss_pct"].get(side), c["site_bone_loss_pct"].get(side)
                    rows.append({"film": f["film"], "variant": f"{kind}{v_i}", "kind": kind, "tooth": p["tooth_id"],
                                 "site": side, "prev_pct": a, "curr_pct": b,
                                 "delta": None if a is None or b is None else round(b - a, 3),
                                 "tooth_delta": round(c["bone_loss_pct"] - p["bone_loss_pct"], 3),
                                 "edited_tooth": int(is_edited),
                                 "edited_site": int(is_edited and side == edited[1]),
                                 "true_delta": true_delta if is_edited and side == edited[1] else 0.0,
                                 "registered": alignment.get("status") == "success", "match": method,
                                 "tta_prev": p.get("tta_disagreement_pct"), "tta_curr": c.get("tta_disagreement_pct")})
        if not rows:                                   # keep a marker so the film is not redone
            rows = [{"film": f["film"], "variant": "none", "kind": "none"}]
        new = not os.path.exists(args.out)
        with open(args.out, "a", newline="", encoding="utf-8") as fh:   # saved after every film
            wr = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
            if new:
                wr.writeheader()
            wr.writerows(rows)
        total += len(rows)
        print(f"[{i}/{len(fl)}] {f['film']}: {len(rows)} site rows", flush=True)
    print(f"appended {total} rows to {args.out}")
    return 0


# ------------------------------------------------------------------ analysis
def _load(paths):
    rows = []
    for p in paths:
        rows += list(csv.DictReader(open(p, encoding="utf-8")))
    return rows


def _dis(r):
    vals = [float(r[k]) for k in ("tta_prev", "tta_curr") if r.get(k) not in ("", "None", None)]
    return max(vals) if len(vals) == 2 else None


def decide(rows, thr, adaptive=None):
    """Per tooth and pair: CHANGE if any site with both readings changed by more than the threshold (bone loss
    increase). With `adaptive` = (split, thr_low, thr_high): teeth whose mirrored readings disagree by at most
    `split` points in both visits use thr_low, all others thr_high."""
    out = {}
    for r in rows:
        if r["registered"] != "True":
            continue
        key = (r["film"], r["variant"], r["tooth"])
        e = out.setdefault(key, {"film": r["film"], "true": 0.0, "max_delta": None, "kind": r["kind"], "dis": _dis(r)})
        e["true"] = max(e["true"], float(r["true_delta"]))
        if r["delta"] not in ("", "None"):
            d = float(r["delta"])
            e["max_delta"] = d if e["max_delta"] is None else max(e["max_delta"], d)
    def t(e):
        if adaptive is None or e["dis"] is None:
            return thr if adaptive is None else adaptive[2]
        return adaptive[1] if e["dis"] <= adaptive[0] else adaptive[2]
    return [{**e, "thr": t(e), "flag": e["max_delta"] is not None and e["max_delta"] > t(e)} for e in out.values()]


def summary(args) -> int:
    from research import stats

    val, test = _load(args.val), _load(args.test)
    # threshold: the (1 - fp) quantile of the largest per-site increase on NO-CHANGE validation teeth
    vt = [e for e in decide(val, float("inf")) if e["true"] == 0 and e["max_delta"] is not None]
    nc = [e["max_delta"] for e in vt]
    thr = float(np.quantile(nc, 1 - args.false_alarm)) if nc else float("nan")
    # adaptive (declared before the test results were seen): split teeth at the median mirrored-reading disagreement
    dv = [e["dis"] for e in vt if e["dis"] is not None]
    split = float(np.median(dv))
    lo = [e["max_delta"] for e in vt if e["dis"] is not None and e["dis"] <= split]
    hi = [e["max_delta"] for e in vt if e["dis"] is None or e["dis"] > split]
    adaptive = (split, float(np.quantile(lo, 1 - args.false_alarm)), float(np.quantile(hi, 1 - args.false_alarm)))
    full = {}
    for name, rule in (("fixed", None), ("adaptive", adaptive)):
        tt = [e for e in decide(test, thr, rule) if e["max_delta"] is not None]
        neg_ = np.array([e["true"] == 0 for e in tt]); fl_ = np.array([e["flag"] for e in tt])
        full[name] = {"specificity": float((~fl_[neg_]).mean()),
                      "sensitivity": {f"{d:g}": float(fl_[np.array([e["true"] == d for e in tt])].mean())
                                      for d in DELTAS if any(e["true"] == d for e in tt)}}
    teeth = [e for e in decide(test, thr, adaptive) if e["max_delta"] is not None]
    films = np.array([e["film"] for e in teeth])
    neg = np.array([e["true"] == 0 for e in teeth])
    flag = np.array([e["flag"] for e in teeth])
    rep = {"threshold_points": round(thr, 3), "threshold_rule": f"{100 * (1 - args.false_alarm):.0f}th percentile of the "
           "largest per-site increase on no-change validation teeth", "validation_no_change_teeth": len(nc),
           "adaptive": {"split_disagreement_points": round(adaptive[0], 3), "threshold_low": round(adaptive[1], 3),
                        "threshold_high": round(adaptive[2], 3)},
           "deployed_rule": "adaptive (declared before test results)", "both_rules_on_test": full}
    spec = (~flag[neg]).mean()
    rep["specificity_no_change"] = {"value": float(spec), "teeth": int(neg.sum()),
                                    "ci95": stats.bootstrap_ci(lambda i: float((~flag[neg][i]).mean()), int(neg.sum()),
                                                               films[neg], 2000)}
    pure = np.array([e["kind"] == "nochange" for e in teeth])
    rep["specificity_pure_no_change_retakes"] = {
        "value": float((~flag[pure]).mean()), "teeth": int(pure.sum()),
        "ci95": stats.wilson(int((~flag[pure]).sum()), int(pure.sum())),
        "note": "teeth in films with no simulated change. The overall specificity above also counts the other teeth of "
                "films with a simulated defect; their neighbours share the edited interdental bone, so some of those "
                "'false alarms' are real changes"}
    rep["sensitivity_by_true_change"] = {}
    for d in DELTAS:
        m = np.array([e["true"] == d for e in teeth])
        if m.any():
            rep["sensitivity_by_true_change"][f"{d:g}"] = {
                "value": float(flag[m].mean()), "teeth": int(m.sum()), "ci95": stats.wilson(int(flag[m].sum()), int(m.sum()))}
    # repeatability of the per-site measurement on no-change test teeth
    d0 = np.array([float(r["delta"]) for r in test if r["kind"] == "nochange" and r["delta"] not in ("", "None")
                   and r["registered"] == "True"])
    if len(d0):
        rep["repeatability"] = {"sites": int(len(d0)), "sd_points": float(d0.std(ddof=1)), "mean_points": float(d0.mean()),
                                "mdc95_points": float(1.96 * d0.std(ddof=1)),
                                "note": "SD of the change measured on no-change pairs already includes both readings, so "
                                        "MDC95 = 1.96 x SD (no extra sqrt 2)"}
    reg = [r["registered"] == "True" for r in test]
    rep["registration_success_share_of_site_rows"] = float(np.mean(reg)) if reg else None
    for d in DELTAS:
        m = np.array([e["true"] in (0.0, d) for e in teeth])
        if m.any():
            pos = np.array([e["true"] == d for e in teeth])[m]
            bal = 0.5 * (flag[m][pos].mean() + (~flag[m][~pos]).mean())
            rep.setdefault("balanced_accuracy_vs_no_change", {})[f"{d:g}"] = float(bal)
    json.dump(rep, open(args.out, "w", encoding="utf-8"), indent=2, default=float)
    print(json.dumps(rep, indent=2, default=float))
    if args.write_calibration:
        import datetime as dt

        from app import config
        from app.security.model_signing import Signer

        cal = {"change_threshold_points": round(adaptive[2], 3), "false_alarm_target": args.false_alarm,
               "adaptive": {"split_disagreement_points": round(adaptive[0], 3), "threshold_low": round(adaptive[1], 3),
                            "threshold_high": round(adaptive[2], 3)},
               "rule": "paired_site_repeatability: a tooth changed when a side measured in both visits moved by more "
                       "than the threshold",
               "created": dt.datetime.now(dt.timezone.utc).isoformat(),
               "source": "research/progression_bench.py: DenPAR validation films, no-change re-takes "
                         f"({len(nc)} teeth); bench results on test films in docs/evidence/progression_bench.json",
               "bench_test": {k: rep[k] for k in ("specificity_no_change", "sensitivity_by_true_change", "repeatability")
                              if k in rep}}
        path = config.WEIGHTS_DIR / "progression_calibration.json"
        json.dump(cal, open(path, "w", encoding="utf-8"), indent=2, default=float)
        Signer().sign_manifest(str(config.WEIGHTS_DIR))
        print(f"wrote and signed {path}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--denpar", default="~/Downloads/DenPAR/Dataset")
    r.add_argument("--split", choices=("val", "test"), required=True)
    r.add_argument("--films", type=int, default=100)
    r.add_argument("--nochange", type=int, default=1, help="no-change re-takes per film")
    r.add_argument("--val-changes", action="store_true", help="also simulate changes on validation films")
    r.add_argument("--seed", type=int, default=0)
    r.add_argument("--shard", help="k/n: process every n-th film starting at k (parallel runs)")
    r.add_argument("--out", required=True)
    s = sub.add_parser("summary")
    s.add_argument("--val", nargs="+", required=True)
    s.add_argument("--test", nargs="+", required=True)
    s.add_argument("--false-alarm", type=float, default=0.05)
    s.add_argument("--write-calibration", action="store_true",
                   help="write the threshold to weights/progression_calibration.json and re-sign the manifest")
    s.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    return run(args) if args.cmd == "run" else summary(args)


if __name__ == "__main__":
    sys.exit(main())
