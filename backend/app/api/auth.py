"""Authentication routes: password login, TOTP MFA step, token refresh, logout, MFA enrolment, sessions."""
from __future__ import annotations

from flask import Blueprint, g, make_response, request
from pydantic import ValidationError

from app.api._common import fail, ok, validation_error
from app.extensions import limiter
from app.schemas import LoginIn, MfaIn, TotpCodeIn
from app.security import auth
from app.security.audit_log import audit, hash_ip
from app.security.zero_trust import public, secured
from app.services import container

bp = Blueprint("auth", __name__)
REFRESH_COOKIE = "pv_refresh"


def _issue_tokens(user: dict, status: int = 200):
    fp = auth.device_fingerprint(request.headers.get("User-Agent"))
    sid, refresh_jti = container.session_store().create(user["doctor_id"], fp, hash_ip(request.remote_addr))
    access = auth.issue_access_token(user["doctor_id"], user["role"], sid, fp)
    body = {"access_token": access, "token_type": "Bearer", "expires_in": int(auth.ACCESS_TTL.total_seconds()),
            "user": {k: user.get(k) for k in ("doctor_id", "name", "email", "role", "mfa_enabled", "clinic_name")}}
    resp, code = ok(body, status)
    resp = make_response(resp, code)
    _set_refresh_cookie(resp, auth.issue_refresh_token(user["doctor_id"], sid, refresh_jti))
    audit().record("LOGIN_SUCCESS", actor=user["doctor_id"], details={"ip": hash_ip(request.remote_addr)})
    return resp


def _set_refresh_cookie(resp, token: str):
    resp.set_cookie(REFRESH_COOKIE, token, max_age=int(auth.REFRESH_TTL.total_seconds()), httponly=True,
                    secure=request.is_secure, samesite="Strict", path="/api/auth")


@bp.post("/api/auth/login")
@public
@limiter.limit("5 per minute")
def login():
    try:
        body = LoginIn.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return validation_error(exc)
    users = container.doctor_manager()
    try:
        user = users.authenticate_doctor(body.email, body.password)
    except PermissionError as exc:
        audit().record("LOGIN_LOCKED", outcome="denied", details={"ip": hash_ip(request.remote_addr)})
        return fail(423, str(exc))
    if not user:
        audit().record("LOGIN_FAILED", outcome="denied", details={"ip": hash_ip(request.remote_addr)})
        return fail(401, "Invalid email or password.")
    if user.get("mfa_enabled"):
        fp = auth.device_fingerprint(request.headers.get("User-Agent"))
        return ok({"mfa_required": True, "mfa_token": auth.issue_mfa_token(user["doctor_id"], fp)})
    return _issue_tokens(user)


@bp.post("/api/auth/mfa")
@public
@limiter.limit("5 per minute")
def mfa_step():
    try:
        body = MfaIn.model_validate(request.get_json(silent=True) or {})
        claims = auth.decode_token(body.mfa_token, "mfa")
    except ValidationError as exc:
        return validation_error(exc)
    except auth.AuthError as exc:
        return fail(401, str(exc))
    if claims.get("fp") != auth.device_fingerprint(request.headers.get("User-Agent")):
        return fail(401, "Device check failed.")
    users = container.doctor_manager()
    if not users.verify_totp(claims["sub"], body.code):
        audit().record("MFA_FAILED", outcome="denied", actor=claims["sub"])
        return fail(401, "Invalid or already-used code.")
    user = users.get_doctor(claims["sub"])
    if not users.is_usable(users.collection.find_one({"doctor_id": claims["sub"]})):
        return fail(403, "Account is disabled or locked.")
    return _issue_tokens(user)


@bp.post("/api/auth/refresh")
@public
@limiter.limit("30 per minute")
def refresh():
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        return fail(401, "No refresh token.")
    try:
        claims = auth.decode_token(token, "refresh")
    except auth.AuthError as exc:
        return fail(401, str(exc))
    sessions, users = container.session_store(), container.doctor_manager()
    session = sessions.get(claims["sid"])
    fp = auth.device_fingerprint(request.headers.get("User-Agent"))
    if not session or session.get("revoked") or session.get("fp") != fp:
        return fail(401, "Session is not active.")
    new_jti = sessions.rotate_refresh(claims["sid"], claims["jti"])
    if new_jti is None:
        audit().record("REFRESH_TOKEN_REUSE", outcome="denied", actor=claims["sub"],
                       details={"action": "session revoked"})
        return fail(401, "Refresh token was already used; the session has been revoked.")
    raw = users.collection.find_one({"doctor_id": claims["sub"]})
    if not users.is_usable(raw):
        sessions.revoke(claims["sid"], reason="account_blocked")
        return fail(403, "Account is disabled or locked.")
    user = users.get_doctor(claims["sub"])
    access = auth.issue_access_token(user["doctor_id"], user["role"], claims["sid"], fp)
    resp, code = ok({"access_token": access, "token_type": "Bearer",
                     "expires_in": int(auth.ACCESS_TTL.total_seconds())})
    resp = make_response(resp, code)
    _set_refresh_cookie(resp, auth.issue_refresh_token(user["doctor_id"], claims["sid"], new_jti))
    return resp


@bp.post("/api/auth/logout")
@secured("self:manage")
def logout():
    container.session_store().revoke(g.session["sid"], reason="logout")
    audit().record("LOGOUT", actor=g.user["id"])
    resp, code = ok({"logged_out": True})
    resp = make_response(resp, code)
    resp.delete_cookie(REFRESH_COOKIE, path="/api/auth")
    return resp


@bp.get("/api/auth/me")
@secured("self:manage")
def me():
    from app.security.rbac import PERMISSIONS

    user = container.doctor_manager().get_doctor(g.user["id"])
    user["permissions"] = sorted(p for p, roles in PERMISSIONS.items() if g.user["role"] in roles)
    return ok(user)


@bp.post("/api/auth/mfa/enroll")
@secured("self:manage")
def mfa_enroll():
    data = container.doctor_manager().start_mfa_enrolment(g.user["id"])
    audit().record("MFA_ENROLMENT_STARTED", actor=g.user["id"])
    return ok(data)


@bp.post("/api/auth/mfa/confirm")
@secured("self:manage")
def mfa_confirm():
    try:
        body = TotpCodeIn.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return validation_error(exc)
    if not container.doctor_manager().confirm_mfa_enrolment(g.user["id"], body.code):
        return fail(400, "That code did not match. Check the time on your phone and try again.")
    audit().record("MFA_ENABLED", actor=g.user["id"])
    return ok({"mfa_enabled": True})


@bp.post("/api/auth/mfa/disable")
@secured("self:manage")
def mfa_disable():
    try:
        body = TotpCodeIn.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return validation_error(exc)
    users = container.doctor_manager()
    if not users.verify_totp(g.user["id"], body.code):
        return fail(400, "Invalid code.")
    users.disable_mfa(g.user["id"])
    audit().record("MFA_DISABLED", actor=g.user["id"])
    return ok({"mfa_enabled": False})


@bp.get("/api/auth/sessions")
@secured("self:manage")
def my_sessions():
    sessions = container.session_store().active_for(g.user["id"])
    for s in sessions:
        s["current"] = s["sid"] == g.session["sid"]
        s["sid"] = s["sid"][:8] + "..."
    return ok(sessions)
