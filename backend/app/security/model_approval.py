"""Clinical approval of a model, signed by a key the model builder does not hold.

The approval gate used to read `approval_status` out of the manifest. That manifest is
signed by the build key, so whoever could sign a model could also mark it approved:
approval recorded who built the model, not who cleared it for use on patients.

Approval is now a separate artifact under a separate key:

    weights/approvals.json       the record: which model, which version, which hash
    weights/approvals.json.sig   RSA-PSS over that record, by keys/model_approval.pem

An approval names the model's **exact SHA-256**, so it covers specific bytes and nothing
else. Rebuilding a model - even to the same version number - produces a different hash and
the old approval no longer applies. Neither key is sufficient alone:

    build key only     can ship bytes, cannot clear them for clinical use
    approval key only  can clear a hash, cannot produce bytes that match one

Both keys in one pair of hands defeats this, as it would any separation of duties. What it
buys is that the split is now expressible and enforced, rather than impossible.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from app import config
from app.security.model_signing import APPROVALS_NAME, Signer, SigningError

logger = logging.getLogger(__name__)

APPROVAL_KEY = "model_approval"
APPROVED = "approved"


class ApprovalError(RuntimeError):
    """Approval material is missing, unreadable or does not verify."""


@dataclass
class ApprovalRecord:
    model_id: str
    model_version: str
    sha256: str
    approved_by: str
    approved_at: str
    expires_at: str | None = None
    note: str | None = None

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


def approval_signer(keys_dir: Path | None = None, password: str | None = None) -> Signer:
    """A Signer bound to the approval keypair, never the build keypair."""
    return Signer(keys_dir=keys_dir, password=password, key_name=APPROVAL_KEY,
                  password_env="MODEL_APPROVAL_PASSWORD")


# ------------------------------------------------------------------- writing ---
def build_approvals(records: list[ApprovalRecord]) -> dict:
    return {
        "version": 1,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "approvals": [r.as_dict() for r in records],
    }


def sign_approvals(weights_dir: Path, records: list[ApprovalRecord],
                   signer: Signer | None = None) -> dict:
    """Write and sign the approval record. Needs the approval key, not the build key."""
    weights_dir = Path(weights_dir)
    signer = signer or approval_signer()
    document = build_approvals(records)
    body = json.dumps(document, sort_keys=True, indent=2).encode()
    (weights_dir / APPROVALS_NAME).write_bytes(body)
    (weights_dir / (APPROVALS_NAME + ".sig")).write_text(signer.sign_bytes(body), encoding="utf-8")
    return document


# ------------------------------------------------------------------- reading ---
def load_approvals(weights_dir: Path | None = None, signer: Signer | None = None) -> dict:
    """Return the verified approval document, or raise. Never returns unverified content."""
    weights_dir = Path(weights_dir or config.WEIGHTS_DIR)
    body_path = weights_dir / APPROVALS_NAME
    sig_path = weights_dir / (APPROVALS_NAME + ".sig")
    if not body_path.exists() or not sig_path.exists():
        raise ApprovalError("no signed approval record (run scripts/approve_model.py)")

    signer = signer or approval_signer()
    body = body_path.read_bytes()
    try:
        verified = signer.verify_bytes(body, sig_path.read_text(encoding="utf-8").strip())
    except SigningError as exc:
        # Typically the approval public key is absent on this host.
        raise ApprovalError(str(exc)) from exc
    if not verified:
        raise ApprovalError("approval signature invalid (record altered, or wrong approval key)")
    try:
        return json.loads(body)
    except ValueError as exc:
        raise ApprovalError("approval record is not valid JSON") from exc


def find(document: dict, model_id: str, model_version: str, sha256: str,
         now: dt.datetime | None = None) -> ApprovalRecord:
    """The approval covering this exact model, version and hash, or raise."""
    now = now or dt.datetime.now(dt.timezone.utc)
    entries = document.get("approvals")
    if not isinstance(entries, list):
        raise ApprovalError("approval record contains no approvals")

    for raw in entries:
        if not isinstance(raw, dict):
            continue
        if raw.get("model_id") != model_id:
            continue
        if str(raw.get("model_version")) != str(model_version):
            raise ApprovalError(
                f"approval covers version {raw.get('model_version')}, not {model_version}")
        if str(raw.get("sha256", "")).lower() != str(sha256).lower():
            # The usual cause is a rebuild: same version, different bytes.
            raise ApprovalError("approval covers a different build of this model version")
        for required in ("approved_by", "approved_at"):
            if not raw.get(required):
                raise ApprovalError(f"approval is missing {required}")

        expires = raw.get("expires_at")
        if expires:
            try:
                deadline = dt.datetime.fromisoformat(expires)
            except ValueError as exc:
                raise ApprovalError("approval has an unreadable expiry") from exc
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=dt.timezone.utc)
            if now > deadline:
                raise ApprovalError("approval has expired")

        return ApprovalRecord(
            model_id=model_id, model_version=str(raw["model_version"]), sha256=str(raw["sha256"]),
            approved_by=str(raw["approved_by"]), approved_at=str(raw["approved_at"]),
            expires_at=expires, note=raw.get("note"))

    raise ApprovalError("no approval has been issued for this model")


def check(model_id: str, model_version: str, sha256: str, weights_dir: Path | None = None,
          signer: Signer | None = None, now: dt.datetime | None = None) -> ApprovalRecord:
    """Load, verify and match in one call. Raises ApprovalError with a safe message."""
    return find(load_approvals(weights_dir, signer), model_id, model_version, sha256, now)
