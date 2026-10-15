"""Whole-film panoramic assessment: bone-loss screen per jaw + worst-tooth bone loss estimate.

Panoramic per-tooth landmarks are not accurate enough to report (docs/MODEL_CARD.md), so for panoramic
films two whole-image models give a PATIENT-LEVEL estimate instead:

  * screen   (panoramic_screen.pt):   generalised crestal bone loss yes / no for the maxilla and the
                                       mandible; trained on ToothXpert MM-OPG, tested on its 450-film split
  * severity (panoramic_severity.pt): bone loss of the WORST tooth (% of root length), fine-tuned from the
                                       screen network on BRAR; tested on 149 held-out BRAR films, with a
                                       split-conformal 90 % interval and the stages that interval allows

Both weight files are signature-checked by the model registry before loading. Architecture, input size,
decision thresholds, conformal radius and test metrics are read from the metrics JSON written by
scripts/train_panoramic_boneloss.py, so nothing here is typed in. If either file is missing or refused,
the assessment is simply absent (None), never a default number.
"""
from __future__ import annotations

import json
import logging
import threading
from typing import TYPE_CHECKING

import cv2
import numpy as np

from app import config
from app.ml.measurement.staging import stage_for_pct, stages_overlapping
from app.ml.registry import registry

if TYPE_CHECKING:          # type hints only; torch is imported lazily at run time
    import torch

logger = logging.getLogger(__name__)
MEAN, STD = 0.449, 0.226          # same normalisation as training


def _network(arch: str, outputs: int):
    import torch.nn as nn
    import torchvision

    m = torchvision.models
    builders = {"resnet18": m.resnet18, "resnet50": m.resnet50, "efficientnet_b3": m.efficientnet_b3,
                "convnext_tiny": m.convnext_tiny}
    net = builders[arch](weights=None)
    if hasattr(net, "fc"):
        net.fc = nn.Linear(net.fc.in_features, outputs)
    else:
        net.classifier[-1] = nn.Linear(net.classifier[-1].in_features, outputs)
    return net


class WholeFilmModels:
    def __init__(self):
        self._lock = threading.Lock()
        self._loaded: dict[str, tuple] = {}

    def _load(self, name: str, outputs: int):
        """(network, metrics) for a verified model, or None."""
        with self._lock:
            if name in self._loaded:
                return self._loaded[name]
            path = registry().get(name)                 # signature-checked; None if missing / refused
            metrics_path = config.WEIGHTS_DIR / f"{name}_metrics.json"
            result = None
            metrics_ok = metrics_path.exists() and registry().signer.verify_weight_file(
                metrics_path, config.WEIGHTS_DIR).get("verified", False)
            if path is not None and metrics_path.exists() and not metrics_ok:
                logger.error("[SECURITY] Refusing %s: its metrics file (thresholds, conformal radius) fails the "
                             "signed manifest", name)
            if path is not None and metrics_ok:
                try:
                    import torch

                    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
                    net = _network(metrics["arch"], outputs)
                    net.load_state_dict(torch.load(str(path), map_location="cpu", weights_only=True))
                    net.eval()
                    result = (net, metrics)
                except Exception as exc:   # wrong architecture / corrupt file: no assessment, logged
                    logger.error("Panoramic model %s could not be loaded: %s", name, type(exc).__name__)
            self._loaded[name] = result
            return result

    @property
    def available(self) -> bool:
        return self._load("panoramic_screen", 2) is not None or self._load("panoramic_severity", 1) is not None

    @staticmethod
    def _input(gray: np.ndarray, size) -> "torch.Tensor":
        import torch

        w, h = size
        x = cv2.resize(gray.reshape(gray.shape[:2]), (w, h), interpolation=cv2.INTER_AREA).astype(np.float32)
        x = (x / 255.0 - MEAN) / STD
        return torch.from_numpy(x)[None, None].expand(1, 3, h, w).contiguous()

    def assess(self, gray: np.ndarray) -> dict | None:
        import torch

        screen, severity = self._load("panoramic_screen", 2), self._load("panoramic_severity", 1)
        if screen is None and severity is None:
            return None
        out = {"level": "patient (whole film)",
               "note": "Whole-film estimate for the patient, not a per-tooth measurement; confirm clinically."}
        with torch.inference_mode():
            if screen is not None:
                net, m = screen
                prob = torch.sigmoid(net(self._input(gray, m["input_size"])))[0].numpy()
                out["screen"] = {
                    jaw: {"probability": round(float(prob[j]), 3),
                          "bone_loss_suggested": bool(prob[j] >= m["jaws"][jaw]["threshold_from_val"]),
                          "threshold": m["jaws"][jaw]["threshold_from_val"],
                          "test": {k: m["jaws"][jaw][k] for k in ("test_auc", "test_sensitivity", "test_specificity")}}
                    for j, jaw in enumerate(("maxilla", "mandible"))}
                out["screen_validation"] = {"dataset": m["dataset"], "test_films": m["test_films"]}
            if severity is not None and not (m_has_q := "conformal_q90_from_val" in severity[1]):
                logger.error("Panoramic severity metrics carry no conformal radius; the estimate is withheld.")
            if severity is not None and m_has_q:
                net, m = severity
                pct = float(np.clip(net(self._input(gray, m["input_size"]))[0, 0].item(), 0.0, 100.0))
                # Asymmetric margins when calibrated (scripts/calibrate_panoramic_interval.py): the model underestimates
                # severe cases, so the interval reaches further up; otherwise the symmetric radius.
                q_dn = float(m.get("conformal_q90_lower_from_val", m["conformal_q90_from_val"]))
                q_up = float(m.get("conformal_q90_upper_from_val", m["conformal_q90_from_val"]))
                low, high = max(0.0, pct - q_dn), min(100.0, pct + q_up)
                out["worst_tooth"] = {
                    "bone_loss_pct": round(pct, 1), "stage": stage_for_pct(pct),
                    "interval_90": [round(low, 1), round(high, 1)], "stage_set": stages_overlapping(low, high),
                    "test": {**{k: m[k] for k in ("test_MAE", "test_stage_agreement", "test_films")},
                             # coverage of the interval actually shown (asymmetric when calibrated)
                             "test_interval_coverage": m.get("test_interval_coverage_asymmetric",
                                                             m["test_interval_coverage"]),
                             "test_type": "same-source held-out (BRAR test split)"},
                    "dataset": m["dataset"]}
        return out


_instance: WholeFilmModels | None = None


def whole_film() -> WholeFilmModels:
    global _instance
    if _instance is None:
        _instance = WholeFilmModels()
    return _instance
