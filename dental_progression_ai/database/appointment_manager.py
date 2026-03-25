import datetime
import uuid
from database.mongodb_connection import MongoDBConnection

APPOINTMENT_TYPES = ["Routine Check-up", "X-Ray & Analysis", "TALPA Review", "Treatment", "Follow-up", "Emergency"]
APPOINTMENT_STATUS = ["Scheduled", "Completed", "Cancelled", "No-Show"]

class AppointmentManager:
    def __init__(self):
        self.db = MongoDBConnection.get_db()
        self.collection = self.db["appointments"]
        self.collection.create_index("appointment_id", unique=True)
        self.collection.create_index("doctor_id")
        self.collection.create_index("patient_id")
        self.collection.create_index("date")

    def create(self, patient_id, doctor_id, date, time, appt_type="Routine Check-up", notes=""):
        appt_id = "APT" + uuid.uuid4().hex[:8].upper()
        doc = {
            "appointment_id": appt_id,
            "patient_id": int(patient_id),
            "doctor_id": doctor_id,
            "date": date,          # YYYY-MM-DD string
            "time": time,          # HH:MM string
            "type": appt_type,
            "status": "Scheduled",
            "notes": notes,
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.collection.insert_one(doc)
        doc.pop("_id", None)
        return doc

    def get_by_doctor(self, doctor_id, status=None):
        query = {"doctor_id": doctor_id}
        if status:
            query["status"] = status
        return list(self.collection.find(query, {"_id": 0}).sort("date", 1))

    def get_by_patient(self, patient_id):
        return list(
            self.collection.find({"patient_id": int(patient_id)}, {"_id": 0})
            .sort("date", -1)
        )

    def get_upcoming(self, doctor_id, days=30):
        today = datetime.date.today().isoformat()
        cutoff = (datetime.date.today() + datetime.timedelta(days=days)).isoformat()
        return list(
            self.collection.find(
                {"doctor_id": doctor_id, "status": "Scheduled",
                 "date": {"$gte": today, "$lte": cutoff}},
                {"_id": 0}
            ).sort("date", 1)
        )

    def update_status(self, appointment_id, new_status):
        self.collection.update_one(
            {"appointment_id": appointment_id},
            {"$set": {"status": new_status,
                      "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}}
        )

    def count_today(self, doctor_id):
        today = datetime.date.today().isoformat()
        return self.collection.count_documents({"doctor_id": doctor_id, "date": today, "status": "Scheduled"})

    def delete(self, appointment_id):
        self.collection.delete_one({"appointment_id": appointment_id})
