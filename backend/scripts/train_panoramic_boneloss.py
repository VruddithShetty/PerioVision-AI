"""Panoramic whole-film bone-loss models (CPU-trainable), validated on held-out data.

Stage 1  --task screen : generalised crestal bone loss yes/no for the maxilla and the mandible, trained on
         ToothXpert MM-OPG (huggingface.co/datasets/jeffrey423/ToothXpert.MM-OPG-Annotations, ~9,200 films,
         Apache-2.0), tested on its official held-out test split (450 films).
Stage 2  --task severity : worst-tooth radiographic bone loss (% of root length) regressed from the whole film,
         fine-tuned from the stage-1 network on BRAR (figshare 10.6084/m9.figshare.30155974, 988 films,
         CC BY 4.0); split 70 / 15 / 15 by patient, stratified by BRAR level; the 15 % test split is never used
         for training or model selection. The validation split also sets a split-conformal interval.

Network: ImageNet-pretrained ResNet-18 (torchvision), grey film resized to 512 x 256, replicated to 3 channels.
Outputs (to --out): weights (.pt state_dict) and a metrics JSON. Nothing here is used by the app until its
test metrics pass the bar in docs/MODEL_CARD.md.

Usage (from backend/):
  python scripts/train_panoramic_boneloss.py --task screen --data ~/Downloads/MM-OPG --out weights/panoramic_screen
  python scripts/train_panoramic_boneloss.py --task severity --data ~/Downloads/BRAR/data \\
         --init weights/panoramic_screen.pt --out weights/panoramic_severity
"""
import argparse
import os as _os

_os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")   # before torch initialises CUDA
import json
import math
import os
import random
import time
import zipfile

import cv2
import numpy as np
import torch
import torch.nn as nn
import torchvision

W, H = 512, 256                   # overridden by --size
MEAN, STD = 0.449, 0.226          # ImageNet grey mean / std
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def prep(gray: np.ndarray) -> np.ndarray:
    gray = gray.reshape(gray.shape[:2])
    return cv2.resize(gray, (W, H), interpolation=cv2.INTER_AREA)


def to_tensor(batch: np.ndarray) -> torch.Tensor:
    x = torch.from_numpy(np.ascontiguousarray(batch)).to(DEVICE).float().div_(255.0).sub_(MEAN).div_(STD)
    return x.unsqueeze(1).expand(-1, 3, -1, -1).contiguous()


def augment(img: np.ndarray, rng: random.Random) -> np.ndarray:
    if rng.random() < 0.5:
        img = img[:, ::-1]                         # left-right mirror keeps both jaw labels
    a, b = rng.uniform(0.8, 1.2), rng.uniform(-20, 20)
    img = np.clip(img.astype(np.float32) * a + b, 0, 255)
    m = cv2.getRotationMatrix2D((W / 2, H / 2), rng.uniform(-4, 4), rng.uniform(0.95, 1.05))
    m[:, 2] += (rng.uniform(-12, 12), rng.uniform(-8, 8))
    return cv2.warpAffine(img, m, (W, H), borderMode=cv2.BORDER_REFLECT).astype(np.uint8)


ARCH = "resnet18"                 # overridden by --arch


def network(outputs: int) -> nn.Module:
    """ImageNet-pretrained backbone with a fresh head of `outputs` units (attribute `head` for re-heading)."""
    m = torchvision.models
    if ARCH == "resnet18":
        net = m.resnet18(weights=m.ResNet18_Weights.IMAGENET1K_V1)
        net.fc = nn.Linear(net.fc.in_features, outputs)
    elif ARCH == "resnet50":
        net = m.resnet50(weights=m.ResNet50_Weights.IMAGENET1K_V2)
        net.fc = nn.Linear(net.fc.in_features, outputs)
    elif ARCH == "efficientnet_b3":
        net = m.efficientnet_b3(weights=m.EfficientNet_B3_Weights.IMAGENET1K_V1)
        net.classifier[-1] = nn.Linear(net.classifier[-1].in_features, outputs)
    elif ARCH == "convnext_tiny":
        net = m.convnext_tiny(weights=m.ConvNeXt_Tiny_Weights.IMAGENET1K_V1)
        net.classifier[-1] = nn.Linear(net.classifier[-1].in_features, outputs)
    else:
        raise ValueError(ARCH)
    return net.to(DEVICE)


