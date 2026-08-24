import datetime
import numpy as np
from database.connection import db
from security.merkle import MerkleAuditLog

class AuditLogger:
    """
    Manages Merkle-verified clinical audit trails.
    """
    
    def __init__(self):
        self.collection = db["audit_logs"]
        self.merkle = MerkleAuditLog()

    def log(self, doctor_id: str, action: str, details: str = "", patient_id: str = None, level: str = "INFO"):
        """
        Creates a tamper-evident audit log entry.
        """
        metadata = {"level": level, "version": "2.0"}
        # MerkleAuditLog.log_action handles sequence, prev_hash, and insertion
        return self.merkle.log_action(doctor_id, action, str(patient_id) if patient_id else "SYSTEM", {"details": details, **metadata})
        
    def get_recent(self, limit=100):
        return list(self.collection.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit))

    def verify_integrity(self):
        """Verifies the entire audit chain."""
        return self.merkle.verify_chain_integrity()

    def publish_root(self, doctor_id):
        return self.merkle.publish_root(doctor_id)

    def check_inference_rate_limit(self, doctor_id: str, window_minutes: int = 60, max_requests: int = 30) -> bool:
        now = datetime.datetime.now(datetime.timezone.utc)
        start_time = (now - datetime.timedelta(minutes=window_minutes)).isoformat()
        count = self.collection.count_documents({
            "doctor_id": str(doctor_id),
            "action": "ANALYSIS",
            "timestamp": {"$gte": start_time}
        })
        return count < max_requests

    def detect_systematic_probing(self, doctor_id: str) -> dict:
        logs = list(self.collection.find({
            "doctor_id": str(doctor_id),
            "action": "ANALYSIS"
        }).sort("timestamp", -1).limit(50))
        if len(logs) < 10: return {"suspicious": False, "pattern": "Insufficient data"}
        newest = datetime.datetime.fromisoformat(logs[0]["timestamp"])
        tenth = datetime.datetime.fromisoformat(logs[9]["timestamp"])
        if (newest - tenth).total_seconds() < 600:
            return {"suspicious": True, "pattern": "Rapid-fire analysis burst detected"}
        intervals = []
        for i in range(len(logs) - 1):
            t1 = datetime.datetime.fromisoformat(logs[i]["timestamp"])
            t2 = datetime.datetime.fromisoformat(logs[i+1]["timestamp"])
            intervals.append((t1 - t2).total_seconds())
        if np.std(intervals) < 5.0:
            return {"suspicious": True, "pattern": "Highly consistent request intervals (Bot behavior)"}
        return {"suspicious": False, "pattern": "Normal behavioral pattern"}
