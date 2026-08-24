import logging
from database.connection import db

class RBACEnforcer:
    """
    Implements a Zero Trust access control layer.
    """
    
    ROLES = {
        "viewer": 10,
        "doctor": 20,
        "admin": 30,
        "superadmin": 40
    }

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def _get_role_level(self, role: str) -> int:
        return self.ROLES.get(role.lower(), 10)

    def can_access(self, current_role: str, required_role: str) -> bool:
        return self._get_role_level(current_role) >= self._get_role_level(required_role)

    def enforce_patient_access(self, doctor_id: str, role: str, patient_doc: dict) -> bool:
        if not patient_doc: return False
        if self.can_access(role, "admin"): return True
            
        owner_id = patient_doc.get("doctor_id")
        if owner_id is None or str(owner_id) == str(doctor_id):
            return True
            
        self.logger.warning(f"[SECURITY] Access DENIED: Dr. {doctor_id} -> Patient {patient_doc.get('patient_id')}")
        return False

    def filter_query_by_role(self, doctor_id: str, role: str, collection_name: str, base_query: dict = None) -> dict:
        query = base_query.copy() if base_query else {}
        if self.can_access(role, "admin"): return query
            
        if collection_name == "patients":
            query["$or"] = [{"doctor_id": str(doctor_id)}, {"doctor_id": None}]
        elif collection_name == "xray_records":
            my_patients = list(db["patients"].find({"doctor_id": str(doctor_id)}, {"patient_id": 1}))
            my_patient_ids = [p["patient_id"] for p in my_patients]
            unassigned = list(db["patients"].find({"doctor_id": None}, {"patient_id": 1}))
            unassigned_ids = [p["patient_id"] for p in unassigned]
            query["patient_id"] = {"$in": my_patient_ids + unassigned_ids}

        return query