def rehead(net: nn.Module, outputs: int) -> nn.Module:
    if hasattr(net, "fc"):
        net.fc = nn.Linear(net.fc.in_features, outputs)
    else:
        net.classifier[-1] = nn.Linear(net.classifier[-1].in_features, outputs)
    return net.to(DEVICE)


def auc(y, p) -> float:
    y, p = np.asarray(y), np.asarray(p)
    pos, neg = p[y == 1], p[y == 0]
    if not len(pos) or not len(neg):
        return float("nan")
    order = np.argsort(np.concatenate([pos, neg]))
    ranks = np.empty(len(order)); ranks[order] = np.arange(1, len(order) + 1)
    return float((ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


# ---------------------------------------------------------------- data
def load_mmopg(folder: str):
    labels = {}
    for split, name in (("train", "mmopg_train.json"), ("test", "mmopg_test.json")):
        for it in json.load(open(os.path.join(folder, name), encoding="utf-8")):
            q = it["conversations"][0]["value"].lower()
            if "generalised crestal bone loss" not in q:
                continue
            jaw = 0 if "maxill" in q else 1
            yes = it["conversations"][1]["value"].strip().lower().startswith("yes")
            labels.setdefault((split, it["image"]), [None, None])[jaw] = int(yes)
    zf = zipfile.ZipFile(os.path.join(folder, "images.zip"))
    names = {os.path.basename(n): n for n in zf.namelist() if n.lower().endswith((".jpg", ".png", ".jpeg"))}
    out = {"train": [], "test": []}
    for (split, img), (mx, md) in labels.items():
        if mx is None or md is None or img not in names:
            continue
        g = cv2.imdecode(np.frombuffer(zf.read(names[img]), np.uint8), cv2.IMREAD_GRAYSCALE)
        if g is not None:
            out[split].append((prep(g), np.array([mx, md], np.float32), img))
    return out


def load_brar(folder: str):
    import pandas as pd

    meta = pd.read_csv(os.path.join(folder, "meta_data.csv"))
    rows = []
    for _, m in meta.iterrows():
        path = os.path.join(folder, f"level_{int(m['Level'])}", m["File name"])
        g = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if g is not None:
            rows.append((prep(g), np.array([float(m["Bone resorption"]) * 100.0], np.float32), m["File name"],
                         int(m["Level"]), int(m["Age"])))
    rng = random.Random(0)  # audit-ok: seeded patient-level split
    split = {"train": [], "val": [], "test": []}
    for lv in (1, 2, 3):
        group = [r for r in rows if r[3] == lv]
        rng.shuffle(group)
        n = len(group)
        split["train"] += group[: int(0.7 * n)]
        split["val"] += group[int(0.7 * n): int(0.85 * n)]
        split["test"] += group[int(0.85 * n):]
    return split


# ---------------------------------------------------------------- training
def run_epochs(net, train, val_fn, loss_fn, epochs, lr, batch=32, seed=0, ckpt=None):
    """Train; keep the best epoch by validation score. With `ckpt`, state is saved after every epoch and a
    rerun resumes from it (Colab disconnects lose nothing but the current epoch)."""
    rng = random.Random(seed)  # audit-ok: seeded shuffling / augmentation
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=1e-4)
    steps = epochs * math.ceil(len(train) / batch)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=steps, pct_start=0.15)
    scaler = torch.amp.GradScaler(enabled=DEVICE == "cuda")
    best, best_state, start = None, None, 0
    if ckpt and os.path.exists(ckpt):
        c = torch.load(ckpt, map_location=DEVICE, weights_only=False)
        net.load_state_dict(c["net"]); opt.load_state_dict(c["opt"]); sched.load_state_dict(c["sched"])
        scaler.load_state_dict(c["scaler"]); rng.setstate(c["rng"])
        best, best_state, start = c["best"], c["best_state"], c["epoch"]
        print(f"resuming after epoch {start} (best val {best:.4f})", flush=True)
    for ep in range(start, epochs):
        net.train()
        rng.shuffle(train)
        t0, tot = time.time(), 0.0
        for i in range(0, len(train), batch):
            chunk = train[i:i + batch]
            x = to_tensor(np.stack([augment(r[0], rng) for r in chunk]))
            y = torch.from_numpy(np.stack([r[1] for r in chunk])).to(DEVICE)
            with torch.autocast(DEVICE, dtype=torch.float16 if DEVICE == "cuda" else torch.bfloat16, enabled=DEVICE == "cuda"):
                out = net(x)
            loss = loss_fn(out.float(), y)
            opt.zero_grad()
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            sched.step()
            tot += loss.item() * len(chunk)
        if DEVICE == "cuda":
            torch.cuda.empty_cache()
        score = val_fn(net)
        print(f"epoch {ep + 1}/{epochs} loss {tot / len(train):.4f} val {score:.4f} ({time.time() - t0:.0f}s)", flush=True)
        if best is None or score > best:
            best, best_state = score, {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}
        if ckpt:
            torch.save({"net": net.state_dict(), "opt": opt.state_dict(), "sched": sched.state_dict(),
                        "scaler": scaler.state_dict(), "rng": rng.getstate(), "best": best,
                        "best_state": best_state, "epoch": ep + 1}, ckpt + ".tmp")
            os.replace(ckpt + ".tmp", ckpt)
    net.load_state_dict(best_state)
    return best


