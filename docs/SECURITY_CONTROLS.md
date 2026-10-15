# PerioVision AI: Security Control Matrix

One row per control. Every row names where it lives and what demonstrates it. A control
with no evidence column entry does not belong in this file.

Status values: **Implemented** (in code, tested) · **Partial** (works, with a stated limit)
· **Operational** (a deployment or repository setting, not code).

---

## Identity and authentication

| Control | Where | Threat | Evidence | Status |
|---|---|---|---|---|
| bcrypt cost 12 with SHA-256 pre-hash | `security/auth.py` | Offline cracking; 72-byte truncation collisions | `test_security_hardening`, Lab: brute-force | Implemented |
| Transparent rehash of legacy hashes on login | `models/doctors.py` | Old hashes persisting | `test_security_hardening` | Implemented |
| Password policy: length, case, digit | `security/auth.py` | Weak passwords | `test_api` | Partial — no breach-list check |
| Account lockout, 5 failures / 15 min | `models/doctors.py` | Brute force | `test_api`, Lab: brute-force | Implemented |
| Login rate limit, 5/min | `api/auth.py` | Distributed guessing | route decorator | Implemented |
| TOTP MFA with QR enrolment | `security/auth.py` | Stolen passwords | `test_api` | Implemented |
| TOTP replay block (used step recorded) | `security/auth.py` | Observed-code reuse | Lab: mfa-replay | Implemented |

## Tokens and sessions

| Control | Where | Threat | Evidence | Status |
|---|---|---|---|---|
| 15-minute access JWT, fixed algorithm | `security/auth.py` | Token theft window | Lab: jwt-replay | Implemented |
| Required claims; `alg:none` rejected | `security/auth.py` | Forgery | Lab: jwt-replay | Implemented |
| Audience claim verified | `security/auth.py` | Cross-service reuse | `test_security_hardening` | Implemented |
| Key ID + retired-key ring | `security/auth.py` | Rotation logging everyone out | `test_security_hardening` | Implemented |
| Refresh in httpOnly SameSite=Strict cookie | `api/auth.py` | Script theft | `test_api` | Implemented |
| Refresh rotation; reuse revokes the session | `models/doctors.py` | Stolen refresh token | `test_api` | Implemented |
| Server-side session, revocable | `models/doctors.py` | Logout that does not log out | `test_authorization` | Implemented |
| 30-minute idle timeout | `security/auth.py` | Abandoned sessions | `security/zero_trust.py` | Implemented |
| Device fingerprint binding | `security/auth.py` | Token used elsewhere | Lab: session-theft | Partial — UA hash only |
| Access token never in localStorage | `frontend/src/store/auth.ts` | XSS theft | code review | Implemented |

## Authorization

| Control | Where | Threat | Evidence | Status |
|---|---|---|---|---|
| RBAC: 4 roles, 20 permissions, deny by default | `security/rbac.py` | Privilege misuse | Lab: privilege-escalation | Implemented |
| Zero Trust guard: token → session → account → policy | `security/zero_trust.py` | Stale or stolen credentials | `test_authorization` | Implemented |
| Role re-read from the database each request | `security/zero_trust.py` | Privilege surviving demotion | `test_authorization` | Implemented |
| Unclassified routes fail closed | `security/zero_trust.py` | Forgotten decorator | `test_api` | Implemented |
| Object-level patient scope, one chokepoint | `api/patients.py` | IDOR / BOLA | Lab: idor | Implemented |
| 404 rather than 403 out of scope | `api/patients.py` | Enumeration | `test_authorization` | Implemented |
| Sub-resources inherit patient scope | `api/analysis.py` | Scope bypass via a child route | `test_authorization` | Implemented |
| Clinical sign-off restricted to dentists | `security/rbac.py` | Admin self-authorising care | `test_authorization` | Implemented |

## Input and API

