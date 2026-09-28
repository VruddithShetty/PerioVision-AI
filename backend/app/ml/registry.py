"""Model registry: verifies every weight file's RSA-PSS-signed hash BEFORE loading it.

An unsigned, unlisted or altered file is refused, the refusal is written to the
audit log, and the pipeline falls back to clearly labelled DEMO behaviour for
that stage. Nothing is ever loaded "with a warning".
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path

from app import config
from app.security.model_signing import Signer

logger = logging.getLogger(__name__)

MODEL_SPECS = {
    "tooth_detector": {"file": "dental_yolov8n.pt", "task": "detect",
                       "purpose": "YOLOv8 tooth detection with FDI tooth numbers"},
    "landmarks": {"file": "dental_landmark_yolov8n-pose.pt", "task": "pose",
                  "purpose": "YOLOv8-pose CEJ / root apex / bone crest keypoints"},
}


@dataclass
class ModelStatus:
    name: str
    file: str
    purpose: str
    present: bool = False
    signature_valid: bool = False
    loaded: bool = False
    sha256: str | None = None
    reason: str | None = None
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


class ModelRegistry:
    def __init__(self, weights_dir: Path | None = None, signer: Signer | None = None, record_events: bool = True):
        self.weights_dir = Path(weights_dir or config.WEIGHTS_DIR)
        self.record_events = record_events
        self.signer = signer or Signer()
        self._models: dict[str, object] = {}
        self._status: dict[str, ModelStatus] = {}
        self._lock = threading.Lock()

    def path_for(self, name: str) -> Path:
        return self.weights_dir / MODEL_SPECS[name]["file"]

    def check(self, name: str) -> ModelStatus:
        spec = MODEL_SPECS[name]
        path = self.path_for(name)
        status = ModelStatus(name=name, file=spec["file"], purpose=spec["purpose"], present=path.exists())
        if not status.present:
            status.reason = "weight file not found"
            return status
        result = self.signer.verify_weight_file(path, self.weights_dir)
        status.signature_valid = bool(result.get("verified"))
        status.sha256 = result.get("sha256")
        status.reason = result.get("reason")
        return status

    def get(self, name: str):
        """Return the loaded model, or None if it is missing or failed verification."""
        with self._lock:
            if name in self._models:
                return self._models[name]
            status = self.check(name)
            model = None
            if status.present and status.signature_valid:
                try:
                    from ultralytics import YOLO

                    model = YOLO(str(self.path_for(name)))
                    status.loaded = True
                    status.extra["classes"] = len(getattr(model, "names", {}) or {})
                except Exception as exc:  # corrupt file that still matched its hash, wrong format, etc.
                    status.reason = f"load failed: {type(exc).__name__}"
            if self.record_events:
                self._record(status)
            self._status[name] = status
            self._models[name] = model
            return model

    def status(self) -> list[dict]:
        out = []
        for name in MODEL_SPECS:
            status = self._status.get(name) or self.check(name)
            out.append(status.as_dict())
        return out

    def reset(self) -> None:
        with self._lock:
            self._models.clear()
            self._status.clear()

    @staticmethod
    def _record(status: ModelStatus) -> None:
        from app.security.audit_log import audit

        if status.loaded:
            audit().record("MODEL_LOADED", actor="system", resource=status.file, details={"sha256": status.sha256})
        elif status.present:
            logger.error("[SECURITY] Refusing to load %s: %s", status.file, status.reason)
            audit().record("MODEL_LOAD_REFUSED", outcome="denied", actor="system", resource=status.file,
                           details={"reason": status.reason})


_registry: ModelRegistry | None = None


def registry() -> ModelRegistry:
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
