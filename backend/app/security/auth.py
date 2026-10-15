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
AUDIENCE = "periovision-api"
ACCESS_TTL = dt.timedelta(minutes=int(os.getenv("ACCESS_TOKEN_MINUTES", "15")))
REFRESH_TTL = dt.timedelta(days=int(os.getenv("REFRESH_TOKEN_DAYS", "7")))
MFA_TTL = dt.timedelta(minutes=5)
SESSION_IDLE_TIMEOUT = dt.timedelta(minutes=int(os.getenv("SESSION_IDLE_MINUTES", "30")))
BCRYPT_ROUNDS = 12
MIN_PASSWORD_LENGTH = 10

_jwt_keys: dict[str, str] | None = None
_jwt_active_kid: str | None = None


class AuthError(Exception):
    """Raised for any token problem; the message is safe to show to the client."""


def _load_jwt_keys() -> None:
    """Build the signing key ring from the environment.

    JWT_SECRET_KEY            the active signing secret (required outside demo mode)
    JWT_SECRET_KEY_RETIRED    optional "kid:secret,kid:secret" of previous secrets, still
                              accepted for verification but never used to sign

    Tokens carry the key ID in their JOSE header, so the active secret can be replaced
    while sessions signed with the previous one stay valid until they expire, instead of
    logging every user out at the moment of rotation.
    """
    global _jwt_keys, _jwt_active_kid
    secret = os.getenv("JWT_SECRET_KEY")
    if not secret:
        if os.getenv("DB_MODE", "").lower() != "demo":
            raise RuntimeError("JWT_SECRET_KEY must be set in .env outside demo mode.")
        logger.warning("[DEMO MODE] No JWT_SECRET_KEY set; using a random key (logins reset on restart).")
        secret = secrets.token_hex(32)
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET_KEY must be at least 32 characters.")

    active_kid = os.getenv("JWT_ACTIVE_KID", "k1").strip() or "k1"
    keys = {active_kid: secret}
    for part in (os.getenv("JWT_SECRET_KEY_RETIRED") or "").split(","):
        kid, _, value = part.strip().partition(":")
        if not kid or not value:
            continue
        if len(value) < 32:
            raise RuntimeError(f"Retired JWT secret '{kid}' must be at least 32 characters.")
        keys.setdefault(kid, value)
    _jwt_keys, _jwt_active_kid = keys, active_kid


def jwt_secret() -> str:
    """The currently active signing secret."""
    if _jwt_keys is None:
        _load_jwt_keys()
    return _jwt_keys[_jwt_active_kid]


def _secret_for(kid: str | None) -> str:
    if _jwt_keys is None:
        _load_jwt_keys()
    if kid is None:  # token issued before key IDs existed
        return _jwt_keys[_jwt_active_kid]
    try:
        return _jwt_keys[kid]
    except KeyError:
        raise AuthError("Invalid token") from None


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# ---------- passwords ----------
# bcrypt silently truncates its input at 72 bytes, so without pre-hashing any two
# passwords sharing a 72-byte prefix collide ("<72 chars>" + "A" == "<72 chars>" + "B").
# We SHA-256 the password first and base64 the digest (44 ASCII bytes, always under
# the limit), which removes the length ceiling entirely. Hashes made this way carry a
# "pv1." marker; hashes written before this change are still verified the old way, so
# existing accounts keep working and are upgraded on their next successful login.
PREHASH_PREFIX = b"pv1."


def _prehash(password: str) -> bytes:
    """SHA-256 -> base64, so bcrypt never sees more than 44 bytes."""
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> bytes:
    return PREHASH_PREFIX + bcrypt.hashpw(_prehash(password), bcrypt.gensalt(rounds=BCRYPT_ROUNDS))


def verify_password(password: str, hashed: bytes) -> bool:
    try:
        if isinstance(hashed, str):
            hashed = hashed.encode("utf-8")
        if hashed.startswith(PREHASH_PREFIX):
            return bcrypt.checkpw(_prehash(password), hashed[len(PREHASH_PREFIX):])
        # Legacy hash: bcrypt over the raw password, truncated at 72 bytes by bcrypt itself.
        return bcrypt.checkpw(password.encode("utf-8"), hashed)
    except (ValueError, TypeError):
        return False


def needs_rehash(hashed: bytes | str) -> bool:
    """True for legacy hashes, so callers can transparently upgrade them on login."""
    if isinstance(hashed, str):
        hashed = hashed.encode("utf-8")
    return not hashed.startswith(PREHASH_PREFIX)


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
    payload = {**claims, "iss": ISSUER, "aud": AUDIENCE, "iat": issued, "nbf": issued,
               "exp": issued + ttl, "jti": claims.get("jti") or uuid.uuid4().hex}
    secret = jwt_secret()
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM, headers={"kid": _jwt_active_kid})


def decode_token(token: str, expected_type: str) -> dict:
    try:
        # The header is unauthenticated at this point; it only selects which key to
        # verify against, and an unknown key ID is rejected before any claim is read.
        kid = jwt.get_unverified_header(token).get("kid")
    except jwt.InvalidTokenError:
        raise AuthError("Invalid token") from None
    secret = _secret_for(kid)
    try:
        claims = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM], issuer=ISSUER,
                            audience=AUDIENCE,
                            options={"require": ["exp", "iat", "sub", "typ", "jti", "aud"]})
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
