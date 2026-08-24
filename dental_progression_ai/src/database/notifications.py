import datetime
import bson
from database.connection import db

class NotificationManager:
    def __init__(self):
        self.collection = db["notifications"]

    def create_notification(self, doctor_id, type, message, priority="MEDIUM", patient_id=None):
        notif = {
            "doctor_id": str(doctor_id),
            "type": type,
            "message": message,
            "priority": priority,
            "patient_id": patient_id,
            "is_read": False,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        return self.collection.insert_one(notif).inserted_id

    def get_unread(self, doctor_id):
        return list(self.collection.find({"doctor_id": str(doctor_id), "is_read": False}).sort("created_at", -1))

    def mark_read(self, notif_id):
        if isinstance(notif_id, str):
            notif_id = bson.ObjectId(notif_id)
        self.collection.update_one({"_id": notif_id}, {"$set": {"is_read": True}})
