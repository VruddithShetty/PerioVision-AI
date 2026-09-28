import os
import sys

# Add src to path to allow importing modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))  # backend/

from app.models.connection import db
from app.security.crypto import PHIEncryptor

def migrate_encryption():
    encryptor = PHIEncryptor()
    collection = db["patients"]
    
    def decrypt_deterministic_legacy(token, key_bytes):
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend
        import base64
        
        try:
            ct = base64.b64decode(token)
            iv = key_bytes[:16]
            cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(iv), backend=default_backend())
            decryptor = cipher.decryptor()
            padded_data = decryptor.update(ct) + decryptor.finalize()
            pad_len = padded_data[-1]
            if pad_len < 1 or pad_len > 16:
                return token
            return padded_data[:-pad_len].decode()
        except:
            return token
            
    print("Starting encryption migration from deterministic CBC to blind index...")
    
    patients = list(collection.find({}))
    migrated_count = 0
    
    for doc in patients:
        needs_update = False
        update_fields = {}
        
        for field in ["patient_name", "contact_number"]:
            if field in doc and doc[field]:
                # Try to decrypt legacy
                val = doc[field]
                is_legacy = False
                
                # Check if it's already randomized (length > 28 and base64 decodable)
                try:
                    raw = base64.b64decode(val)
                    if len(raw) > 12: # Check if it could be new format
                        encryptor.decrypt_random(val)
                        continue # Successfully decrypted random, already migrated
                except:
                    pass
                
                pt = decrypt_deterministic_legacy(val, encryptor.key_bytes)
                if pt != val:
                    # It was legacy deterministic!
                    needs_update = True
                    update_fields[field] = encryptor.encrypt_random(pt)
                    update_fields[f"{field}_idx"] = encryptor.get_blind_index(pt)
                    
                    # Store backup for rollback
                    update_fields[f"{field}_backup_legacy"] = val
        
        if needs_update:
            collection.update_one({"_id": doc["_id"]}, {"$set": update_fields})
            migrated_count += 1
            
    print(f"Migrated {migrated_count} records.")

def rollback_migration():
    encryptor = PHIEncryptor()
    collection = db["patients"]
    patients = list(collection.find({}))
    rolled_back = 0
    for doc in patients:
        updates = {}
        for field in ["patient_name", "contact_number"]:
            if f"{field}_backup_legacy" in doc:
                updates[field] = doc[f"{field}_backup_legacy"]
                # Can unset index and backup if desired
        if updates:
            collection.update_one({"_id": doc["_id"]}, {"$set": updates})
            rolled_back += 1
    print(f"Rolled back {rolled_back} records.")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--rollback":
        rollback_migration()
    else:
        migrate_encryption()
