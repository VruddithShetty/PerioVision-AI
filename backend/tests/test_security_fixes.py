"""Regression tests for the security fixes of 2026-10-04 (Priority 1, item 5).

Each test first describes the attack, then proves the defence holds:
  * honeypot decoys stay armed after an encryption-key rotation
  * patient search (blind index) still finds old patients after a key rotation
  * audit anchors are chained, so deleting an anchor is detected
  * entries written after the last anchor are reported as unanchored (never silently "intact")
  * an independent witness copy of the anchors exposes a rolled-back anchor file
  * the v2 Merkle tree is domain-separated (no duplicate-last-leaf collision)
  * raw IP addresses never reach the audit log
  * AES-GCM: same plaintext never gives the same ciphertext (no deterministic / static-IV mode)
"""
import json
import secrets
import uuid

import pytest

from app.models.connection import db
from app.security import audit_log, crypto
from app.security.audit_log import AnchorStore, MerkleAuditLog, merkle_root, merkle_root_v2
from app.security.crypto import KeyRing, PHIEncryptor


# ------------------------------------------------------------------ helpers
def _rotated_encryptor(old: PHIEncryptor) -> PHIEncryptor:
    """Same ring plus a brand-new active key, as after step 1 of scripts/rotate_keys.py."""
    keys = dict(old.keyring.keys)
    keys["new"] = secrets.token_bytes(32)
    return PHIEncryptor(keyring=KeyRing._checked("new", keys))


@pytest.fixture()
def fresh_log(monkeypatch, tmp_path):
    monkeypatch.setattr(audit_log, "_anchor_store", AnchorStore())
    lg = MerkleAuditLog()
    name = f"audit_fix_{uuid.uuid4().hex}"
    lg.logs, lg.roots = db[name], db[name + "_roots"]
    lg.logs.create_index("seq", unique=True)
    return lg


# ------------------------------------------------------------------ honeypot
def test_honeypot_decoys_stay_armed_after_key_rotation(app, monkeypatch):
    """Attack: rotate the encryption key (a routine admin task). Before the fix the decoy tags were
    HMACs under the *active* key, so every existing decoy silently stopped triggering."""
    from app.security import honeypot as hp

    with app.app_context():
        old = crypto.get_encryptor()
        monkeypatch.setattr(hp, "get_encryptor", lambda: old)
        mgr = hp.HoneypotManager()
        mgr.decoys = db[f"decoys_{uuid.uuid4().hex}"]
        mgr.deploy(count=2)
        decoy_ids = [d["patient_id"] for d in db["patients"].find({"doctor_id": hp.DECOY_OWNER})][-2:]
        assert all(mgr.is_decoy(pid) for pid in decoy_ids)

        rotated = _rotated_encryptor(old)
        monkeypatch.setattr(hp, "get_encryptor", lambda: rotated)
        assert all(mgr.is_decoy(pid) for pid in decoy_ids), "decoys were disarmed by key rotation"
        assert not mgr.is_decoy(987654321), "an ordinary ID must not look like a decoy"


def test_honeypot_tag_is_not_a_raw_encryption_key_hmac(app):
    """Key separation: the decoy tag must use a derived key, never the AES key itself."""
    import hashlib
    import hmac

    from app.security import honeypot as hp

    with app.app_context():
        key = crypto.get_encryptor().keyring.active_key
        raw = hmac.new(key, b"decoy:1234", hashlib.sha256).hexdigest()
        assert hp.HoneypotManager()._tag(1234) != raw


# ------------------------------------------------------------------ blind index after rotation
def test_blind_index_search_survives_key_rotation():
    """Attack/fault: after rotation the search index was computed with the new key while old records
    kept the old index, so searching an existing patient's name returned nothing.
    `reindex_record` (called by scripts/rotate_keys.py) rebuilds it."""
    old = PHIEncryptor(keyring=KeyRing._checked("a", {"a": secrets.token_bytes(32)}))
    doc = old.encrypt_patient_record({"patient_name": "Test Person", "contact_number": "555"})
    rotated = _rotated_encryptor(old)
    assert doc["patient_name_idx"] != rotated.get_blind_index("Test Person")   # the bug
    fixed = rotated.reindex_record(dict(doc))
    assert fixed["patient_name_idx"] == rotated.get_blind_index("Test Person")
    assert fixed["contact_number_idx"] == rotated.get_blind_index("555")


# ------------------------------------------------------------------ audit anchors
def test_deleting_an_anchor_is_detected(fresh_log):
    """Attack: delete the newest anchor line, then roll the log back to the previous anchor.
    Anchors are now hash-chained and numbered, so a gap in the chain is reported."""
    for i in range(5):
        fresh_log.record(f"E{i}")
    fresh_log.publish_root("t")
    for i in range(5):
        fresh_log.record(f"F{i}")
    fresh_log.publish_root("t")
    for i in range(3):
        fresh_log.record(f"G{i}")
    fresh_log.publish_root("t")
    store = fresh_log.anchors
    del store._memory[1]                          # remove the middle anchor
    res = fresh_log.verify_chain_integrity()
    assert not res["chain_intact"]
    assert "anchor chain" in res["reason"]


