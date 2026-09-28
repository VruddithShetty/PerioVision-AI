"""Analysis records (one per radiograph per visit), review decisions and signed reports.

Images (radiograph, annotated overlay, Grad-CAM overlay) are never stored in the
database: records hold only IDs of encrypted blobs (app/services/storage_service.py).
"""
from __future__ import annotations

import datetime as dt
import secrets

import pymongo

from app.models.connection import db


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


class AnalysisStore:
    def __init__(self):
        self.collection = db["analyses"]
        self.collection.create_index("analysis_id", unique=True)
        self.collection.create_index([("patient_id", pymongo.ASCENDING), ("visit_date", pymongo.ASCENDING)])

    def create(self, doc: dict) -> dict:
        doc = {"analysis_id": "AN-" + secrets.token_hex(6), "created": _now(), **doc}
        self.collection.insert_one(dict(doc))
        doc.pop("_id", None)
        return doc

    def get(self, analysis_id: str):
        return self.collection.find_one({"analysis_id": str(analysis_id)}, {"_id": 0})

    def for_patient(self, patient_id: int) -> list[dict]:
        return list(self.collection.find({"patient_id": int(patient_id)}, {"_id": 0}).sort("visit_date", 1))

    def latest_for_patient(self, patient_id: int, before_date: str | None = None):
        query = {"patient_id": int(patient_id)}
        if before_date:
            query["visit_date"] = {"$lte": str(before_date)}
        return self.collection.find_one(query, {"_id": 0}, sort=[("visit_date", -1), ("created", -1)])

    def review_queue(self, patient_ids: list[int] | None = None) -> list[dict]:
        query = {"review.status": "review_required"}
        if patient_ids is not None:
            query["patient_id"] = {"$in": patient_ids}
        return list(self.collection.find(query, {"_id": 0}).sort("created", 1))

    def record_review(self, analysis_id: str, decision: dict) -> bool:
        res = self.collection.update_one(
            {"analysis_id": str(analysis_id)},
            {"$set": {"review.status": decision["status"], "review.decision": decision},
             "$push": {"review.history": decision}})
        return res.matched_count == 1

    def count(self, query: dict | None = None) -> int:
        return self.collection.count_documents(query or {})

    def recent(self, limit: int = 10, patient_ids: list[int] | None = None) -> list[dict]:
        query = {} if patient_ids is None else {"patient_id": {"$in": patient_ids}}
        return list(self.collection.find(query, {"_id": 0}).sort("created", -1).limit(limit))


class ReportStore:
    def __init__(self):
        self.collection = db["reports"]
        self.collection.create_index("report_id", unique=True)

    def create(self, doc: dict) -> dict:
        doc = {"report_id": "RPT-" + secrets.token_hex(8), "created": _now(), **doc}
        self.collection.insert_one(dict(doc))
        doc.pop("_id", None)
        return doc

    def get(self, report_id: str):
        return self.collection.find_one({"report_id": str(report_id)}, {"_id": 0})

    def list(self, patient_ids: list[int] | None = None, limit: int = 100) -> list[dict]:
        query = {} if patient_ids is None else {"patient_id": {"$in": patient_ids}}
        return list(self.collection.find(query, {"_id": 0}).sort("created", -1).limit(limit))


class PerioChartStore:
    """Six-point periodontal charts (probing depth, recession, bleeding, plaque, mobility, furcation)."""

    def __init__(self):
        self.collection = db["perio_charts"]
        self.collection.create_index("chart_id", unique=True)

    def create(self, doc: dict) -> dict:
        doc = {"chart_id": "PC-" + secrets.token_hex(6), "created": _now(), **doc}
        self.collection.insert_one(dict(doc))
        doc.pop("_id", None)
        return doc

    def for_patient(self, patient_id: int) -> list[dict]:
        return list(self.collection.find({"patient_id": int(patient_id)}, {"_id": 0}).sort("exam_date", -1))

    def latest(self, patient_id: int):
        return self.collection.find_one({"patient_id": int(patient_id)}, {"_id": 0}, sort=[("exam_date", -1), ("created", -1)])
