import datetime
from database.connection import db

class ThreatIntelligenceCollector:
    def __init__(self):
        self.logs = db["audit_logs"]

    def get_security_metrics(self, days=7) -> dict:
        now = datetime.datetime.now(datetime.timezone.utc)
        since = (now - datetime.timedelta(days=days)).isoformat()
        
        adv_count = self.logs.count_documents({"action": "ADVERSARIAL_DETECTED", "timestamp": {"$gte": since}})
        honeypot_count = self.logs.count_documents({"action": "HONEYPOT_BREACH", "timestamp": {"$gte": since}})
        failed_logins = self.logs.count_documents({"action": "LOGIN_FAILED", "timestamp": {"$gte": since}})
        merkle_roots = db["merkle_roots"].count_documents({"timestamp": {"$gte": since}})
        
        return {
            "adversarial_hits": adv_count,
            "honeypot_breaches": honeypot_count,
            "failed_logins": failed_logins,
            "verified_states": merkle_roots,
            "total_threat_events": adv_count + honeypot_count + failed_logins
        }

    def get_risk_score(self, doctor_id: str) -> float:
        recent_count = self.logs.count_documents({
            "doctor_id": str(doctor_id),
            "metadata.level": {"$in": ["WARNING", "CRITICAL"]}
        })
        return min(1.0, recent_count / 5.0)
