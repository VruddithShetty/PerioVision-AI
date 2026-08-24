import json
import hashlib
import datetime
from database.connection import db

class MerkleAuditLog:
    """
    Implements a tamper-evident audit trail using a chained hash sequence 
    and Merkle trees for global integrity verification.
    """
    
    def __init__(self):
        self.logs = db["audit_logs"]
        self.roots = db["merkle_roots"]

    def _hash_entry(self, entry_dict: dict) -> str:
        if '_id' in entry_dict:
            entry_data = {k: v for k, v in entry_dict.items() if k != '_id'}
        else:
            entry_data = entry_dict
        canonical_json = json.dumps(entry_data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()

    def _compute_merkle_root(self, leaf_hashes: list) -> str:
        if not leaf_hashes:
            return hashlib.sha256(b"").hexdigest()
        current_layer = leaf_hashes
        while len(current_layer) > 1:
            next_layer = []
            if len(current_layer) % 2 != 0:
                current_layer.append(current_layer[-1])
            for i in range(0, len(current_layer), 2):
                combined = current_layer[i] + current_layer[i+1]
                next_layer.append(hashlib.sha256(combined.encode('utf-8')).hexdigest())
            current_layer = next_layer
        return current_layer[0]

    def log_action(self, doctor_id: str, action: str, entity_id: str, metadata: dict) -> str:
        last_entry = self.logs.find_one(sort=[("sequence_number", -1)])
        seq = (last_entry["sequence_number"] + 1) if last_entry else 0
        prev_hash = last_entry["entry_hash"] if last_entry else "GENESIS"
        entry = {
            "doctor_id": str(doctor_id),
            "action": action,
            "entity_id": str(entity_id),
            "metadata": metadata,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "sequence_number": seq,
            "prev_hash": prev_hash
        }
        entry["entry_hash"] = self._hash_entry(entry)
        self.logs.insert_one(entry)
        return entry["entry_hash"]

    def publish_root(self, doctor_id: str) -> str:
        import os
        
        all_logs = list(self.logs.find().sort("sequence_number", 1))
        leaf_hashes = [log["entry_hash"] for log in all_logs]
        root_hash = self._compute_merkle_root(leaf_hashes)
        
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        self.roots.insert_one({
            "root_hash": root_hash,
            "timestamp": timestamp,
            "total_entries": len(all_logs),
            "published_by": str(doctor_id)
        })
        
        # FIX: External anchor (write-only append log outside MongoDB)
        anchor_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
        os.makedirs(anchor_dir, exist_ok=True)
        anchor_file = os.path.join(anchor_dir, "merkle_anchor.log")
        try:
            with open(anchor_file, "a") as f:
                f.write(f"{timestamp} | {root_hash} | {len(all_logs)}\n")
        except IOError:
            pass # Depending on environment, might not have write access.
            
        return root_hash

    def verify_chain_integrity(self) -> dict:
        import os
        
        all_logs = list(self.logs.find().sort("sequence_number", 1))
        if not all_logs:
            return {"chain_intact": True, "entries_verified": 0}
        broken_at = None
        for i in range(1, len(all_logs)):
            current = all_logs[i]
            previous = all_logs[i-1]
            if current["prev_hash"] != previous["entry_hash"]:
                broken_at = current["sequence_number"]
                break
            stored_hash = current["entry_hash"]
            actual_hash = self._hash_entry({k: v for k, v in current.items() if k != "entry_hash"})
            if stored_hash != actual_hash:
                broken_at = current["sequence_number"]
                break
                
        current_root = self._compute_merkle_root([log["entry_hash"] for log in all_logs])
        
        # Read from external anchor log to verify
        matches_published = True
        anchor_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
        anchor_file = os.path.join(anchor_dir, "merkle_anchor.log")
        if os.path.exists(anchor_file):
            try:
                with open(anchor_file, "r") as f:
                    lines = f.readlines()
                    if lines:
                        last_line = lines[-1].strip()
                        parts = last_line.split(" | ")
                        if len(parts) >= 2:
                            anchored_root = parts[1]
                            if current_root != anchored_root:
                                matches_published = False
                                broken_at = broken_at if broken_at is not None else "TAMPERED_ROOT"
            except IOError:
                pass
        else:
            # Fallback to DB if anchor not found (e.g. fresh start)
            latest_root_doc = self.roots.find_one(sort=[("timestamp", -1)])
            matches_published = (current_root == latest_root_doc["root_hash"]) if latest_root_doc else True
            
        return {
            "chain_intact": broken_at is None,
            "broken_at_sequence": broken_at,
            "entries_verified": len(all_logs),
            "current_root": current_root,
            "matches_published_root": matches_published
        }
