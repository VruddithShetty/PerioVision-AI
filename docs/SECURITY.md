# PerioVision AI: Security Design

PerioVision AI is a clinical decision-support system. Its controls are **aligned with** HIPAA Security Rule safeguards and the OWASP Top 10. It is **not** HIPAA-certified, and it has not had an external security assessment.

## 1. Assets and threat model

| Asset | Threat | Main controls |
|---|---|---|
| Patient identity (name, contact, notes) | Database theft, insider browsing | AES-256-GCM field encryption, blind indexes, pseudonyms in logs, RBAC + object-level checks, decoy records |
| Radiographs, overlays, PDF reports | Disk theft, file swapping | AES-256-GCM blob encryption with purpose-bound associated data, random blob IDs |
| Model weights | Poisoned or swapped model | RSA-PSS signed SHA-256 manifest; the registry refuses unsigned or altered files |
| Clinical report | Forged or edited PDF | SHA-256 of the PDF signed with RSA-PSS; public `/verify` endpoint; QR verification ID |
| Audit trail | Covering tracks after misuse | Hash chain over every entry + HMAC-authenticated Merkle anchors stored outside the database |
| Accounts / sessions | Credential stuffing, token theft, replay | bcrypt, lockout, rate limits, TOTP MFA, short-lived JWT bound to device + server-side session, refresh-token rotation with reuse detection |
| Inference | Adversarial or out-of-distribution images | Upload guard, quality gate, perturbation heuristics, OOD checks; flagged cases forced into clinician review |
| API surface | Injection, IDOR, info leaks | Strict pydantic schemas, no raw request data in queries, deny-by-default routing, safe error messages, security headers, CORS allow-list |

## 2. Controls, and what each one defends against

