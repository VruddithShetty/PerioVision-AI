"""RSA-PSS (SHA-256) signing and verification for model weights and generated reports.

* Model weights: `weights/manifest.json` lists every weight file with its SHA-256
  and size, plus every JSON file that changes what a model outputs (the conformal
  calibration, the whole-film decision thresholds and conformal radius, and the
  risk model's coefficients, listed under `external/`); `weights/manifest.json.sig`
  is an RSA-PSS signature over that manifest. `app/ml/registry.py` refuses to load any file that is missing from
  the signed manifest or whose hash no longer matches.
* Reports: the SHA-256 of the PDF bytes is signed, and the signature is stored
  with the report record so `/api/reports/verify` can check it later.

Only the public key is needed to verify. The private key
(`keys/model_signing.pem`) is encrypted with MODEL_SIGNING_PASSWORD and is only
used by `scripts/sign_model.py` and the report generator.
"""
from __future__ import annotations

import base64
import datetime as dt
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
APPROVALS_NAME = "approvals.json"  # written by security/model_approval.py, which imports it from here
WEIGHT_SUFFIXES = {".pt", ".pth", ".onnx", ".pkl", ".joblib", ".json"}
# Files that sit in weights/ but are not model behaviour, so the manifest must not
# hash them. The manifest cannot contain itself. approvals.json is rewritten every
# time a model is cleared, and signing it would mean the next approval invalidated
# the manifest and the registry refused every model.
UNSIGNED_NAMES = {MANIFEST_NAME, APPROVALS_NAME}
# Model-behaviour files kept outside weights/ (they live with the code); signed under these manifest keys.
EXTERNAL_FILES = {"external/risk_model_nhanes.json":
                  Path(__file__).resolve().parent.parent / "ml" / "fusion" / "risk_model_nhanes.json"}


class SigningError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _next_manifest_version(weights_dir: Path) -> int:
    """One past the version in the manifest already present, so re-signing moves forward."""
    existing = Path(weights_dir) / MANIFEST_NAME
    if not existing.exists():
        return 1
    try:
        return int(json.loads(existing.read_text(encoding="utf-8")).get("manifest_version", 0)) + 1
    except (ValueError, OSError):
        return 1


class Signer:
    """Signs with one named keypair.

    Two exist, deliberately held by different people:

      model_signing   the build key. Attests "these are the bytes, this is the
                      version, this is where they came from."
      model_approval  the approval key. Attests "I clear this exact model, at this
                      exact version and hash, for clinical use."

    Splitting them is the point. With one key, whoever can sign a model can also
    mark it approved, so approval records who built it rather than who cleared it.
    """

    def __init__(self, keys_dir: Path | None = None, password: str | None = None,
                 key_name: str = "model_signing", password_env: str | None = None):
        self.keys_dir = Path(keys_dir or config.KEYS_DIR)
        self.key_name = key_name
        self.password_env = password_env or f"{key_name.upper()}_PASSWORD"
        self.priv_path = self.keys_dir / f"{key_name}.pem"
        self.pub_path = self.keys_dir / f"{key_name}.pub"
        pw = password if password is not None else os.environ.get(self.password_env)
        self.password = pw.encode() if pw else None

    # ---------- keys ----------
    def generate_keypair(self, overwrite: bool = False) -> None:
        if self.priv_path.exists() and not overwrite:
            raise SigningError(f"{self.priv_path} already exists; refusing to overwrite it.")
        if not self.password:
            raise SigningError(f"{self.password_env} is not set.")
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
            raise SigningError(f"{self.password_env} is not set in .env.")
        if not self.priv_path.exists():
            raise SigningError(
                f"No {self.key_name} key. Run: python scripts/sign_model.py --init-keys")
        try:
            # A wrong password raises; the key file is never deleted or regenerated here.
            return serialization.load_pem_private_key(self.priv_path.read_bytes(), password=self.password)
        except (ValueError, TypeError) as exc:
            raise SigningError(
                f"Could not unlock the {self.key_name} key with {self.password_env}.") from exc

    def _public_key(self):
        if not self.pub_path.exists():
            raise SigningError(f"Public key missing (keys/{self.key_name}.pub).")
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
    def build_manifest(self, weights_dir: Path, models: dict | None = None,
                       manifest_version: int | None = None) -> dict:
        """Hash every weight file, and carry per-model provenance when it is supplied.

        `models` maps a model name to its identity, version, build provenance and
        approval record. `manifest_version` is a counter that must increase with each
        signing; the registry refuses a manifest older than one it has already
        accepted, which is what stops an archived bundle being replayed.
        """
        files = {}
        for p in sorted(Path(weights_dir).rglob("*")):
            if p.is_file() and p.suffix.lower() in WEIGHT_SUFFIXES and p.name not in UNSIGNED_NAMES:
                rel = p.relative_to(weights_dir).as_posix()
                files[rel] = {"sha256": sha256_file(p), "size": p.stat().st_size}
        for key, p in EXTERNAL_FILES.items():
            if p.is_file():
                files[key] = {"sha256": sha256_file(p), "size": p.stat().st_size}
        manifest = {"version": 1, "files": files}
        if models is not None:
            # Bind each declared model to the hash of the file it names, so the
            # provenance block cannot describe one file while another is loaded.
            enriched = {}
            for name, meta in models.items():
                entry = dict(meta)
                rel = entry.get("file")
                if rel in files:
                    entry["sha256"] = files[rel]["sha256"]
                enriched[name] = entry
            manifest["models"] = enriched
            manifest["manifest_version"] = int(
                manifest_version if manifest_version is not None else _next_manifest_version(weights_dir))
            manifest["created_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        return manifest

    def sign_manifest(self, weights_dir: Path, models: dict | None = None,
                      manifest_version: int | None = None) -> dict:
        weights_dir = Path(weights_dir)
        manifest = self.build_manifest(weights_dir, models, manifest_version)
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
        external = {v.resolve(): k for k, v in EXTERNAL_FILES.items()}
        try:
            rel = path.resolve().relative_to(weights_dir.resolve()).as_posix()
        except ValueError:
            rel = external.get(path.resolve())
            if rel is None:
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