| Control | Where | Threat | Evidence | Status |
|---|---|---|---|---|
| Pydantic schemas, `extra="forbid"` | `app/schemas/` | NoSQL injection, mass assignment | Lab: nosql-injection | Implemented |
| Upload guard: size, extension, magic bytes | `security/upload_guard.py` | Disguised files | Lab: disguised-upload | Implemented |
| Pixel and dimension caps | `security/upload_guard.py` | Decompression bombs | Lab: upload-limits | Implemented |
| Re-encode from pixels (drops EXIF) | `security/upload_guard.py` | Metadata leakage | `test_upload_guard` | Implemented |
| DICOM PHI tag removal | `security/upload_guard.py` | Identifiers in imaging metadata | `test_upload_guard` | Implemented |
| Random storage identifiers | `security/upload_guard.py` | Path traversal | Lab: path-traversal | Implemented |
| Allow-listed image layers | `api/analysis.py` | Traversal via a path parameter | Lab: path-traversal | Implemented |
| Security headers: CSP, HSTS, nosniff, frame DENY | `app/__init__.py` | Clickjacking, sniffing, caching PHI | `test_api` | Implemented |
| CORS allow-list | `app/__init__.py` | Cross-site API use | `test_api` | Implemented |
| Generic errors, no stack traces | `app/__init__.py` | Information disclosure | `test_api` | Implemented |
| Global rate limit 120/min | `app/extensions.py` | API abuse | config | Partial — in-memory unless `REDIS_URL` |
| Real client IP behind a proxy | `app/__init__.py` | One shared rate-limit bucket | config | Implemented |

## Cryptography and keys

| Control | Where | Threat | Evidence | Status |
|---|---|---|---|---|
| AES-256-GCM, fresh 96-bit nonce | `security/crypto.py` | Reading or altering PHI | `test_crypto` | Implemented |
| Purpose-bound AAD | `security/crypto.py` | Substituting one blob for another | Lab: encryption-tamper | Implemented |
| Key IDs, key ring, rotation | `security/crypto.py` | Long-lived key exposure | `test_crypto` | Implemented |
| HKDF separation per purpose | `security/crypto.py` | Key reuse across uses | `test_crypto` | Implemented |
| Blind index for encrypted search | `security/crypto.py` | Searchability vs confidentiality | `test_crypto` | Implemented |
| Pseudonyms in logs and analytics | `security/crypto.py` | PHI in telemetry | `test_security_events` | Implemented |

## Model and AI

| Control | Where | Threat | Evidence | Status |
|---|---|---|---|---|
| RSA-PSS signed SHA-256 manifest | `security/model_signing.py` | Tampered weights | Lab: model-tamper | Implemented |
| Approval gate after the signature check | `security/model_provenance.py` | Unapproved model in clinical use | Lab: model-approval | Implemented |
| Approval countersigned under a separate key, bound to the exact hash | `security/model_approval.py`, `scripts/approve_model.py` | A model builder clearing their own model for use on patients | Lab: separation-of-duties | Implemented |
| Monotonic manifest version + external floor | `security/model_provenance.py` | Replaying an archived signed bundle | Lab: model-downgrade | Implemented |
| Model identity bound to file and hash | `security/model_signing.py` | Substitution under the expected name | `test_model_provenance` | Implemented |
| Provenance: training commit, dataset version | `config/model_approvals.json` | Unknown lineage | CI check | Partial — recorded, not verified |
| Refusal audited without sensitive detail | `ml/registry.py` | Leaking layout via logs | `test_model_provenance` | Implemented |
| Adversarial screening → review | `security/adversarial.py` | Manipulated inputs | Lab: adversarial-input | Partial — a heuristic |
| OOD detection → review | `ml/uncertainty/ood.py` | Inputs outside the training distribution | `test_ml_logic` | Partial |
| Conformal prediction intervals | `ml/uncertainty/conformal.py` | Overconfident output | `test_ml_logic` | Implemented |
| Mandatory clinician review | `ml/uncertainty/review_router.py` | Autonomous diagnosis | `test_clinical` | Implemented |

