"""Data classification and retention.

The important assertions here are the refusals: retention must not be able to
touch the audit log, and clinical records must not be swept automatically.
"""
import datetime as dt

import pytest

from app import config
from app.models.connection import db
from app.security import retention


@pytest.fixture()
def clean_stores(tmp_path, monkeypatch):
    """Isolated stores and an isolated blob directory.

    purge() removes every blob no record points at, so it must never be pointed at
    the shared directory other tests are writing into: it would delete their
    radiographs and make this suite order-dependent. BLOB_DIR is redirected at a
    temporary folder for the duration.
    """
    blob_dir = tmp_path / "blobs"
    blob_dir.mkdir()
    monkeypatch.setattr(config, "BLOB_DIR", blob_dir)
    for name in ("sessions", "uploads", "analyses", "reports"):
        db[name].delete_many({})
    yield
    for name in ("sessions", "uploads", "analyses", "reports"):
        db[name].delete_many({})


def ago(**kw):
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(**kw)).isoformat()


def ahead(**kw):
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(**kw)).isoformat()


def make_blob(blob_id: str) -> None:
    (config.BLOB_DIR / f"{blob_id}.bin").write_bytes(b"PVE1 pretend ciphertext")


# ------------------------------------------------------------ classification ---
def test_every_store_the_app_writes_to_is_classified():
    """An unclassified store is one nobody decided a retention rule for."""
    written = {"patients", "analyses", "reports", "perio_charts", "corrections", "doctors",
               "sessions", "uploads", "security_decoys", "audit_logs", "merkle_roots", "meta"}
    missing = sorted(written - set(retention.BY_STORE))
    assert not missing, f"classify these in retention.CLASSIFICATION: {missing}"


def test_patient_data_is_never_marked_purgeable_except_working_material():
    """Clinical records must not be swept; only uploads that became nothing may go."""
    sweepable = {d.store for d in retention.CLASSIFICATION
                 if d.classification == retention.PATIENT and d.purgeable}
    assert sweepable == {"uploads"}


def test_the_audit_trail_is_protected():
    assert "audit_logs" in retention.PROTECTED
    assert "merkle_roots" in retention.PROTECTED


@pytest.mark.parametrize("store", ["audit_logs", "merkle_roots"])
def test_purging_the_audit_trail_is_refused(store):
    """Deleting a hash-chain entry breaks verification for every entry after it."""
    with pytest.raises(retention.ProtectedStore, match="chain"):
        retention.assert_purgeable(store)


@pytest.mark.parametrize("store", ["patients", "analyses", "reports", "perio_charts", "doctors"])
def test_purging_clinical_or_account_stores_is_refused(store):
    with pytest.raises(retention.ProtectedStore):
        retention.assert_purgeable(store)


def test_unclassified_store_is_refused_rather_than_assumed_safe():
    with pytest.raises(retention.ProtectedStore, match="not classified"):
        retention.assert_purgeable("some_new_collection")


def test_sessions_and_uploads_are_purgeable():
    retention.assert_purgeable("sessions")
    retention.assert_purgeable("uploads")


# -------------------------------------------------------------------- plan ---
def test_plan_reports_without_changing_anything(clean_stores):
    db["sessions"].insert_one({"sid": "s-old", "last_seen": ago(days=90), "revoked": True})
    db["uploads"].insert_one({"upload_id": "u-old", "blob": "b-old", "expires": ago(days=2),
                              "used": False})
    make_blob("b-old")

    report = retention.plan(db)
    assert report["items"]["sessions"]["count"] == 1
    assert report["items"]["uploads"]["count"] == 1
    assert report["total"] >= 2

    # Nothing was touched.
    assert db["sessions"].count_documents({}) == 1
    assert db["uploads"].count_documents({}) == 1
    assert (config.BLOB_DIR / "b-old.bin").exists()


def test_recent_sessions_and_live_uploads_are_left_alone(clean_stores):
    db["sessions"].insert_one({"sid": "s-new", "last_seen": ago(minutes=5), "revoked": False})
    db["uploads"].insert_one({"upload_id": "u-live", "blob": "b-live", "expires": ahead(hours=1),
                              "used": False})
    report = retention.plan(db)
    assert report["items"]["sessions"]["count"] == 0
    assert report["items"]["uploads"]["count"] == 0


def test_an_upload_already_turned_into_an_analysis_is_not_swept(clean_stores):
    """Once claimed, the analysis owns the blob; retention must not take it."""
    db["uploads"].insert_one({"upload_id": "u-used", "blob": "b-used", "expires": ago(days=5),
                              "used": True})
    assert retention.plan(db)["items"]["uploads"]["count"] == 0


# ------------------------------------------------------------ orphaned blobs ---
def test_orphaned_blobs_are_found(clean_stores):
    """The real leak: an upload record expires and its radiograph stays on disk."""
    make_blob("b-referenced")
    make_blob("b-orphan")
    db["analyses"].insert_one({"analysis_id": "AN-1", "blobs": {"radiograph": "b-referenced"}})

    orphans = retention.orphaned_blobs(db)
    assert "b-orphan" in orphans
    assert "b-referenced" not in orphans


# ------------------------------------------------------------------- purge ---
def test_purge_removes_expired_material_and_its_blobs(clean_stores, app):
    db["sessions"].insert_one({"sid": "s-old", "last_seen": ago(days=90), "revoked": True})
    db["uploads"].insert_one({"upload_id": "u-old", "blob": "b-old", "expires": ago(days=2),
                              "used": False})
    make_blob("b-old")

    with app.app_context():
        result = retention.purge(db)

    assert result["sessions"] == 1
    assert result["uploads"] == 1
    assert result["blobs"] == 1
    assert db["sessions"].count_documents({}) == 0
    assert db["uploads"].count_documents({}) == 0
    assert not (config.BLOB_DIR / "b-old.bin").exists()


def test_purge_keeps_blobs_an_analysis_still_references(clean_stores, app):
    make_blob("b-kept")
    db["analyses"].insert_one({"analysis_id": "AN-2", "blobs": {"radiograph": "b-kept"}})
    db["sessions"].insert_one({"sid": "s-old", "last_seen": ago(days=90), "revoked": True})

    with app.app_context():
        retention.purge(db)

    assert (config.BLOB_DIR / "b-kept.bin").exists(), "a referenced radiograph was deleted"


def test_purge_does_not_touch_the_audit_log(clean_stores, app):
    from app.security.audit_log import audit

    with app.app_context():
        before = len(audit().recent(limit=1000))
        db["sessions"].insert_one({"sid": "s-old", "last_seen": ago(days=90), "revoked": True})
        retention.purge(db)
        after = audit().recent(limit=1000)

    assert len(after) >= before, "purge removed audit entries"
    assert any(e["action"] == "RETENTION_PURGE" for e in after[:5]), "purge was not audited"


def test_purge_is_audited_without_patient_detail(clean_stores, app):
    from app.security.audit_log import audit

    db["uploads"].insert_one({"upload_id": "u-old", "blob": "b-old", "expires": ago(days=2),
                              "used": False})
    make_blob("b-old")
    with app.app_context():
        retention.purge(db)
        entry = next(e for e in audit().recent(limit=10) if e["action"] == "RETENTION_PURGE")

    assert set(entry["details"]) == {"sessions", "uploads", "blobs"}
    assert "u-old" not in str(entry), "an upload identifier reached the audit log"
