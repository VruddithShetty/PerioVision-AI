import os
from dotenv import load_dotenv

class ProductionReadinessChecker:
    def __init__(self):
        load_dotenv()

    def run_preflight_check(self) -> dict:
        results = {
            "secrets_hardening": self._check_secrets(),
            "encryption_keys": self._check_encryption(),
            "database_security": self._check_db(),
            "compliance_indicators": self._check_compliance()
        }
        is_ready = all(r["status"] == "PASS" for r in results.values())
        return {"is_ready": is_ready, "details": results}

    def _check_secrets(self):
        sk = os.getenv("SECRET_KEY", "")
        if len(sk) < 32 or sk == "your_secret_key_here":
            return {"status": "FAIL", "reason": "Weak SECRET_KEY"}
        return {"status": "PASS"}

    def _check_encryption(self):
        if not os.getenv("FIELD_ENCRYPTION_KEY"):
            return {"status": "FAIL", "reason": "Missing encryption key"}
        return {"status": "PASS"}

    def _check_db(self):
        uri = os.getenv("MONGO_URI", "")
        if "localhost" not in uri and "tls=true" not in uri.lower():
            return {"status": "FAIL", "reason": "Missing TLS in production"}
        return {"status": "PASS"}

    def _check_compliance(self):
        from database.connection import db
        if not db["patients"].find_one({"is_honeypot": True}):
            return {"status": "FAIL", "reason": "Honeypot inactive"}
        return {"status": "PASS"}
