"""Authentication primitives: bcrypt passwords, JWT access/refresh tokens, sessions, TOTP MFA.

Token design
* Access token: HS256 JWT, 15 minutes, carries user id, session id (sid), a
  device fingerprint hash (fp) and a unique jti. The role inside it is only a
  UI hint; the Zero Trust guard always re-reads the role from the database.
* Refresh token: HS256 JWT, 7 days, sent as an httpOnly SameSite=Strict cookie.
  Every refresh rotates it; presenting an old refresh token again is treated as
  theft and revokes the whole session.
* MFA token: 5-minute JWT issued after a correct password when TOTP is enabled;
  it can only be exchanged at /api/auth/mfa for real tokens.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import io
import logging
import os
import secrets
import uuid

import bcrypt
import jwt
import pyotp

logger = logging.getLogger(__name__)

JWT_ALGORITHM = "HS256"
ISSUER = "periovision-ai"
ACCESS_TTL = dt.timedelta(minutes=int(os.getenv("ACCESS_TOKEN_MINUTES", "15")))
REFRESH_TTL = dt.timedelta(days=int(os.getenv("REFRESH_TOKEN_DAYS", "7")))
MFA_TTL = dt.timedelta(minutes=5)
SESSION_IDLE_TIMEOUT = dt.timedelta(minutes=int(os.getenv("SESSION_IDLE_MINUTES", "30")))
BCRYPT_ROUNDS = 12
MIN_PASSWORD_LENGTH = 10

_jwt_secret: str | None = None


class AuthError(Exception):
    """Raised for any token problem; the message is safe to show to the client."""


def jwt_secret() -> str:
    global _jwt_secret
    if _jwt_secret is None:
        secret = os.getenv("JWT_SECRET_KEY")
        if not secret:
            if os.getenv("DB_MODE", "").lower() != "demo":
                raise RuntimeError("JWT_SECRET_KEY must be set in .env outside demo mode.")
            logger.warning("[DEMO MODE] No JWT_SECRET_KEY set; using a random key (logins reset on restart).")
            secret = secrets.token_hex(32)
        if len(secret) < 32:
            raise RuntimeError("JWT_SECRET_KEY must be at least 32 characters.")
        _jwt_secret = secret
    return _jwt_secret


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# ---------- passwords ----------
def hash_password(password: str) -> bytes:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS))


def verify_password(password: str, hashed: bytes) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed)
    except (ValueError, TypeError):
        return False


def password_problems(password: str) -> list[str]:
    problems = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"at least {MIN_PASSWORD_LENGTH} characters")
    if password.lower() == password or password.upper() == password:
        problems.append("both upper- and lower-case letters")
    if not any(c.isdigit() for c in password):
        problems.append("a digit")
    return problems


# ---------- device fingerprint ----------
def device_fingerprint(user_agent: str | None) -> str:
    return hashlib.sha256((user_agent or "").encode()).hexdigest()[:32]


# ---------- JWT ----------
def _encode(claims: dict, ttl: dt.timedelta) -> str:
    issued = now()
    payload = {**claims, "iss": ISSUER, "iat": issued, "nbf": issued, "exp": issued + ttl,
               "jti": claims.get("jti") or uuid.uuid4().hex}
    return jwt.encode(payload, jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_token(token: str, expected_type: str) -> dict:
    try:
        claims = jwt.decode(token, jwt_secret(), algorithms=[JWT_ALGORITHM], issuer=ISSUER,
                            options={"require": ["exp", "iat", "sub", "typ", "jti"]})
    except jwt.ExpiredSignatureError:
        raise AuthError("Token expired") from None
    except jwt.InvalidTokenError:
        raise AuthError("Invalid token") from None
    if claims.get("typ") != expected_type:
        raise AuthError("Wrong token type")
    return claims


def issue_access_token(user_id: str, role: str, sid: str, fp: str) -> str:
    return _encode({"sub": user_id, "role": role, "sid": sid, "fp": fp, "typ": "access"}, ACCESS_TTL)


def issue_refresh_token(user_id: str, sid: str, jti: str) -> str:
    return _encode({"sub": user_id, "sid": sid, "typ": "refresh", "jti": jti}, REFRESH_TTL)


def issue_mfa_token(user_id: str, fp: str) -> str:
    return _encode({"sub": user_id, "fp": fp, "typ": "mfa"}, MFA_TTL)


# ---------- TOTP ----------
def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_provisioning(secret: str, email: str) -> dict:
    """otpauth:// URI plus a QR code PNG (base64) for authenticator apps."""
    import qrcode

    uri = pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="PerioVision AI")
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return {"otpauth_uri": uri, "qr_png_base64": base64.b64encode(buf.getvalue()).decode()}


def verify_totp(secret: str, code: str, last_used_step: int | None) -> int | None:
    """Return the matched time step (to store, blocking replay) or None if the code is wrong or reused."""
    if not code or not str(code).isdigit():
        return None
    totp = pyotp.TOTP(secret)
    current = int(now().timestamp()) // totp.interval
    for step in (current - 1, current, current + 1):  # allow 30 s clock drift either way
        if last_used_step is not None and step <= last_used_step:
            continue
        if secrets.compare_digest(totp.at(step * totp.interval), str(code)):
            return step
    return None
