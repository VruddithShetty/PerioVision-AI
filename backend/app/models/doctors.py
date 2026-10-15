"""User accounts (collection "doctors" for backward compatibility) and login sessions.

Roles: admin, dentist, technician, auditor (see app/security/rbac.py).
TOTP secrets are stored AES-GCM encrypted. Passwords are bcrypt hashes.
"""
from __future__ import annotations

import datetime as dt
import uuid

from app.models.connection import db
from app.security import auth
from app.security.crypto import get_encryptor
from app.security.rbac import normalize_role

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
PUBLIC_FIELDS = {"_id": 0, "password": 0, "mfa_secret": 0, "two_factor_secret": 0, "mfa_last_step": 0}


def _clean_email(email) -> str:
    if not isinstance(email, str) or "@" not in email or len(email) > 254:
        raise ValueError("A valid email address is required.")
    return email.strip().lower()


class DoctorManager:
    """Manages user accounts, lockout and MFA."""

    def __init__(self):
        self.collection = db["doctors"]
        self.collection.create_index("email", unique=True)
        self.collection.create_index("doctor_id", unique=True)

    # ---------- accounts ----------
    def register_doctor(self, name, email, password, specialization=None, clinic_name=None, phone=None,
                        role="dentist"):
        email = _clean_email(email)
        role = normalize_role(role)
        if role is None:
            raise ValueError("Unknown role.")
        problems = auth.password_problems(str(password))
        if problems:
            raise ValueError("Password needs " + ", ".join(problems) + ".")
        if self.collection.find_one({"email": email}):
            raise ValueError("Email already registered.")

        doctor_id = str(uuid.uuid4())
        self.collection.insert_one({
            "doctor_id": doctor_id,
            "name": str(name)[:120],
            "email": email,
            "password": auth.hash_password(str(password)),
            "specialization": specialization,
            "clinic_name": clinic_name,
            "phone": phone,
            "role": role,
            "active": True,
            "created_date": auth.now().isoformat(),
            "last_login": None,
            "failed_attempts": 0,
            "locked_until": None,
            "mfa_enabled": False,
            "mfa_secret": None,
            "mfa_last_step": None,
        })
        return doctor_id

    def authenticate_doctor(self, email, plain_password):
        """Return the public user document, None for bad credentials, or raise PermissionError if locked."""
        try:
            email = _clean_email(email)
        except ValueError:
            return None
        if not isinstance(plain_password, str):
            return None
        user = self.collection.find_one({"email": email})
        if not user or not user.get("active", True):
            auth.verify_password(plain_password, auth.hash_password("timing-equaliser"))  # same cost either way
            return None

        current = auth.now()
        if user.get("locked_until"):
            if current < dt.datetime.fromisoformat(user["locked_until"]):
                raise PermissionError("Account locked due to multiple failed login attempts. Try again later.")
            self.collection.update_one({"email": email}, {"$set": {"failed_attempts": 0, "locked_until": None}})
            user["failed_attempts"] = 0

        if auth.verify_password(plain_password, user["password"]):
            updates = {"failed_attempts": 0, "last_login": current.isoformat()}
            if auth.needs_rehash(user["password"]):
                # Upgrade a pre-truncation-fix hash now that we hold the plaintext.
                updates["password"] = auth.hash_password(plain_password)
            self.collection.update_one({"email": email}, {"$set": updates})
            return self.get_doctor(user["doctor_id"])

        attempts = user.get("failed_attempts", 0) + 1
        updates = {"failed_attempts": attempts}
        if attempts >= MAX_FAILED_ATTEMPTS:
            updates["locked_until"] = (current + dt.timedelta(minutes=LOCKOUT_MINUTES)).isoformat()
        self.collection.update_one({"email": email}, {"$set": updates})
        return None

    def get_doctor(self, doctor_id):
        doc = self.collection.find_one({"doctor_id": str(doctor_id)}, PUBLIC_FIELDS)
        if doc:
            doc["role"] = normalize_role(doc.get("role"))
            doc["mfa_enabled"] = bool(doc.get("mfa_enabled") or doc.get("two_factor_enabled"))
        return doc

    def get_all_doctors(self):
        users = list(self.collection.find({}, PUBLIC_FIELDS))
        for u in users:
            u["role"] = normalize_role(u.get("role"))
        return users

    def set_role(self, doctor_id, role):
        role = normalize_role(role)
        if role is None:
            raise ValueError("Unknown role.")
        return self.collection.update_one({"doctor_id": str(doctor_id)}, {"$set": {"role": role}}).matched_count == 1

    def set_active(self, doctor_id, active: bool):
        return self.collection.update_one({"doctor_id": str(doctor_id)},
                                          {"$set": {"active": bool(active)}}).matched_count == 1

    def lock_account(self, doctor_id: str, minutes: int = 1440):
        until = (auth.now() + dt.timedelta(minutes=int(minutes))).isoformat()
        self.collection.update_one({"doctor_id": str(doctor_id)}, {"$set": {"locked_until": until}})

    def is_usable(self, user_doc) -> bool:
        if not user_doc or not user_doc.get("active", True):
            return False
        locked = user_doc.get("locked_until")
        return not (locked and auth.now() < dt.datetime.fromisoformat(locked))

    # ---------- MFA ----------
    def start_mfa_enrolment(self, doctor_id) -> dict:
        user = self.collection.find_one({"doctor_id": str(doctor_id)})
        if not user:
            raise ValueError("User not found.")
        secret = auth.new_totp_secret()
        self.collection.update_one({"doctor_id": str(doctor_id)}, {"$set": {
            "mfa_pending_secret": get_encryptor().encrypt_random(secret, aad=b"mfa")}})
        return auth.totp_provisioning(secret, user["email"])

    def confirm_mfa_enrolment(self, doctor_id, code) -> bool:
        user = self.collection.find_one({"doctor_id": str(doctor_id)})
        if not user or not user.get("mfa_pending_secret"):
            return False
        secret = get_encryptor().decrypt_random(user["mfa_pending_secret"], aad=b"mfa")
        step = auth.verify_totp(secret, code, None)
        if step is None:
            return False
        self.collection.update_one({"doctor_id": str(doctor_id)}, {
            "$set": {"mfa_secret": user["mfa_pending_secret"], "mfa_enabled": True, "mfa_last_step": step},
            "$unset": {"mfa_pending_secret": ""}})
        return True

    def disable_mfa(self, doctor_id):
        self.collection.update_one({"doctor_id": str(doctor_id)}, {
            "$set": {"mfa_enabled": False, "mfa_secret": None, "mfa_last_step": None}})

    def mfa_enabled(self, doctor_id) -> bool:
        user = self.collection.find_one({"doctor_id": str(doctor_id)}, {"mfa_enabled": 1})
        return bool(user and user.get("mfa_enabled"))

    def verify_totp(self, doctor_id, code) -> bool:
        user = self.collection.find_one({"doctor_id": str(doctor_id)})
        if not user or not user.get("mfa_secret"):
            return False
        secret = get_encryptor().decrypt_random(user["mfa_secret"], aad=b"mfa")
        step = auth.verify_totp(secret, code, user.get("mfa_last_step"))
        if step is None:
            return False
        self.collection.update_one({"doctor_id": str(doctor_id)}, {"$set": {"mfa_last_step": step}})
        return True


