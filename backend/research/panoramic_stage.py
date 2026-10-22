"""Per-tooth panoramic bone-loss stage from dentist-graded PDCNN boxes.

Pipeline (all steps reproducible from the COCO export of PDCNN, 1,747 panoramic films, 50,080 teeth):
  1. `build`  crop every graded tooth box (with a margin) to a fixed size, keep its grade (healthy/mild/medium/severe).
  2. `train`  train a small CNN on the crops; films are split 70 / 15 / 15 into train / calibration / test.
  3. `evaluate` split-conformal prediction sets (least-ambiguous set rule) on the calibration films, then coverage,
              set size, accuracy and quadratic-weighted kappa on the held-out test films.

Split by FILM (one film = one source image), so no tooth of a test film is seen in training.
Patients may appear in more than one film; the export has no patient id, which is stated in the report.

Run from backend/:
  python -m research.panoramic_stage build    --coco <via_export_coco_BL.json> --images <Images> --out <dir>
  python -m research.panoramic_stage train    --data <dir> --out <dir> --epochs 40
  python -m research.panoramic_stage evaluate --data <dir> --model <dir>/model.pt --out ../docs/evidence/panoramic_stage_pdcnn.json
"""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

GRADES = ["healthy", "mild", "medium", "severe"]  # ordinal: index = severity
CROP = 96
MARGIN = 0.15
SPLIT_SEED = 0
ALPHA = 0.10  # 90 % target coverage


# ----------------------------------------------------------------------------- build
def build(coco_path: Path, images_dir: Path, out: Path) -> None:
    coco = json.loads(coco_path.read_text(encoding="utf-8"))
    by_image = defaultdict(list)
    for ann in coco["annotations"]:
        by_image[ann["image_id"]].append(ann)
    films = sorted({img["file_name"].split(".tif")[0] for img in coco["images"]})
    rng = random.Random(SPLIT_SEED)
    shuffled = films[:]
    rng.shuffle(shuffled)
    n = len(shuffled)
    split_of = {}
    for i, f in enumerate(shuffled):
        split_of[f] = "train" if i < 0.70 * n else ("cal" if i < 0.85 * n else "test")

    crops, labels, films_out, splits = [], [], [], []
    for img in coco["images"]:
        path = images_dir / img["file_name"]
        gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if gray is None:
            continue
        film = img["file_name"].split(".tif")[0]
        h, w = gray.shape
        for ann in by_image.get(img["id"], []):
            x, y, bw, bh = ann["bbox"]
            mx, my = bw * MARGIN, bh * MARGIN
            x0, y0 = max(0, int(x - mx)), max(0, int(y - my))
            x1, y1 = min(w, int(x + bw + mx)), min(h, int(y + bh + my))
            if x1 - x0 < 4 or y1 - y0 < 4:
                continue
            crop = cv2.resize(gray[y0:y1, x0:x1], (CROP, CROP), interpolation=cv2.INTER_AREA)
            crops.append(crop)
            labels.append(ann["category_id"] - 1)
            films_out.append(film)
            splits.append(split_of[film])

    out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out / "crops.npz", x=np.stack(crops), y=np.array(labels, dtype=np.int64),
                        film=np.array(films_out), split=np.array(splits))
    counts = {s: {g: int(sum(1 for a, b in zip(splits, labels) if a == s and b == k))
                  for k, g in enumerate(GRADES)} for s in ("train", "cal", "test")}
    (out / "build_summary.json").write_text(json.dumps({"films": n, "teeth": len(labels), "crop": CROP,
                                                        "counts": counts, "split_seed": SPLIT_SEED},
                                                       indent=2), encoding="utf-8")
    print(json.dumps(counts, indent=2))


# ----------------------------------------------------------------------------- model
def make_model():
    import torch.nn as nn

    def block(i, o):
        return nn.Sequential(nn.Conv2d(i, o, 3, padding=1, bias=False), nn.BatchNorm2d(o), nn.ReLU(inplace=True),
                             nn.Conv2d(o, o, 3, padding=1, bias=False), nn.BatchNorm2d(o), nn.ReLU(inplace=True),
                             nn.MaxPool2d(2))
    return nn.Sequential(block(1, 32), block(32, 64), block(64, 128), block(128, 192),
                         nn.AdaptiveAvgPool2d(1), nn.Flatten(), nn.Dropout(0.3), nn.Linear(192, len(GRADES)))


def _load(data: Path):
    z = np.load(data / "crops.npz")
    return z["x"], z["y"], z["split"]


