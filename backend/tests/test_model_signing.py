"""RSA-PSS model signing: the registry must refuse unsigned or altered weights."""
import pytest

from app.ml.registry import ModelRegistry
from app.security.model_signing import Signer, SigningError


@pytest.fixture()
def signer(tmp_path):
    s = Signer(keys_dir=tmp_path / "keys", password="Unit-test-pass-1")
    s.generate_keypair()
    return s


def test_sign_and_verify_bytes(signer):
    sig = signer.sign_bytes(b"hello")
    assert signer.verify_bytes(b"hello", sig)
    assert not signer.verify_bytes(b"hellO", sig)


def test_existing_key_is_never_overwritten(signer):
    with pytest.raises(SigningError):
        signer.generate_keypair()


def test_wrong_password_raises_and_keeps_key(signer, tmp_path):
    other = Signer(keys_dir=tmp_path / "keys", password="wrong-password-9")
    with pytest.raises(SigningError):
        other.sign_bytes(b"x")
    assert (tmp_path / "keys" / "model_signing.pem").exists()


def test_manifest_detects_tampering(signer, tmp_path):
    weights = tmp_path / "weights"
    weights.mkdir()
    model = weights / "dental_yolov8n.pt"
    model.write_bytes(b"pretend weights" * 1000)
    assert signer.verify_weight_file(model, weights)["verified"] is False  # unsigned
    signer.sign_manifest(weights)
    assert signer.verify_weight_file(model, weights)["verified"] is True
    model.write_bytes(model.read_bytes() + b"\x00")                        # altered after signing
    res = signer.verify_weight_file(model, weights)
    assert res["verified"] is False and "hash mismatch" in res["reason"]


def test_forged_manifest_is_rejected(signer, tmp_path):
    weights = tmp_path / "weights"
    weights.mkdir()
    (weights / "dental_yolov8n.pt").write_bytes(b"a" * 100)
    signer.sign_manifest(weights)
    manifest = weights / "manifest.json"
    manifest.write_text(manifest.read_text().replace('"version": 1', '"version": 2'))
    assert "signature invalid" in signer.verify_weight_file(weights / "dental_yolov8n.pt", weights)["reason"]


def test_registry_refuses_unsigned_model(signer, tmp_path):
    weights = tmp_path / "weights"
    weights.mkdir()
    (weights / "dental_yolov8n.pt").write_bytes(b"not signed")
    reg = ModelRegistry(weights_dir=weights, signer=signer)
    assert reg.get("tooth_detector") is None
    status = {s["name"]: s for s in reg.status()}["tooth_detector"]
    assert status["present"] and not status["signature_valid"] and not status["loaded"]


def test_behaviour_changing_json_is_signed(signer, tmp_path):
    """Thresholds and calibration decide what a model outputs, so they are signed too."""
    weights = tmp_path / "weights"
    weights.mkdir()
    (weights / "dental_yolov8n.pt").write_bytes(b"pretend weights")
    calibration = weights / "conformal_calibration.json"
    calibration.write_text('{"q": 0.12}', encoding="utf-8")

    manifest = signer.sign_manifest(weights)
    assert "conformal_calibration.json" in manifest["files"]
    assert signer.verify_weight_file(calibration, weights)["verified"] is True

    calibration.write_text('{"q": 0.99}', encoding="utf-8")  # widen the interval silently
    assert signer.verify_weight_file(calibration, weights)["verified"] is False


def test_the_manifest_never_signs_itself_or_the_approvals_record(signer, tmp_path):
    """Both live in weights/ and both end in .json, which is now a signed suffix.

    The manifest cannot contain its own hash. approvals.json is rewritten every time a
    model is cleared, so signing it would mean the next approval invalidated the manifest
    and the registry refused every model - the approval gate would take the whole system
    down with it.
    """
    from app.security.model_signing import APPROVALS_NAME, MANIFEST_NAME

    weights = tmp_path / "weights"
    weights.mkdir()
    (weights / "dental_yolov8n.pt").write_bytes(b"pretend weights")
    (weights / APPROVALS_NAME).write_text('{"version": 1, "approvals": []}', encoding="utf-8")

    manifest = signer.sign_manifest(weights)
    assert MANIFEST_NAME not in manifest["files"]
    assert APPROVALS_NAME not in manifest["files"]

    # Re-approving rewrites approvals.json; the weights must still verify afterwards.
    (weights / APPROVALS_NAME).write_text('{"version": 1, "approvals": [1]}', encoding="utf-8")
    assert signer.verify_weight_file(weights / "dental_yolov8n.pt", weights)["verified"] is True
