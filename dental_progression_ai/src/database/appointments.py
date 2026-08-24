import datetime
from database.connection import db

class AppointmentManager:
    def __init__(self):
        self.collection = db["appointments"]

    def schedule_appointment(self, doctor_id, patient_id, appointment_date, notes=""):
        appointment = {
            "doctor_id": str(doctor_id),
            "patient_id": int(patient_id),
            "date": appointment_date,
            "notes": notes,
            "status": "Scheduled",
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        return self.collection.insert_one(appointment).inserted_id

    def get_upcoming_appointments(self, doctor_id):
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return list(self.collection.find({
            "doctor_id": str(doctor_id),
            "date": {"$gte": now}
        }).sort("date", 1))

    def cancel_appointment(self, appointment_id):
        self.collection.update_one({"_id": appointment_id}, {"$set": {"status": "Cancelled"}})