def train(data: Path, out: Path, epochs: int, batch: int = 128, lr: float = 2e-3, patience: int = 8,
          limit: int | None = None) -> None:
    import torch
    import torch.nn.functional as F

    torch.manual_seed(SPLIT_SEED)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    x, y, split = _load(data)
    tr, va = split == "train", split == "cal"
    if limit:  # smoke test on a small random subset; the full run never sets this
        keep = np.zeros(len(y), dtype=bool)
        rng = np.random.default_rng(SPLIT_SEED)
        keep[np.flatnonzero(tr)[rng.permutation(tr.sum())[:limit]]] = True
        keep[np.flatnonzero(va)[rng.permutation(va.sum())[:limit // 4]]] = True
        tr, va = tr & keep, va & keep
    xt = torch.tensor(x[tr]).float().div(255).unsqueeze(1)
    yt = torch.tensor(y[tr])
    xv = torch.tensor(x[va]).float().div(255).unsqueeze(1).to(dev)
    yv = torch.tensor(y[va]).to(dev)
    model = make_model().to(dev)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=epochs * ((len(xt) + batch - 1) // batch))
    best, best_state, bad = 1e9, None, 0
    out.mkdir(parents=True, exist_ok=True)
    for ep in range(epochs):
        model.train()
        perm = torch.randperm(len(xt))
        for i in range(0, len(xt), batch):
            idx = perm[i:i + batch]
            xb = xt[idx].to(dev)
            # light augmentation: flips and small brightness/contrast changes (radiographs are not rotated in practice)
            if random.random() < 0.5:
                xb = torch.flip(xb, dims=[3])
            xb = (xb * (0.9 + 0.2 * random.random())).clamp(0, 1)
            loss = F.cross_entropy(model(xb), yt[idx].to(dev), label_smoothing=0.05)
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
        model.eval()
        with torch.no_grad():
            vloss = F.cross_entropy(model(xv), yv).item()
        print(f"epoch {ep + 1}/{epochs} val_loss {vloss:.4f}", flush=True)
        if vloss < best - 1e-4:
            best, bad = vloss, 0
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        else:
            bad += 1
            if bad >= patience:
                print("early stop", flush=True)
                break
    model.load_state_dict(best_state)
    torch.save(model.state_dict(), out / "model.pt")
    print(f"saved {out / 'model.pt'} (best val loss {best:.4f})")


def predict_proba(model_path: Path, x: np.ndarray) -> np.ndarray:
    import torch

    model = make_model()
    model.load_state_dict(torch.load(model_path, map_location="cpu"))
    model.eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(x), 512):
            xb = torch.tensor(x[i:i + 512]).float().div(255).unsqueeze(1)
            p = torch.softmax(model(xb), dim=1) + torch.softmax(model(torch.flip(xb, dims=[3])), dim=1)
            out.append((p / 2).numpy())
    return np.concatenate(out)


# ----------------------------------------------------------------------------- conformal sets
def conformal_threshold(p_cal: np.ndarray, y_cal: np.ndarray, alpha: float) -> float:
    scores = 1.0 - p_cal[np.arange(len(y_cal)), y_cal]
    n = len(scores)
    level = min(1.0, np.ceil((n + 1) * (1 - alpha)) / n)
    return float(np.quantile(scores, level, method="higher"))


def prediction_sets(p: np.ndarray, q: float) -> list[list[int]]:
    return [[k for k in range(len(GRADES)) if 1.0 - row[k] <= q] for row in p]


def _kappa_quadratic(y: np.ndarray, pred: np.ndarray) -> float:
    k = len(GRADES)
    w = np.array([[((i - j) ** 2) / ((k - 1) ** 2) for j in range(k)] for i in range(k)])
    obs = np.zeros((k, k))
    for a, b in zip(y, pred):
        obs[a, b] += 1
    obs /= obs.sum()
    exp = np.outer(obs.sum(1), obs.sum(0))
    return float(1 - (w * obs).sum() / (w * exp).sum())


def evaluate(data: Path, model_path: Path, out: Path, boot: int = 1000) -> None:
    z = np.load(data / "crops.npz")
    x, y, split, films = z["x"], z["y"], z["split"], z["film"]
    cal, test = split == "cal", split == "test"
    p_cal = predict_proba(model_path, x[cal])
    p_test = predict_proba(model_path, x[test])
    y_cal, y_test = y[cal], y[test]
    q = conformal_threshold(p_cal, y_cal, ALPHA)
    sets = prediction_sets(p_test, q)
    covered = np.array([yt in s for yt, s in zip(y_test, sets)])
    size = np.array([len(s) for s in sets])
    pred = p_test.argmax(1)
    acc = (pred == y_test).astype(float)
    rng = np.random.default_rng(SPLIT_SEED)
    idx = rng.integers(0, len(y_test), size=(boot, len(y_test)))
    acc_ci = np.percentile(acc[idx].mean(1), [2.5, 97.5])
    cov_ci = np.percentile(covered[idx].mean(1), [2.5, 97.5])
    report = {
        "dataset": "PDCNN per-tooth grades (dentist labels), panoramic, split by film",
        "teeth_test": int(len(y_test)), "films_test": int(len(set(films[test]))),
        "target_coverage": 1 - ALPHA, "conformal_threshold": q,
        "coverage": float(covered.mean()), "coverage_ci95": cov_ci.tolist(),
        "coverage_by_grade": {GRADES[k]: float(covered[y_test == k].mean()) for k in range(len(GRADES))},
        "mean_set_size": float(size.mean()), "single_grade_share": float((size == 1).mean()),
        "accuracy": float(acc.mean()), "accuracy_ci95": acc_ci.tolist(),
        "quadratic_kappa": _kappa_quadratic(y_test, pred),
        "recall_by_grade": {GRADES[k]: float((pred[y_test == k] == k).mean()) for k in range(len(GRADES))},
        "mean_absolute_grade_error": float(np.abs(pred - y_test).mean()),
        "model": str(model_path.name),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--coco", type=Path, required=True)
    b.add_argument("--images", type=Path, required=True)
    b.add_argument("--out", type=Path, required=True)
    t = sub.add_parser("train")
    t.add_argument("--data", type=Path, required=True)
    t.add_argument("--out", type=Path, required=True)
    t.add_argument("--epochs", type=int, default=40)
    t.add_argument("--limit", type=int, default=None, help="smoke test only: train on a random subset")
    e = sub.add_parser("evaluate")
    e.add_argument("--data", type=Path, required=True)
    e.add_argument("--model", type=Path, required=True)
    e.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.cmd == "build":
        build(a.coco, a.images, a.out)
    elif a.cmd == "train":
        train(a.data, a.out, a.epochs, limit=a.limit)
    else:
        evaluate(a.data, a.model, a.out)


if __name__ == "__main__":
    main()
