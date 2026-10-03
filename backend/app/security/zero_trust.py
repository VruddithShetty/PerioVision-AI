"""Zero Trust request guard (NIST SP 800-207 style): verify every request, deny by default.

For every protected request the guard re-checks, in order:
  1. token   - a valid, unexpired access JWT from the Authorization header
  2. session - the server-side session exists, is not revoked or idle, and the
               device fingerprint matches the one bound at login
  3. user    - the account exists, is active and not locked; the role is read
               from the database, never trusted from the token
  4. policy  - the role holds the permission the route requires (RBAC matrix); roles listed in
               REQUIRE_MFA_ROLES must have MFA enabled for anything beyond their own account
Any failure stops the request and is written to the audit log.

`enforce_deny_by_default` (installed by the app factory) refuses any route that
was registered without `@secured(...)` or `@public`, so a forgotten decorator
fails closed instead of open.
"""
from __future__ import annotations

from functools import wraps

from flask import g, jsonify, request

from app import config
from app.security import auth
from app.security.audit_log import audit, hash_ip
from app.security.rbac import has_permission, normalize_role


def _deny(status: int, message: str, action: str, actor: str | None = None, **details):
    audit().record(action, outcome="denied", actor=actor, resource=request.path,
                   details={"reason": message, "method": request.method, "ip": hash_ip(request.remote_addr), **details})
    return jsonify({"data": None, "meta": {}, "error": {"code": status, "message": message, "details": None},
                    "mode": config.APP_MODE}), status


def _bearer_token() -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:].strip() or None
    return None


def verify_request(permission: str):
    """Run all four checks. Returns (user, session) or a Flask error response."""
    from app.services import container

    token = _bearer_token()
    if not token:
        return _deny(401, "Authentication required", "AUTH_MISSING")
    try:
        claims = auth.decode_token(token, "access")
    except auth.AuthError as exc:
        return _deny(401, str(exc), "AUTH_INVALID_TOKEN")

    user_id = claims["sub"]
    sessions = container.session_store()
    session = sessions.get(claims.get("sid"))
    if not session or session.get("revoked") or session.get("user_id") != user_id:
        return _deny(401, "Session is not active", "AUTH_SESSION_REJECTED", actor=user_id)
    if sessions.is_idle(session):
        sessions.revoke(session["sid"], reason="idle_timeout")
        return _deny(401, "Session timed out", "AUTH_SESSION_IDLE", actor=user_id)
    fp = auth.device_fingerprint(request.headers.get("User-Agent"))
    if claims.get("fp") != fp or session.get("fp") != fp:
        sessions.revoke(session["sid"], reason="device_mismatch")
        return _deny(401, "Device check failed", "AUTH_DEVICE_MISMATCH", actor=user_id)

    users = container.doctor_manager()
    raw_user = users.collection.find_one({"doctor_id": user_id})
    if not users.is_usable(raw_user):
        return _deny(403, "Account is disabled or locked", "AUTH_ACCOUNT_BLOCKED", actor=user_id)
    role = normalize_role(raw_user.get("role"))

    if role in config.REQUIRE_MFA_ROLES and not raw_user.get("mfa_enabled") and permission != "self:manage":
        return _deny(403, "Multi-factor authentication must be set up before using this account. "
                          "Open Security center to enrol an authenticator app.", "AUTH_MFA_ENROLMENT_REQUIRED",
                     actor=user_id, role=role)
    if not has_permission(role, permission):
        return _deny(403, "You do not have permission for this action", "PERMISSION_DENIED",
                     actor=user_id, permission=permission, role=role)

    sessions.touch(session["sid"])
    user = {"id": user_id, "role": role, "name": raw_user.get("name"), "email": raw_user.get("email")}
    return user, session


def secured(permission: str):
    """Route decorator: full Zero Trust verification plus an RBAC permission check."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            result = verify_request(permission)
            if not isinstance(result, tuple) or len(result) != 2 or not isinstance(result[0], dict):
                return result
            g.user, g.session = result
            return f(*args, **kwargs)
        wrapper.zero_trust_permission = permission
        return wrapper
    return decorator


def public(f):
    """Mark a route as intentionally reachable without authentication."""
    f.zero_trust_public = True
    return f


def enforce_deny_by_default(app):
    @app.before_request
    def _check_route_is_classified():
        if request.endpoint is None or request.endpoint == "static":
            return None
        if request.method == "OPTIONS":
            return None  # CORS preflight; the real request is still checked
        view = app.view_functions.get(request.endpoint)
        if view is not None and (getattr(view, "zero_trust_public", False)
                                 or getattr(view, "zero_trust_permission", None)):
            return None
        return _deny(403, "Route is not classified; denied by default", "POLICY_UNCLASSIFIED_ROUTE")
