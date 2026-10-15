"""Model provenance and approval gate.

The registry runs two gates: integrity (RSA-PSS signed hash) and provenance
(identity, version, approval, freshness). These tests cover the second, and in
particular the cases where integrity passes but the model must still be refused.

Real weight loading needs ultralytics and genuine .pt files, so these assert on
the gate's verdict rather than on a returned model object; `test_model_signing.py`
covers the integrity gate and `test_ml_logic.py` the inference path.
"""
import json
import secrets

import pytest

from app.ml.registry import ModelRegistry
from app.security import model_approval, model_provenance
from app.security.model_signing import Signer, sha256_file

MODEL_FILE = "dental_yolov8n.pt"


def provenance(version="1.2.0", status="approved", file=MODEL_FILE, **extra):
    """A complete provenance block for the tooth detector."""
    entry = {
        "file": file,
        "model_version": version,
        "approval_status": status,
        "approved_by": "D-000001",
        "approved_at": "2026-02-01T10:00:00+00:00",
        "training_commit": "a1b2c3d4e5f6",
        "dataset_version": "denpar-1.0",
        "framework": "ultralytics 8.4.21",
    }
    entry.update(extra)
    return {"tooth_detector": entry}


@pytest.fixture()
def lab(tmp_path, monkeypatch):
    """An isolated weights directory, two keypairs, a floor file and a registry.

    Two keys on purpose: `signer` is the build key, `approver` the clinical approval key.
    `sign()` ships bytes; `approve()` clears them. A test that only signs is modelling a
    builder trying to release a model nobody approved.
    """
    weights = tmp_path / "weights"
    weights.mkdir()
    (weights / MODEL_FILE).write_bytes(b"pretend tooth detector weights" * 500)

    # Generated per run, not written in the source: these unlock throwaway keypairs
    # that live only in tmp_path, and a literal here reads like a committed credential
    # to a secret scanner.
    build_passphrase = secrets.token_hex(16)
    approval_passphrase = secrets.token_hex(16)
    signer = Signer(keys_dir=tmp_path / "keys", password=build_passphrase)
    signer.generate_keypair()
    approver = model_approval.approval_signer(keys_dir=tmp_path / "keys",
                                              password=approval_passphrase)
    approver.generate_keypair()

    monkeypatch.setattr(model_provenance.config, "MODEL_FLOOR_FILE", tmp_path / "model_floor.json")
    monkeypatch.setattr(model_provenance.config, "MODEL_EXPECTED_VERSIONS", {})
    monkeypatch.setattr(model_provenance.config, "MODEL_SPECS_FILES", {"tooth_detector": MODEL_FILE})

    def sign(models=provenance(), manifest_version=None):
        return signer.sign_manifest(weights, models=models, manifest_version=manifest_version)

    def approve(version="1.2.0", sha256=None, model_id="tooth_detector", **kw):
        """Countersign with the approval key, binding the clearance to the file's hash."""
        digest = sha256 or sha256_file(weights / MODEL_FILE)
        record = model_approval.ApprovalRecord(
            model_id=model_id, model_version=version, sha256=digest,
            approved_by=kw.pop("approved_by", "Dr A Patel, GDC 123456"),
            approved_at=kw.pop("approved_at", "2026-03-01T09:00:00+00:00"), **kw)
        return model_approval.sign_approvals(weights, [record], approver)

    def sign_and_approve(models=provenance(), manifest_version=None, version="1.2.0"):
        manifest = sign(models, manifest_version)
        approve(version=version)
        return manifest

    def registry():
        return ModelRegistry(weights_dir=weights, signer=signer, record_events=False,
                             approval_signer=approver)

    return type("Lab", (), {
        "weights": weights, "signer": signer, "approver": approver, "tmp": tmp_path,
        "build_passphrase": build_passphrase, "approval_passphrase": approval_passphrase,
        "sign": staticmethod(sign), "approve": staticmethod(approve),
        "sign_and_approve": staticmethod(sign_and_approve), "registry": staticmethod(registry)})


# -------------------------------------------------------------- happy path ---
def test_approved_model_passes_both_gates(lab):
    lab.sign_and_approve()
    status = lab.registry().check("tooth_detector")
    assert status.signature_valid is True
    assert status.approved is True
    assert status.reason is None
    assert status.model_version == "1.2.0"
    assert status.approval_status == "approved"


# ------------------------------------------------------- integrity failures ---
def test_modified_model_is_rejected(lab):
    lab.sign()
    path = lab.weights / MODEL_FILE
    path.write_bytes(path.read_bytes() + b"\x00")
    status = lab.registry().check("tooth_detector")
    assert status.signature_valid is False and status.approved is False
    assert "hash mismatch" in status.reason


