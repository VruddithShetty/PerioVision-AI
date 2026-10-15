"""Provenance and approval checks that run after a model's signature verifies.

A valid signature proves a file has not been altered since it was signed. It does
not prove the file is the model this deployment is supposed to run: an archived
bundle of an old weight file together with its own still-valid manifest and
signature verifies perfectly, and so does a model that was signed for evaluation
and never approved for clinical use.

So the signed manifest also carries, per model: an identity, a version, build
provenance, and an approval record. This module checks those, and refuses:

  unknown model        the manifest has no entry for the model being loaded
  unapproved model     approval_status is anything other than "approved"
  wrong model          the entry points at a different weight file
  wrong version        a deployment pinned an exact version and this is not it
  downgrade            the manifest is older than one this deployment already ran

Rollback is caught with a floor: the highest manifest_version seen is recorded
outside the weights directory and never decreases. The weights directory is
mounted read-only in the container while the floor lives in writable storage, so
restoring an old signed bundle cannot also restore the floor that would accept it.
This mirrors how the audit log anchors Merkle roots outside the database.

Refusal reasons are written to the audit log, so they name what failed without
quoting hashes, paths or any other material an attacker could use.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from app import config

logger = logging.getLogger(__name__)

APPROVED = "approved"
# Fields a model entry must carry before it is considered describable at all.
REQUIRED_FIELDS = ("file", "model_version", "approval_status")


@dataclass
class ProvenanceResult:
    ok: bool
    reason: str | None = None
    model_version: str | None = None
    manifest_version: int | None = None
    approval_status: str | None = None
    approved_by: str | None = None

    def as_dict(self) -> dict:
        return {"model_version": self.model_version, "manifest_version": self.manifest_version,
                "approval_status": self.approval_status, "approved_by": self.approved_by}


# ----------------------------------------------------------- version floor ---
def _floor_path() -> Path:
    return Path(config.MODEL_FLOOR_FILE)


def read_floor() -> int:
    """Highest manifest_version this deployment has accepted. 0 when nothing has run yet."""
    path = _floor_path()
    if not path.exists():
        return 0
    try:
        return int(json.loads(path.read_text(encoding="utf-8")).get("manifest_version", 0))
    except (ValueError, OSError) as exc:
        # A corrupt floor must not silently become 0, which would re-open rollback.
        logger.error("[SECURITY] Model version floor is unreadable (%s); treating it as blocking.", exc)
        raise ProvenanceFloorError("model version floor is unreadable") from exc


def raise_floor(manifest_version: int) -> None:
    """Record a newly accepted manifest version. Never lowers the floor."""
    if manifest_version <= read_floor():
        return
    path = _floor_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"manifest_version": int(manifest_version)}), encoding="utf-8")


class ProvenanceFloorError(RuntimeError):
    """The floor could not be read, so downgrade protection cannot be enforced."""


# ------------------------------------------------------------------ checks ---
def check(name: str, manifest: dict, sha256: str | None = None,
          weights_dir=None, approval_signer=None) -> ProvenanceResult:
    """Decide whether the model called `name` in this manifest may be loaded.

    `sha256` is the hash of the file on disk. It is matched against a separately
    signed approval, so clearance covers specific bytes rather than a version label.
    """
    models = manifest.get("models")
    if not isinstance(models, dict):
        return ProvenanceResult(False, "manifest carries no provenance (re-sign with scripts/sign_model.py)")

    entry = models.get(name)
    if not isinstance(entry, dict):
        return ProvenanceResult(False, "model is not described in the signed manifest")

    missing = [f for f in REQUIRED_FIELDS if not entry.get(f)]
    if missing:
        return ProvenanceResult(False, f"provenance is incomplete (missing: {', '.join(sorted(missing))})")

    status = str(entry["approval_status"]).lower()
    model_version = str(entry["model_version"])
    manifest_version = manifest.get("manifest_version")
    result = ProvenanceResult(True, None, model_version, manifest_version, status)

    expected_file = (config.MODEL_SPECS_FILES or {}).get(name)
    if expected_file and entry["file"] != expected_file:
        return ProvenanceResult(False, "manifest entry points at a different weight file",
                                model_version, manifest_version, status)

    if status != APPROVED:
        return ProvenanceResult(False, f"model is not approved for clinical use (status: {status})",
                                model_version, manifest_version, status)

    # The manifest only *declares* approval, and the build key signs the manifest. The
    # authority is a separate record under a separate key, naming this exact hash, so
    # whoever builds a model cannot also clear it.
    from app.security import model_approval

    if not sha256:
        return ProvenanceResult(False, "model hash unavailable, so approval cannot be matched",
                                model_version, manifest_version, status)
    try:
        record = model_approval.check(name, model_version, sha256, weights_dir, approval_signer)
    except model_approval.ApprovalError as exc:
        return ProvenanceResult(False, f"clinical approval missing or invalid: {exc}",
                                model_version, manifest_version, status)

    pinned = config.MODEL_EXPECTED_VERSIONS.get(name)
    if pinned and pinned != model_version:
        return ProvenanceResult(False, "model version is not the version this deployment pins",
                                model_version, manifest_version, status)

    if not isinstance(manifest_version, int):
        return ProvenanceResult(False, "manifest has no version, so rollback cannot be ruled out",
                                model_version, manifest_version, status)

    floor = read_floor()
    if manifest_version < floor:
        return ProvenanceResult(False, "manifest is older than one already accepted (downgrade refused)",
                                model_version, manifest_version, status)

    result.approved_by = record.approved_by
    return result
