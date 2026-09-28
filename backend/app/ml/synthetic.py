"""Synthetic, radiograph-like images for demo mode, tests and the Security Lab.

They contain no patient data. Each image is a row of "teeth" (bright roots and
crowns) set in alveolar bone whose crest height can be chosen per tooth, so demo
visits can show bone loss that changes over time.
"""
from __future__ import annotations

import cv2
import numpy as np

WIDTH, HEIGHT = 1400, 700
TOOTH_W, GAP, LEFT = 70, 35, 60
TOP, APEX = 150, 560           # crown top and root apex (y)
CEJ = TOP + int(0.28 * (APEX - TOP))


def tooth_boxes(n: int = 12) -> list[list[float]]:
    return [[float(LEFT + i * (TOOTH_W + GAP)), float(TOP), float(LEFT + i * (TOOTH_W + GAP) + TOOTH_W), float(APEX)]
            for i in range(n)]


def make_radiograph(bone_loss_pct: list[float], seed: int = 0) -> np.ndarray:
    """bone_loss_pct[i] = how far the crest sits below the CEJ, as % of the CEJ-apex distance."""
    rng = np.random.default_rng(seed)
    img = np.full((HEIGHT, WIDTH), 38, np.float32)
    boxes = tooth_boxes(len(bone_loss_pct))
    root_len = APEX - CEJ
    for i, (x1, _y1, x2, _y2) in enumerate(boxes):
        # interdental bone to the right of each tooth (and left of the first one)
        crest = int(CEJ + root_len * np.clip(bone_loss_pct[i], 0, 95) / 100.0)
        left = int(x2)
        right = int(x2 + GAP) if i < len(boxes) - 1 else WIDTH
        img[crest:HEIGHT - 60, left:right] = 118
        if i == 0:
            img[crest:HEIGHT - 60, 0:int(x1)] = 118
    for x1, y1, x2, y2 in boxes:
        x1, x2 = int(x1), int(x2)
        img[int(y1):CEJ, x1:x2] = 215                     # crown (enamel)
        img[CEJ:int(y2), x1 + 8:x2 - 8] = 185             # root
        img[int(y1) + 25:int(y2) - 20, x1 + 28:x2 - 28] = 90  # pulp canal
    img = cv2.GaussianBlur(img, (0, 0), 3)
    img += rng.normal(0, 2.0, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def to_png(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    return buf.tobytes()


def demo_crest_y(gray: np.ndarray, bbox, cej_y: float) -> float | None:
    """DEMO heuristic: find the alveolar crest as the first bright (bone) row in the
    interdental strips beside a tooth, scanning down from the CEJ."""
    x1, _y1, x2, y2 = [int(v) for v in bbox]
    h, w = gray.shape
    strips = []
    for a, b in ((x2 + 6, x2 + 22), (x1 - 22, x1 - 6)):
        a, b = max(0, a), min(w, b)
        if b - a >= 4:
            strips.append(gray[:, a:b].mean(axis=1))
    if not strips:
        return None
    profile = np.convolve(np.max(strips, axis=0), np.ones(9) / 9, mode="same")
    start, stop = int(cej_y), min(h, int(y2))
    if stop - start < 10:
        return None
    segment = profile[start:stop]
    background = float(np.percentile(profile, 5))
    threshold = background + 0.5 * (float(segment.max()) - background)
    above = np.nonzero(segment > threshold)[0]
    return float(start + above[0]) if len(above) else None
