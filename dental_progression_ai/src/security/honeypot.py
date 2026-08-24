import logging
from database.connection import db

class HoneypotManager:
    def __init__(self):
        self.collection = db["patients"]
        self.logger = logging.getLogger(__name__)

    def create_honeypot_patient(self):
        import random
        import string
        
        # Cleanup old static honeypot if exists
        self.collection.delete_many({"patient_id": 999999})
        
        # Check if we already have dynamic honeypots deployed
        if self.collection.count_documents({"is_honeypot": True}) >= 3:
            return
            
        names = ["VIP_OVERRIDE", "SYS_ADMIN_TEST", "SEC_VAULT_01"]
        
        for name in names:
            rand_id = random.randint(1000000, 9999999)
            rand_name = name + "_" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
            honeypot_data = {
                "patient_id": rand_id,
                "patient_name": rand_name,
                "age": random.randint(25, 60),
                "gender": "Unknown",
                "notes": "CONFIDENTIAL HIGH VALUE TARGET",
                "is_honeypot": True,
                "doctor_id": None # Global scope
            }
            # Only insert if ID doesn't exist
            if not self.collection.find_one({"patient_id": rand_id}):
                self.collection.insert_one(honeypot_data)
                
        print("[SECURITY] Dynamic randomized honeypot records deployed.")

    def check_honeypot_access(self, patient_id: int, doctor_id: str) -> bool:
        doc = self.collection.find_one({"patient_id": int(patient_id), "is_honeypot": True})
        if doc:
            self.logger.critical(f"🚨 HONEYPOT BREACH: Dr. {doctor_id} accessed {doc['patient_name']}")
            return True
        return False
