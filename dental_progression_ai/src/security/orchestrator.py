import logging
from database.audit import AuditLogger
from database.doctors import DoctorManager
from database.notifications import NotificationManager

class SecurityOrchestrator:
    def __init__(self):
        self.audit_log = AuditLogger()
        self.notif_mgr = NotificationManager()
        self.doctor_mgr = DoctorManager()
        self.logger = logging.getLogger(__name__)

    def trigger_incident_response(self, event_type: str, doctor_id: str, details: str):
        self.logger.critical(f"[INCIDENT RESPONSE] {event_type} for Dr. {doctor_id}")
        
        if event_type == "HONEYPOT_BREACH":
            self.doctor_mgr.lock_account(doctor_id, minutes=525600)
            self.audit_log.log(doctor_id, "INCIDENT_PLAYBOOK_EXEC", details="HONEYPOT_BREACH -> Permanent Lock", level="CRITICAL")
            self.notif_mgr.create_notification("admin", "🚨 CRITICAL: Honeypot Breach", f"Dr {doctor_id} locked.", "HIGH")

        elif event_type == "ADVERSARIAL_BURST":
            self.doctor_mgr.lock_account(doctor_id, minutes=60)
            self.audit_log.log(doctor_id, "INCIDENT_PLAYBOOK_EXEC", details="ADVERSARIAL_BURST -> 1hr Lock", level="WARNING")

        elif event_type == "CHAIN_TAMPERING":
            self.notif_mgr.create_notification("admin", "🚨 SYSTEM INTEGRITY ALERT", "Merkle chain mismatch.", "CRITICAL")
            
    def monitor_events(self, event_list):
        for event in event_list:
            if event.get("level") == "CRITICAL":
                self.trigger_incident_response(event["action"], event["doctor_id"], event.get("details", ""))
