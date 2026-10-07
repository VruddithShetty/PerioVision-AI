"""Combine several keypoint readings of the same film into one: mirrored test-time augmentation and model ensembles.

Pure numpy, no app imports, so the Colab evaluation (research/compare_landmark_models.py) runs exactly this code.

A *reading* is one pass of one landmark model over the film: (boxes [n, 4] xyxy, keypoints [n, k, 3] x / y / conf,
box confidences [n]), already mapped back to the original film's coordinates (a mirrored pass is un-mirrored and, for
two-site models, its left / right sites swapped back). The first reading is the anchor: its teeth define the output.
Every other reading contributes the tooth whose box overlaps the anchor tooth best (IoU >= 0.5, each used once).

For each anchor tooth: keypoint coordinates and confidences are the plain mean over the readings that found it (the
same averaging the single-model mirrored reading has always used, so existing calibrations stay valid), and the disagreement is the RANGE (max - min) of the bone-loss values those readings give
(percentage points). With one model and its mirrored pass this range is |normal - mirrored|, the difficulty signal the
adaptive conformal interval and the progression threshold already use; with an ensemble it also captures how much the
models disagree. A tooth found by a single reading gets disagreement None (treated as the hardest case).
"""
from __future__ import annotations

import numpy as np

SITES5 = ((0, 1), (2, 3))          # two-site layout: (cej, crest) on the left, then on the right; apex = 4
SWAP5 = [2, 3, 0, 1, 4]            # left <-> right after a mirror flip


def iou(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def bone_loss_pct(cej, apex, crest) -> float | None:
    """Same formula as app/ml/measurement/bone_loss.py (projection on the root axis, clamped 0-100)."""
    cej, apex, crest = (np.asarray(p, float)[:2] for p in (cej, apex, crest))
    root = apex - cej
    L2 = float(root @ root)
    if L2 <= 1e-6:
        return None
    return max(0.0, min(100.0, float((crest - cej) @ root) / L2 * 100.0))


def reading_pct(k) -> float | None:
    """Bone loss of one tooth in one reading, without any confidence cut-off: 3 keypoints (CEJ, apex, crest) or the
    worse of the two sites for 5 keypoints."""
    if len(k) == 5:
        vals = [bone_loss_pct(k[c], k[4], k[r]) for c, r in SITES5]
        vals = [v for v in vals if v is not None]
        return max(vals) if vals else None
    return bone_loss_pct(k[0], k[1], k[2])


def unmirror(boxes, kpts, width: int):
    """Map a reading of the mirrored film back to the original film (and swap two-site sides)."""
    boxes = np.stack([width - boxes[:, 2], boxes[:, 1], width - boxes[:, 0], boxes[:, 3]], 1) if len(boxes) else boxes
    kpts = kpts.copy()
    if len(kpts):
        kpts[:, :, 0] = width - kpts[:, :, 0]
        if kpts.shape[1] == 5:
            kpts = kpts[:, SWAP5]
    return boxes, kpts


def fuse(readings: list[tuple]) -> list[tuple]:
    """[(boxes, kpts, confs)] -> [(box, fused_kpts, box_conf, disagreement)] for the anchor reading's teeth."""
    if not readings:
        return []
    boxes0, kpts0, confs0 = readings[0]
    out = []
    used = [set() for _ in readings]
    for i in range(len(boxes0)):
        members = [kpts0[i]]
        for r, (boxes, kpts, _c) in enumerate(readings[1:], start=1):
            best_j, best = None, 0.0
            for j in range(len(boxes)):
                if j in used[r]:
                    continue
                v = iou(boxes0[i], boxes[j])
                if v > best:
                    best_j, best = j, v
            if best_j is not None and best >= 0.5:
                used[r].add(best_j)
                members.append(kpts[best_j])
        fused = np.stack(members).mean(0)                           # [k, 3]
        pcts = [p for p in (reading_pct(m) for m in members) if p is not None]
        dis = float(max(pcts) - min(pcts)) if len(members) > 1 and len(pcts) == len(members) else None
        out.append((boxes0[i], fused, float(confs0[i]), dis))
    return out
