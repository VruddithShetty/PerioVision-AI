"""Model registry: verifies and approves every weight file BEFORE loading it.

Two gates, in order:
  1. integrity  - the SHA-256 matches the RSA-PSS-signed manifest
  2. provenance - the signed manifest declares this model, names this exact file,
                  carries a clinical approval countersigned under a second key,
                  matches any version this deployment pins, and is not older than
                  a manifest already run

The second gate exists because the first cannot answer whether this is the right
model. An archived weight file kept with its own valid manifest and signature
passes integrity perfectly, and so does a model signed for evaluation but never
approved for clinical use.

Both load paths are gated: the YOLO detectors and the optional panoramic torch
state dicts alike. An unsigned, unlisted, unapproved, superseded or altered file
is refused, the refusal is audited, and the pipeline falls back to clearly
labelled DEMO behaviour for that stage. Nothing is ever loaded with a warning.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path

from app import config
from app.security import model_provenance
from app.security.model_signing import MANIFEST_NAME, Signer

logger = logging.getLogger(__name__)

MODEL_SPECS = {
    "tooth_detector": {"file": "dental_yolov8n.pt", "task": "detect",
                       "purpose": "YOLO11m tooth detection with FDI tooth numbers (DENTEX, fine-tuned on Aga Khan folders 1+3)"},
    "landmarks": {"file": "dental_landmark_yolov8n-pose.pt", "task": "pose",
                  "purpose": "YOLO-pose CEJ / root apex / bone crest keypoints"},
    # Optional extra members of a landmark ensemble (same keypoint layout as "landmarks"; app/ml/landmarks/fusion.py)
    "landmarks_2": {"file": "dental_landmark_ens2-pose.pt", "task": "pose", "optional": True,
                    "purpose": "Landmark ensemble member 2"},
    "landmarks_3": {"file": "dental_landmark_ens3-pose.pt", "task": "pose", "optional": True,
                    "purpose": "Landmark ensemble member 3"},
    # Optional whole-film panoramic models (torch state dicts; see app/ml/panoramic/whole_film.py)
    "panoramic_screen": {"file": "panoramic_screen.pt", "task": "torch_state_dict", "optional": True,
                         "purpose": "Panoramic generalised bone loss per jaw (ConvNeXt-T, ToothXpert MM-OPG)"},
    "panoramic_severity": {"file": "panoramic_severity.pt", "task": "torch_state_dict", "optional": True,
                           "purpose": "Panoramic worst-tooth bone loss % (ConvNeXt-T, BRAR)"},
}


@dataclass
class ModelStatus:
    name: str
    file: str
    purpose: str
    optional: bool = False
    present: bool = False
    signature_valid: bool = False
    approved: bool = False
    loaded: bool = False
    sha256: str | None = None
    model_version: str | None = None
    manifest_version: int | None = None
    approval_status: str | None = None
    approved_by: str | None = None
    reason: str | None = None
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


class ModelRegistry:
    def __init__(self, weights_dir: Path | None = None, signer: Signer | None = None,
                 record_events: bool = True, approval_signer: Signer | None = None):
        self.weights_dir = Path(weights_dir or config.WEIGHTS_DIR)
        self.record_events = record_events
        # Two distinct keys: `signer` verifies the build, `approval_signer` the clearance.
        self.signer = signer or Signer()
        self.approval_signer = approval_signer
        self._models: dict[str, object] = {}
        self._status: dict[str, ModelStatus] = {}
        self._lock = threading.Lock()

    def path_for(self, name: str) -> Path:
        return self.weights_dir / MODEL_SPECS[name]["file"]

    def check(self, name: str) -> ModelStatus:
        spec = MODEL_SPECS[name]
        path = self.path_for(name)
        status = ModelStatus(name=name, file=spec["file"], purpose=spec["purpose"], present=path.exists(),
                             optional=bool(spec.get("optional")))
        if not status.present:
            status.reason = "weight file not found"
            return status
        result = self.signer.verify_weight_file(path, self.weights_dir)
        status.signature_valid = bool(result.get("verified"))
        status.sha256 = result.get("sha256")
        status.reason = result.get("reason")
        if not status.signature_valid:
            return status

        # Integrity passed. Now decide whether this is a model we are allowed to run.
        manifest = self._manifest()
        if manifest is None:
            status.reason = "signed manifest could not be read"
            return status
        verdict = model_provenance.check(name, manifest, sha256=status.sha256,
                                         weights_dir=self.weights_dir,
                                         approval_signer=self.approval_signer)
        status.approved = verdict.ok
        status.model_version = verdict.model_version
        status.manifest_version = verdict.manifest_version
        status.approval_status = verdict.approval_status
        status.approved_by = verdict.approved_by
        if not verdict.ok:
            status.reason = verdict.reason
        return status

    def _manifest(self) -> dict | None:
        """The manifest body. Only read after its signature has verified."""
        import json

        try:
            return json.loads((self.weights_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def get(self, name: str):
        """Return the loaded model, or None if it is missing or failed verification."""
        with self._lock:
            if name in self._models:
                return self._models[name]
            status = self.check(name)
            model = None
            # Approval gates both load paths - the YOLO models and the panoramic
            # state dicts - so neither can reach inference unapproved.
            usable = status.present and status.signature_valid and status.approved
            if usable and MODEL_SPECS[name]["task"] == "torch_state_dict":
                # verified file; the caller builds the network and loads the state dict
                model = self.path_for(name)
                status.loaded = True
            elif usable:
                try:
                    from ultralytics import YOLO

                    model = YOLO(str(self.path_for(name)))
                    status.loaded = True
                    status.extra["classes"] = len(getattr(model, "names", {}) or {})
                except Exception as exc:  # corrupt file that still matched its hash, wrong format, etc.
                    status.reason = f"load failed: {type(exc).__name__}"
            if status.loaded and status.manifest_version is not None:
                # Only a model that actually loaded moves the floor forward, so a failed
                # load cannot raise the bar against the version still in use.
                model_provenance.raise_floor(status.manifest_version)
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
            audit().record("MODEL_LOADED", actor="system", resource=status.file,
                           details={"sha256": status.sha256, "model_version": status.model_version,
                                    "manifest_version": status.manifest_version,
                                    "approved_by": status.approved_by})
        elif status.present:
            logger.error("[SECURITY] Refusing to load %s: %s", status.file, status.reason)
            # The reason names which gate failed; it never quotes hashes, paths or key
            # material, so the log stays safe for an auditor to read.
            audit().record("MODEL_LOAD_REFUSED", outcome="denied", actor="system", resource=status.file,
                           details={"reason": status.reason, "model_version": status.model_version,
                                    "approval_status": status.approval_status})


_registry: ModelRegistry | None = None


def registry() -> ModelRegistry:
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