| Control | Where | Defends against |
|---|---|---|
| **AES-256-GCM**, fresh 96-bit random nonce per message, authenticated | `backend/app/security/crypto.py` | Reading or silently modifying stored PHI/images |
| **Key IDs + key ring + rotation** (`FIELD_ENCRYPTION_KEYS`, KMS-style key file, `scripts/rotate_keys.py`) | `crypto.py` | Long-lived key exposure; lets old keys be retired |
| **HKDF-separated keys** for blind index and pseudonyms | `crypto.py` | Reusing the encryption key for hashing |
| **bcrypt** (cost 12, SHA-256 pre-hash so the 72-byte truncation limit does not apply) + password policy | `security/auth.py`, `models/doctors.py` | Offline password cracking; long passwords sharing a 72-byte prefix colliding |
| **JWT access (15 min) + refresh (7 days, httpOnly SameSite=Strict cookie, rotated)**, audience-scoped, signed under a key ID so the secret can rotate without ending live sessions | `security/auth.py`, `api/auth.py` | Token theft (short lifetime), refresh replay (reuse revokes the session), cross-service token reuse, key-rotation outages |
| **TOTP MFA** with QR enrolment and replay protection | `security/auth.py`, `api/auth.py` | Stolen passwords |
| **Account lockout** (5 failures, 15 min) + **rate limiting** (login 5/min, API 120/min) | `models/doctors.py`, `extensions.py` | Brute force, credential stuffing |
| **RBAC**: 4 roles, explicit permission matrix, enforced by `@secured(...)` | `security/rbac.py` | Privilege misuse |
| **Zero Trust guard** (NIST SP 800-207 principles): every request re-checks token, session, device fingerprint, account state and policy; deny by default | `security/zero_trust.py` | Stolen/replayed tokens, revoked users, forgotten decorators |
| **Object-level access**: users only see patients they own or are on the care team for | `rbac.can_access_patient` | IDOR / horizontal privilege escalation |
| **RSA-PSS model signing** + hash manifest; registry refuses to load and logs `MODEL_LOAD_REFUSED` | `security/model_signing.py`, `ml/registry.py`, `scripts/sign_model.py` | Model tampering / supply-chain swap |
| **Model provenance and approval gate**: the signed manifest also declares each model's identity, version, training commit and dataset version. A model is refused unless the manifest names it, points at the expected file, matches any version the deployment pins, and is no older than a manifest already accepted (a floor kept in writable storage, outside the read-only weights mount). Applies to all four models, panoramic included | `security/model_provenance.py`, `ml/registry.py`, `config/model_approvals.json` | Running an unapproved, superseded or substituted model whose signature is nonetheless valid, including replay of an archived weights bundle with its own valid signature |
| **Separation of duties**: clinical approval is countersigned under a second key (`model_approval`) the model builder does not hold, and names the model's exact SHA-256, so a rebuild voids it | `security/model_approval.py`, `scripts/approve_model.py` | A model builder clearing their own model for use on patients |
| **Signed reports** + `/api/reports/verify` | `services/report_service.py` | Forged or edited reports |
| **Tamper-evident audit log**: hash chain (genesis included), unique sequence numbers, Merkle roots every 20 entries authenticated with `AUDIT_ANCHOR_KEY` and written to `backend/logs/merkle_anchors.jsonl`. Since 2026-10-04: anchors are numbered and hash-chained (v2), the Merkle tree is domain-separated, an optional witness copy goes to `AUDIT_ANCHOR_WITNESS_DIR`, and verification reports `unanchored_entries` | `security/audit_log.py`, `scripts/verify_audit.py` | Undetected log edits, deletions, full rewrites |
| **Upload guard**: size, extension, magic bytes, pixel limits, re-encode (drops EXIF), DICOM PHI tags removed, random names | `security/upload_guard.py` | Disguised files, decompression bombs, metadata leaks, path traversal |
| **Adversarial / OOD heuristics** routed to review | `security/adversarial.py`, `ml/uncertainty/ood.py` | Manipulated inputs silently changing results |
| **Decoy (honeypot) patients**: realistic, unflagged, tracked by an HMAC tag under a key derived for that purpose (stays armed through key rotation, re-tagged by `scripts/rotate_keys.py`); access revokes sessions and locks the account for 60 min | `security/honeypot.py` | ID enumeration, insider browsing |
| **Security headers** (CSP `default-src 'none'`, nosniff, frame DENY, no-referrer, HSTS on HTTPS), `Cache-Control: no-store` | `app/__init__.py` | Clickjacking, MIME sniffing, caching PHI |
| **CORS allow-list** (`CORS_ORIGINS`) | `app/__init__.py` | Cross-site API use |
| **Strict input validation** (pydantic, extra fields forbidden) | `app/schemas/` | NoSQL operator injection (`{"$ne": null}`), mass assignment |
| **Safe errors**: generic messages, no stack traces, debug off | `app/__init__.py`, `wsgi.py` | Information disclosure |
| **Secrets only in `.env`** (gitignored); private key password-protected and gitignored | `.gitignore`, `config.py` | Secret leakage via git |
| **Pinned dependencies**, audited by `pip-audit` and `npm audit` in CI (weekly as well as per push) and patched by Dependabot | `backend/requirements.txt`, `.github/workflows/security.yml`, `.github/dependabot.yml` | Unexpected upstream changes; known CVEs in dependencies |
| **Secret scanning** (gitleaks over full history) and **CodeQL** static analysis for Python and TypeScript | `.github/workflows/security.yml` | Credentials committed to the repository; injection and unsafe-API patterns in our own code |
| **Container scanning** (Trivy over the built image, failing on fixable HIGH/CRITICAL) and a **CycloneDX SBOM** kept with every build | `.github/workflows/security.yml` | CVEs in the OS userland that no Python manifest lists; not knowing what shipped when an advisory lands |
| **Pinned supply chain**: every GitHub Action pinned to a commit SHA and both base images to a digest | `.github/workflows/*.yml`, `backend/Dockerfile`, `docker-compose.yml` | A mutable tag being repointed at attacker-controlled code that then runs with the repository's token |
| **Real client IP behind a proxy** (`TRUSTED_PROXY_COUNT` enables ProxyFix; off by default so the header cannot be forged when no proxy is present) | `app/__init__.py`, `app/config.py` | Rate limits collapsing into one shared bucket; audit records logging the proxy instead of the caller |
| **Hardened container**: waitress, non-root user (uid 10001), read-only root filesystem, `cap_drop: ALL`, `no-new-privileges`, memory limits, weights and keys mounted read-only | `backend/Dockerfile`, `docker-compose.yml` | Container escape and privilege escalation; a compromised process rewriting its own code, model weights or signing keys |
| **Security event taxonomy and detection**: every recorded event is classified, and windowed rules over the audit log raise alerts for credential guessing, authorization probing, mass patient access, refused model loads and decoy access. Served at `GET /api/security/events` under `security:read` | `security/events.py`, `api/security.py` | Slow or distributed abuse that each single refusal looks innocent against |
| **Data classification and retention**: twelve stores classified; a sweep cannot touch the audit log, clinical records, or any store nobody has classified. Orphaned encrypted blobs are found and removable | `security/retention.py` | PHI outliving the record that pointed at it; a retention job destroying the audit trail |

