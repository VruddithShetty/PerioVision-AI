"""Tamper-evident audit log: edits, deletions and forged anchors are detected and pinpointed."""
import uuid

import pytest

from app.models.connection import db
from app.security import audit_log
from app.security.audit_log import AnchorStore, MerkleAuditLog, entry_hash, merkle_root


@pytest.fixture()
def log(monkeypatch):
    """A fresh, isolated log (separate collections and anchor store)."""
    monkeypatch.setattr(audit_log, "_anchor_store", AnchorStore())
    lg = MerkleAuditLog()
    name = f"audit_test_{uuid.uuid4().hex}"   # id() can be reused across tests, which shared stale entries
    lg.logs, lg.roots = db[name], db[name + "_roots"]
    lg.logs.create_index("seq", unique=True)
    for i in range(12):
        lg.record(f"EVENT_{i}", actor="tester", details={"i": i})
    yield lg
    # Drop them too: a uuid name stops collisions, but left-behind collections still
    # accumulate across a run and make the in-memory database grow for no reason.
    db.drop_collection(name)
    db.drop_collection(name + "_roots")


def test_clean_chain_verifies(log):
    res = log.verify_chain_integrity()
    assert res["chain_intact"] and res["entries_verified"] == 12


def test_modified_entry_is_pinpointed(log):
    log.logs.update_one({"seq": 5}, {"$set": {"action": "NOTHING_TO_SEE"}})
    res = log.verify_chain_integrity()
    assert not res["chain_intact"] and res["first_tampered_seq"] == 5


def test_genesis_entry_is_checked_too(log):
    log.logs.update_one({"seq": 0}, {"$set": {"actor": "someone-else"}})
    assert log.verify_chain_integrity()["first_tampered_seq"] == 0


def test_deleted_entry_is_detected(log):
    log.logs.delete_one({"seq": 7})
    res = log.verify_chain_integrity()
    assert not res["chain_intact"] and res["first_tampered_seq"] == 7


def test_consistent_rewrite_is_caught_by_anchor(log):
    log.publish_root()
    # Attacker rewrites entry 3 AND recomputes every later hash so the chain itself looks valid.
    entries = list(log.logs.find({}, {"_id": 0}).sort("seq", 1))
    entries[3]["action"] = "REWRITTEN"
    prev = entries[2]["entry_hash"]
    for e in entries[3:]:
        e["prev_hash"] = prev
        e["entry_hash"] = entry_hash(e)
        prev = e["entry_hash"]
        log.logs.replace_one({"seq": e["seq"]}, e)
    res = log.verify_chain_integrity()
    assert not res["chain_intact"]
    assert "anchored Merkle root does not match" in res["reason"]


def test_forged_anchor_is_detected(log):
    anchor = log.publish_root()
    audit_log._anchor_store._memory[-1]["root"] = "0" * 64
    res = log.verify_chain_integrity()
    assert not res["chain_intact"] and "forged" in res["reason"]
    assert anchor["count"] == 12


def test_merkle_root_changes_with_any_leaf():
    leaves = [f"{i:064x}" for i in range(5)]
    base = merkle_root(leaves)
    for i in range(5):
        changed = list(leaves)
        changed[i] = "f" * 64
        assert merkle_root(changed) != base