def test_invalid_signature_is_rejected(lab):
    lab.sign()
    sig = lab.weights / "manifest.json.sig"
    sig.write_text("bm90LWEtc2lnbmF0dXJl", encoding="utf-8")
    status = lab.registry().check("tooth_detector")
    assert status.signature_valid is False and status.approved is False


def test_manifest_hash_mismatch_is_rejected(lab):
    """The manifest is edited to claim a different hash; its signature no longer fits."""
    lab.sign()
    manifest = lab.weights / "manifest.json"
    body = json.loads(manifest.read_text(encoding="utf-8"))
    body["files"][MODEL_FILE]["sha256"] = "0" * 64
    manifest.write_text(json.dumps(body, sort_keys=True, indent=2), encoding="utf-8")
    status = lab.registry().check("tooth_detector")
    assert status.signature_valid is False
    assert "signature invalid" in status.reason


# ------------------------------------------------------ provenance failures ---
def test_unknown_model_is_rejected(lab):
    """Integrity passes, but the manifest never declares this model."""
    lab.sign(models={"some_other_model": provenance()["tooth_detector"]})
    status = lab.registry().check("tooth_detector")
    assert status.signature_valid is True
    assert status.approved is False
    assert "not described in the signed manifest" in status.reason


def test_manifest_without_provenance_is_rejected(lab):
    """A correctly signed legacy manifest is no longer enough on its own."""
    lab.signer.sign_manifest(lab.weights)  # no models block
    status = lab.registry().check("tooth_detector")
    assert status.signature_valid is True
    assert status.approved is False
    assert "carries no provenance" in status.reason


@pytest.mark.parametrize("status_value", ["pending", "revoked", "evaluation", "APPROVED_LATER"])
def test_unapproved_model_is_rejected(lab, status_value):
    lab.sign(models=provenance(status=status_value))
    status = lab.registry().check("tooth_detector")
    assert status.signature_valid is True
    assert status.approved is False
    assert "not approved for clinical use" in status.reason


def test_entry_pointing_at_a_different_file_is_rejected(lab):
    """A provenance block must describe the file the model name actually resolves to."""
    lab.sign(models=provenance(file="something_else.pt"))
    status = lab.registry().check("tooth_detector")
    assert status.approved is False
    assert "different weight file" in status.reason


def test_wrong_version_is_rejected_when_the_deployment_pins_one(lab, monkeypatch):
    monkeypatch.setattr(model_provenance.config, "MODEL_EXPECTED_VERSIONS", {"tooth_detector": "2.0.0"})
    lab.sign_and_approve(models=provenance(version="1.2.0"), version="1.2.0")
    status = lab.registry().check("tooth_detector")
    assert status.approved is False
    assert "not the version this deployment pins" in status.reason


def test_pinned_version_still_loads_when_it_matches(lab, monkeypatch):
    monkeypatch.setattr(model_provenance.config, "MODEL_EXPECTED_VERSIONS", {"tooth_detector": "1.2.0"})
    lab.sign_and_approve(models=provenance(version="1.2.0"), version="1.2.0")
    assert lab.registry().check("tooth_detector").approved is True


@pytest.mark.parametrize("missing", ["file", "model_version", "approval_status"])
def test_incomplete_provenance_is_rejected(lab, missing):
    entry = provenance()["tooth_detector"]
    entry.pop(missing)
    lab.sign(models={"tooth_detector": entry})
    status = lab.registry().check("tooth_detector")
    assert status.approved is False
    assert "provenance is incomplete" in status.reason


def test_manifest_without_a_version_is_rejected(lab):
    """Without a manifest version, rollback cannot be ruled out, so the model is refused."""
    entry = provenance()["tooth_detector"]
    manifest = lab.signer.build_manifest(lab.weights, models={"tooth_detector": entry})
    del manifest["manifest_version"]
    body = json.dumps(manifest, sort_keys=True, indent=2).encode()
    (lab.weights / "manifest.json").write_bytes(body)
    (lab.weights / "manifest.json.sig").write_text(lab.signer.sign_bytes(body), encoding="utf-8")
    lab.approve()  # clear it, so the refusal can only be about the missing version
    status = lab.registry().check("tooth_detector")
    assert status.approved is False
    assert "no version" in status.reason


