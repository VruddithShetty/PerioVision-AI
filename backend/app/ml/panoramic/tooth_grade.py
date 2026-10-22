"""Per-tooth bone-loss GRADE on panoramic films (healthy / mild / medium / severe).

A small CNN reads each detected tooth crop and gives probabilities for the four dentist grades of the PDCNN
export. The grade is reported with a split-conformal SET: one threshold per grade, so each grade reaches the
90 % target on held-out films (scripts: research/panoramic_stage.py). The output is a grade and a set, never a
bone-loss percentage: the grades are dentist labels, not measurements.

Weights (panoramic_grade.pt) and metrics (panoramic_grade_metrics.json, holding the per-grade thresholds) are
signature-checked by the registry. If either is missing or refused, no grade is shown (None).
"""
from __future__ import annotations

import json
import logging
import threading

import cv2
import numpy as np

from app import config
from app.ml.registry import registry

logger = logging.getLogger(__name__)
GRADES = ["healthy", "mild", "medium", "severe"]


def _network():
    import torch.nn as nn

    def block(i, o):
        return nn.Sequential(nn.Conv2d(i, o, 3, padding=1, bias=False), nn.BatchNorm2d(o), nn.ReLU(inplace=True),
                             nn.Conv2d(o, o, 3, padding=1, bias=False), nn.BatchNorm2d(o), nn.ReLU(inplace=True),
                             nn.MaxPool2d(2))
    # must match research/panoramic_stage.py make_model() exactly
    return nn.Sequential(block(1, 32), block(32, 64), block(64, 128), block(128, 192),
                         nn.AdaptiveAvgPool2d(1), nn.Flatten(), nn.Dropout(0.3), nn.Linear(192, len(GRADES)))


class ToothGrader:
    def __init__(self):
        self._lock = threading.Lock()
        self._model = None
        self._metrics = None
        self._tried = False

    def _load(self):
        with self._lock:
            if self._tried:
                return self._model, self._metrics
            self._tried = True
            path = registry().get("panoramic_grade")          # signature-checked; None if missing or refused
            metrics_path = config.WEIGHTS_DIR / "panoramic_grade_metrics.json"
            if path is None or not metrics_path.exists():
                return None, None
            if not registry().signer.verify_weight_file(metrics_path, config.WEIGHTS_DIR).get("verified", False):
                logger.error("[SECURITY] Refusing panoramic grades: the metrics file fails the signed manifest")
                return None, None
            try:
                import torch

                metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
                if metrics.get("grades") != GRADES or "conformal_threshold_by_grade" not in metrics:
                    logger.error("Panoramic grade metrics do not match the expected grades: no grades shown")
                    return None, None
                net = _network()
                net.load_state_dict(torch.load(str(path), map_location="cpu", weights_only=True))
                net.eval()
                self._model, self._metrics = net, metrics
            except Exception as exc:                          # corrupt file or wrong architecture: no grades, logged
                logger.error("Panoramic grade model could not be loaded: %s", type(exc).__name__)
            return self._model, self._metrics

    @property
    def available(self) -> bool:
        return self._load()[0] is not None

    def grade_teeth(self, gray: np.ndarray, detections: list[dict]) -> dict[str, dict]:
        """{tooth_id: {grade, set, probabilities, threshold_by_grade}} for every detected tooth, or {} if unavailable."""
        import torch

        model, m = self._load()
        if model is None or not detections:
            return {}
        size, margin = int(m["input_size"]), float(m["crop_margin"])
        h, w = gray.shape[:2]
        crops, ids = [], []
        for det in detections:
            bx0, by0, bx1, by1 = det["bbox"]    # corner format [x1, y1, x2, y2] in pixels, as the detector returns it
            mx, my = (bx1 - bx0) * margin, (by1 - by0) * margin
            x0, y0 = max(0, int(bx0 - mx)), max(0, int(by0 - my))
            x1, y1 = min(w, int(bx1 + mx)), min(h, int(by1 + my))
            if x1 - x0 < 4 or y1 - y0 < 4:
                continue
            crops.append(cv2.resize(gray[y0:y1, x0:x1], (size, size), interpolation=cv2.INTER_AREA))
            ids.append(det["tooth_id"])
        if not crops:
            return {}
        x = torch.tensor(np.stack(crops)).float().div(255).unsqueeze(1)
        with torch.inference_mode():
            p = (torch.softmax(model(x), 1) + torch.softmax(model(torch.flip(x, dims=[3])), 1)) / 2
        p = p.numpy()
        q = np.array([m["conformal_threshold_by_grade"][g] for g in GRADES])
        out = {}
        for tooth_id, row in zip(ids, p):
            keep = [GRADES[k] for k in range(len(GRADES)) if 1.0 - row[k] <= q[k]]
            out[tooth_id] = {"grade": GRADES[int(row.argmax())], "set": keep,
                             "probabilities": {g: round(float(row[k]), 3) for k, g in enumerate(GRADES)},
                             "target_coverage": m["conformal_target_coverage"]}
        return out


_instance: ToothGrader | None = None


def tooth_grader() -> ToothGrader:
    global _instance
    if _instance is None:
        _instance = ToothGrader()
    return _instance
