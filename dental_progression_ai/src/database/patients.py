import datetime
from database.connection import db
from database.id_generator import get_next_patient_id
from security.encryption import PHIEncryptor
from security.rbac import RBACEnforcer
from security.honeypot import HoneypotManager
from security.orchestrator import SecurityOrchestrator

class PatientManager:
    """
    Manages patient records with integrated PHI encryption and Zero-Trust RBAC.
    """
    
    def __init__(self):
        self.phi_encryptor = PHIEncryptor()
        self.rbac = RBACEnforcer()
        self.honeypot = HoneypotManager()
        self.orchestrator = SecurityOrchestrator()
        self.collection = db["patients"]

    def create_patient(self, name, age, gender, contact, notes, risk_factors=None, doctor_id=None):
        import re
        sanitized_name = re.sub(r'<[^>]*>', '', str(name))
        patient_id = get_next_patient_id()
        patient_document = {
            "patient_id": patient_id,
            "patient_name": sanitized_name,
            "age": age,
            "gender": gender,
            "contact_number": contact,
            "notes": notes,
            "risk_factors": risk_factors or [],
            "doctor_id": str(doctor_id) if doctor_id else None,
            "created_date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "deleted": False
        }
        encrypted_doc = self.phi_encryptor.encrypt_patient_record(patient_document)
        self.collection.insert_one(encrypted_doc)
        return patient_id

    def get_patient(self, patient_id, requester_id=None, requester_role="doctor"):
        doc = self.collection.find_one({"patient_id": int(patient_id), "deleted": {"$ne": True}}, {"_id": 0})
        if not doc: return None
        if doc.get("is_honeypot"):
            self.orchestrator.trigger_incident_response("HONEYPOT_BREACH", str(requester_id), f"Accessed patient {patient_id}")
            return {"error": "CRITICAL SECURITY VIOLATION: ACCOUNT LOCKED"}
        if requester_id and not self.rbac.enforce_patient_access(requester_id, requester_role, doc):
            return {"error": "Access Denied"}
        return self.phi_encryptor.decrypt_patient_record(doc)

    def search_patients(self, query, requester_id=None, requester_role="doctor"):
        query_idx = self.phi_encryptor.get_blind_index(query)
        search_filter = {
            "deleted": {"$ne": True},
            "$or": [
                {"patient_name_idx": query_idx},
                {"contact_number_idx": query_idx}
            ]
        }
        rbac_filter = self.rbac.filter_query_by_role(requester_id, requester_role, "patients", search_filter)
        results = list(self.collection.find(rbac_filter, {"_id": 0}))
        return [self.phi_encryptor.decrypt_patient_record(r) for r in results]

    def list_all_patients(self, requester_id=None, requester_role="doctor"):
        rbac_filter = self.rbac.filter_query_by_role(requester_id, requester_role, "patients", {"deleted": {"$ne": True}})
        results = list(self.collection.find(rbac_filter, {"_id": 0}).sort("created_date", -1))
        return [self.phi_encryptor.decrypt_patient_record(r) for r in results]

    def get_patients_by_doctor(self, doctor_id):
        results = list(self.collection.find({"doctor_id": str(doctor_id), "deleted": {"$ne": True}}, {"_id": 0}))
        return [self.phi_encryptor.decrypt_patient_record(r) for r in results]

    def update_patient(self, patient_id, fields_dict, requester_id=None, requester_role="doctor"):
        doc = self.collection.find_one({"patient_id": int(patient_id)})
        if not self.rbac.enforce_patient_access(requester_id, requester_role, doc):
            return False
        if fields_dict:
            self.collection.update_one({"patient_id": int(patient_id)}, {"$set": fields_dict})
            return True
        return False

    def delete_patient(self, patient_id):
        self.collection.update_one({"patient_id": int(patient_id)}, {"$set": {"deleted": True}})
