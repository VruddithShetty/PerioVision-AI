"""AES-256-GCM encryption: round trip, fresh nonce every time, tamper detection, key rotation."""
import base64
import secrets

import pytest
from cryptography.exceptions import InvalidTag

from app.security.crypto import KeyConfigError, KeyRing, PHIEncryptor


def ring(*kids, active=None):
    keys = {k: secrets.token_bytes(32) for k in kids}
    return KeyRing._checked(active or kids[0], keys)


@pytest.fixture()
def enc():
    return PHIEncryptor(keyring=ring("k1"))


def test_round_trip_text_and_bytes(enc):
    assert enc.decrypt_random(enc.encrypt_random("Jane Example")) == "Jane Example"
    blob = b"\x89PNG fake image bytes" * 100
    assert enc.decrypt_bytes(enc.encrypt_bytes(blob)) == blob


def test_nonce_is_unique_per_encryption(enc):
    tokens = [enc.encrypt_random("same text") for _ in range(200)]
    assert len(set(tokens)) == 200
    nonces = {base64.b64decode(t.split(":", 3)[3])[:12] for t in tokens}
    assert len(nonces) == 200


def test_tampered_ciphertext_is_rejected(enc):
    token = enc.encrypt_random("secret")
    prefix, payload = token.rsplit(":", 1)
    raw = bytearray(base64.b64decode(payload))
    raw[-1] ^= 0x01
    with pytest.raises(InvalidTag):
        enc.decrypt_random(prefix + ":" + base64.b64encode(bytes(raw)).decode())
    blob = bytearray(enc.encrypt_bytes(b"report"))
    blob[-3] ^= 0xFF
    with pytest.raises(InvalidTag):
        enc.decrypt_bytes(bytes(blob))


def test_associated_data_binds_purpose(enc):
    blob = enc.encrypt_bytes(b"radiograph pixels", aad=b"radiograph")
    with pytest.raises(InvalidTag):
        enc.decrypt_bytes(blob, aad=b"report")


def test_key_rotation_keeps_old_data_readable():
    old_ring = ring("k1")
    old = PHIEncryptor(keyring=old_ring)
    token = old.encrypt_random("before rotation")
    new_ring = KeyRing._checked("k2", {"k1": old_ring.keys["k1"], "k2": secrets.token_bytes(32)})
    new = PHIEncryptor(keyring=new_ring)
    assert new.decrypt_random(token) == "before rotation"
    rotated = new.rotate_token(token)
    assert rotated.startswith("enc:v1:k2:")
    assert new.decrypt_random(rotated) == "before rotation"
    with pytest.raises(KeyConfigError):
        PHIEncryptor(keyring=KeyRing._checked("k2", {"k2": new_ring.keys["k2"]})).decrypt_random(token)


def test_bad_keys_are_refused():
    with pytest.raises(KeyConfigError):
        PHIEncryptor("abcd")  # too short: no silent hashing of weak keys any more
    with pytest.raises(KeyConfigError):
        KeyRing._checked("missing", {"k1": secrets.token_bytes(32)})


def test_patient_record_encryption_and_blind_index(enc):
    doc = enc.encrypt_patient_record({"patient_name": "Asha Rao", "contact_number": "555-0101", "age": 40})
    assert doc["patient_name"].startswith("enc:v1:") and doc["age"] == 40
    assert doc["patient_name_idx"] == enc.get_blind_index("  asha rao ")
    assert enc.decrypt_patient_record(doc)["patient_name"] == "Asha Rao"
    assert enc.pseudonymize(1001) == enc.pseudonymize(1001) != enc.pseudonymize(1002)