@torch.inference_mode()
def predict(net, rows, batch=8):
    """Small batches in half precision: full-size panoramic films at 1024 x 512 need a lot of GPU memory."""
    net.eval()
    out = []
    for i in range(0, len(rows), batch):
        with torch.autocast(DEVICE, dtype=torch.float16, enabled=DEVICE == "cuda"):
            y = net(to_tensor(np.stack([r[0] for r in rows[i:i + batch]])))
        out.append(y.float().cpu().numpy())
    if DEVICE == "cuda":
        torch.cuda.empty_cache()
    return np.concatenate(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", choices=("screen", "severity"), required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--init")
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--arch", default="resnet18", choices=("resnet18", "resnet50", "efficientnet_b3", "convnext_tiny"))
    ap.add_argument("--size", type=int, nargs=2, default=(512, 256), metavar=("W", "H"))
    ap.add_argument("--batch", type=int, default=32)
    args = ap.parse_args()
    global W, H, ARCH
    W, H, ARCH = args.size[0], args.size[1], args.arch
    torch.manual_seed(0)
    data = os.path.expanduser(args.data)

    if args.task == "screen":
        d = load_mmopg(data)
        rng = random.Random(1)  # audit-ok: seeded validation hold-out
        rng.shuffle(d["train"])
        nval = len(d["train"]) // 10
        val, train, test = d["train"][:nval], d["train"][nval:], d["test"]
        print(f"MM-OPG films: train {len(train)}, val {len(val)}, test {len(test)}")
        net = network(2)
        crit = nn.BCEWithLogitsLoss()

        def val_auc(n):
            p = predict(n, val)
            y = np.stack([r[1] for r in val])
            return float(np.nanmean([auc(y[:, j], p[:, j]) for j in (0, 1)]))

        run_epochs(net, train, val_auc, crit, args.epochs, args.lr, args.batch, ckpt=os.path.expanduser(args.out) + ".ckpt")
        pv, yv = 1 / (1 + np.exp(-predict(net, val))), np.stack([r[1] for r in val])
        pt, yt = 1 / (1 + np.exp(-predict(net, test))), np.stack([r[1] for r in test])
        metrics = {"task": "generalised crestal bone loss, per jaw", "dataset": "ToothXpert MM-OPG (Apache-2.0)",
                   "train_films": len(train), "val_films": len(val), "test_films": len(test), "jaws": {}}
        for j, jaw in enumerate(("maxilla", "mandible")):
            thr = max(np.linspace(0.05, 0.95, 91), key=lambda t: ((pv[:, j] >= t) & (yv[:, j] == 1)).sum() / max(1, (yv[:, j] == 1).sum())
                      + ((pv[:, j] < t) & (yv[:, j] == 0)).sum() / max(1, (yv[:, j] == 0).sum()))   # Youden on val
            pred = pt[:, j] >= thr
            pos, neg = yt[:, j] == 1, yt[:, j] == 0
            metrics["jaws"][jaw] = {"test_auc": round(auc(yt[:, j], pt[:, j]), 4), "threshold_from_val": round(float(thr), 3),
                                    "test_sensitivity": round(float(pred[pos].mean()), 4),
                                    "test_specificity": round(float((~pred[neg]).mean()), 4),
                                    "test_accuracy": round(float((pred == pos).mean()), 4),
                                    "test_prevalence": round(float(pos.mean()), 4)}
    else:
        d = load_brar(data)
        train, val, test = d["train"], d["val"], d["test"]
        print(f"BRAR films: train {len(train)}, val {len(val)}, test {len(test)}")
        net = network(2)
        if args.init:
            net.load_state_dict(torch.load(os.path.expanduser(args.init), map_location=DEVICE))
        net = rehead(net, 1)
        crit = nn.SmoothL1Loss(beta=5.0)

        def val_neg_mae(n):
            return -float(np.mean(np.abs(predict(n, val)[:, 0] - np.array([r[1][0] for r in val]))))

        run_epochs(net, train, val_neg_mae, crit, args.epochs, args.lr, args.batch, ckpt=os.path.expanduser(args.out) + ".ckpt")
        st = lambda p: "I" if p < 15 else "II" if p <= 33 else "III"  # noqa: E731
        pv = np.clip(predict(net, val)[:, 0], 0, 100); yv = np.array([r[1][0] for r in val])
        pt = np.clip(predict(net, test)[:, 0], 0, 100); yt = np.array([r[1][0] for r in test])
        scores = np.sort(np.abs(pv - yv))
        q = float(scores[min(len(scores) - 1, math.ceil((len(scores) + 1) * 0.9) - 1)])   # split-conformal 90 %
        sets = [[s for s, (a, b) in {"I": (0, 15), "II": (15, 33), "III": (33, 100)}.items()
                 if min(100, p + q) >= a and max(0, p - q) <= b] for p in pt]
        mean_only = float(np.mean([r[1][0] for r in train]))
        metrics = {"task": "worst-tooth radiographic bone loss % from the whole panoramic film",
                   "dataset": "BRAR (CC BY 4.0), expert worst-tooth bone loss / root length",
                   "train_films": len(train), "val_films": len(val), "test_films": len(test),
                   "test_MAE": round(float(np.mean(np.abs(pt - yt))), 3),
                   "test_median_abs_error": round(float(np.median(np.abs(pt - yt))), 3),
                   "test_MAE_predicting_training_mean": round(float(np.mean(np.abs(mean_only - yt))), 3),
                   "test_stage_agreement": round(float(np.mean([st(a) == st(b) for a, b in zip(pt, yt)])), 4),
                   "test_grade_agreement": round(float(np.mean([
                       (("A" if a / g < 0.25 else "B" if a / g <= 1 else "C") == ("A" if b / g < 0.25 else "B" if b / g <= 1 else "C"))
                       for a, b, g in zip(pt, yt, [r[4] for r in test])])), 4),
                   "conformal_q90_from_val": round(q, 3),
                   "test_interval_coverage": round(float(np.mean(np.abs(pt - yt) <= q)), 4),
                   "test_reference_stage_in_set": round(float(np.mean([st(b) in s for b, s in zip(yt, sets)])), 4),
                   "test_set_sizes": {str(k): sum(len(s) == k for s in sets) for k in (1, 2, 3)}}
    out = os.path.expanduser(args.out)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    metrics.update({"arch": ARCH, "input_size": [W, H]})
    torch.save(net.state_dict(), out + ".pt")
    with open(out + "_metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    if os.path.exists(out + ".ckpt"):
        os.remove(out + ".ckpt")              # training finished: the resume checkpoint is no longer needed
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
