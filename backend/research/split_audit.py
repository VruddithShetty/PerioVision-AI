"""Patient-level split: make one, and prove that no patient (or image) is in more than one split.

Two sub-commands, both CPU-only, no GUI:

  make   Build a patient-level train / val / test split from a manifest CSV (columns: image, patient_id,
         optional stratum). All images of a patient go to the same split; strata (e.g. severity level) are
         kept balanced. The split is written to JSON and immediately verified.

  audit  Check an existing split. Three independent checks:
           1. patient overlap   - only when the dataset has patient IDs (BRAR: one film per patient;
                                  DenPAR / DENTEX / MM-OPG publish none, so this check is UNVERIFIABLE there)
           2. exact duplicates  - same pixels (SHA-256 of the decoded grey image) in two splits
           3. near duplicates   - 64-bit difference hash (dHash) within --max-hamming bits across splits:
                                  catches re-exported, resized or re-compressed copies of the same film, the
                                  usual sign of the same patient / visit appearing twice
         With --against, the same duplicate checks run between this dataset and another one (e.g. the
         external AKU films vs. every training set), which is how "never used for training" is shown.

Built-in dataset adapters (--dataset): brar, denpar, mmopg, yolo (images/<split>/...), folder (one split, e.g.
an external test set), manifest (your own CSV with image, split[, patient_id]).

Examples (from backend/):
  python -m research.split_audit audit --dataset brar   --root ~/Downloads/BRAR/data --out ../docs/evidence/split_audit_brar.json
  python -m research.split_audit audit --dataset denpar --root ~/Downloads/DenPAR/Dataset --out ../docs/evidence/split_audit_denpar.json
  python -m research.split_audit audit --dataset folder --root ~/Downloads/OPG-AKU/Niihhaa-Dataset-4ac91db/dataset \
      --against yolo:~/Downloads/DP_datasets/datasets/detection --out ../docs/evidence/split_audit_aku_vs_training.json
  python -m research.split_audit make --manifest my_images.csv --out my_split.json --seed 0
"""
from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import os
import random
import re
import sys
from collections import defaultdict

import cv2
import numpy as np

IMG_EXT = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff")


# ------------------------------------------------------------------ adapters -> list of rows
def _images(folder: str) -> list[str]:
    return sorted(p for p in glob.glob(os.path.join(folder, "**", "*"), recursive=True)
                  if p.lower().endswith(IMG_EXT))


def load_brar(root: str) -> list[dict]:
    """Reproduces scripts/train_panoramic_boneloss.py:load_brar exactly (seed 0, stratified by level).
    Patient ID = the number in 'patient_image_000123_<hash>.jpg' (BRAR: one film per patient)."""
    import pandas as pd

    meta = pd.read_csv(os.path.join(root, "meta_data.csv"))
    rows = []
    for _, m in meta.iterrows():
        path = os.path.join(root, f"level_{int(m['Level'])}", m["File name"])
        if os.path.exists(path):   # the training script also skips unreadable films
            pid = re.match(r"patient_image_(\d+)_", m["File name"])
            rows.append({"image": path, "patient_id": pid.group(1) if pid else None, "stratum": int(m["Level"])})
    rng = random.Random(0)  # audit-ok: must match the training split exactly
    out = []
    for lv in (1, 2, 3):
        group = [r for r in rows if r["stratum"] == lv]
        rng.shuffle(group)
        n = len(group)
        for i, r in enumerate(group):
            r["split"] = "train" if i < int(0.7 * n) else "val" if i < int(0.85 * n) else "test"
            out.append(r)
    return out


def load_denpar(root: str) -> list[dict]:
    names = {"Training": "train", "Validation": "val", "Testing": "test"}
    return [{"image": p, "split": s, "patient_id": None}
            for folder, s in names.items() for p in _images(os.path.join(root, folder, "Images"))]


def load_yolo(root: str) -> list[dict]:
    """<root>/images/<split>/*  (or <root>/<split>/images/*)."""
    rows = []
    for p in _images(root):
        parts = [x.lower() for x in os.path.normpath(p).split(os.sep)]
        split = next((x for x in reversed(parts) if x in ("train", "val", "valid", "test", "yolo_train", "yolo_val")),
                     "unsplit")
        rows.append({"image": p, "split": {"valid": "val", "yolo_train": "train", "yolo_val": "val"}.get(split, split),
                     "patient_id": None})
    return rows