## Audit, detection and data lifecycle

| Control | Where | Threat | Evidence | Status |
|---|---|---|---|---|
| Hash-chained audit log | `security/audit_log.py` | Editing history | Lab: audit-tamper | Implemented |
| Merkle roots anchored outside the database | `security/audit_log.py` | Wholesale rewrite | Lab: audit-tamper | Implemented |
| Multi-process safe append | `security/audit_log.py` | Lost or duplicated sequence | `test_audit_chain` | Implemented |
| 48 events classified by category and severity | `security/events.py` | Unlabelled events nothing can alert on | `test_security_events` | Implemented |
| 12 windowed detection rules | `security/events.py` | Slow or distributed abuse | Lab: detection | Implemented |
| Alerts carry no PHI | `api/security.py` | Auditors seeing patient data | `test_security_events` | Implemented |
| 12 data stores classified | `security/retention.py` | Unmanaged data | `test_retention` | Implemented |
| Protected stores refuse purging | `security/retention.py` | Destroying the audit trail | Lab: retention-protection | Implemented |
| Orphaned blob detection | `security/retention.py` | PHI outliving its record | `test_retention` | Implemented |
| Decoy patient records | `security/honeypot.py` | Enumeration, insider browsing | Lab: deception | Implemented |

## Reports

| Control | Where | Threat | Evidence | Status |
|---|---|---|---|---|
| SHA-256 of the PDF signed with RSA-PSS | `services/report_service.py` | Forged or edited reports | Lab: report-tamper | Implemented |
| Public verification endpoint + QR | `api/reports.py` | Verification depending on database trust | `test_api` | Implemented |
| Reports scoped by patient authorization | `api/reports.py` | Cross-patient download | `test_authorization` | Implemented |

## Infrastructure and supply chain

| Control | Where | Threat | Evidence | Status |
|---|---|---|---|---|
| waitress, not the development server | `backend/Dockerfile` | Dev server in production | file | Implemented |
| Non-root container (uid 10001) | `backend/Dockerfile` | Privilege escalation | file | Implemented |
| Read-only rootfs, `cap_drop: ALL`, no-new-privileges | `docker-compose.yml` | Container escape | compose validated | Implemented |
| Weights and keys mounted read-only | `docker-compose.yml` | Process rewriting its own trust anchors | compose validated | Implemented |
| Base images pinned by digest | `Dockerfile`, compose | Mutable tag swap | digests resolved | Implemented |
| All 9 GitHub Actions pinned to SHAs | `.github/workflows/` | Retagged action running with repo token | each SHA verified via API | Implemented |
| pip-audit + npm audit | CI | Known CVEs | CI | Implemented |
| gitleaks over full history | CI | Committed credentials | CI | Implemented |
| CodeQL, Python and TypeScript | CI | Injection and unsafe APIs | CI | Implemented |
| Trivy on the built image | CI | Base-image CVEs | CI | Partial — unproven until first run |
| CycloneDX SBOM per build | CI | "Were we affected?" | 26 components verified | Implemented |
| Dependabot: pip, npm, actions, docker | `.github/dependabot.yml` | Stale pins | file | Implemented |
| Model approval metadata validated | CI | Bad merge breaking approval data | tested both ways | Implemented |
| Branch protection, required review | — | Unreviewed code on main | — | **Not configured** |

---

## Deliberately not implemented

| Rejected | Why |
|---|---|
| CSRF tokens | Bearer header plus a SameSite=Strict cookie scoped to `/api/auth` |
| Bandit, Semgrep | Python coverage overlaps CodeQL; three SAST tools add noise, not coverage |
| A second rate limiter for authorization failures | Duplicates the existing limiter; detection is the right layer |
| Encrypting the audit log | Breaks verification, and it holds no PHI |
| Field encryption on bone-loss values | Must stay queryable; pseudonymisation suffices |
| A full SIEM | Disproportionate; a clean event taxonomy a SIEM can consume is the right scope |