### Transport security (TLS/HTTPS)

The Flask development server speaks HTTP on 127.0.0.1 only. For anything beyond one laptop, put it behind a TLS terminator. For a local demo with a self-signed certificate:

```bash
openssl req -x509 -newkey rsa:3072 -nodes -keyout backend/keys/dev-tls.key -out backend/keys/dev-tls.crt -days 30 -subj "/CN=localhost"
cd backend && python -c "from wsgi import app; app.run(ssl_context=('keys/dev-tls.crt','keys/dev-tls.key'), port=5443)"
```

The browser will warn that the certificate is self-signed, which is expected for local development. With HTTPS, the API also sends `Strict-Transport-Security`, and the refresh cookie gets the `Secure` flag.

## 3. RBAC permission matrix

Enforced by `@secured("<permission>")` on every route (`backend/app/security/rbac.py`). It is also served live at `GET /api/security/rbac-matrix`. Roles from older data are mapped as superadmin→admin, doctor→dentist and viewer→auditor.

| Permission | admin | dentist | technician | auditor |
|---|:-:|:-:|:-:|:-:|
| patient:read | ✅ | ✅ (own/care team) | ✅ (own/care team) | ❌ |
| patient:write | ✅ | ✅ | ❌ | ❌ |
| radiograph:upload | ❌ | ✅ | ✅ | ❌ |
| analysis:run | ❌ | ✅ | ✅ | ❌ |
| analysis:read | ✅ | ✅ | ✅ | ❌ |
| chart:read (perio charts) | ✅ | ✅ (own/care team) | ✅ (own/care team) | ❌ |
| chart:write | ❌ | ✅ | ✅ | ❌ |
| care:read (care plan, recall board) | ✅ | ✅ | ✅ | ❌ |
| review:read | ✅ | ✅ | ❌ | ❌ |
| review:signoff | ❌ | ✅ | ❌ | ❌ |
| report:generate | ❌ | ✅ | ❌ | ❌ |
| report:read | ✅ | ✅ | ❌ | ❌ |
| audit:read / audit:verify | ✅ | ❌ | ❌ | ✅ |
| model:read | ✅ | ✅ | ❌ | ✅ |
| security:read, security_lab:run | ✅ | ❌ | ❌ | ✅ |
| admin:users, admin:config | ✅ | ❌ | ❌ | ❌ |
| self:manage (own profile, MFA, sessions) | ✅ | ✅ | ✅ | ✅ |

Design choices: auditors can verify the audit trail but never see PHI. Admins manage the system but do not make clinical decisions. Only dentists sign off and issue reports.

## 4. HIPAA Security Rule: aligned controls (not certified)