def load_mmopg(root: str) -> list[dict]:
    """<root>/mmopg_train.json, mmopg_test.json and the images unzipped anywhere under <root>
    (unzip images.zip first). Official train / test split; the app's validation films come from train."""
    files = {os.path.basename(p): p for p in _images(root)}
    rows, seen = [], set()
    for split, name in (("train", "mmopg_train.json"), ("test", "mmopg_test.json")):
        for it in json.load(open(os.path.join(root, name), encoding="utf-8")):
            img = it["image"]
            if (split, img) not in seen and img in files:
                seen.add((split, img))
                rows.append({"image": files[img], "split": split, "patient_id": None})
    return rows


def load_folder(root: str, split: str = "external") -> list[dict]:
    return [{"image": p, "split": split, "patient_id": None} for p in _images(root)]


def load_manifest(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return [{"image": r["image"], "split": r.get("split", "unsplit"), "patient_id": r.get("patient_id") or None,
                 "stratum": r.get("stratum")} for r in csv.DictReader(f)]


def load(spec: str, root: str | None) -> list[dict]:
    """'brar', 'denpar', 'yolo', 'folder', 'manifest' with --root, or 'kind:path' for --against."""
    if ":" in spec and root is None and not re.match(r"^[A-Za-z]:\\", spec):
        spec, root = spec.split(":", 1)
    root = os.path.expanduser(root or "")
    rows = {"brar": load_brar, "denpar": load_denpar, "yolo": load_yolo, "folder": load_folder, "mmopg": load_mmopg,
            "manifest": load_manifest}[spec](root)
    if not rows:   # an empty dataset would make every check "PASS" without checking anything
        raise SystemExit(f"No images found for {spec} at '{root}'. Check the path.")
    return rows


# ------------------------------------------------------------------ hashing
def fingerprints(path: str) -> tuple[str, int] | None:
    """(SHA-256 of the decoded grey pixels, 64-bit dHash) or None if unreadable."""
    g = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if g is None:
        return None
    g = g.reshape(g.shape[:2])
    sha = hashlib.sha256(g.tobytes() + str(g.shape).encode()).hexdigest()
    small = cv2.resize(g, (9, 8), interpolation=cv2.INTER_AREA).astype(np.int16)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    return sha, int("".join("1" if b else "0" for b in bits), 2)


def _hash_rows(rows: list[dict], label: str) -> list[dict]:
    out = []
    for i, r in enumerate(rows, 1):
        fp = fingerprints(r["image"])
        if fp is not None:
            out.append({**r, "sha": fp[0], "dhash": fp[1]})
        if i % 2000 == 0:
            print(f"  [{label}] hashed {i}/{len(rows)}", flush=True)
    return out


def near_pairs(a: list[dict], b: list[dict] | None, max_hamming: int) -> list[tuple[dict, dict, int]]:
    """Pairs within max_hamming bits. Band index (8 bands x 8 bits) avoids comparing every pair:
    two hashes within <= 7 bits always share at least one identical band."""
    assert max_hamming <= 7
    same = b is None
    b = a if same else b
    bands = [defaultdict(list) for _ in range(8)]
    for j, r in enumerate(b):
        for k in range(8):
            bands[k][(r["dhash"] >> (8 * k)) & 0xFF].append(j)
    pairs = set()
    for i, r in enumerate(a):
        cand = set()
        for k in range(8):
            cand.update(bands[k][(r["dhash"] >> (8 * k)) & 0xFF])
        for j in cand:
            if same and j <= i:
                continue
            d = bin(r["dhash"] ^ b[j]["dhash"]).count("1")
            if d <= max_hamming:
                pairs.add((i, j, d))
    return [(a[i], b[j], d) for i, j, d in sorted(pairs)]


def confirm_pair(a: str, b: str, min_ncc: float) -> float | None:
    """Second stage for a dHash candidate: correlation of the two films at 128 x 128. Returns the
    correlation when it is >= min_ncc and the aspect ratios agree within 5 %, else None."""
    ga, gb = cv2.imread(a, cv2.IMREAD_GRAYSCALE), cv2.imread(b, cv2.IMREAD_GRAYSCALE)
    if ga is None or gb is None:
        return None
    ga, gb = ga.reshape(ga.shape[:2]), gb.reshape(gb.shape[:2])
    if abs(ga.shape[1] / ga.shape[0] - gb.shape[1] / gb.shape[0]) > 0.05 * ga.shape[1] / ga.shape[0]:
        return None
    x = cv2.resize(ga, (128, 128), interpolation=cv2.INTER_AREA).astype(np.float64).ravel()
    y = cv2.resize(gb, (128, 128), interpolation=cv2.INTER_AREA).astype(np.float64).ravel()
    ncc = float(np.corrcoef(x, y)[0, 1])
    return ncc if ncc >= min_ncc else None


# ------------------------------------------------------------------ audit
SHOW_NAMES = False


def _rel(p: str) -> str:
    """By default never print file names: some datasets carry personal names in them. --show-names is for
    datasets with neutral names (DenPAR '166.jpg', BRAR 'patient_image_000123_x.jpg')."""
    if SHOW_NAMES:
        return os.path.basename(p)
    return f"{os.path.basename(os.path.dirname(p))}/...{hashlib.sha256(os.path.basename(p).encode()).hexdigest()[:10]}"


def audit(rows: list[dict], against: list[dict] | None, max_hamming: int, min_ncc: float = 0.97) -> dict:
    by_split = defaultdict(list)
    for r in rows:
        by_split[r["split"]].append(r)
    report = {"images_per_split": {s: len(v) for s, v in sorted(by_split.items())}}

    # 1. patients
    have_ids = rows and all(r.get("patient_id") for r in rows)
    if have_ids:
        pats = {s: {r["patient_id"] for r in v} for s, v in by_split.items()}
        overlaps = {f"{a}&{b}": len(pats[a] & pats[b]) for a in pats for b in pats if a < b}
        report["patients_per_split"] = {s: len(v) for s, v in sorted(pats.items())}
        report["images_per_patient_max"] = max(sum(1 for r in rows if r["patient_id"] == p)
                                               for p in {r["patient_id"] for r in rows})
        report["patient_overlap"] = overlaps
        report["check_patient_overlap"] = "PASS" if not any(overlaps.values()) else "FAIL"
    else:
        report["check_patient_overlap"] = "UNVERIFIABLE (dataset publishes no patient IDs)"

    # 2 + 3. duplicates across splits within the dataset
    hashed = _hash_rows(rows, "dataset")
    report["unreadable_images"] = len(rows) - len(hashed)
    sha_splits = defaultdict(set)
    for r in hashed:
        sha_splits[r["sha"]].add(r["split"])
    exact_cross = sum(1 for s in sha_splits.values() if len(s) > 1)
    exact_within = len(hashed) - len(sha_splits)
    report["exact_duplicates_across_splits"] = exact_cross
    report["exact_duplicates_total_images_minus_unique"] = exact_within
    by_sha = defaultdict(list)
    for r in hashed:
        by_sha[r["sha"]].append(r)
    report["exact_duplicate_groups"] = [[f"{r['split']}:{_rel(r['image'])}" for r in g]
                                        for g in by_sha.values() if len(g) > 1]
    pairs = [(x, y, d) for x, y, d in near_pairs(hashed, None, max_hamming) if x["split"] != y["split"]]
    confirmed = []
    for x, y, d in pairs:
        ncc = 1.0 if x["sha"] == y["sha"] else confirm_pair(x["image"], y["image"], min_ncc)
        if ncc is not None:
            confirmed.append({"a": f"{x['split']}:{_rel(x['image'])}", "b": f"{y['split']}:{_rel(y['image'])}",
                              "hamming": d, "ncc_128px": round(ncc, 4)})
    report["near_duplicate_candidates_across_splits"] = len(pairs)
    report["near_duplicates_confirmed_across_splits"] = len(confirmed)
    report["near_duplicate_confirmed"] = confirmed
    report["min_ncc"] = min_ncc
    report["check_duplicates"] = "PASS" if exact_cross == 0 and not confirmed else "FAIL (leak across splits)"

    # cross-dataset
    if against is not None:
        other = _hash_rows(against, "against")
        shas = {r["sha"] for r in other}
        ex = sum(1 for r in hashed if r["sha"] in shas)
        xp = near_pairs(hashed, other, max_hamming)
        conf = []
        for x, y, d in xp:
            ncc = 1.0 if x["sha"] == y["sha"] else confirm_pair(x["image"], y["image"], min_ncc)
            if ncc is not None:
                conf.append({"this": _rel(x["image"]), "other": f"{y['split']}:{_rel(y['image'])}",
                             "hamming": d, "ncc_128px": round(ncc, 4)})
        report["against"] = {"images": len(other), "exact_matches": ex, "near_duplicate_candidates": len(xp),
                             "near_duplicates_confirmed": len(conf), "confirmed": conf[:50],
                             "check": "PASS" if ex == 0 and not conf else "FAIL (overlap with the other dataset)"}
    report["max_hamming"] = max_hamming
    report["note"] = ("Near-duplicate pairs are candidates, not proof: inspect them. Different patients' films "
                      "taken on the same machine can look alike at 8x8 resolution; the same film re-exported "
                      "usually gives hamming 0-3.")
    return report


# ------------------------------------------------------------------ make
def make_split(rows: list[dict], fractions=(0.7, 0.15, 0.15), seed: int = 0) -> dict:
    """Patient-level, stratified split. Returns {'train': [...images], 'val': [...], 'test': [...]}."""
    if not all(r.get("patient_id") for r in rows):
        raise SystemExit("Every row needs a patient_id for a patient-level split.")
    patients = defaultdict(list)
    for r in rows:
        patients[r["patient_id"]].append(r)
    # a patient's stratum = the most common stratum of their images (e.g. their worst severity level)
    strata = defaultdict(list)
    for pid, imgs in patients.items():
        s = [str(i.get("stratum")) for i in imgs]
        strata[max(set(s), key=s.count)].append(pid)
    rng = random.Random(seed)  # audit-ok: seeded split
    split = {"train": [], "val": [], "test": []}
    for key in sorted(strata):
        pids = sorted(strata[key])
        rng.shuffle(pids)
        n = len(pids)
        a, b = int(round(fractions[0] * n)), int(round((fractions[0] + fractions[1]) * n))
        for name, chunk in (("train", pids[:a]), ("val", pids[a:b]), ("test", pids[b:])):
            split[name] += [i["image"] for p in chunk for i in patients[p]]
    verify_split(split, {i["image"]: i["patient_id"] for i in rows})
    return split


def verify_split(split: dict, patient_of: dict) -> None:
    seen = {}
    for name, imgs in split.items():
        for img in imgs:
            p = patient_of[img]
            if seen.setdefault(p, name) != name:
                raise AssertionError(f"patient {p} is in both {seen[p]} and {name}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("audit")
    a.add_argument("--dataset", required=True, choices=("brar", "denpar", "yolo", "folder", "manifest", "mmopg"))
    a.add_argument("--root", required=True)
    a.add_argument("--against", help="kind:path of another dataset, e.g. yolo:~/data/detection")
    a.add_argument("--max-hamming", type=int, default=4)
    a.add_argument("--min-ncc", type=float, default=0.97, help="correlation needed to confirm a near duplicate")
    a.add_argument("--show-names", action="store_true", help="print file names (only for non-identifying names)")
    a.add_argument("--out", required=True)
    m = sub.add_parser("make")
    m.add_argument("--manifest", required=True, help="CSV with columns image, patient_id[, stratum]")
    m.add_argument("--fractions", type=float, nargs=3, default=(0.7, 0.15, 0.15))
    m.add_argument("--seed", type=int, default=0)
    m.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    if args.cmd == "make":
        split = make_split(load_manifest(args.manifest), tuple(args.fractions), args.seed)
        json.dump(split, open(args.out, "w", encoding="utf-8"), indent=1)
        print({k: len(v) for k, v in split.items()}, "- verified: no patient in two splits")
        return 0

    global SHOW_NAMES
    SHOW_NAMES = args.show_names
    rows = load(args.dataset, args.root)
    against = load(args.against, None) if args.against else None
    report = {"dataset": args.dataset, "root_name": os.path.basename(os.path.normpath(os.path.expanduser(args.root))),
              **audit(rows, against, args.max_hamming, args.min_ncc)}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    json.dump(report, open(args.out, "w", encoding="utf-8"), indent=2)
    print(json.dumps(report, indent=2)[:6000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