class SessionStore:
    """Server-side record of every login session so tokens can be revoked and re-verified."""

    def __init__(self):
        self.collection = db["sessions"]
        self.collection.create_index("sid", unique=True)

    def create(self, user_id: str, fp: str, ip_hash: str) -> tuple[str, str]:
        sid, refresh_jti = uuid.uuid4().hex, uuid.uuid4().hex
        stamp = auth.now().isoformat()
        self.collection.insert_one({"sid": sid, "user_id": str(user_id), "fp": fp, "ip_hash": ip_hash,
                                    "refresh_jti": refresh_jti, "created": stamp, "last_seen": stamp,
                                    "revoked": False})
        return sid, refresh_jti

    def get(self, sid: str):
        return self.collection.find_one({"sid": str(sid)}, {"_id": 0})

    def touch(self, sid: str):
        self.collection.update_one({"sid": str(sid)}, {"$set": {"last_seen": auth.now().isoformat()}})

    def rotate_refresh(self, sid: str, presented_jti: str) -> str | None:
        """Swap the refresh token ID. If an old ID is replayed, revoke the session (token theft)."""
        new_jti = uuid.uuid4().hex
        result = self.collection.update_one({"sid": str(sid), "refresh_jti": str(presented_jti), "revoked": False},
                                            {"$set": {"refresh_jti": new_jti, "last_seen": auth.now().isoformat()}})
        if result.matched_count == 1:
            return new_jti
        self.revoke(sid, reason="refresh_token_reuse")
        return None

    def revoke(self, sid: str, reason: str = "logout"):
        self.collection.update_one({"sid": str(sid)}, {"$set": {"revoked": True, "revoked_reason": reason}})

    def revoke_all_for(self, user_id: str, reason: str):
        self.collection.update_many({"user_id": str(user_id)}, {"$set": {"revoked": True, "revoked_reason": reason}})

    def active_for(self, user_id: str | None = None):
        query = {"revoked": False}
        if user_id:
            query["user_id"] = str(user_id)
        return list(self.collection.find(query, {"_id": 0, "refresh_jti": 0}).sort("last_seen", -1))

    def is_idle(self, session_doc) -> bool:
        return auth.now() - dt.datetime.fromisoformat(session_doc["last_seen"]) > auth.SESSION_IDLE_TIMEOUT
