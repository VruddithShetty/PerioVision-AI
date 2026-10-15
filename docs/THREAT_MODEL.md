# PerioVision AI: Threat Model

Scope: the Flask API, its MongoDB store, encrypted blob storage, the model registry, the
audit trail, and the container and CI that ship them. The React frontend is in scope only
as a client — it holds no secrets and enforces nothing.

Residual risk is stated honestly. "Low" means the control is implemented and demonstrated,
not that the threat is impossible.

---

## 1. Assets

| Asset | Why an attacker wants it | Where it lives |
|---|---|---|
| Patient identity | Directly identifying; saleable | `patients`, AES-256-GCM per field |
| Radiographs | Clinical images tied to a person | Encrypted blobs on disk |
| Clinical findings | Diagnosis, staging, risk | `analyses`, `perio_charts` |
| Signed reports | Forgeable clinical documents | `reports` + encrypted PDF blob |
| Credentials | Account takeover | `doctors`: bcrypt + TOTP secrets |
| Model weights | Change what the system concludes | `weights/`, signed manifest |
| Audit trail | Cover tracks | `audit_logs` + external anchors |
| Encryption keys | Everything at rest | Environment only, never in the database |

## 2. Threat actors

| # | Actor | Capability | Realistic goal |
|---|---|---|---|
| A1 | Unauthenticated internet | Reach public routes | Get in |
| A2 | Authenticated clinician, malicious | A valid session | Read patients not theirs |
| A3 | Compromised clinician account | Stolen token or password | Bulk exfiltration |
| A4 | Compromised administrator | Account management | Escalate, then hide it |
| A5 | Insider with database access | Direct MongoDB reads | Read PHI without the API |
| A6 | Insider with filesystem access | Blob storage | Read radiographs |
| A7 | Supply-chain attacker | A dependency, action or base image | Code execution in CI or runtime |
| A8 | ML-pipeline attacker | Can place a weight file | Change clinical conclusions |
| A9 | Container escape | A foothold in the process | Reach the host |

---

## 3. Threat → control → evidence

Every row names the test or Lab scenario that demonstrates it. "Lab: x" is a scenario in
the Security Lab, runnable from `GET /api/security-lab`.

### Authentication and session

| Threat | Control | Evidence | Residual |
|---|---|---|---|
| Credential stuffing | bcrypt cost 12, lockout 5/15 min, 5 logins/min | Lab: brute-force | **Low** |
| Long-password collision | SHA-256 pre-hash before bcrypt (72-byte truncation) | `test_security_hardening` | **Low** |
| Forged JWT, `alg:none` | Fixed algorithm, required claims, issuer and audience | Lab: jwt-replay | **Low** |
| Cross-service token reuse | `aud` claim verified | `test_security_hardening` | **Low** |
| Token theft | 15-minute access token bound to a device fingerprint | Lab: session-theft | **Medium** — fingerprint is a UA hash |
| Refresh token theft | Rotation; replay revokes the whole session | `test_api` | **Low** |
| TOTP replay | Used time step recorded | Lab: mfa-replay | **Low** |
| Stale privilege after demotion | Role re-read from the database each request | `test_authorization` | **Low** |

### Authorization

| Threat | Control | Evidence | Residual |
|---|---|---|---|
| IDOR / horizontal access | `load_patient_or_404`, single chokepoint | Lab: idor, `test_authorization` | **Low** |
| Patient enumeration | 404 with an identical body to a genuine miss | `test_authorization` | **Low** |
| Vertical escalation | Explicit permission matrix, deny by default | Lab: privilege-escalation | **Low** |
| Unprotected new route | `enforce_deny_by_default` refuses unclassified routes | `test_api` | **Low** |
| Nested resource leak | Sub-resources reach the same patient check | `test_authorization` | **Low** |
| Authorization probing | Refusals audited; `authorization_probing` rule | Lab: detection | **Medium** — alerts, does not block |

### Input and API

