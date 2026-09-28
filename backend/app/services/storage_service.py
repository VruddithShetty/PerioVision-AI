"""Encrypted blob storage for radiographs, overlays and reports.

Every file is AES-256-GCM encrypted (app/security/crypto.py) before it touches
disk, stored under a random ID (never a user-supplied name), and bound to its
purpose through the GCM associated data, so a report blob cannot be swapped in
for a radiograph without failing decryption.
"""
from __future__ import annotations

import re
import secrets

from app import config
from app.security.crypto import get_encryptor

_ID = re.compile(r"^[a-f0-9]{32}$")


def _path(blob_id: str):
    if not _ID.match(blob_id or ""):
        raise ValueError("Invalid blob id")
    return config.BLOB_DIR / f"{blob_id}.bin"


def put(data: bytes, purpose: str) -> str:
    blob_id = secrets.token_hex(16)
    config.BLOB_DIR.mkdir(parents=True, exist_ok=True)
    _path(blob_id).write_bytes(get_encryptor().encrypt_bytes(data, aad=purpose.encode()))
    return blob_id


def get(blob_id: str, purpose: str) -> bytes:
    return get_encryptor().decrypt_bytes(_path(blob_id).read_bytes(), aad=purpose.encode())


def exists(blob_id: str) -> bool:
    try:
        return _path(blob_id).exists()
    except ValueError:
        return False


def raw_path(blob_id: str):
    """Path of the encrypted file (used by the Security Lab tamper demo)."""
    return _path(blob_id)
