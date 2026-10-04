"""Tamper-evident audit log: an append-only hash chain plus anchored Merkle roots.

How it detects tampering
1. Hash chain: every entry stores the SHA-256 of the previous entry
   (`prev_hash`) and its own hash over all of its fields (`entry_hash`).
   Editing, deleting or reordering any entry breaks the chain from that point.
   Verification checks *every* entry, including the first (genesis) one.
2. Merkle anchors: every ANCHOR_EVERY entries (and on demand) the Merkle root
   of the log so far is computed, authenticated with an HMAC key that is not
   stored in the database, and written to a separate anchor store (a file
   outside MongoDB in live mode). Someone who rewrites the whole chain
   consistently in the database still cannot forge the anchored roots.
3. Anchor chain (v2, 2026-10-04): every anchor carries its number (`anchor_seq`) and the hash of the
   previous anchor (`prev_anchor`), and the Merkle tree is domain-separated (leaf and node hashes are
   tagged differently, odd nodes are promoted instead of duplicated). Deleting or reordering an anchor
   breaks the chain. Anchors written before v2 (no `v` field) are still verified the old way.
4. Witness copy: with AUDIT_ANCHOR_WITNESS_DIR set, every anchor is also appended to a file there. Point
   it at storage the application server cannot rewrite (another machine, a WORM / object-lock bucket
   mount, a write-only share). Rolling back the local log and anchor file then no longer matches the
   witness. Without a witness, an attacker with full control of the server can still roll back to an
   earlier anchor; verification says so instead of claiming more.
5. Entries written after the newest anchor are reported as `unanchored_entries`: the hash chain covers
   them, but deleting them from the end cannot be proven until the next anchor.

Privacy: entries never hold PHI. Patients appear only as pseudonyms, IP
addresses as salted hashes, and there are no emails or names.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
from pathlib import Path

import pymongo.errors

from app import config
from app.models.connection import db

logger = logging.getLogger(__name__)

GENESIS_HASH = "0" * 64
ANCHOR_EVERY = int(os.getenv("AUDIT_ANCHOR_EVERY", "20"))
HASHED_FIELDS = ("seq", "timestamp", "actor", "action", "outcome", "resource", "details", "prev_hash")

_anchor_key: bytes | None = None
_lock = threading.Lock()


def _key() -> bytes:
    global _anchor_key
    if _anchor_key is None:
        raw = os.getenv("AUDIT_ANCHOR_KEY")
        if raw:
            _anchor_key = hashlib.sha256(raw.encode()).digest()
        elif config.IS_DEMO:
            _anchor_key = secrets.token_bytes(32)
        else:
            raise RuntimeError("AUDIT_ANCHOR_KEY must be set in .env outside demo mode.")
    return _anchor_key


def entry_hash(entry: dict) -> str:
    body = {k: entry.get(k) for k in HASHED_FIELDS}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def merkle_root(leaves: list[str]) -> str:
    if not leaves:
        return hashlib.sha256(b"").hexdigest()
    layer = list(leaves)
    while len(layer) > 1:
        if len(layer) % 2:
            layer.append(layer[-1])
        layer = [hashlib.sha256((layer[i] + layer[i + 1]).encode()).hexdigest() for i in range(0, len(layer), 2)]
    return layer[0]


def _h(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def merkle_root_v2(leaves: list[str]) -> str:
    """Domain-separated Merkle root (RFC 6962 style): leaf = H(0x00 || leaf), node = H(0x01 || left || right).
    An odd node is promoted unchanged, so [a, b, c] and [a, b, c, c] give different roots."""
    if not leaves:
        return _h(b"\x02empty")
    layer = [_h(b"\x00" + bytes.fromhex(x)) for x in leaves]
    while len(layer) > 1:
        nxt = [_h(b"\x01" + bytes.fromhex(layer[i]) + bytes.fromhex(layer[i + 1]))
               for i in range(0, len(layer) - 1, 2)]
        if len(layer) % 2:
            nxt.append(layer[-1])
        layer = nxt
    return layer[0]


def anchor_digest(anchor: dict) -> str:
    """Hash of one anchor record, linked from the next anchor (`prev_anchor`)."""
    body = {k: anchor.get(k) for k in ("v", "anchor_seq", "count", "root", "timestamp", "prev_anchor", "hmac")}
    return _h(json.dumps(body, sort_keys=True, separators=(",", ":")).encode())


def hash_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    return hmac.new(_key(), ip.encode(), hashlib.sha256).hexdigest()[:16]


class AnchorStore:
    """Where Merkle roots are anchored, kept apart from the audit collection."""

    def __init__(self):
        self.path = config.LOGS_DIR / "merkle_anchors.jsonl"
        self._memory: list[dict] = []
        witness = os.getenv("AUDIT_ANCHOR_WITNESS_DIR")
        self.witness_path = (Path(witness) / "merkle_anchors_witness.jsonl") if witness else None

    def _uses_file(self) -> bool:
        return not config.IS_DEMO  # demo data is in-memory, so its anchors are too

    def append(self, anchor: dict) -> None:
        if self._uses_file():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(anchor, sort_keys=True) + "\n")
        else:
            self._memory.append(dict(anchor))
        if self.witness_path is not None:
            try:
                self.witness_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.witness_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(anchor, sort_keys=True) + "\n")
            except OSError as exc:   # a missing witness must be visible, never silently skipped
                logger.error("Audit anchor witness could not be written: %s", type(exc).__name__)

    def witness(self) -> list[dict] | None:
        """Anchors in the witness copy, or None when no witness is configured."""
        if self.witness_path is None:
            return None
        if not self.witness_path.exists():
            return []
        with open(self.witness_path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def all(self) -> list[dict]:
        if self._uses_file():
            if not self.path.exists():
                return []
            with open(self.path, encoding="utf-8") as f:
                return [json.loads(line) for line in f if line.strip()]
        return [dict(a) for a in self._memory]


_anchor_store = AnchorStore()


def _sign_anchor(count: int, root: str, timestamp: str) -> str:
    """v1 anchor MAC (kept so anchors written before v2 still verify)."""
    return hmac.new(_key(), f"{count}|{root}|{timestamp}".encode(), hashlib.sha256).hexdigest()


def _sign_anchor_v2(anchor_seq: int, count: int, root: str, timestamp: str, prev_anchor: str) -> str:
    msg = f"v2|{anchor_seq}|{count}|{root}|{timestamp}|{prev_anchor}"
    return hmac.new(_key(), msg.encode(), hashlib.sha256).hexdigest()


def _anchor_ok(a: dict) -> tuple[bool, str]:
    """(MAC is genuine, anchor version)."""
    if a.get("v") == 2:
        mac = _sign_anchor_v2(a["anchor_seq"], a["count"], a["root"], a["timestamp"], a["prev_anchor"])
        return hmac.compare_digest(a.get("hmac", ""), mac), "v2"
    return hmac.compare_digest(a.get("hmac", ""), _sign_anchor(a["count"], a["root"], a["timestamp"])), "v1"


class MerkleAuditLog:
    def __init__(self):
        self.logs = db["audit_logs"]
        self.roots = db["merkle_roots"]
        self.anchors = _anchor_store
        self.logs.create_index("seq", unique=True)

    # ---------- writing ----------
    def record(self, action: str, outcome: str = "success", actor: str | None = None,
               resource: str | None = None, details: dict | None = None) -> dict:
        """Append one entry. Safe under concurrency: `seq` is unique, so a lost race retries."""
        for _ in range(20):
            with _lock:
                last = self.logs.find_one(sort=[("seq", -1)])
                entry = {
                    "seq": (last["seq"] + 1) if last else 0,
                    "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "actor": str(actor) if actor else "anonymous",
                    "action": str(action),
                    "outcome": str(outcome),
                    "resource": str(resource) if resource else None,
                    "details": details or {},
                    "prev_hash": last["entry_hash"] if last else GENESIS_HASH,
                }
                entry["entry_hash"] = entry_hash(entry)
                try:
                    self.logs.insert_one(dict(entry))
                except pymongo.errors.DuplicateKeyError:
                    continue
            if (entry["seq"] + 1) % ANCHOR_EVERY == 0:
                self.publish_root(actor="system")
            return entry
        raise RuntimeError("Could not append audit entry (sequence contention).")

    def log_action(self, doctor_id, action, entity_id, metadata):
        """Compatibility wrapper for older callers."""
        return self.record(action, outcome=(metadata or {}).get("outcome", "success"), actor=doctor_id,
                           resource=entity_id, details=metadata)

    def publish_root(self, actor: str = "system") -> dict:
        leaves = [e["entry_hash"] for e in self.logs.find({}, {"entry_hash": 1}).sort("seq", 1)]
        timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
        root = merkle_root_v2(leaves)
        previous = self.anchors.all()
        anchor_seq = len(previous)
        prev_anchor = anchor_digest(previous[-1]) if previous else GENESIS_HASH
        anchor = {"v": 2, "anchor_seq": anchor_seq, "count": len(leaves), "root": root, "timestamp": timestamp,
                  "prev_anchor": prev_anchor, "published_by": str(actor),
                  "hmac": _sign_anchor_v2(anchor_seq, len(leaves), root, timestamp, prev_anchor)}
        self.anchors.append(anchor)
        self.roots.insert_one(dict(anchor))
        return anchor

    # ---------- reading ----------
    def recent(self, limit: int = 50, action: str | None = None, actor: str | None = None) -> list[dict]:
        query = {}
        if action:
            query["action"] = str(action)
        if actor:
            query["actor"] = str(actor)
        return list(self.logs.find(query, {"_id": 0}).sort("seq", -1).limit(int(limit)))

    def verify_chain_integrity(self) -> dict:
        """Check every entry and every anchor. Reports the first tampered entry, if any."""
        entries = list(self.logs.find({}, {"_id": 0}).sort("seq", 1))
        first_bad, reason = None, None
        prev = GENESIS_HASH
        for index, e in enumerate(entries):
            if e.get("seq") != index:
                first_bad, reason = index, "entry missing or out of order"
                break
            if e.get("prev_hash") != prev:
                first_bad, reason = e["seq"], "link to previous entry broken"
                break
            if entry_hash(e) != e.get("entry_hash"):
                first_bad, reason = e["seq"], "entry content was modified"
                break
            prev = e["entry_hash"]

        leaves = [e.get("entry_hash") for e in entries]
        anchors = self.anchors.all()
        anchor_results = []
        prev_v2, last_count = None, 0
        for a in anchors:
            genuine, version = _anchor_ok(a)
            root_fn = merkle_root_v2 if version == "v2" else merkle_root
            matches = a["count"] <= len(leaves) and root_fn(leaves[:a["count"]]) == a["root"]
            linked = a["count"] >= last_count
            if version == "v2":
                # the first v2 anchor may follow v1 anchors; after that, numbers and links must be continuous
                if prev_v2 is not None:
                    linked = linked and a["anchor_seq"] == prev_v2["anchor_seq"] + 1 \
                        and a["prev_anchor"] == anchor_digest(prev_v2)
                prev_v2 = a
            last_count = max(last_count, a["count"])
            anchor_results.append({"count": a["count"], "timestamp": a["timestamp"], "version": version,
                                   "anchor_genuine": genuine, "root_matches": matches, "linked": linked})
            if reason is None and not genuine:
                reason = "anchor record itself was forged"
            elif reason is None and not matches:
                first_bad = first_bad if first_bad is not None else min(a["count"], len(leaves)) - 1
                reason = "anchored Merkle root does not match (log rewritten or truncated)"
            elif reason is None and not linked:
                reason = "anchor chain broken (an anchor was deleted, inserted or reordered)"

        witness = self.anchors.witness()
        witness_ok = None
        if witness is not None:
            local = {anchor_digest(a) for a in anchors}
            missing = [w for w in witness if anchor_digest(w) not in local]
            witness_ok = not missing
            if missing and reason is None:
                reason = (f"witness copy holds {len(missing)} anchor(s) missing locally "
                          "(local log or anchor file rolled back)")

        return {
            "chain_intact": first_bad is None and reason is None,
            "unanchored_entries": len(leaves) - (anchors[-1]["count"] if anchors else 0),
            "witness_configured": witness is not None,
            "witness_consistent": witness_ok,
            "first_tampered_seq": first_bad,
            "reason": reason,
            "entries_verified": len(entries),
            "current_root": merkle_root_v2(leaves),
            "anchors_checked": len(anchor_results),
            "anchors": anchor_results[-5:],
            "latest_anchor": anchors[-1] if anchors else None,
        }


_default: MerkleAuditLog | None = None


def audit() -> MerkleAuditLog:
    global _default
    if _default is None:
        _default = MerkleAuditLog()
    return _default
