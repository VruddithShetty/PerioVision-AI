"""Honeypot (decoy) patient records that detect ID-guessing and insider browsing.

Design, versus the earlier static version:
* Decoys look like ordinary patients: realistic synthetic names, normal
  clinical fields, the same encryption, IDs inside the normal ID range. There is
  no "is_honeypot" flag or tell-tale name on the record itself.
* Which IDs are decoys is kept in a separate collection as HMAC tags, so even
  someone reading the patients collection cannot tell them apart.
* Decoys belong to no real clinician, so legitimate users never see them; the
  only ways to reach one are guessing IDs or bulk browsing.
* Touching one writes a critical audit entry, revokes the user's sessions and
  locks the account for 60 minutes (not permanently, so the alarm cannot be
  abused to lock out a colleague for good).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets

from app.models.connection import db
from app.security.crypto import _derive, get_encryptor

logger = logging.getLogger(__name__)

_FIRST = ["Asha", "Rohan", "Meera", "Karan", "Priya", "Arjun", "Nisha", "Vikram", "Leela", "Dev", "Sara", "Omar",
          "Elena", "Tomas", "Mina", "Jonah"]
_LAST = ["Rao", "Menon", "Iyer", "Kapoor", "Nair", "Shah", "Das", "Pillai", "Costa", "Novak", "Lind", "Okafor"]
DECOY_OWNER = "system-decoy-owner"
LOCK_MINUTES = 60


class HoneypotManager:
    def __init__(self):
        self.patients = db["patients"]
        self.decoys = db["security_decoys"]

    @staticmethod
    def _tag_with(key: bytes, patient_id) -> str:
        return hmac.new(_derive(key, b"honeypot-tag"), f"decoy:{patient_id}".encode(), hashlib.sha256).hexdigest()

    def _tag(self, patient_id) -> str:
        """Tag under the active key, using a key derived for this purpose (never the AES key itself)."""
        return self._tag_with(get_encryptor().keyring.active_key, patient_id)

    def _candidate_tags(self, patient_id) -> list[str]:
        """Tags under every key in the ring, so decoys stay armed after a key rotation (the old key stays in
        the ring until scripts/rotate_keys.py has re-tagged them). Also the pre-2026-10-04 format, which was
        an HMAC under the raw encryption key."""
        tags = []
        for key in get_encryptor().keyring.keys.values():
            tags.append(self._tag_with(key, patient_id))
            tags.append(hmac.new(key, f"decoy:{patient_id}".encode(), hashlib.sha256).hexdigest())
        return tags

    def is_decoy(self, patient_id) -> bool:
        return self.decoys.find_one({"tag": {"$in": self._candidate_tags(patient_id)}}) is not None

    def retag_all(self, patient_ids) -> int:
        """Re-tag existing decoys under the active key (run during key rotation). Returns how many."""
        n = 0
        for pid in patient_ids:
            doc = self.decoys.find_one({"tag": {"$in": self._candidate_tags(pid)}})
            if doc is not None and doc["tag"] != self._tag(pid):
                self.decoys.update_one({"_id": doc["_id"]}, {"$set": {"tag": self._tag(pid)}})
                n += 1
        return n

    def deploy(self, count: int = 3) -> int:
        """Create decoys if fewer than `count` exist. Returns how many were added."""
        existing = self.decoys.count_documents({})
        added = 0
        from app.models.patients import PatientManager

        mgr = PatientManager()
        for _ in range(max(0, count - existing)):
            data = {"name": f"{secrets.choice(_FIRST)} {secrets.choice(_LAST)}",
                    "age": 30 + secrets.randbelow(40),
                    "sex": secrets.choice(["female", "male"]),
                    "smoking_status": secrets.choice(["never", "former", "current"]),
                    "diabetic": secrets.randbelow(4) == 0,
                    "hba1c": round(5.2 + secrets.randbelow(30) / 10, 1),
                    "notes": ""}
            doc = mgr.create_patient(data, owner_id=DECOY_OWNER)
            self.patients.update_one({"patient_id": doc["patient_id"]}, {"$set": {"care_team": []}})
            self.decoys.insert_one({"tag": self._tag(doc["patient_id"])})
            added += 1
        return added

    def on_access(self, patient_doc: dict, user_id: str) -> None:
        from app.security.audit_log import audit
        from app.services import container

        logger.critical("[SECURITY] Honeypot record accessed by user %s", user_id)
        audit().record("HONEYPOT_TRIGGERED", outcome="alert", actor=user_id, resource=patient_doc.get("pseudo_id"),
                       details={"response": f"sessions revoked, account locked {LOCK_MINUTES} min"})
        container.session_store().revoke_all_for(user_id, reason="honeypot")
        container.doctor_manager().lock_account(user_id, minutes=LOCK_MINUTES)

    # Older API
    def check_honeypot_access(self, patient_id: int, doctor_id: str) -> bool:
        return self.is_decoy(patient_id)
