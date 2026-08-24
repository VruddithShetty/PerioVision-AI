import datetime
import uuid
import bcrypt
import pyotp
import random
from database.connection import db
from database.audit import AuditLogger

# Initialize logger
audit_log = AuditLogger()

def hash_password(password: str) -> bytes:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12))

def verify_password(plain_password: str, hashed_password: bytes) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password)

class DoctorManager:
    """
    Manages doctor profiles, authentication, and 2FA.
    """
    
    def __init__(self):
        self.collection = db["doctors"]
        
    def register_doctor(self, name, email, password, specialization=None, clinic_name=None, phone=None, role="doctor"):
        existing = db["doctors"].find_one({"email": email})
        if existing:
            raise ValueError("Email already registered.")
            
        doctor_id = str(uuid.uuid4())
        totp_secret = pyotp.random_base32()
        
        document = {
            "doctor_id": doctor_id,
            "name": name,
            "email": email,
            "password": hash_password(password),
            "specialization": specialization,
            "clinic_name": clinic_name,
            "phone": phone,
            "role": role,
            "created_date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "last_login": None,
            "failed_attempts": 0,
            "locked_until": None,
            "two_factor_secret": totp_secret,
            "two_factor_enabled": False
        }
        db["doctors"].insert_one(document)
        audit_log.log(doctor_id, "doctor_registered")
        return doctor_id

    def authenticate_doctor(self, email, plain_password):
        doctor = db["doctors"].find_one({"email": email})
        if not doctor:
            return None
            
        now = datetime.datetime.now(datetime.timezone.utc)
        
        if doctor.get("locked_until"):
            locked_until = datetime.datetime.fromisoformat(doctor["locked_until"])
            if now < locked_until:
                raise PermissionError("Account locked due to multiple failed login attempts.")
            else:
                db["doctors"].update_one({"email": email}, {"$set": {"failed_attempts": 0, "locked_until": None}})
                
        if verify_password(plain_password, doctor["password"]):
            db["doctors"].update_one({"email": email}, {"$set": {"failed_attempts": 0, "last_login": now.isoformat()}})
            audit_log.log(doctor["doctor_id"], "LOGIN_SUCCESS")
            doctor.pop("password", None)
            doctor.pop("_id", None)
            return doctor
        else:
            failed_attempts = doctor.get("failed_attempts", 0) + 1
            updates = {"failed_attempts": failed_attempts}
            
            if failed_attempts >= 5:
                updates["locked_until"] = (now + datetime.timedelta(minutes=15)).isoformat()
                audit_log.log(doctor["doctor_id"], "ACCOUNT_LOCKED", details="5 failed login attempts", level="WARNING")
                
            db["doctors"].update_one({"email": email}, {"$set": updates})
            audit_log.log(doctor["doctor_id"], "LOGIN_FAILED", details=f"Attempt {failed_attempts}")
            return None

    def get_doctor(self, doctor_id):
        return db["doctors"].find_one({"doctor_id": doctor_id}, {"_id": 0, "password": 0})

    def get_all_doctors(self):
        return list(db["doctors"].find({}, {"password": 0, "_id": 0}))

    def lock_account(self, doctor_id: str, minutes: int = 1440):
        until = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=minutes)).isoformat()
        db["doctors"].update_one({"doctor_id": doctor_id}, {"$set": {"locked_until": until}})
        audit_log.log(doctor_id, "ACCOUNT_LOCKED_MANUAL", details=f"Locked for {minutes}m", level="CRITICAL")

    def verify_totp(self, doctor_id, code):
        doctor = db["doctors"].find_one({"doctor_id": doctor_id})
        if not doctor or not doctor.get("two_factor_secret"):
            return False
        totp = pyotp.TOTP(doctor["two_factor_secret"])
        return totp.verify(code)
