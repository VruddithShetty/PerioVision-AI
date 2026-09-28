"""Patient records: identifying fields encrypted (AES-256-GCM), clinical fields for risk fusion.

* Name, contact and notes are encrypted; name and contact also get blind indexes for exact search.
* Each patient has a `pseudo_id` (HMAC-derived) used in logs and analytics instead of the real ID.
* Object-level access: admins see all; dentists/technicians only their own patients or ones
  where they are on the care team (app/security/rbac.py).
"""
from __future__ import annotations

import datetime as dt

import pymongo

from app.models.connection import db
from app.security.crypto import get_encryptor
from app.security.rbac import can_access_patient, patient_query_for

CLINICAL_FIELDS = ("age", "sex", "smoking_status", "cigarettes_per_day", "diabetic", "hba1c", "teeth_lost_perio")


class PatientManager:
    def __init__(self):
        self.collection = db["patients"]
        self.collection.create_index("patient_id", unique=True)
        self.enc = get_encryptor()

    def _next_id(self) -> int:
        last = self.collection.find_one(sort=[("patient_id", pymongo.DESCENDING)])
        return (last["patient_id"] + 1) if last else 1001

    def create_patient(self, data: dict, owner_id: str) -> dict:
        for _ in range(5):
            patient_id = self._next_id()
            doc = {
                "patient_id": patient_id,
                "pseudo_id": self.enc.pseudonymize(patient_id),
                "patient_name": data["name"],
                "contact_number": data.get("contact") or "",
                "notes": data.get("notes") or "",
                **{f: data.get(f) for f in CLINICAL_FIELDS},
                "doctor_id": str(owner_id),
                "care_team": [str(owner_id)],
                "created_date": dt.datetime.now(dt.timezone.utc).isoformat(),
                "deleted": False,
            }
            try:
                self.collection.insert_one(self.enc.encrypt_patient_record(doc))
                return self._public(self.collection.find_one({"patient_id": patient_id}, {"_id": 0}))
            except pymongo.errors.DuplicateKeyError:
                continue
        raise RuntimeError("Could not allocate a patient ID.")

    def _public(self, doc):
        return self.enc.decrypt_patient_record(doc) if doc else None

    def get_raw(self, patient_id):
        try:
            pid = int(patient_id)
        except (TypeError, ValueError):
            return None
        return self.collection.find_one({"patient_id": pid, "deleted": {"$ne": True}}, {"_id": 0})

    def get_patient(self, patient_id, user_id: str, role: str):
        """Return the decrypted record, or None if it does not exist or the user may not see it."""
        doc = self.get_raw(patient_id)
        if not doc or not can_access_patient(user_id, role, doc):
            return None
        return self._public(doc)

    def list_patients(self, user_id: str, role: str, search: str | None = None):
        base = {"deleted": {"$ne": True}, "doctor_id": {"$ne": "system-decoy-owner"}}
        if search:
            idx = self.enc.get_blind_index(search)
            base["$and"] = [{"$or": [{"patient_name_idx": idx}, {"contact_number_idx": idx},
                                     {"pseudo_id": str(search).strip()}]}]
        docs = self.collection.find(patient_query_for(user_id, role, base), {"_id": 0}).sort("created_date", -1)
        return [self._public(d) for d in docs]

    def update_patient(self, patient_id, data: dict, user_id: str, role: str):
        doc = self.get_raw(patient_id)
        if not doc or not can_access_patient(user_id, role, doc):
            return None
        updates = {f: data[f] for f in CLINICAL_FIELDS if f in data}
        for src, field in (("name", "patient_name"), ("contact", "contact_number"), ("notes", "notes")):
            if src in data and data[src] is not None:
                updates.update(self.enc.encrypt_patient_record({field: data[src]}))
        if updates:
            self.collection.update_one({"patient_id": doc["patient_id"]}, {"$set": updates})
        return self.get_patient(patient_id, user_id, role)

    def add_to_care_team(self, patient_id, member_id: str):
        self.collection.update_one({"patient_id": int(patient_id)}, {"$addToSet": {"care_team": str(member_id)}})

    def delete_patient(self, patient_id):
        self.collection.update_one({"patient_id": int(patient_id)}, {"$set": {"deleted": True}})

    def clinical_profile(self, patient_doc: dict) -> dict:
        return {f: patient_doc.get(f) for f in CLINICAL_FIELDS}
