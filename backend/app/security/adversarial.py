"""Heuristic detection of adversarial / perturbed radiographs.

Two simple, explainable statistics, both measured after resizing to 1024 px wide:
  * noise residual: mean |image - 3x3 median filter|. Gradient-sign attacks
    (FGSM/PGD-style) add dense pixel-level noise that a median filter removes.
  * high-frequency power share: fraction of spectral power beyond 25 % of the
    Nyquist radius.
Thresholds were set from 30 real panoramic radiographs in the project's dataset
folder (natural residual 0.2-2.8, +/-8 sign noise 4.1-6.6), so natural images
are not flagged while a +/-8 grey-level perturbation is. This is a screening
heuristic, not a guarantee: flagged images go to clinician review.
"""
from __future__ import annotations

import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)

NORMALISED_WIDTH = 1024


def _normalise(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    if gray.dtype != np.uint8:
        gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    h, w = gray.shape
    return cv2.resize(gray, (NORMALISED_WIDTH, max(1, int(NORMALISED_WIDTH * h / w))), interpolation=cv2.INTER_LINEAR)


def noise_residual(gray: np.ndarray) -> float:
    return float(np.abs(gray.astype(np.float32) - cv2.medianBlur(gray, 3).astype(np.float32)).mean())


def high_frequency_share(gray: np.ndarray, radius: float = 0.25) -> float:
    g = gray.astype(np.float32)
    power = np.abs(np.fft.fftshift(np.fft.fft2(g - g.mean()))) ** 2
    h, w = g.shape
    yy, xx = np.ogrid[:h, :w]
    dist = np.sqrt(((yy - h / 2) / (h / 2)) ** 2 + ((xx - w / 2) / (w / 2)) ** 2)
    total = power.sum()
    return float(power[dist > radius].sum() / total) if total > 0 else 0.0


class AdversarialInputDetector:
    def __init__(self, residual_threshold: float = 3.5, hf_threshold: float = 0.05):
        self.residual_threshold = residual_threshold
        self.hf_threshold = hf_threshold

    def detect_adversarial(self, image: np.ndarray) -> dict:
        gray = _normalise(image)
        residual = noise_residual(gray)
        hf = high_frequency_share(gray)
        triggers = []
        if residual > self.residual_threshold:
            triggers.append("Dense pixel-level noise detected (possible adversarial perturbation).")
        if hf > self.hf_threshold:
            triggers.append("Unusually strong high-frequency content.")
        return {"is_suspicious": bool(triggers), "triggers": triggers,
                "metrics": {"noise_residual": round(residual, 3), "high_frequency_share": round(hf, 4)}}
