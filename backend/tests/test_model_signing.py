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
