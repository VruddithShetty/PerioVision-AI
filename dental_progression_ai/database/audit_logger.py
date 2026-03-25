import datetime
from database.mongodb_connection import MongoDBConnection

class AuditLogger:
    def __init__(self):
        self.db = MongoDBConnection.get_db()
        self.collection = self.db["audit_logs"]
        self.collection.create_index("timestamp")
        self.collection.create_index("doctor_id")

    def log(self, doctor_id, action, details="", level="INFO"):
        """
        Record an auditable action.
        level: INFO | WARNING | CRITICAL
        """
        entry = {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "doctor_id": doctor_id,
            "action": action,
            "details": details,
            "level": level,
        }
        self.collection.insert_one(entry)

    def get_recent(self, n=50, level=None):
        query = {}
        if level:
            query["level"] = level
        return list(
            self.collection.find(query, {"_id": 0})
            .sort("timestamp", -1)
            .limit(n)
        )

    def get_by_doctor(self, doctor_id, n=100):
        return list(
            self.collection.find({"doctor_id": doctor_id}, {"_id": 0})
            .sort("timestamp", -1)
            .limit(n)
        )

    def get_stats(self):
        """Returns basic stats for admin overview."""
        total  = self.collection.count_documents({})
        warns  = self.collection.count_documents({"level": "WARNING"})
        crits  = self.collection.count_documents({"level": "CRITICAL"})
        return {"total": total, "warnings": warns, "critical": crits}
