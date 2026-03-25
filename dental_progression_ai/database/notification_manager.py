import datetime
from database.mongodb_connection import MongoDBConnection

class NotificationManager:
    def __init__(self):
        self.db = MongoDBConnection.get_db()
        self.collection = self.db["notifications"]
        self.collection.create_index("doctor_id")
        self.collection.create_index("read")

    def create_alert(self, doctor_id, title, message, level="info", patient_id=None):
        """
        level: info | warning | danger
        """
        doc = {
            "doctor_id": doctor_id,
            "title": title,
            "message": message,
            "level": level,
            "patient_id": patient_id,
            "read": False,
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.collection.insert_one(doc)

    def get_unread(self, doctor_id, limit=50):
        return list(
            self.collection.find({"doctor_id": doctor_id, "read": False}, {"_id": 0})
            .sort("created_at", -1)
            .limit(limit)
        )

    def get_all(self, doctor_id, limit=100):
        return list(
            self.collection.find({"doctor_id": doctor_id}, {"_id": 0})
            .sort("created_at", -1)
            .limit(limit)
        )

    def mark_read(self, doctor_id):
        """Mark all as read for a doctor."""
        self.collection.update_many({"doctor_id": doctor_id, "read": False}, {"$set": {"read": True}})

    def unread_count(self, doctor_id):
        return self.collection.count_documents({"doctor_id": doctor_id, "read": False})

    def auto_risk_alert(self, doctor_id, patient_name, patient_id, high_risk_teeth):
        """Auto-generate a high-risk notification from analysis results."""
        if high_risk_teeth:
            teeth_str = ", ".join([t.replace("tooth_", "T") for t in high_risk_teeth])
            self.create_alert(
                doctor_id=doctor_id,
                title=f"🔴 High Risk Detected — {patient_name}",
                message=f"Patient {patient_name} shows HIGH risk on: {teeth_str}. Immediate review recommended.",
                level="danger",
                patient_id=patient_id
            )
