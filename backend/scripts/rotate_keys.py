"""Re-encrypt all stored data under the currently active encryption key.

Steps for a key rotation:
  1. Add a new key to FIELD_ENCRYPTION_KEYS in .env and make it FIELD_ENCRYPTION_ACTIVE_KID,
     keeping the old key in the ring.
  2. Run:  python scripts/rotate_keys.py
  3. When it reports 0 items still on old keys, the old key can be removed from the ring.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))  # backend/

from app import config  # noqa: E402
from app.models.connection import db  # noqa: E402
from app.security.crypto import BLOB_MAGIC, get_encryptor  # noqa: E402


def main() -> int:
    enc = get_encryptor()
    active = enc.keyring.active_kid
    fields = 0
    for doc in db["patients"].find({}):
        updates = {}
        for field in enc.ENCRYPTED_FIELDS:
            value = doc.get(field)
            if enc.is_token(value) and not value.startswith(f"enc:v1:{active}:"):
                updates[field] = enc.rotate_token(value, aad=field.encode())
        if updates:
            db["patients"].update_one({"_id": doc["_id"]}, {"$set": updates})
            fields += len(updates)
    for doc in db["doctors"].find({"mfa_secret": {"$ne": None}}):
        value = doc.get("mfa_secret")
        if enc.is_token(value) and not value.startswith(f"enc:v1:{active}:"):
            db["doctors"].update_one({"_id": doc["_id"]}, {"$set": {"mfa_secret": enc.rotate_token(value, aad=b"mfa")}})
            fields += 1
    blobs = 0
    purposes = ("radiograph", "annotated", "gradcam", "report", "upload")
    for path in config.BLOB_DIR.glob("*.bin"):
        data = path.read_bytes()
        if not data.startswith(BLOB_MAGIC):
            continue
        kid = data[5:5 + data[4]].decode()
        if kid == active:
            continue
        for purpose in purposes:
            try:
                path.write_bytes(enc.rotate_bytes(data, aad=purpose.encode()))
                blobs += 1
                break
            except Exception:
                continue
    print(f"Re-encrypted {fields} fields and {blobs} files under key '{active}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
