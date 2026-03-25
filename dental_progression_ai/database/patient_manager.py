import datetime
from database.mongodb_connection import MongoDBConnection

class PatientManager:
    def __init__(self):
        self.db = MongoDBConnection.get_db()
        self.collection = self.db["patients"]
        self.collection.create_index("patient_id", unique=True)

    def create_patient(self, patient_id, name, age, gender, contact_number, notes="", doctor_id=None):
        patient_document = {
            "patient_id": patient_id,
            "patient_name": name,
            "age": age,
            "gender": gender,
            "contact_number": contact_number,
            "notes": notes,
            "doctor_id": doctor_id,
            "created_date": datetime.datetime.now().strftime("%Y-%m-%d")
        }
        self.collection.insert_one(patient_document)
        return patient_document

    def get_patient(self, patient_id):
        patient_id = int(patient_id)
        return self.collection.find_one({"patient_id": patient_id}, {"_id": 0})

    def get_all_patients(self):
        return list(self.collection.find({}, {"_id": 0}))

    def get_patients_by_doctor(self, doctor_id):
        """Returns only patients belonging to the given doctor_id."""
        return list(self.collection.find({"doctor_id": doctor_id}, {"_id": 0}))

    def get_last_patient_id(self):
        last_patient = self.collection.find_one(sort=[("patient_id", -1)])
        if last_patient and "patient_id" in last_patient:
            return last_patient["patient_id"]
        return None

    def transfer_patient(self, patient_id, new_doctor_id):
        """Transfer a patient to a different doctor. Returns True on success."""
        result = self.collection.update_one(
            {"patient_id": int(patient_id)},
            {"$set": {"doctor_id": new_doctor_id,
                      "transferred_date": datetime.datetime.now().strftime("%Y-%m-%d")}}
        )
        return result.modified_count > 0

    def update_patient(self, patient_id, **kwargs):
        allowed = {"patient_name", "age", "gender", "contact_number", "notes"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if updates:
            self.collection.update_one({"patient_id": int(patient_id)}, {"$set": updates})
