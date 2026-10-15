"""Data classification and retention.

Every store the application writes to is classified, given a retention rule, and
either purgeable or explicitly not. Two things this is careful about:

Nothing is deleted implicitly. `plan()` reports what is due and changes nothing;
`purge()` only acts when asked. Clinical records are the evidence behind a
diagnosis, so an automatic sweep that quietly removed them would be worse than
keeping them too long. Deletion is an operator decision, taken with the plan in
front of them.

The audit log is never purged. It is a hash chain: entry N commits to entry N-1,
so removing an old entry does not free space, it breaks verification for
everything after it and makes the trail look tampered with. A naive "delete
records older than N days" sweep applied to every collection would destroy the
one control that proves nothing else was destroyed. PROTECTED names those stores
and purge() refuses them.

What is safe to remove is the transient material: revoked and expired sessions,
uploads that passed their TTL without being turned into an analysis, and the
encrypted blobs those uploads left behind. That last one is the real leak - an
upload record expires but its radiograph stays on disk, so PHI outlives the
record that pointed at it.
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ------------------------------------------------------------ classification ---
PUBLIC = "public"
INTERNAL = "internal"
CONFIDENTIAL = "confidential"
PATIENT = "patient"          # highest: identifiable or clinical information


@dataclass(frozen=True)
class DataClass:
    store: str
    classification: str
    contains: str
    encrypted: str
    retention: str
    purgeable: bool
    reason: str


# The matrix the documentation renders, kept next to the code that enforces it so
# the two cannot drift apart.
CLASSIFICATION: tuple[DataClass, ...] = (
    DataClass("patients", PATIENT, "name, contact, notes, clinical risk factors",
              "AES-256-GCM per field, blind index for search", "kept while the patient is active",
              False, "the clinical record; removal is a practice decision, not a sweep"),
    DataClass("analyses", PATIENT, "per-tooth measurements, staging, risk, blob IDs",
              "blobs AES-256-GCM; measurements in clear", "kept with the patient record",
              False, "evidence behind a diagnosis and any report issued from it"),
    DataClass("reports", PATIENT, "PDF hash, RSA-PSS signature, pseudonym",
              "PDF blob AES-256-GCM", "kept with the patient record",
              False, "a signed clinical document; deleting it breaks verification"),
    DataClass("perio_charts", PATIENT, "pocket depths, recession, bleeding",
              "in clear, scoped by patient authorization", "kept with the patient record",
              False, "clinical measurements"),
    DataClass("corrections", PATIENT, "clinician corrections to model output",
              "in clear, pseudonymous", "kept for retraining provenance",
              False, "training provenance; removal would break model lineage"),
    DataClass("doctors", CONFIDENTIAL, "accounts, bcrypt hashes, TOTP secrets",
              "password hashed, secrets at rest", "kept while the account exists",
              False, "account lifecycle is an administrative action"),
    DataClass("sessions", INTERNAL, "session IDs, device fingerprints, refresh IDs",
              "no PHI", "30 days after revocation or last use",
              True, "transient; keeping them only widens the window for replay"),
    DataClass("uploads", PATIENT, "radiograph metadata and a blob reference",
              "blob AES-256-GCM", "TTL on upload, then purgeable",
              True, "an upload never turned into an analysis is working material"),
    DataClass("security_decoys", INTERNAL, "decoy patient records",
              "same handling as real records", "kept while deception is deployed",
              False, "removing them silently disables the control"),
    DataClass("audit_logs", CONFIDENTIAL, "who, what, when, which resource, result",
              "hash-chained; pseudonyms, no PHI", "kept indefinitely",
              False, "a hash chain: removing an entry breaks every later one"),
    DataClass("merkle_roots", CONFIDENTIAL, "anchored Merkle roots",
              "HMAC-authenticated", "kept indefinitely",
              False, "the anchors that prove the audit log was not rewritten"),
    DataClass("meta", INTERNAL, "counters and schema markers", "none",
              "kept indefinitely", False, "tiny, and identifiers must not be reissued"),
)

BY_STORE = {d.store: d for d in CLASSIFICATION}

# Stores purge() must never touch, whatever a policy says.
PROTECTED = frozenset({"audit_logs", "merkle_roots"})


# ------------------------------------------------------------------ policies ---
@dataclass(frozen=True)
class Policy:
    store: str
    after: dt.timedelta
    description: str


SESSION_RETENTION = dt.timedelta(days=30)

POLICIES: tuple[Policy, ...] = (
    Policy("sessions", SESSION_RETENTION,
           "Revoked or idle sessions, 30 days after they were last used."),
    Policy("uploads", dt.timedelta(0),
           "Uploads past their TTL that were never turned into an analysis."),
)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _parse(value) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


# ------------------------------------------------------------------- planning ---
def _expired_sessions(db, now: dt.datetime) -> list[dict]:
    cutoff = now - SESSION_RETENTION
    out = []
    for doc in db["sessions"].find({}, {"_id": 0}):
        last = _parse(doc.get("last_seen")) or _parse(doc.get("created"))
        if last is None or last > cutoff:
            continue
        # Only sessions that can no longer be used: revoked, or long past idle timeout.
        if doc.get("revoked") or last <= cutoff:
            out.append(doc)
    return out


def _expired_uploads(db, now: dt.datetime) -> list[dict]:
    out = []
    for doc in db["uploads"].find({}, {"_id": 0}):
        if doc.get("used"):
            continue  # claimed by an analysis; the analysis owns the blob now
        expires = _parse(doc.get("expires"))
        if expires is not None and expires <= now:
            out.append(doc)
    return out


def orphaned_blobs(db) -> list[str]:
    """Encrypted blobs on disk that nothing in the database points at any more.

    An upload that expires leaves its radiograph behind: the record goes, the
    ciphertext stays. Those files are still PHI, so they are found and reported.
    """
    from app import config

    referenced: set[str] = set()
    for doc in db["analyses"].find({}, {"_id": 0, "blobs": 1}):
        referenced.update(str(v) for v in (doc.get("blobs") or {}).values())
    for doc in db["uploads"].find({}, {"_id": 0, "blob": 1}):
        if doc.get("blob"):
            referenced.add(str(doc["blob"]))
    for doc in db["reports"].find({}, {"_id": 0, "blob": 1, "pdf_blob": 1}):
        for key in ("blob", "pdf_blob"):
            if doc.get(key):
                referenced.add(str(doc[key]))

    blob_dir = config.BLOB_DIR
    if not blob_dir.exists():
        return []
    return sorted(p.stem for p in blob_dir.glob("*.bin") if p.stem not in referenced)


def plan(db=None, now: dt.datetime | None = None) -> dict:
    """What retention *would* remove. Changes nothing."""
    if db is None:
        from app.models.connection import db as default_db

        db = default_db
    now = now or _now()
    sessions = _expired_sessions(db, now)
    uploads = _expired_uploads(db, now)
    orphans = orphaned_blobs(db)
    return {
        "generated_at": now.isoformat(),
        "items": {
            "sessions": {"count": len(sessions), "policy": POLICIES[0].description,
                         "ids": [s.get("sid", "")[:8] for s in sessions[:50]]},
            "uploads": {"count": len(uploads), "policy": POLICIES[1].description,
                        "ids": [u.get("upload_id", "")[:12] for u in uploads[:50]]},
            "orphaned_blobs": {"count": len(orphans), "policy":
                               "Encrypted files no record points at any more.",
                               "ids": [b[:12] for b in orphans[:50]]},
        },
        "total": len(sessions) + len(uploads) + len(orphans),
        "protected": sorted(PROTECTED),
    }


# -------------------------------------------------------------------- purging ---
class ProtectedStore(RuntimeError):
    """A caller tried to purge a store that must never be purged."""


def purge(db=None, now: dt.datetime | None = None, actor: str = "system") -> dict:
    """Remove what plan() reports. Call deliberately; nothing schedules this."""
    if db is None:
        from app.models.connection import db as default_db

        db = default_db
    from app import config
    from app.security.audit_log import audit

    now = now or _now()
    sessions = _expired_sessions(db, now)
    uploads = _expired_uploads(db, now)

    for doc in sessions:
        db["sessions"].delete_one({"sid": doc["sid"]})
    for doc in uploads:
        db["uploads"].delete_one({"upload_id": doc["upload_id"]})

    # Blobs last: an upload row removed above turns its blob into an orphan, so this
    # pass collects those too and the two never disagree about what is still referenced.
    removed_blobs = []
    for blob_id in orphaned_blobs(db):
        path = config.BLOB_DIR / f"{blob_id}.bin"
        try:
            path.unlink()
            removed_blobs.append(blob_id)
        except OSError as exc:
            logger.warning("Could not remove orphaned blob %s: %s", blob_id, exc)

    result = {"sessions": len(sessions), "uploads": len(uploads), "blobs": len(removed_blobs),
              "at": now.isoformat()}
    audit().record("RETENTION_PURGE", actor=actor,
                   details={k: v for k, v in result.items() if k != "at"})
    return result


def assert_purgeable(store: str) -> None:
    """Guard for any future caller that purges by store name."""
    if store in PROTECTED:
        raise ProtectedStore(
            f"{store} is a tamper-evident store: removing entries breaks chain verification")
    entry = BY_STORE.get(store)
    if entry is None:
        raise ProtectedStore(f"{store} is not classified; classify it before purging it")
    if not entry.purgeable:
        raise ProtectedStore(f"{store} holds {entry.classification} data: {entry.reason}")
