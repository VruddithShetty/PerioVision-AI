import os
import base64
import logging
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from dotenv import load_dotenv

load_dotenv()

class PHIEncryptor:
    """
    Handles HIPAA-compliant field-level encryption for MongoDB.
    Uses AES-256-GCM for primary encryption and HMAC-SHA256 blind indexes for searchable fields.
    """
    
    def __init__(self, key: str = None):
        from security.secrets import get_secret
        if key is None:
            key = get_secret("FIELD_ENCRYPTION_KEY")
        if not key:
            raise ValueError("CRITICAL SECURITY ERROR: FIELD_ENCRYPTION_KEY is missing.")
        
        if isinstance(key, str):
            try:
                self.key_bytes = bytes.fromhex(key)
            except ValueError:
                try:
                    self.key_bytes = base64.urlsafe_b64decode(key)
                except Exception:
                    self.key_bytes = key.encode()
        elif isinstance(key, bytes):
            self.key_bytes = key
        else:
            self.key_bytes = str(key).encode()

        import hashlib
        if len(self.key_bytes) != 32:
            self.key_bytes = hashlib.sha256(self.key_bytes).digest()

        self.aesgcm = AESGCM(self.key_bytes)
        fernet_key = base64.urlsafe_b64encode(self.key_bytes)
        self.fernet = Fernet(fernet_key)

    def encrypt_random(self, data: str) -> str:
        nonce = os.urandom(12)
        ct = self.aesgcm.encrypt(nonce, data.encode(), None)
        return base64.b64encode(nonce + ct).decode()

    def decrypt_random(self, token: str) -> str:
        data = base64.b64decode(token)
        nonce = data[:12]
        ct = data[12:]
        return self.aesgcm.decrypt(nonce, ct, None).decode()

    def encrypt_deterministic(self, data: str) -> str:
        import hmac
        import hashlib
        nonce = hmac.new(self.key_bytes, str(data).encode(), hashlib.sha256).digest()[:12]
        ct = self.aesgcm.encrypt(nonce, str(data).encode(), None)
        return base64.b64encode(nonce + ct).decode()

    def decrypt_deterministic(self, token: str) -> str:
        return self.decrypt_random(token)

    def get_blind_index(self, data: str) -> str:
        import hmac
        import hashlib
        # Normalize: lower and strip whitespace to ensure stable indexing
        normalized = str(data).strip().lower()
        h = hmac.new(self.key_bytes, normalized.encode(), hashlib.sha256)
        return base64.b64encode(h.digest()).decode()

    def encrypt_patient_record(self, doc: dict) -> dict:
        """Encrypts sensitive fields using AES-GCM and generates blind indexes for search."""
        for field in ["patient_name", "contact_number", "notes"]:
            if field in doc and doc[field]:
                str_val = str(doc[field])
                if field in ["patient_name", "contact_number"]:
                    doc[f"{field}_idx"] = self.get_blind_index(str_val)
                doc[field] = self.encrypt_random(str_val)
                
        return doc

    def decrypt_patient_record(self, doc: dict) -> dict:
        if not doc: return None
        for field in ["patient_name", "contact_number", "notes"]:
            if field in doc and doc[field]:
                val = doc[field]
                is_ciphertext = False
                if isinstance(val, str) and len(val) >= 28:
                    try:
                        base64.b64decode(val, validate=True)
                        is_ciphertext = True
                    except Exception:
                        pass
                if is_ciphertext:
                    try:
                        doc[field] = self.decrypt_random(val)
                    except Exception as e:
                        try:
                            doc[field] = self.decrypt_deterministic(val)
                        except Exception:
                            raise e
                        
        # Strip indexes from output
        doc.pop("patient_name_idx", None)
        doc.pop("contact_number_idx", None)
        return doc

