from functools import wraps
from flask import request, session, current_app
from security.merkle import MerkleAuditLog
import traceback
import logging

logger = logging.getLogger("AuditMiddleware")
audit_log = MerkleAuditLog()

def audit_action(action_name):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            doctor_id = session.get("doctor_id", "anonymous")
            ip_address = request.remote_addr
            user_agent = request.headers.get("User-Agent", "")
            
            # Extract resource_id from kwargs if any, otherwise it's just the URL
            resource_id = str(kwargs) if kwargs else request.path
            
            outcome = "success"
            error_msg = ""
            
            try:
                response = f(*args, **kwargs)
                # If response is a tuple (like from jsonify(...), 400), check status
                if isinstance(response, tuple):
                    if len(response) > 1 and int(response[1]) >= 400:
                        outcome = "failure"
                return response
            except Exception as e:
                outcome = "failure"
                error_msg = str(e)
                logger.error(f"Action failed: {traceback.format_exc()}")
                raise
            finally:
                metadata = {
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                    "outcome": outcome,
                    "error": error_msg
                }
                if request.is_json:
                    try:
                        req_json = request.json
                        if req_json and isinstance(req_json, dict) and "email" in req_json:
                            metadata["email"] = req_json["email"]
                    except Exception:
                        pass
                try:
                    audit_log.log_action(
                        doctor_id=doctor_id,
                        action=action_name,
                        entity_id=resource_id,
                        metadata=metadata
                    )
                except Exception as e:
                    logger.error(f"Failed to write audit log: {str(e)}")
                    
        return decorated_function
    return decorator