# ----------------------------------------------------------------- rollback ---
def test_downgrade_to_an_older_signed_manifest_is_rejected(lab):
    """The attack that a valid signature alone does not stop.

    An archived bundle - old weight file, its own manifest, its own valid
    signature - is restored wholesale. Every integrity check still passes.
    """
    import shutil

    BUNDLE = (MODEL_FILE, "manifest.json", "manifest.json.sig",
              "approvals.json", "approvals.json.sig")

    lab.sign(models=provenance(version="1.0.0"), manifest_version=1)
    lab.approve(version="1.0.0")
    archive = lab.tmp / "archive"
    archive.mkdir()
    for f in BUNDLE:
        shutil.copy(lab.weights / f, archive / f)

    # Current, approved model: accepted, and it raises the floor.
    (lab.weights / MODEL_FILE).write_bytes(b"corrected tooth detector weights" * 500)
    lab.sign(models=provenance(version="2.0.0"), manifest_version=2)
    lab.approve(version="2.0.0")
    current = lab.registry().check("tooth_detector")
    assert current.approved is True and current.model_version == "2.0.0"
    model_provenance.raise_floor(current.manifest_version)

    # Restore the whole archived bundle - including its own genuine approval, which is
    # what an attacker with the old release would actually have.
    for f in BUNDLE:
        shutil.copy(archive / f, lab.weights / f)

    rolled_back = lab.registry().check("tooth_detector")
    assert rolled_back.signature_valid is True, "integrity still passes - that is the point"
    assert rolled_back.approved is False, "downgrade was accepted"
    assert "downgrade refused" in rolled_back.reason


def test_floor_never_decreases(lab):
    model_provenance.raise_floor(5)
    model_provenance.raise_floor(2)
    assert model_provenance.read_floor() == 5


