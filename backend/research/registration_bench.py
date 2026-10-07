"""Registration bench: are re-takes of the same film accepted, and are different patients' films refused?

Positives: DenPAR films and a realistic re-take of each (research.progression_bench.retake: rotation, scale, shift,
slight projective tilt, exposure, noise, blur, JPEG). Negatives: pairs of films of DIFFERENT DenPAR images, drawn at
random (as in scripts/evaluate_registration.py --make-negatives). Both run the app's feature registration at the
app's 1024 px working size (RadiographAligner.align_by_features). The tooth-overlap check in register_images can only
refuse more, so the false-acceptance rate here is an upper bound for the app.

Usage (from backend/):  python -m research.registration_bench --films 200 --negatives 300 --out ../docs/evidence/registration_bench.json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import random
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))  # backend/

import cv2  # noqa: E402

from app.ml.preprocessing.alignment import RadiographAligner  # noqa: E402
from research import stats  # noqa: E402
from research.progression_bench import LEAKED, retake  # noqa: E402


def _load(path):
    g = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    return g.reshape(g.shape[:2])


def _small(g):
    h, w = g.shape
    return cv2.resize(g, (1024, max(1, int(h * 1024 / w))))


def accepted(aligner, prev, curr) -> tuple[bool, str | None]:
    aligner.align_by_features(_small(curr), _small(prev))
    info = aligner.last_alignment_info
    return info["alignment_status"] == "success", info.get("reason")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--denpar", default="~/Downloads/DenPAR/Dataset")
    ap.add_argument("--films", type=int, default=200)
    ap.add_argument("--negatives", type=int, default=300)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    root = os.path.expanduser(args.denpar)
    paths = sorted(p for split in ("Validation", "Testing") for p in glob.glob(os.path.join(root, split, "Images", "*.jpg"))
                   if os.path.splitext(os.path.basename(p))[0] not in LEAKED)
    rng = random.Random(args.seed)  # audit-ok: seeded bench construction
    films = rng.sample(paths, min(args.films, len(paths)))
    negs = []
    while len(negs) < args.negatives:
        a, b = rng.sample(paths, 2)
        negs.append((a, b))
    report = {}
    for label, fallback in (("similarity_only", False), ("with_affine_fallback", True)):
        aligner = RadiographAligner()
        aligner.AFFINE_FALLBACK = fallback
        pos = [accepted(aligner, _load(f), retake(_load(f), random.Random(f"{args.seed}:{f}")))[0] for f in films]
        neg = [accepted(aligner, _load(a), _load(b))[0] for a, b in negs]
        report[label] = {"retake_pairs": len(pos), "retakes_accepted": sum(pos),
                         "retake_acceptance": sum(pos) / len(pos), "retake_acceptance_ci95": stats.wilson(sum(pos), len(pos)),
                         "different_patient_pairs": len(neg), "false_acceptances": sum(neg),
                         "false_acceptance_ci95": stats.wilson(sum(neg), len(neg))}
        print(label, json.dumps(report[label]))
    json.dump(report, open(args.out, "w", encoding="utf-8"), indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