| Threat | Control | Evidence | Residual |
|---|---|---|---|
| NoSQL operator injection | Pydantic `extra="forbid"`, typed fields | Lab: nosql-injection | **Low** |
| Mass assignment | Ownership fields are not in any schema | `test_authorization` | **Low** |
| Disguised upload, polyglot, SVG | Magic bytes must match extension; re-encode from pixels | Lab: disguised-upload | **Low** |
| Decompression bomb | Pixel and dimension caps before decode | Lab: upload-limits | **Low** |
| Path traversal | Random storage IDs; allow-listed image layers | Lab: path-traversal | **Low** |
| EXIF / DICOM PHI leak | Re-encoded from pixels; DICOM PHI tags removed | `test_upload_guard` | **Low** |
| Information disclosure | Generic errors, no stack traces | `test_api` | **Low** |

### Data at rest

| Threat | Control | Evidence | Residual |
|---|---|---|---|
| Database theft (A5) | AES-256-GCM per field; keys never in the database | `test_crypto` | **Low** |
| Blob theft (A6) | AES-256-GCM with purpose-bound AAD | Lab: encryption-tamper | **Low** |
| Ciphertext tampering | GCM authentication tag | Lab: encryption-tamper | **Low** |
| Swapping one blob for another | AAD bound to purpose | Lab: encryption-tamper | **Low** |
| Key compromise | HKDF per purpose; key IDs; rotation | `test_crypto` | **Medium** — keys are environment-held |
| PHI outliving its record | Retention finds orphaned blobs | `test_retention` | **Low** |
| Catastrophic retention sweep | Protected stores; unclassified refused | Lab: retention-protection | **Low** |

### Model and AI

| Threat | Control | Evidence | Residual |
|---|---|---|---|
| Tampered weights | RSA-PSS signed SHA-256 manifest | Lab: model-tamper | **Low** |
| Unapproved model in clinical use | Approval gate, countersigned under a separate key | Lab: model-approval, separation-of-duties | **Low** — the build key cannot self-approve |
| Model rollback | Monotonic manifest version with an external floor | Lab: model-downgrade | **Low** |
| Model substitution | Manifest binds model name to file and hash | `test_model_provenance` | **Low** |
| Adversarial input | Noise-residual screening → clinician review | Lab: adversarial-input | **Medium** — a heuristic, not a defence |
| Out-of-distribution input | OOD checks force review | `test_ml_logic` | **Medium** |
| Autonomous misdiagnosis | Mandatory review; only a dentist signs off | `test_authorization` | **Low** |

### Audit, reports, supply chain, infrastructure

| Threat | Control | Evidence | Residual |
|---|---|---|---|
| Editing an audit entry | Hash chain pinpoints the first bad entry | Lab: audit-tamper | **Low** |
| Rewriting the whole chain | Merkle roots anchored outside the database | Lab: audit-tamper | **Low** |
| Deleting audit entries | Retention refuses the store | Lab: retention-protection | **Low** |
| Forged or edited report | SHA-256 + RSA-PSS; public verification | Lab: report-tamper | **Low** |
| Vulnerable dependency | pip-audit, npm audit, Dependabot | CI | **Low** |
| Base-image CVE | Trivy on the built image | CI | **Medium** — unproven until first run |
| Malicious GitHub Action | All 9 pinned to commit SHAs | CI | **Low** |
| Committed credential | gitleaks over full history; startup scanner | Lab: secret-leakage | **Low** |
| Container escape | Non-root, `cap_drop: ALL`, read-only rootfs | `docker-compose.yml` | **Low** |
| Unreviewed code reaching main | — | — | **Medium — no branch protection** |

---

## 4. Threats accepted without a control

Stated rather than hidden.

| Threat | Why not addressed |
|---|---|
| Denial of service | Rate limiting slows abuse; a real DoS defence belongs at the edge, not here |
| An approver clearing a model they never evaluated | Separation of duties is enforced; diligence is not something software can check |
| An administrator abusing legitimate access | Audited and detectable, not preventable by design |
| Physical or hypervisor compromise | Out of scope |
| Breaking AES-256-GCM or RSA-PSS | Out of scope |

## 5. The most valuable things to fix next

1. **Route alerts somewhere a human sees them.** Detection exists; nobody is paged.
2. **Enable branch protection and required review.** A settings change, not code.
3. **Strengthen device binding** beyond a User-Agent hash.