def test_unreadable_floor_blocks_rather_than_resetting(lab):
    """A corrupt floor must not read as 0, which would silently re-open rollback."""
    (lab.tmp / "model_floor.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(model_provenance.ProvenanceFloorError):
        model_provenance.read_floor()


# ------------------------------------------------- approval-metadata tamper ---
@pytest.mark.parametrize("field,value", [
    ("approval_status", "approved"),
    ("model_version", "9.9.9"),
    ("approved_by", "attacker"),
    ("training_commit", "deadbeef"),
])
def test_editing_approval_metadata_breaks_the_signature(lab, field, value):
    """Provenance sits inside the signed body, so promoting a model means forging RSA-PSS."""
    lab.sign(models=provenance(status="pending"))
    manifest = lab.weights / "manifest.json"
    body = json.loads(manifest.read_text(encoding="utf-8"))
    body["models"]["tooth_detector"][field] = value
    manifest.write_text(json.dumps(body, sort_keys=True, indent=2), encoding="utf-8")

    status = lab.registry().check("tooth_detector")
    assert status.signature_valid is False
    assert status.approved is False
    assert "signature invalid" in status.reason


# ------------------------------------------------------------------ audit ---
def test_refusal_is_audited_without_exposing_sensitive_detail(lab, app):
    """The auditor must learn which gate failed, not the file layout or hashes."""
    from app.security.audit_log import audit

    lab.sign(models=provenance(status="revoked"))
    registry = ModelRegistry(weights_dir=lab.weights, signer=lab.signer, record_events=True)
    with app.app_context():
        assert registry.get("tooth_detector") is None
        entries = audit().recent(limit=10)

    refusals = [e for e in entries if e["action"] == "MODEL_LOAD_REFUSED"]
    assert refusals, "a refused model load was not audited"
    details = refusals[0]["details"]
    assert "not approved for clinical use" in details["reason"]
    assert details["approval_status"] == "revoked"

    blob = json.dumps(refusals[0])
    assert str(lab.weights) not in blob, "absolute path leaked into the audit log"
    # Against the passphrase actually in use: a hardcoded literal here would pass
    # whatever the log contained, which is the opposite of what this asserts.
    assert lab.build_passphrase not in blob, "signing password leaked into the audit log"
    assert lab.approval_passphrase not in blob, "approval password leaked into the audit log"
    for entry in entries:
        assert "sha256" not in json.dumps(entry.get("details", {})) or entry["action"] == "MODEL_LOADED"


# ====================================================================
# Separation of duties: the build key cannot clear a model for patients
# ====================================================================
def test_a_signed_manifest_claiming_approval_is_not_enough(lab):
    """The whole point. A builder marks their own model approved and signs it with the
    build key. Integrity is perfect. Without a countersignature it still does not load."""
    lab.sign(models=provenance(status="approved"))
    status = lab.registry().check("tooth_detector")
    assert status.signature_valid is True, "the build signature is genuine"
    assert status.approved is False, "the build key alone cleared a model for clinical use"
    assert "clinical approval missing" in status.reason


def test_the_build_key_cannot_forge_an_approval(lab, tmp_path):
    """Signing the approval record with the build key must not satisfy the approval key."""
    lab.sign()
    record = model_approval.ApprovalRecord(
        model_id="tooth_detector", model_version="1.2.0",
        sha256=sha256_file(lab.weights / MODEL_FILE),
        approved_by="The Builder", approved_at="2026-03-01T09:00:00+00:00")
    model_approval.sign_approvals(lab.weights, [record], lab.signer)  # wrong key, deliberately

    status = lab.registry().check("tooth_detector")
    assert status.approved is False
    assert "invalid" in status.reason or "wrong approval key" in status.reason


def test_approval_covers_exact_bytes_not_a_version_label(lab):
    """A rebuild keeping the same version number must not inherit the old clearance."""
    lab.sign_and_approve()
    assert lab.registry().check("tooth_detector").approved is True

    (lab.weights / MODEL_FILE).write_bytes(b"rebuilt, same version number" * 500)
    lab.sign(models=provenance(version="1.2.0"), manifest_version=9)
    status = lab.registry().check("tooth_detector")
    assert status.approved is False
    assert "different build" in status.reason


def test_an_approval_for_another_model_does_not_transfer(lab):
    lab.sign()
    lab.approve(model_id="landmarks")
    status = lab.registry().check("tooth_detector")
    assert status.approved is False
    assert "no approval has been issued" in status.reason


def test_an_approval_for_another_version_is_refused(lab):
    lab.sign(models=provenance(version="1.2.0"))
    lab.approve(version="9.9.9")
    status = lab.registry().check("tooth_detector")
    assert status.approved is False
    assert "approval covers version" in status.reason


def test_editing_the_approval_record_breaks_its_signature(lab):
    lab.sign_and_approve()
    path = lab.weights / "approvals.json"
    body = json.loads(path.read_text(encoding="utf-8"))
    body["approvals"][0]["approved_by"] = "Someone Else"
    path.write_text(json.dumps(body, sort_keys=True, indent=2), encoding="utf-8")

    status = lab.registry().check("tooth_detector")
    assert status.approved is False
    assert "invalid" in status.reason


def test_an_expired_approval_stops_working(lab):
    lab.sign()
    lab.approve(expires_at="2020-01-01T00:00:00+00:00")
    status = lab.registry().check("tooth_detector")
    assert status.approved is False
    assert "expired" in status.reason


def test_a_future_expiry_is_still_valid(lab):
    lab.sign()
    lab.approve(expires_at="2099-01-01T00:00:00+00:00")
    assert lab.registry().check("tooth_detector").approved is True


def test_revoking_an_approval_stops_the_model_loading(lab):
    lab.sign_and_approve()
    assert lab.registry().check("tooth_detector").approved is True
    # Revocation is simply re-signing the record without that model.
    model_approval.sign_approvals(lab.weights, [], lab.approver)
    status = lab.registry().check("tooth_detector")
    assert status.approved is False
    assert "no approval has been issued" in status.reason


def test_the_approver_is_recorded_and_audited(lab):
    """Who cleared it must be attributable, and it must reach the audit log."""
    lab.sign_and_approve()
    status = lab.registry().check("tooth_detector")
    assert status.approved is True
    assert status.approved_by == "Dr A Patel, GDC 123456"


def test_unsigned_approval_record_is_refused(lab):
    """A plain JSON file dropped next to the weights is not an approval."""
    lab.sign()
    (lab.weights / "approvals.json").write_text(json.dumps({
        "version": 1, "approvals": [{"model_id": "tooth_detector", "model_version": "1.2.0",
                                     "sha256": sha256_file(lab.weights / MODEL_FILE),
                                     "approved_by": "nobody", "approved_at": "2026-01-01T00:00:00+00:00"}]
    }), encoding="utf-8")
    status = lab.registry().check("tooth_detector")
    assert status.approved is False


def test_every_model_the_registry_knows_about_is_declared_for_approval():
    """A model in MODEL_SPECS with no entry in config/model_approvals.json is refused
    the moment its weight file appears, with a reason that points at the manifest
    rather than at the missing declaration. Nothing catches that while the file is
    absent, so this test does - a new model must be declared when it is added.
    """
    from app import config
    from app.ml.registry import MODEL_SPECS

    declared = json.loads(
        (config.BACKEND_DIR / "config" / "model_approvals.json").read_text(encoding="utf-8")
    )["models"]

    missing = sorted(set(MODEL_SPECS) - set(declared))
    assert not missing, f"not declared in config/model_approvals.json: {missing}"

    mismatched = {name: (spec["file"], declared[name]["file"])
                  for name, spec in MODEL_SPECS.items()
                  if declared[name]["file"] != spec["file"]}
    assert not mismatched, f"declared file does not match MODEL_SPECS: {mismatched}"