def test_unanchored_tail_is_reported_not_hidden(fresh_log):
    """Attack: delete the last entries written after the latest anchor. Nothing local can prove they
    existed, so verification must say how many entries are NOT yet protected by an anchor."""
    for i in range(6):
        fresh_log.record(f"E{i}")
    fresh_log.publish_root("t")
    for i in range(4):
        fresh_log.record(f"T{i}")
    res = fresh_log.verify_chain_integrity()
    assert res["chain_intact"]
    assert res["unanchored_entries"] == 4


def test_witness_copy_exposes_rolled_back_anchor_file(fresh_log, tmp_path):
    """Attack: an insider with server access truncates both the log and the local anchor file to an
    earlier, self-consistent state. The independent witness copy still has the newer anchor."""
    fresh_log.anchors.witness_path = tmp_path / "witness.jsonl"
    for i in range(4):
        fresh_log.record(f"E{i}")
    fresh_log.publish_root("t")
    for i in range(4):
        fresh_log.record(f"F{i}")
    fresh_log.publish_root("t")
    # roll back: drop the last anchor locally and the entries it covered
    fresh_log.anchors._memory.pop()
    fresh_log.logs.delete_many({"seq": {"$gte": 4}})
    fresh_log.roots.delete_many({})
    res = fresh_log.verify_chain_integrity()
    assert not res["chain_intact"]
    assert "witness" in res["reason"]


def test_v2_merkle_root_is_domain_separated():
    """v1 duplicated the last leaf on odd layers, so [a, b, c] and [a, b, c, c] had the same root
    (the CVE-2012-2459 pattern). v2 tags leaves and nodes differently and promotes odd nodes."""
    a, b, c = (format(i, "064x") for i in (1, 2, 3))
    assert merkle_root([a, b, c]) == merkle_root([a, b, c, c])           # the old weakness, kept for v1 anchors
    assert merkle_root_v2([a, b, c]) != merkle_root_v2([a, b, c, c])
    assert merkle_root_v2([a]) != a                                       # a leaf is never its own root


def test_old_v1_anchors_still_verify(fresh_log):
    """Backward compatibility: anchors written before the fix (no version field) still verify."""
    for i in range(5):
        fresh_log.record(f"E{i}")
    leaves = [e["entry_hash"] for e in fresh_log.logs.find({}).sort("seq", 1)]
    ts = "2026-10-01T00:00:00+00:00"
    root = merkle_root(leaves)
    fresh_log.anchors.append({"count": 5, "root": root, "timestamp": ts, "published_by": "old",
                              "hmac": audit_log._sign_anchor(5, root, ts)})
    res = fresh_log.verify_chain_integrity()
    assert res["chain_intact"], res


# ------------------------------------------------------------------ IP privacy ("GeoIP leakage")
def test_raw_ip_never_reaches_the_audit_log(client):
    """Log in from a distinctive address; the audit log may hold only the keyed hash of it."""
    ip = "203.0.113.77"   # TEST-NET-3 documentation range
    client.post("/api/auth/login", json={"email": "nobody@test.local", "password": "wrong-Password1"},
                environ_base={"REMOTE_ADDR": ip}, headers={"User-Agent": "pytest-browser/1.0"})
    dumped = json.dumps(list(db["audit_logs"].find({}, {"_id": 0})), default=str)
    assert ip not in dumped
    assert audit_log.hash_ip(ip) in dumped


def test_no_ip_geolocation_code_or_dependency():
    """There is no GeoIP lookup anywhere in the backend (a lookup would send or store location data)."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    banned = ("geoip", "maxminddb", "ip-api.com", "ipinfo.io", "ipapi.co")
    hits = [str(p) for p in (root / "app").rglob("*.py") if any(b in p.read_text(encoding="utf-8").lower()
                                                                  for b in banned)]
    reqs = (root / "requirements.txt").read_text(encoding="utf-8").lower()
    assert not hits and not any(b in reqs for b in banned), hits


# ------------------------------------------------------------------ AES mode
def test_encryption_is_randomised_authenticated_gcm():
    """No deterministic / static-IV mode: equal plaintexts give different ciphertexts, and a flipped
    bit is rejected (GCM tag), which CBC without a MAC would not do."""
    enc = PHIEncryptor(keyring=KeyRing._checked("k", {"k": secrets.token_bytes(32)}))
    tokens = {enc.encrypt_random("same text") for _ in range(50)}
    assert len(tokens) == 50
    blob = bytearray(enc.encrypt_bytes(b"radiograph bytes"))
    blob[-1] ^= 1
    with pytest.raises(Exception):
        enc.decrypt_bytes(bytes(blob))
    src = open(crypto.__file__, encoding="utf-8").read()
    assert "modes.CBC" not in src and "AESGCM" in src
