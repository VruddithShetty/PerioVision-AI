# OWASP Top 10 (2021) review

_Reviewed 2026-10-18 against the code on `main`. Every control names the file that implements it and the test that
fails if it breaks. Controls are aligned with OWASP guidance; the system has not had an external penetration test._

| # | Category | Status |
|---|---|---|
| A01 | Broken Access Control | covered |
| A02 | Cryptographic Failures | covered (one gap fixed 2026-10-18) |
| A03 | Injection | covered (one gap fixed 2026-10-18) |
| A04 | Insecure Design | covered |
| A05 | Security Misconfiguration | covered (two gaps fixed 2026-10-15/18) |
| A06 | Vulnerable and Outdated Components | covered, one accepted risk (PyTorch) |
| A07 | Identification and Authentication Failures | covered (password minimum raised 2026-10-18) |
| A08 | Software and Data Integrity Failures | covered |
| A09 | Security Logging and Monitoring Failures | covered |
| A10 | Server-Side Request Forgery | not applicable (no server-side URL fetching) |

## A01 Broken Access Control

- **Deny by default:** every route needs an explicit permission; a route without one is refused
  (`security/zero_trust.py: enforce_deny_by_default`). Test: `tests/test_api.py` (deny by default).
- **Role-based access:** four roles with an explicit permission matrix (`security/rbac.py`, `@secured(...)`); auditors
  never see patient data, admins make no clinical decisions, only dentists sign off. Tests: `tests/test_api.py` (RBAC
  matrix), `tests/test_attacks.py::test_technician_cannot_sign_off_even_with_a_real_analysis`.
- **Object-level checks (IDOR):** a user sees only patients they own or are on the care team for
  (`rbac.can_access_patient`). Test: patient isolation in `tests/test_api.py`.
- **Decoy records** revoke the session and lock the account when opened (`security/honeypot.py`). Test: honeypot test.
- **CORS** allow-list only (`CORS_ORIGINS`); the frontend is served from the same origin as `/api`.

## A02 Cryptographic Failures

- Patient fields and every stored file encrypted with **AES-256-GCM**, fresh 96-bit random nonce, key IDs and a key
  ring with rotation (`security/crypto.py`, `scripts/rotate_keys.py`). Tests: `tests/test_crypto.py` (200 distinct
  nonces, tamper detection, associated-data binding, rotation, weak-key refusal).
- Passwords hashed with **bcrypt** (cost 12). Test: `test_passwords_are_stored_as_bcrypt_hashes`.
- Separate HKDF-derived keys for blind indexes, pseudonyms and decoy tags.
- **TLS** terminated at a reverse proxy; HSTS and the `Secure` cookie flag are sent on HTTPS.
- **Fixed 2026-10-18:** behind a proxy the app saw plain HTTP, so the refresh cookie lacked `Secure` and HSTS was
  not sent. `TRUST_PROXY_HOPS` (default 0) now makes the app honour the proxy's `X-Forwarded-Proto/-For` from that many
  trusted proxies only; with 0, client-supplied forwarded headers are ignored and cannot be spoofed.
  Test: `tests/test_security_fixes.py::test_forwarded_https_is_trusted_only_when_configured`.

## A03 Injection

- **NoSQL injection:** every request body is a strict pydantic schema (unknown fields and operator objects such as
  `{"$ne": null}` rejected); no request data is placed raw into a query. Test: NoSQL injection test in `tests/test_api.py`.
- **XSS:** React escapes all output; the codebase has no `dangerouslySetInnerHTML`, `innerHTML` or `eval`. The website
  is served with a strict Content-Security-Policy (`script-src 'self'`, see A05).
- **No shell or subprocess** use in the application code; no dynamic SQL, regex or template built from input.
- **Fixed 2026-10-18 (PDF markup injection):** a dentist's name and review comment were placed into ReportLab
  paragraph markup unescaped, so a comment containing tags could break report generation or put a clickable link into
  a signed clinical report. They are now escaped. Test: `tests/test_api.py::test_review_comment_cannot_inject_pdf_markup`
  (fails on the old code).

## A04 Insecure Design

- Threat model and trust boundaries: `docs/SECURITY.md`, `docs/ARCHITECTURE.md`.
- Clinical safety by design: calibrated uncertainty, a review router that forces dentist sign-off whenever anything is
  uncertain, and signed reports only after sign-off (`ml/uncertainty/review_router.py`).
- Fail closed: an unsigned or altered model, calibration or risk-coefficient file is refused and its output withheld;
  without a verified detector a production deployment returns 503 instead of demo output.
- Rate limits: login 5/min, API 120/min (`extensions.py`); account lockout after 5 failures for 15 minutes.

## A05 Security Misconfiguration

- API security headers: CSP `default-src 'none'`, `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`,
  `Cache-Control: no-store`, HSTS on HTTPS (`app/__init__.py`). Generic error messages, no stack traces, debug off.
