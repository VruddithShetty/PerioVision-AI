"""Write one row per test item (film, jaw, person) for every model, so confidence intervals, confusion
matrices and error analysis can be computed from real predictions instead of summary numbers.

Sub-commands (run from backend/; all work on CPU, faster with a GPU; no GUI):

  brar-severity  Panoramic worst-tooth bone loss on the BRAR test split. The split is rebuilt exactly as in
                 training (seed 0, stratified by level; checked by research.split_audit). Also writes the
                 validation films, labelled split=val, for calibration work.
  mmopg-screen   Panoramic bone-loss screen (maxilla / mandible) on the official MM-OPG 450-film test split.
  nhanes-risk    Clinical risk model on the NHANES 2013-14 temporal test cycle (both model variants).
  yolo-detector  Tooth detector on any YOLO-format test folder (e.g. the DENTEX test split): per-film
                 true / false positives, misses and correct FDI numbers.

Every model file is checked against the signed manifest's SHA-256 before use, so the numbers belong to the
deployed weights.

Examples:
  python -m research.export_predictions brar-severity --data ~/Downloads/BRAR/data --out ../docs/evidence/predictions/brar_severity_per_film.csv
  python -m research.export_predictions mmopg-screen --data ~/Downloads/MM-OPG --out ../docs/evidence/predictions/mmopg_screen_per_film.csv
  python -m research.export_predictions nhanes-risk --data ~/Downloads/NHANES --out ../docs/evidence/predictions/nhanes_risk_per_person.csv
  python -m research.export_predictions yolo-detector --images DENTEX/images/test --labels DENTEX/labels/test \
      --names dentex_fdi.yaml --out ../docs/evidence/predictions/dentex_detector_per_film.csv
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))  # backend/

import cv2  # noqa: E402
import numpy as np  # noqa: E402

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MEAN, STD = 0.449, 0.226


def _weights_dir(arg: str | None) -> str:
    return os.path.abspath(os.path.expanduser(arg or os.path.join(BACKEND, "weights")))


def verified_path(weights_dir: str, name: str) -> str:
    """Path of a weight file whose SHA-256 matches the signed manifest (refuses anything else)."""
    path = os.path.join(weights_dir, name)
    manifest = json.load(open(os.path.join(weights_dir, "manifest.json"), encoding="utf-8"))
    want = manifest["files"][name]["sha256"]
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    if h.hexdigest() != want:
        raise SystemExit(f"{name}: SHA-256 does not match the manifest; refusing to evaluate an unknown model.")
    return path


def _write(rows: list[dict], out: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    print(f"wrote {len(rows)} rows to {out}")


def _whole_film_net(weights_dir: str, name: str, outputs: int):
    import torch

    from app.ml.panoramic.whole_film import _network

    metrics = json.load(open(os.path.join(weights_dir, f"{name}_metrics.json"), encoding="utf-8"))
    net = _network(metrics["arch"], outputs)
    net.load_state_dict(torch.load(verified_path(weights_dir, f"{name}.pt"), map_location="cpu", weights_only=True))
    device = "cuda" if torch.cuda.is_available() else "cpu"
    return net.to(device).eval(), metrics, device


def _predict(net, device, grays: list[np.ndarray], size, batch: int = 8) -> np.ndarray:
    """Same preprocessing as training and the app: INTER_AREA resize, grey -> 3 channels, fixed mean / std."""
    import torch

    w, h = size
    out = []
    with torch.inference_mode():
        for i in range(0, len(grays), batch):
            x = np.stack([cv2.resize(g.reshape(g.shape[:2]), (w, h), interpolation=cv2.INTER_AREA) for g in grays[i:i + batch]])
            t = torch.from_numpy(x).float().div_(255.0).sub_(MEAN).div_(STD).unsqueeze(1).expand(-1, 3, -1, -1)
            out.append(net(t.contiguous().to(device)).float().cpu().numpy())
            print(f"  {min(i + batch, len(grays))}/{len(grays)}", flush=True)
    return np.concatenate(out)


# ------------------------------------------------------------------ BRAR
def brar_severity(args) -> int:
    import pandas as pd

    from research.split_audit import load_brar

    wd = _weights_dir(args.weights)
    net, metrics, device = _whole_film_net(wd, "panoramic_severity", 1)
    data = os.path.expanduser(args.data)
    meta = pd.read_csv(os.path.join(data, "meta_data.csv")).set_index("File name")
    rows = [r for r in load_brar(data) if r["split"] in ("test", "val")]
    grays = [cv2.imread(r["image"], cv2.IMREAD_GRAYSCALE) for r in rows]
    pred = np.clip(_predict(net, device, grays, metrics["input_size"])[:, 0], 0, 100)
    out = []
    for r, p, g in zip(rows, pred, grays):
        m = meta.loc[os.path.basename(r["image"])]
        out.append({"film": os.path.basename(r["image"]), "split": r["split"], "brar_level": int(m["Level"]),
                    "age": int(m["Age"]), "sex_code": int(m["Gender"]), "ref_pct": round(float(m["Bone resorption"]) * 100, 3),
                    "pred_pct": round(float(p), 3), "missing_teeth": int(m["Number of missing teeth"]),
                    "implants": int(m["Implant"]), "residual_roots": int(m["Residual root"]),
                    "functional_tooth_pairs": int(m["Functional tooth logarithm"]),
                    "image_w": g.shape[1], "image_h": g.shape[0]})
    test = [o for o in out if o["split"] == "test"]
    mae = float(np.mean([abs(o["pred_pct"] - o["ref_pct"]) for o in test]))
    print(f"BRAR test films {len(test)}; MAE {mae:.3f} (metrics file says {metrics['test_MAE']})")
    if abs(mae - metrics["test_MAE"]) > 0.05:
        print("WARNING: does not reproduce the metrics file; the split or preprocessing differs.")
    _write(out, args.out)
    return 0


# ------------------------------------------------------------------ MM-OPG
def mmopg_screen(args) -> int:
    wd = _weights_dir(args.weights)
    net, metrics, device = _whole_film_net(wd, "panoramic_screen", 2)
    folder = os.path.expanduser(args.data)
    labels = {}
    for it in json.load(open(os.path.join(folder, "mmopg_test.json"), encoding="utf-8")):
        q = it["conversations"][0]["value"].lower()
        if "generalised crestal bone loss" not in q:
            continue
        jaw = 0 if "maxill" in q else 1
        labels.setdefault(it["image"], [None, None])[jaw] = int(it["conversations"][1]["value"].strip().lower().startswith("yes"))
    zf = zipfile.ZipFile(os.path.join(folder, "images.zip"))
    names = {os.path.basename(n): n for n in zf.namelist() if n.lower().endswith((".jpg", ".png", ".jpeg"))}
    films = [(img, lab) for img, lab in sorted(labels.items()) if None not in lab and img in names]
    grays = [cv2.imdecode(np.frombuffer(zf.read(names[img]), np.uint8), cv2.IMREAD_GRAYSCALE) for img, _ in films]
    keep = [i for i, g in enumerate(grays) if g is not None]
    films, grays = [films[i] for i in keep], [grays[i] for i in keep]
    prob = 1 / (1 + np.exp(-_predict(net, device, grays, metrics["input_size"])))
    out = []
    for (img, lab), p, g in zip(films, prob, grays):
        for j, jaw in enumerate(("maxilla", "mandible")):
            out.append({"film": img, "jaw": jaw, "y": lab[j], "prob": round(float(p[j]), 5),
                        "threshold_from_val": metrics["jaws"][jaw]["threshold_from_val"],
                        "image_w": g.shape[1], "image_h": g.shape[0]})
    print(f"MM-OPG test films {len(films)} (metrics file says {metrics['test_films']})")
    _write(out, args.out)
    return 0


# ------------------------------------------------------------------ NHANES
def nhanes_risk(args) -> int:
    sys.path.insert(0, os.path.join(BACKEND, "scripts"))
    from train_risk_model_nhanes import load_cycle  # noqa: E402

    model = json.load(open(os.path.join(BACKEND, "app", "ml", "fusion", "risk_model_nhanes.json"), encoding="utf-8"))
    test = load_cycle(os.path.expanduser(args.data), "H")
    out = []
    for name, m in model["models"].items():
        d = test.dropna(subset=m["features"])
        z = m["intercept"] + sum(d[f].to_numpy() * c for f, c in m["coefficients"].items())
        p = 1 / (1 + np.exp(-z))
        for seqn, y, pp, age in zip(d.index, d["perio"], p, d["age"]):
            out.append({"model": name, "row": int(seqn), "y": int(y), "prob": round(float(pp), 6), "age": int(age)})
        from research.stats import auc
        print(f"{name}: n={len(d)} AUC {auc(d['perio'].to_numpy(), p):.4f} (model file says {m['test']['roc_auc']})")
    _write(out, args.out)
    return 0


# ------------------------------------------------------------------ YOLO detector (DENTEX test)
def yolo_detector(args) -> int:
    import glob

    import yaml

    from app.ml.landmarks.cej_abc_extractor import _iou
    from app.services import container

    det = container.tooth_detector()
    if not det.available:
        raise SystemExit("Tooth detector not available (weights missing or signature refused).")
    names = yaml.safe_load(open(os.path.expanduser(args.names), encoding="utf-8"))["names"]
    names = names if isinstance(names, dict) else dict(enumerate(names))
    out = []
    for img_path in sorted(glob.glob(os.path.join(os.path.expanduser(args.images), "*"))):
        stem = os.path.splitext(os.path.basename(img_path))[0]
        lab = os.path.join(os.path.expanduser(args.labels), stem + ".txt")
        img = cv2.imread(img_path)
        if img is None or not os.path.exists(lab):
            continue
        h, w = img.shape[:2]
        gt = []
        for line in open(lab, encoding="utf-8"):
            c, cx, cy, bw, bh = map(float, line.split()[:5])
            gt.append({"fdi": str(names[int(c)]), "bbox": [(cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h]})
        pred, used, tp, right = det.detect_teeth(img), set(), 0, 0
        for g in gt:
            best = max(((i, _iou(g["bbox"], p["bbox"])) for i, p in enumerate(pred) if i not in used),
                       key=lambda x: x[1], default=(None, 0.0))
            if best[0] is not None and best[1] >= 0.5:
                used.add(best[0])
                tp += 1
                right += pred[best[0]]["tooth_id"] == g["fdi"]
        out.append({"film": stem, "teeth_gt": len(gt), "tp": tp, "fp": len(pred) - len(used), "fn": len(gt) - tp,
                    "right_number": right, "image_w": w, "image_h": h})
    _write(out, args.out)
    return 0


def dentex_disease(args) -> int:
    """Deployed detector on the DENTEX challenge's official DISEASE test set (250 films). Only diseased teeth are
    outlined (label '<condition>-<name>-<FDI>'), so this measures recall with the right FDI number on those
    teeth; precision cannot be measured (healthy teeth are unlabelled)."""
    import glob

    from app.ml.landmarks.cej_abc_extractor import _iou
    from app.services import container

    det = container.tooth_detector()
    if not det.available:
        raise SystemExit("Tooth detector not available (weights missing or signature refused).")
    root = os.path.expanduser(args.data)
    out = []
    for lab in sorted(glob.glob(os.path.join(root, "label", "*.json"))):
        stem = os.path.splitext(os.path.basename(lab))[0]
        imgs = glob.glob(os.path.join(root, "input", stem + ".*"))
        img = cv2.imread(imgs[0]) if imgs else None
        if img is None:
            continue
        gt = []
        for s in json.load(open(lab, encoding="utf-8"))["shapes"]:
            fdi = str(s["label"]).rsplit("-", 1)[-1]
            p = np.asarray(s["points"], float)
            gt.append({"fdi": fdi, "bbox": [p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()]})
        pred, used, found, right = det.detect_teeth(img), set(), 0, 0
        for g in gt:
            best = max(((i, _iou(g["bbox"], p["bbox"])) for i, p in enumerate(pred) if i not in used),
                       key=lambda x: x[1], default=(None, 0.0))
            if best[0] is not None and best[1] >= 0.5:
                used.add(best[0])
                found += 1
                right += pred[best[0]]["tooth_id"] == g["fdi"]
        out.append({"film": stem, "teeth_gt": len(gt), "tp": found, "fn": len(gt) - found, "right_number": right,
                    "image_w": img.shape[1], "image_h": img.shape[0]})
    tot = sum(o["teeth_gt"] for o in out)
    print(f"films {len(out)}, diseased teeth {tot}, found with right number "
          f"{sum(o['right_number'] for o in out) / max(tot, 1):.4f}")
    _write(out, args.out)
    return 0


def pdcnn_brar(args) -> int:
    """External check of the PDCNN per-tooth bone-loss detector (Model C) on BRAR films it never saw.
    Per film: the most severe class among detected teeth (conf >= 0.25), next to BRAR's expert worst-tooth %."""
    import pandas as pd
    from ultralytics import YOLO

    from research.split_audit import load_brar

    model = YOLO(os.path.expanduser(args.model))
    names = model.names
    data = os.path.expanduser(args.data)
    meta = pd.read_csv(os.path.join(data, "meta_data.csv")).set_index("File name")
    rows = [r for r in load_brar(data) if r["split"] == args.split]
    out = []
    for n, r in enumerate(rows, 1):
        res = model.predict(r["image"], imgsz=args.imgsz, conf=0.25, verbose=False)[0]
        cls = [names[int(c)] for c in res.boxes.cls.tolist()] if res.boxes is not None else []
        m = meta.loc[os.path.basename(r["image"])]
        order = ["healthy", "mild", "medium", "severe"]
        worst = max(cls, key=order.index) if cls else "none"
        out.append({"film": os.path.basename(r["image"]), "ref_pct": round(float(m["Bone resorption"]) * 100, 3),
                    "brar_level": int(m["Level"]), "teeth_detected": len(cls), "worst_class": worst,
                    **{f"n_{c}": cls.count(c) for c in order}})
        if n % 25 == 0:
            print(f"  {n}/{len(rows)}", flush=True)
    _write(out, args.out)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("brar-severity", "mmopg-screen", "nhanes-risk"):
        s = sub.add_parser(name)
        s.add_argument("--data", required=True)
        s.add_argument("--out", required=True)
        s.add_argument("--weights", help="weights folder (default backend/weights)")
    s = sub.add_parser("yolo-detector")
    s.add_argument("--images", required=True)
    s.add_argument("--labels", required=True)
    s.add_argument("--names", required=True, help="the dataset YAML whose 'names' map class index -> FDI number")
    s.add_argument("--out", required=True)
    s = sub.add_parser("pdcnn-brar")
    s.add_argument("--model", required=True)
    s.add_argument("--data", required=True)
    s.add_argument("--split", default="test")
    s.add_argument("--imgsz", type=int, default=1024)
    s.add_argument("--out", required=True)
    s = sub.add_parser("dentex-disease")
    s.add_argument("--data", required=True, help="DENTEX_test/disease (with input/ and label/)")
    s.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "pdcnn-brar":
        return pdcnn_brar(args)
    if args.cmd == "dentex-disease":
        return dentex_disease(args)
    return {"brar-severity": brar_severity, "mmopg-screen": mmopg_screen, "nhanes-risk": nhanes_risk,
            "yolo-detector": yolo_detector}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
