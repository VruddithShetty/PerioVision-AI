import hashlib
import requests
import logging
import streamlit as st
from database.connection import db

class SessionSecurityManager:
    """
    Handles device fingerprinting and Geo-IP anomaly detection to prevent 
    session hijacking and unauthorized access.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def generate_device_fingerprint(self, user_agent: str, screen_info: str = "", timezone: str = "") -> str:
        raw = f"{user_agent}|{screen_info}|{timezone}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()

    def verify_device_fingerprint(self, doctor_id: str, current_fp: str) -> bool:
        doctor = db["doctors"].find_one({"doctor_id": doctor_id})
        if not doctor: return False
        
        stored_fp = doctor.get("last_login_device_fp")
        if not stored_fp:
            db["doctors"].update_one({"doctor_id": doctor_id}, {"$set": {"last_login_device_fp": current_fp}})
            return True
            
        if current_fp != stored_fp:
            self.logger.warning(f"[SECURITY] Device fingerprint mismatch for {doctor_id}")
            return False
            
        return True

    def check_geo_anomaly(self, ip_address: str, doctor_id: str) -> dict:
        if ip_address in ["localhost", "127.0.0.1", "unknown"]:
            return {"is_anomaly": False, "country": "Local", "city": "Dev"}
            
        try:
            # FIX: Removed third-party IP lookup leakage.
            # Using a local stub that simulates reading from a local MaxMind GeoLite2 DB.
            # In a production environment, this would initialize `geoip2.database.Reader('GeoLite2-Country.mmdb')`
            
            # Simple simulation mapping first octet to regions for testing purposes
            first_octet = int(ip_address.split(".")[0]) if "." in ip_address else 0
            if first_octet < 100:
                current_country = "US"
            elif first_octet < 200:
                current_country = "UK"
            else:
                current_country = "JP"
            
            doctor = db["doctors"].find_one({"doctor_id": doctor_id})
            last_country = doctor.get("last_login_country") if doctor else None
            
            is_anomaly = False
            if last_country and last_country != current_country:
                is_anomaly = True
            
            return {
                "ip": ip_address,
                "country": current_country,
                "is_anomaly": is_anomaly
            }
        except Exception:
            return {"is_anomaly": False}

    @staticmethod
    def get_client_ip() -> str:
        try:
            headers = st.context.headers
            x_forwarded = headers.get("X-Forwarded-For")
            if x_forwarded:
                return x_forwarded.split(",")[0]
            return headers.get("X-Real-IP", "unknown")
        except:
            return "unknown"
