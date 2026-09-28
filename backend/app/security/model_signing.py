"""RSA-PSS (SHA-256) signing and verification for model weights and generated reports.

* Model weights: `weights/manifest.json` lists every weight file with its SHA-256
  and size; `weights/manifest.json.sig` is an RSA-PSS signature over that
  manifest. `app/ml/registry.py` refuses to load any file that is missing from
  the signed manifest or whose hash no longer matches.
* Reports: the SHA-256 of the PDF bytes is signed, and the signature is stored
  with the report record so `/api/reports/verify` can check it later.

Only the public key is needed to verify. The private key
(`keys/model_signing.pem`) is encrypted with MODEL_SIGNING_PASSWORD and is only
used by `scripts/sign_model.py` and the report generator.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app import config

PSS = padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH)
MANIFEST_NAME = "manifest.json"
WEIGHT_SUFFIXES = {".pt", ".pth", ".onnx", ".pkl", ".joblib"}


class SigningError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Signer:
    def __init__(self, keys_dir: Path | None = None, password: str | None = None):
        self.keys_dir = Path(keys_dir or config.KEYS_DIR)
        self.priv_path = self.keys_dir / "model_signing.pem"
        self.pub_path = self.keys_dir / "model_signing.pub"
        pw = password if password is not None else os.environ.get("MODEL_SIGNING_PASSWORD")
        self.password = pw.encode() if pw else None

    # ---------- keys ----------
    def generate_keypair(self, overwrite: bool = False) -> None:
        if self.priv_path.exists() and not overwrite:
            raise SigningError(f"{self.priv_path} already exists; refusing to overwrite it.")
        if not self.password:
            raise SigningError("MODEL_SIGNING_PASSWORD is not set.")
        self.keys_dir.mkdir(parents=True, exist_ok=True)
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        self.priv_path.write_bytes(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(self.password)))
        self.pub_path.write_bytes(key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))

    def has_private_key(self) -> bool:
        return self.priv_path.exists() and bool(self.password)

    def _private_key(self):
        if not self.password:
            raise SigningError("MODEL_SIGNING_PASSWORD is not set in .env.")
        if not self.priv_path.exists():
            raise SigningError("No signing key. Run: python scripts/sign_model.py --init-keys")
        try:
            # A wrong password raises; the key file is never deleted or regenerated here.
            return serialization.load_pem_private_key(self.priv_path.read_bytes(), password=self.password)
        except (ValueError, TypeError) as exc:
            raise SigningError("Could not unlock the signing key with MODEL_SIGNING_PASSWORD.") from exc

    def _public_key(self):
        if not self.pub_path.exists():
            raise SigningError("Public signing key missing (keys/model_signing.pub).")
        return serialization.load_pem_public_key(self.pub_path.read_bytes())

    def public_key_fingerprint(self) -> str | None:
        if not self.pub_path.exists():
            return None
        return hashlib.sha256(self.pub_path.read_bytes()).hexdigest()[:16]

    # ---------- raw bytes ----------
    def sign_bytes(self, data: bytes) -> str:
        return base64.b64encode(self._private_key().sign(data, PSS, hashes.SHA256())).decode()

    def verify_bytes(self, data: bytes, signature_b64: str) -> bool:
        try:
            self._public_key().verify(base64.b64decode(signature_b64), data, PSS, hashes.SHA256())
            return True
        except (InvalidSignature, ValueError, TypeError):
            return False

    # ---------- weight manifest ----------
    def build_manifest(self, weights_dir: Path) -> dict:
        files = {}
        for p in sorted(Path(weights_dir).rglob("*")):
            if p.is_file() and p.suffix.lower() in WEIGHT_SUFFIXES:
                rel = p.relative_to(weights_dir).as_posix()
                files[rel] = {"sha256": sha256_file(p), "size": p.stat().st_size}
        return {"version": 1, "files": files}

    def sign_manifest(self, weights_dir: Path) -> dict:
        weights_dir = Path(weights_dir)
        manifest = self.build_manifest(weights_dir)
        body = json.dumps(manifest, sort_keys=True, indent=2).encode()
        (weights_dir / MANIFEST_NAME).write_bytes(body)
        (weights_dir / (MANIFEST_NAME + ".sig")).write_text(self.sign_bytes(body), encoding="utf-8")
        return manifest

    def verify_weight_file(self, path: Path, weights_dir: Path | None = None) -> dict:
        """Check one weight file against the signed manifest. Never raises."""
        weights_dir = Path(weights_dir or config.WEIGHTS_DIR)
        path = Path(path)
        manifest_path = weights_dir / MANIFEST_NAME
        sig_path = weights_dir / (MANIFEST_NAME + ".sig")
        if not path.exists():
            return {"verified": False, "reason": "weight file not found"}
        if not manifest_path.exists() or not sig_path.exists():
            return {"verified": False, "reason": "no signed manifest (run scripts/sign_model.py)"}
        body = manifest_path.read_bytes()
        try:
            if not self.verify_bytes(body, sig_path.read_text(encoding="utf-8").strip()):
                return {"verified": False, "reason": "manifest signature invalid (manifest altered)"}
        except SigningError as exc:
            return {"verified": False, "reason": str(exc)}
        try:
            rel = path.resolve().relative_to(weights_dir.resolve()).as_posix()
        except ValueError:
            return {"verified": False, "reason": "file is outside the weights folder"}
        entry = json.loads(body).get("files", {}).get(rel)
        if entry is None:
            return {"verified": False, "reason": "file is not in the signed manifest"}
        actual = sha256_file(path)
        if actual != entry["sha256"]:
            return {"verified": False, "reason": "hash mismatch (file altered since signing)", "sha256": actual}
        return {"verified": True, "sha256": actual}


class ModelIntegrityVerifier(Signer):
    """Backward-compatible name used by older modules."""

    def verify_model(self, model_path: str) -> dict:
        return self.verify_weight_file(Path(model_path))
