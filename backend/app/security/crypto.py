"""AES-256-GCM encryption for data at rest, with key IDs and key rotation.

* Every encryption uses a fresh random 96-bit nonce (``os.urandom(12)``) and is
  authenticated (GCM tag), so tampering is detected on decrypt.
* Keys come from the environment (or a KMS-style JSON key file), never from code.
  Each ciphertext records the ID of the key that produced it, so old keys can
  stay available for decryption while new data uses the active key.
* Searchable fields use an HMAC "blind index" computed with a *separate* key
  derived via HKDF, so the encryption key itself is never used for hashing.

Key configuration (first match wins):
  FIELD_ENCRYPTION_KEYFILE   path to JSON {"active": "k2", "keys": {"k1": "<64 hex>", "k2": "<64 hex>"}}
  FIELD_ENCRYPTION_KEYS      "k2:<64 hex>,k1:<64 hex>" with FIELD_ENCRYPTION_ACTIVE_KID=k2
  FIELD_ENCRYPTION_KEY       single key, used as key ID "k1"
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

logger = logging.getLogger(__name__)

TOKEN_PREFIX = "enc:v1:"      # text tokens:   enc:v1:<kid>:<b64(nonce||ciphertext+tag)>
BLOB_MAGIC = b"PVE1"          # binary blobs:  PVE1 | kid_len(1) | kid | nonce(12) | ciphertext+tag
NONCE_BYTES = 12


class KeyConfigError(RuntimeError):
    pass


def _parse_key(kid: str, value: str) -> bytes:
    try:
        key = bytes.fromhex(value.strip())
    except ValueError as exc:
        raise KeyConfigError(f"Encryption key '{kid}' is not valid hex.") from exc
    if len(key) != 32:
        raise KeyConfigError(f"Encryption key '{kid}' must be 32 bytes (64 hex characters) for AES-256.")
    return key


@dataclass
class KeyRing:
    active_kid: str
    keys: dict[str, bytes]

    @classmethod
    def from_env(cls) -> "KeyRing":
        keyfile = os.getenv("FIELD_ENCRYPTION_KEYFILE")
        if keyfile:
            with open(keyfile, encoding="utf-8") as f:
                data = json.load(f)
            keys = {kid: _parse_key(kid, v) for kid, v in data["keys"].items()}
            return cls._checked(data["active"], keys)

        multi = os.getenv("FIELD_ENCRYPTION_KEYS")
        if multi:
            keys = {}
            for part in multi.split(","):
                kid, _, value = part.strip().partition(":")
                keys[kid] = _parse_key(kid, value)
            active = os.getenv("FIELD_ENCRYPTION_ACTIVE_KID") or next(iter(keys))
            return cls._checked(active, keys)

        single = os.getenv("FIELD_ENCRYPTION_KEY")
        if single:
            return cls._checked("k1", {"k1": _parse_key("k1", single)})

        if os.getenv("DB_MODE", "").lower() == "demo":
            logger.warning("[DEMO MODE] No FIELD_ENCRYPTION_KEY set; using a throwaway in-memory key.")
            return cls._checked("demo", {"demo": secrets.token_bytes(32)})
        raise KeyConfigError("No encryption key configured (set FIELD_ENCRYPTION_KEY in .env).")

    @classmethod
    def _checked(cls, active: str, keys: dict[str, bytes]) -> "KeyRing":
        if active not in keys:
            raise KeyConfigError(f"Active key ID '{active}' is not in the key ring.")
        for kid in keys:
            if not kid or ":" in kid or len(kid.encode()) > 32:
                raise KeyConfigError(f"Invalid key ID '{kid}'.")
        return cls(active, keys)

    @property
    def active_key(self) -> bytes:
        return self.keys[self.active_kid]


def _derive(key: bytes, purpose: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"periovision:" + purpose).derive(key)


class PHIEncryptor:
    """Field- and file-level encryption for protected health information."""

    ENCRYPTED_FIELDS = ("patient_name", "contact_number", "notes")
    INDEXED_FIELDS = ("patient_name", "contact_number")

    def __init__(self, key: str | None = None, keyring: KeyRing | None = None):
        if keyring is None:
            keyring = KeyRing._checked("k1", {"k1": _parse_key("k1", key)}) if key else KeyRing.from_env()
        self.keyring = keyring
        self.key_bytes = keyring.active_key  # kept for older scripts
        self._index_key = _derive(keyring.active_key, b"blind-index")
        self._pseudo_key = _derive(keyring.active_key, b"pseudonym")

    # ---------- text ----------
    def encrypt_random(self, data: str, aad: bytes | None = None) -> str:
        kid = self.keyring.active_kid
        nonce = os.urandom(NONCE_BYTES)
        ct = AESGCM(self.keyring.active_key).encrypt(nonce, str(data).encode(), aad)
        return f"{TOKEN_PREFIX}{kid}:{base64.b64encode(nonce + ct).decode()}"

    def decrypt_random(self, token: str, aad: bytes | None = None) -> str:
        if token.startswith(TOKEN_PREFIX):
            kid, _, payload = token[len(TOKEN_PREFIX):].partition(":")
            key = self._key_for(kid)
        else:
            # Legacy format (before key IDs): base64(nonce||ct) under the first/only key.
            payload, key = token, self.keyring.keys.get("k1", self.keyring.active_key)
        raw = base64.b64decode(payload)
        return AESGCM(key).decrypt(raw[:NONCE_BYTES], raw[NONCE_BYTES:], aad).decode()

    def is_token(self, value) -> bool:
        return isinstance(value, str) and value.startswith(TOKEN_PREFIX)

    # ---------- binary (radiographs, reports) ----------
    def encrypt_bytes(self, data: bytes, aad: bytes | None = None) -> bytes:
        kid = self.keyring.active_kid.encode()
        nonce = os.urandom(NONCE_BYTES)
        ct = AESGCM(self.keyring.active_key).encrypt(nonce, data, aad)
        return BLOB_MAGIC + bytes([len(kid)]) + kid + nonce + ct

    def decrypt_bytes(self, blob: bytes, aad: bytes | None = None) -> bytes:
        if not blob.startswith(BLOB_MAGIC):
            raise ValueError("Not a PerioVision encrypted blob.")
        n = blob[4]
        kid = blob[5:5 + n].decode()
        nonce = blob[5 + n:5 + n + NONCE_BYTES]
        return AESGCM(self._key_for(kid)).decrypt(nonce, blob[5 + n + NONCE_BYTES:], aad)

    def rotate_token(self, token: str, aad: bytes | None = None) -> str:
        """Re-encrypt a text token under the currently active key."""
        return self.encrypt_random(self.decrypt_random(token, aad), aad)

    def rotate_bytes(self, blob: bytes, aad: bytes | None = None) -> bytes:
        return self.encrypt_bytes(self.decrypt_bytes(blob, aad), aad)

    def _key_for(self, kid: str) -> bytes:
        try:
            return self.keyring.keys[kid]
        except KeyError:
            raise KeyConfigError(f"Key '{kid}' is not available; keep retired keys in the key ring.") from None

    # ---------- hashing helpers ----------
    def get_blind_index(self, data: str) -> str:
        normalized = str(data).strip().lower()
        return base64.b64encode(hmac.new(self._index_key, normalized.encode(), hashlib.sha256).digest()).decode()

    def pseudonymize(self, identifier) -> str:
        """Stable, non-reversible ID for logs and analytics (e.g. 'P-3fa91c20b7')."""
        digest = hmac.new(self._pseudo_key, str(identifier).encode(), hashlib.sha256).hexdigest()
        return f"P-{digest[:10]}"

    def reindex_record(self, doc: dict) -> dict:
        """Recompute the blind indexes under the active key. The index key is derived from the active key,
        so after a rotation old indexes no longer match searches; scripts/rotate_keys.py calls this."""
        for field in self.INDEXED_FIELDS:
            value = doc.get(field)
            if self.is_token(value):
                doc[f"{field}_idx"] = self.get_blind_index(self.decrypt_random(value, aad=field.encode()))
        return doc

    # ---------- documents ----------
    def encrypt_patient_record(self, doc: dict) -> dict:
        """Encrypt sensitive fields and add blind indexes for search."""
        for field in self.ENCRYPTED_FIELDS:
            if doc.get(field):
                value = str(doc[field])
                if field in self.INDEXED_FIELDS:
                    doc[f"{field}_idx"] = self.get_blind_index(value)
                doc[field] = self.encrypt_random(value, aad=field.encode())
        return doc

    def decrypt_patient_record(self, doc: dict) -> dict | None:
        if not doc:
            return None
        for field in self.ENCRYPTED_FIELDS:
            value = doc.get(field)
            if not value or not isinstance(value, str):
                continue
            if self.is_token(value):
                doc[field] = self.decrypt_random(value, aad=field.encode())
            elif len(value) >= 28:
                try:  # legacy records written without key IDs or AAD
                    doc[field] = self.decrypt_random(value)
                except Exception:
                    pass  # plaintext from before encryption was enabled
        doc.pop("patient_name_idx", None)
        doc.pop("contact_number_idx", None)
        return doc


_default: PHIEncryptor | None = None


def get_encryptor() -> PHIEncryptor:
    """Process-wide encryptor built from the environment key configuration."""
    global _default
    if _default is None:
        _default = PHIEncryptor()
    return _default
