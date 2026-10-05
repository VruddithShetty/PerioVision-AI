"""Conformal calibration of per-tooth bone-loss % on a labelled held-out set.

For every image it runs the SAME pipeline as the app (analysis_service.locate_teeth: panoramic
detector, then the periapical keypoint path, mirrored test-time augmentation; teeth the app would
report as "not measured" are skipped), matches each labelled tooth (box IoU >= 0.5), and compares
bone loss from predicted vs labelled CEJ / apex / crest keypoints.

Default (--method adaptive), normalised split conformal:
  1. the calibration split is halved (fixed seed);
  2. half A fits sigma(x) = max(floor, a + b * d), where d = the tooth's disagreement between the
     normal and mirrored readings (percentage points);
  3. half B gives the scores |error| / sigma(x) that set q;
  4. --test-images/--test-labels (a split NOT used above) measures the coverage actually reached.
  5. Asymmetric margins (default): half B also stores signed scores (reference - predicted) / sigma(x); each
     side of the interval gets its own quantile at 1 - alpha / 2 (coverage >= 1 - alpha by the union bound).
     The landmark model underestimates severe bone loss, so the upper margin is wider. Coverage is reported
     per reference stage for both the symmetric and the asymmetric interval, and the manifest is re-signed.
--method standard keeps fixed-width intervals (q from half B, sigma = 1).

The previous calibration file is kept as a timestamped backup next to it.

Usage (from backend/), e.g. DenPAR:
    python scripts/calibrate_conformal.py --images <pose>/images/val --labels <pose>/labels/val \\
        --test-images <pose>/images/test --test-labels <pose>/labels/test --source "DenPAR ..."
Label format per line: class cx cy w h  cej_x cej_y v  apex_x apex_y v  crest_x crest_y v (normalised).
IMPORTANT: coverage is only as meaningful as the labels. Write down where they came from with --source.
"""
import argparse
import datetime as dt
import glob
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))  # backend/

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from app import config  # noqa: E402
from app.ml.landmarks.cej_abc_extractor import _iou  # noqa: E402
from app.ml.measurement.bone_loss import bone_loss_for_tooth  # noqa: E402
from app.ml.uncertainty import calibration  # noqa: E402
from app.ml.uncertainty.conformal import conformal_quantile  # noqa: E402
from app.services import container  # noqa: E402
from app.services.analysis_service import locate_teeth, measured  # noqa: E402
from evaluate_landmarks import read_labels  # noqa: E402  (same folder)

LEVELS = (0.8, 0.9, 0.95)


def collect(images: str, labels: str, limit: int = 0) -> list[dict]:
    files = sorted(glob.glob(os.path.join(images, "*.jpg")) + glob.glob(os.path.join(images, "*.png")))
    files = files[:limit] if limit else files
    rows = []
    for n, img_path in enumerate(files, 1):
        label = os.path.join(labels, os.path.splitext(os.path.basename(img_path))[0] + ".txt")
        gray = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
        if gray is None or not os.path.exists(label):
            continue
        gray = gray.reshape(gray.shape[:2])  # some JPEGs decode as (h, w, 1)
        h, w = gray.shape
        found = locate_teeth(gray)
        dets, lms, used = found["detections"], found["landmarks"], set()
        for ref in read_labels(label, w, h):
            best = max(((i, _iou(d["bbox"], ref["bbox"])) for i, d in enumerate(dets) if i not in used),
                       key=lambda x: x[1], default=(None, 0.0))
            if best[0] is None or best[1] < 0.5:
                continue
            used.add(best[0])
            lm = lms.get(dets[best[0]]["tooth_id"])
            if not measured(lm):
                continue
            p, r = bone_loss_for_tooth(lm)["bone_loss_pct"], bone_loss_for_tooth(ref)["bone_loss_pct"]
            if p is not None and r is not None:
                rows.append({"pred": p, "ref": r, "d": lm.get("tta_disagreement_pct")})
        if n % 20 == 0 or n == len(files):
            print(f"[{n}/{len(files)}] {len(rows)} matched teeth", flush=True)
    return rows


def fit_sigma(rows: list[dict]) -> dict:
    with_d = [r for r in rows if r["d"] is not None]
    d = np.array([r["d"] for r in with_d])
    e = np.array([abs(r["pred"] - r["ref"]) for r in with_d])
    slope, intercept = np.polyfit(d, e, 1)
    floor = float(np.percentile(e, 25))
    spec = {"type": "linear in mirrored-pass disagreement (percentage points)", "intercept": float(intercept),
            "slope": float(max(slope, 0.0)), "floor": floor}
    spec["missing_sigma"] = max(floor, spec["intercept"] + spec["slope"] * float(np.percentile(d, 95)))
    return spec


