import hashlib
import datetime
import pyotp
from database.mongodb_connection import MongoDBConnection

class DoctorManager:
    def __init__(self):
        self.db = MongoDBConnection.get_db()
        self.collection = self.db["doctors"]
        self.collection.create_index("doctor_id", unique=True)
        self.collection.create_index("email", unique=True)

    def _hash_password(self, password):
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    def _is_first_doctor(self):
        return self.collection.count_documents({}) == 0

    def register_doctor(self, doctor_id, name, email, password, license_number, clinic="", city=""):
        """Register a new doctor. First registration is automatically admin."""
        role = "admin" if self._is_first_doctor() else "doctor"
        doc = {
            "doctor_id": doctor_id,
            "name": name,
            "email": email.strip().lower(),
            "password_hash": self._hash_password(password),
            "license_number": license_number,
            "clinic": clinic,
            "city": city,
            "role": role,
            "status": "active",       # active | inactive
            "totp_secret": None,      # None until 2FA is enrolled
            "totp_enabled": False,
            "created_date": datetime.datetime.now().strftime("%Y-%m-%d"),
            "last_login": None,
        }
        self.collection.insert_one(doc)
        doc.pop("_id", None)
        doc.pop("password_hash", None)
        return doc

    def authenticate(self, email, password):
        """Check credentials. Returns doctor doc (no password_hash) or None."""
        record = self.collection.find_one(
            {"email": email.strip().lower(),
             "password_hash": self._hash_password(password),
             "status": "active"},   # inactive doctors cannot log in
            {"_id": 0, "password_hash": 0}
        )
        if record:
            self.collection.update_one(
                {"doctor_id": record["doctor_id"]},
                {"$set": {"last_login": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}}
            )
        return record

    def verify_totp(self, doctor_id, code):
        """Verify a TOTP code. Returns True if valid."""
        doc = self.collection.find_one({"doctor_id": doctor_id})
        if not doc or not doc.get("totp_secret"):
            return False
        totp = pyotp.TOTP(doc["totp_secret"])
        return totp.verify(code, valid_window=1)

    def generate_totp_secret(self, doctor_id):
        """Generate and store a new TOTP secret. Returns the secret string."""
        secret = pyotp.random_base32()
        self.collection.update_one({"doctor_id": doctor_id}, {"$set": {"totp_secret": secret, "totp_enabled": False}})
        return secret

    def enable_totp(self, doctor_id):
        self.collection.update_one({"doctor_id": doctor_id}, {"$set": {"totp_enabled": True}})

    def disable_totp(self, doctor_id):
        self.collection.update_one({"doctor_id": doctor_id}, {"$set": {"totp_secret": None, "totp_enabled": False}})

    def get_totp_uri(self, doctor_id, email):
        """Returns provisioning URI for QR code generation."""
        doc = self.collection.find_one({"doctor_id": doctor_id})
        if not doc or not doc.get("totp_secret"):
            return None
        totp = pyotp.TOTP(doc["totp_secret"])
        return totp.provisioning_uri(name=email, issuer_name="PerioVision AI")

    def get_doctor(self, doctor_id):
        return self.collection.find_one({"doctor_id": doctor_id}, {"_id": 0, "password_hash": 0})

    def get_all_doctors(self):
        return list(self.collection.find({}, {"_id": 0, "password_hash": 0}))

    def get_doctors_by_status(self, status="active"):
        return list(self.collection.find({"status": status}, {"_id": 0, "password_hash": 0}))

    def set_status(self, doctor_id, status):
        """Admin: activate or deactivate a doctor account."""
        self.collection.update_one({"doctor_id": doctor_id}, {"$set": {"status": status}})

    def set_role(self, doctor_id, role):
        self.collection.update_one({"doctor_id": doctor_id}, {"$set": {"role": role}})

    def email_exists(self, email):
        return self.collection.find_one({"email": email.strip().lower()}) is not None

    def get_next_doctor_id(self):
        last = self.collection.find_one(sort=[("doctor_id", -1)])
        if last and "doctor_id" in last:
            try:
                return int(last["doctor_id"]) + 1
            except (TypeError, ValueError):
                pass
        return 1001

    def update_profile(self, doctor_id, clinic=None, city=None, name=None):
        updates = {}
        if clinic is not None: updates["clinic"] = clinic
        if city is not None:   updates["city"]   = city
        if name is not None:   updates["name"]   = name
        if updates:
            self.collection.update_one({"doctor_id": doctor_id}, {"$set": updates})

    def get_system_stats(self):
        total   = self.collection.count_documents({})
        active  = self.collection.count_documents({"status": "active"})
        admins  = self.collection.count_documents({"role": "admin"})
        with_2fa = self.collection.count_documents({"totp_enabled": True})
        return {"total": total, "active": active, "admins": admins, "with_2fa": with_2fa}