- **Fixed 2026-10-18 (website headers):** the built website now ships a strict Content-Security-Policy
  (`script-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`, `connect-src 'self'`), plus
  `Permissions-Policy`, `Cross-Origin-Opener-Policy`, `nosniff`, `DENY` framing and HSTS, in `frontend/vercel.json`
  and for `vite preview` in `frontend/vite.config.ts`. The one inline script was moved to `public/theme-init.js` so no
  inline script is allowed. Checked by crawling all 15 pages of the production build: 0 policy violations,
  0 console errors.
- **Fixed 2026-10-15 (container):** the production image runs as a non-root user, and `backend/.dockerignore` keeps
  `.env*`, `keys-production/` (private signing key), production weights, storage and logs out of the image.
- Secrets only in `.env` / `.env.production` (gitignored); the app refuses to start outside demo mode without them;
  `JWT_SECRET_KEY` must be at least 32 characters.
- Demo mode is visibly labelled on every page and in every API response.

## A06 Vulnerable and Outdated Components

All versions are pinned (`backend/requirements.txt`, `frontend/package-lock.json`). Audit of 2026-10-18:

| Component | Finding | Action |
|---|---|---|
| pymongo 4.15.4 | 4 advisories | upgraded to 4.18.2 |
| cryptography 46.0.6 | 5 advisories | upgraded to 50.0.0 |
| PyJWT 2.12.1 | 15 advisories | upgraded to 2.15.0 |
| Pillow 12.2.0 | 13 advisories | upgraded to 12.3.0 |
| PyTorch 2.10.0 | CVE-2026-4538 (`.pt2` export loading, no fixed version), CVE-2025-3000 (`torch.jit.script`) | **accepted risk**, see below |
| npm packages shipped to users | 0 advisories (`npm audit --omit=dev`) | none needed |
| npm build tools (Vite dev server, Tailwind file watcher) | 9 advisories, development machine only | non-breaking fixes applied; the rest need major upgrades of Vite / Tailwind and do not reach users |

**PyTorch accepted risk.** Both advisories need a local attacker on the server and concern features the app never
uses: loading `.pt2` export files and `torch.jit.script`. The app loads only model files whose RSA-PSS signature has
been verified first (A08), the panoramic models with `torch.load(weights_only=True)`, and it never accepts model
files from users. Upgrading PyTorch changes the engine every model, calibration and test was validated on, so it is
done only together with a full re-validation (live tests, self-check re-recording, test-set evaluation).

Re-run: `cd backend; python -m pip_audit -r requirements.txt` and `cd frontend; npm audit --omit=dev`.

## A07 Identification and Authentication Failures

- Passwords: at least **12 characters** with upper- and lower-case letters and a digit (raised from 10 on 2026-10-18,
  OWASP ASVS 2.1.1), bcrypt-hashed; lockout after 5 failures for 15 minutes; login rate limit 5/min.
- **MFA** (TOTP with replay protection) required for dentists and admins in live mode; cannot be skipped via the API.
  Tests: `test_mfa_cannot_be_skipped_by_calling_the_api_directly`, `test_privileged_roles_must_enrol_mfa_before_anything_else`.
- Sessions: 15-minute access token in memory only, bound to a server-side session and a device fingerprint;
  7-day refresh token in an `HttpOnly`, `SameSite=Strict` cookie, rotated on every use, **reuse revokes the session**;
  30-minute idle timeout. JWT algorithm pinned (HS256), issuer checked; expired, forged and `alg:none` tokens rejected.
  Tests: `tests/test_api.py`, `tests/test_attacks.py::test_forged_tokens_are_rejected`.

## A08 Software and Data Integrity Failures

- Every model, calibration, metrics and risk-coefficient file is listed in an RSA-PSS signed SHA-256 manifest and
  verified before it is loaded; a startup self-check confirms the models reproduce the outputs recorded at signing.
  Tests: `tests/test_model_signing.py`, live test `test_a_one_byte_change_to_the_weights_is_refused_and_logged`.
- Clinical reports: the PDF's SHA-256 is signed; public verification detects any edit. Test: end-to-end test.
- Dependencies pinned with lock files; the Docker images install exact versions.

## A09 Security Logging and Monitoring Failures

- Tamper-evident audit log: hash chain over every entry, numbered and chained Merkle anchors authenticated with a key
  outside the database, optional write-once witness copy (`security/audit_log.py`). Verification names the first
  tampered entry. Tests: `tests/test_audit_chain.py`, `tests/test_security_fixes.py`.
- Logged: logins (success, failure, lockout), access denials, uploads, predictions, reviews, reports, model loads and
  refusals, decoy access. Logs contain no patient names: pseudonyms and keyed IP hashes only.
- The Security center shows sessions and lets an auditor verify the chain; the Security Lab demonstrates 7 of 7
  attacks being blocked.

## A10 Server-Side Request Forgery

The backend makes no outbound HTTP requests (no `requests`, `urllib`, `httpx` in `backend/app`), so no
user-supplied URL can make the server fetch anything. The only outside resource is Google Fonts, loaded by the
browser and allowed by the CSP.