def sigma(spec: dict | None, d) -> float:
    if not spec:
        return 1.0
    if d is None:
        return spec["missing_sigma"]
    return max(spec["floor"], spec["intercept"] + spec["slope"] * d)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--test-images")
    ap.add_argument("--test-labels")
    ap.add_argument("--method", choices=("adaptive", "standard"), default="adaptive")
    ap.add_argument("--source", default="YOLO-pose validation split (see docs/DATASETS.md)")
    ap.add_argument("--image-type", default="periapical")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    if not container.tooth_detector().available:
        print("ERROR: the tooth detector is not available (missing or unsigned weights). Run scripts/sign_model.py.")
        return 2
    cal = collect(args.images, args.labels, args.limit)
    if len(cal) < 40:
        print(f"ERROR: only {len(cal)} matched teeth; need at least 40 for a meaningful calibration.")
        return 1
    test = collect(args.test_images, args.test_labels, args.limit) if args.test_images else None

    order = np.random.default_rng(0).permutation(len(cal))  # audit-ok: seeded calibration split
    A, B = [cal[i] for i in order[: len(cal) // 2]], [cal[i] for i in order[len(cal) // 2:]]
    spec = fit_sigma(A) if args.method == "adaptive" else None
    held_out = test if test else A                 # coverage on the test split, else the other half
    scores = np.array([abs(r["pred"] - r["ref"]) / sigma(spec, r["d"]) for r in B])
    signed = np.array([(r["ref"] - r["pred"]) / sigma(spec, r["d"]) for r in B])
    err = np.array([abs(r["pred"] - r["ref"]) for r in held_out])
    levels = {}
    for cov in LEVELS:
        q = conformal_quantile(scores, cov)
        hw = np.array([q * sigma(spec, r["d"]) for r in held_out]) if np.isfinite(q) else None
        levels[str(cov)] = {
            "q_from_half": float(q) if np.isfinite(q) else None,
            "empirical_coverage_other_half": round(float(np.mean(err <= hw)), 4) if hw is not None else None,
            "mean_half_width_pct": round(float(hw.mean()), 3) if hw is not None else None,
        }
    ho_pred = np.array([r["pred"] for r in held_out])
    ho_ref = np.array([r["ref"] for r in held_out])
    ho_sig = np.array([sigma(spec, r["d"]) for r in held_out])
    ho_stage = np.where(ho_ref < 15, "I", np.where(ho_ref <= 33, "II", "III"))
    for cov in LEVELS:
        tail = 1 - (1 - cov) / 2
        q_up, q_dn = conformal_quantile(signed, tail), conformal_quantile(-signed, tail)
        lvl = levels[str(cov)]
        if np.isfinite(q_up) and np.isfinite(q_dn):
            q_up, q_dn = max(0.0, float(q_up)), max(0.0, float(q_dn))
            inside = (ho_ref >= ho_pred - q_dn * ho_sig) & (ho_ref <= ho_pred + q_up * ho_sig)
            lvl["asymmetric"] = {"q_lower": round(q_dn, 5), "q_upper": round(q_up, 5),
                                 "coverage": round(float(inside.mean()), 4),
                                 "mean_width_pct": round(float(((q_dn + q_up) * ho_sig).mean()), 3),
                                 "coverage_by_reference_stage": {s: round(float(inside[ho_stage == s].mean()), 4)
                                                                 for s in ("I", "II", "III") if (ho_stage == s).any()}}
        if lvl["q_from_half"] is not None:
            sym = np.abs(ho_ref - ho_pred) <= lvl["q_from_half"] * ho_sig
            lvl["symmetric_coverage_by_reference_stage"] = {s: round(float(sym[ho_stage == s].mean()), 4)
                                                            for s in ("I", "II", "III") if (ho_stage == s).any()}
    data = {
        "created": dt.datetime.now(dt.timezone.utc).isoformat(),
        "method": "normalised split conformal" if spec else "split conformal",
        "source": args.source,
        "notes": (f"q from half of {os.path.basename(os.path.normpath(args.images))} ({len(B)} teeth)"
                  + (f"; sigma fitted on the other half ({len(A)} teeth)" if spec else "")
                  + (f"; coverage measured on {os.path.basename(os.path.normpath(args.test_images))} ({len(test)} teeth)"
                     if test else "; coverage measured on the other calibration half")
                  + ". Predictions use the app pipeline incl. mirrored test-time augmentation."),
        "image_type": args.image_type,
        "n_scores": int(len(scores)),
        "scores": [round(float(s), 5) for s in scores],
        "signed_scores": [round(float(s), 5) for s in signed],
        "sigma": spec,
        "levels": levels,
        "mean_absolute_error_pct": round(float(np.mean(np.abs(ho_pred - ho_ref))), 3),
        "reliability_bins": calibration._bins(ho_pred, ho_ref),
    }
    if config.CALIBRATION_FILE.exists():
        backup = config.CALIBRATION_FILE.with_name(f"conformal_calibration.backup-{dt.datetime.now():%Y%m%d-%H%M%S}.json")
        config.CALIBRATION_FILE.replace(backup)
        print(f"Previous calibration kept as {backup.name}")
    with open(config.CALIBRATION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    try:
        from app.security.model_signing import Signer

        Signer().sign_manifest(config.WEIGHTS_DIR)
        print("Re-signed weights/manifest.json (the calibration file is part of the signed manifest).")
    except Exception as exc:  # the app refuses an unsigned calibration, so say so loudly
        print(f"WARNING: could not re-sign the manifest ({exc}); run scripts/sign_model.py or the app will refuse "
              "this calibration and withhold per-tooth numbers.")
    calibration.reset_cache()
    print(f"Saved {data['method']} calibration: {len(scores)} scores, held-out MAE {data['mean_absolute_error_pct']} points.")
    for cov, lvl in levels.items():
        print(f"  target {cov}: q = {lvl['q_from_half']}  held-out coverage = {lvl['empirical_coverage_other_half']}"
              f"  mean half-width = {lvl['mean_half_width_pct']}  by stage {lvl.get('symmetric_coverage_by_reference_stage')}")
        if "asymmetric" in lvl:
            print(f"    asymmetric: {lvl['asymmetric']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
