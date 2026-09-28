"""Thin wrapper over the tamper-evident audit log (kept for modules that use AuditLogger)."""
from app.security.audit_log import audit


class AuditLogger:
    def log(self, doctor_id: str, action: str, details: str = "", patient_id: str = None, level: str = "INFO"):
        return audit().record(action, actor=doctor_id, resource=patient_id,
                              details={"level": level, "details": details})

    def get_recent(self, limit=100):
        return audit().recent(limit)

    def verify_integrity(self):
        return audit().verify_chain_integrity()

    def publish_root(self, doctor_id):
        return audit().publish_root(actor=doctor_id)
