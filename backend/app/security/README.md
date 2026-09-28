# app/security

Security controls, one file per concern: `crypto.py` (AES-256-GCM with key IDs and rotation), `auth.py` (bcrypt, JWT access/refresh, TOTP MFA), `rbac.py` (4 roles, permission matrix), `zero_trust.py` (per-request verification, deny by default), `audit_log.py` (hash chain + anchored Merkle roots), `model_signing.py` (RSA-PSS), `upload_guard.py`, `adversarial.py`, `honeypot.py` (decoy records), `secrets.py` (optional AWS Secrets Manager). See `docs/SECURITY.md`.