| Safeguard (45 CFR §164.312) | How PerioVision aligns |
|---|---|
| Access control (a)(1): unique user IDs, automatic logoff, encryption | Per-user accounts, 30-minute idle session timeout, AES-256-GCM at rest |
| Audit controls (b) | Hash-chained, anchored audit log of logins, access, uploads, predictions, reports, model loads and denials |
| Integrity (c)(1) | GCM authentication tags, signed models and reports, tamper-evident log |
| Person or entity authentication (d) | bcrypt passwords + TOTP MFA |
| Transmission security (e)(1) | TLS termination required outside local development (see above) |
| Minimum necessary (§164.502(b)) | Role- and care-team-scoped access; auditors see no PHI; pseudonyms in logs |

## 5. Known limitations

- Authorization failures are detected but not throttled. A burst raises an `authorization_probing` alert on
  `GET /api/security/events`, but nothing automatically blocks the account: detection is deliberately kept
  separate from enforcement, and no second rate limiter was added alongside the existing one.
- Detection is computed on demand from the audit log, not streamed. Nobody is paged; an alert is visible when
  the security centre is opened. Routing alerts onward is left to deployment.
- Model approval is an attestation of clinical fitness, not proof of it. The approver signs under a key the
  builder does not hold, so the two roles are separated and the clearance covers exact bytes, but nothing
  verifies the approver actually evaluated the model, and one person holding both keys defeats the split.
- Retention never deletes on its own: `plan()` reports and `purge()` only runs when called. Nothing schedules
  it, so retention happens only when someone makes it happen.

- Decoy records are excluded from normal lists by a system owner ID. Someone with direct database access could spot them. The design targets API-level probing.
- In demo mode, data and audit anchors live in memory and disappear on restart.
- Without `AUDIT_ANCHOR_WITNESS_DIR` on storage the server cannot rewrite, an attacker with full control of the server (database, anchor file and `AUDIT_ANCHOR_KEY`) can roll the log back to an earlier anchor. Entries after the newest anchor (up to 19) are protected by the hash chain only; verification shows how many.
- IP addresses are stored only as keyed hashes (`hash_ip`), and there is no GeoIP lookup anywhere (tested in `tests/test_security_fixes.py`). Behind a reverse proxy, configure the proxy's real-client-IP header, otherwise every request shows the proxy's address.

## 6. Security fixes of 2026-10-04

Each fix has a test in `backend/tests/test_security_fixes.py` that **fails on the code before the fix** (checked by stashing the fix: 7 of 11 new tests failed) and passes after it.

| Issue | Before | After |
|---|---|---|
| Decoys disarmed by key rotation | Decoy tags were HMACs under the raw active AES key. After a routine key rotation every existing decoy stopped triggering, silently. | Tags use an HKDF-derived key; lookups try every key in the ring and the old format; `rotate_keys.py` re-tags decoys. |
| Patient search broken by key rotation | Blind indexes were not rebuilt, so old patients disappeared from name / phone search after rotation. | `PHIEncryptor.reindex_record`, called by `rotate_keys.py`. |
| Anchor deletion undetected | Anchors were independent records; deleting one (or the newest one plus the entries it covered) left no trace. | v2 anchors carry `anchor_seq` and `prev_anchor`; a gap or reorder is reported. Optional witness copy catches a rollback of the newest anchor. |
| Merkle second-preimage pattern | Odd layers duplicated the last leaf, so `[a,b,c]` and `[a,b,c,c]` shared a root (the CVE-2012-2459 pattern; limited here because the HMAC also covers the count). | RFC 6962-style leaf / node prefixes, odd node promoted. v1 anchors still verify. |
| Silent unanchored tail | Verification said "intact" while up to 19 newest entries could be deleted without trace. | `unanchored_entries` is reported. |

The four weaknesses listed in the project brief (deterministic AES-CBC with a static IV, an unanchored Merkle root, GeoIP leakage, a static honeypot) are **not present in this code**: encryption is AES-256-GCM with a fresh random 96-bit nonce, roots were already HMAC-anchored outside the database, no GeoIP code exists, and decoys were already randomised. Tests now guard each of these so they cannot come back.
- The rate limiter's in-memory store is per process. Use `REDIS_URL` with multiple workers.
- The adversarial checks are heuristics tuned on 30 real radiographs, not a certified defence.
