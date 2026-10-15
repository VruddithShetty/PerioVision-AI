# PerioVision AI: Security Testing

Nothing in this project is claimed as a control unless something demonstrates it. Three
layers do that: unit and integration tests, the Security Lab, and CI scanners.

```
296 automated tests          pytest, demo mode, throwaway keys
 22 Security Lab scenarios   110 assertions, runnable from the API
  6 CI jobs                  dependency CVEs, secrets, CodeQL, container scan,
                             SBOM, model manifest integrity
```

---

## 1. The test suite

| File | Tests | Covers |
|---|---|---|
| `test_authorization.py` | 57 | IDOR, escalation, deny-by-default, mass assignment, stale privilege |
| `test_model_provenance.py` | 37 | Approval gate, separation of duties, rollback, tampered metadata |
| `test_security_events.py` | 21 | Taxonomy completeness, detection rules, no PHI in alerts |
| `test_retention.py` | 20 | Classification, protected stores, orphaned blobs |
| `test_api.py` | 21 | Headers, CORS, tokens, lockout, end-to-end workflow |
| `test_crypto.py` | — | AES-GCM round trip, nonce uniqueness, tamper, rotation |
| `test_audit_chain.py` | — | Edits, deletions, reordering, forged anchors |
| `test_security_hardening.py` | 16 | bcrypt truncation, JWT audience and rotation, scanner precision |
| `test_upload_guard.py`, `test_model_signing.py` (8), `test_clinical.py`, `test_ml_logic.py`, `test_contract.py`, `test_phase3.py` | — | Uploads, signing, clinical logic, OpenAPI |

Run: `cd backend && DB_MODE=demo python -m pytest -q`

## 2. Three tests that enforce rather than check

Most tests confirm behaviour. These three prevent decay:

**`test_every_recorded_event_is_classified`** reads every `audit().record("NAME")` out of the
source and fails if any name is missing from the taxonomy. A new event must be categorised
when it is added. It has already caught one: the retention work introduced
`RETENTION_PURGE` and this test refused it.

**`test_every_store_the_app_writes_to_is_classified`** does the same for data stores, so a
new collection cannot default to unmanaged.

**`test_every_model_the_registry_knows_about_is_declared_for_approval`** fails if a model
in `MODEL_SPECS` has no entry in `config/model_approvals.json`, or names a different file.
Nothing else catches that while the weight file is absent - the registry stops at "weight
file not found" and never reaches the approval gate - so the gap only appears the day
someone installs the weights. It has already caught one: merging the landmark ensemble
added `landmarks_2` and `landmarks_3` to the registry without declaring either.

## 3. Mutation testing

A test that cannot fail proves nothing. Controls were deliberately broken and reverted:

| Mutation | Tests that failed |
|---|---|
| `can_access_patient` always `True` | **12** |
| `has_permission` always `True` | **20** |
| Zero Trust reads the role from the token, not the database | **1** |
| Approval check removed | **5** |
| Version floor ignored | **1** |
| Countersignature requirement removed | **9** |
| One event removed from the taxonomy | **1** |

The single-test results matter most. Only `test_demotion_applies_to_an_already_issued_token`
stands between a demoted admin and fifteen more minutes of admin rights; only
`test_downgrade_to_an_older_signed_manifest_is_rejected` catches a model rollback. Before
this work, neither existed.

After every mutation run, `grep MUTANT` over `backend/app/` confirms nothing was left behind.

## 4. The Security Lab

21 scenarios, 104 assertions, all against throwaway material — temporary directories,
synthetic images, an isolated audit collection, a temporary keypair. Nothing touches real
patients, weights, the audit trail or the signing key.

`GET /api/security-lab` lists them; `POST /api/security-lab/run-all` runs them. Requires
`security_lab:run` (admin or auditor).

| Group | Scenarios |
|---|---|
| Model trust | model-tamper, model-approval, model-downgrade, separation-of-duties |
| Audit and reports | audit-tamper, report-tamper |
| Identity and session | jwt-replay, session-theft, brute-force, mfa-replay |
| Authorization | privilege-escalation, idor, nosql-injection |
| Uploads | disguised-upload, upload-limits, path-traversal |
| Data at rest | encryption-tamper, secret-leakage, retention-protection |
| AI | adversarial-input |
| Detection | detection, deception |

Each scenario returns step-by-step results. `defended` is true only if every step passed, and
a scenario that raises is reported as not defended rather than hidden.

The two worth watching: **model-approval** signs a model correctly, confirms the signature
verifies, then shows it refused because it was never approved — integrity and authorisation
are visibly different questions. **model-downgrade** archives a model with its own valid
signature, restores the bundle, shows every integrity check passing, and shows it refused on
freshness.

## 5. CI

| Job | Finds |
|---|---|
| pip-audit | CVEs in pinned Python dependencies |
| npm audit | the same for the frontend, failing at high severity |
| gitleaks | credentials anywhere in the git history |
| CodeQL | injection and unsafe-API patterns in our own code |
| Trivy | CVEs in the built image, base OS included |
| SBOM | CycloneDX for both halves, kept 90 days |
| Model metadata | approval data that a bad merge has broken |

Bandit and Semgrep are deliberately absent: their Python coverage overlaps CodeQL, and three
SAST tools produce noise rather than coverage.

**pip-audit has already paid for itself** — 34 advisories on first run, concentrated in
PyJWT (14), pillow (13) and cryptography (5). All fixed; it reports clean now.

## 6. What is not tested

- **Trivy and the SBOM jobs have never executed.** Syntax and pins are verified; the first CI
  run is the real test. Expect base-image findings.
- **No load or DoS testing.**
- **No external penetration test.**
- **Adversarial screening is not evaluated against an adaptive attacker.** It is a heuristic
  tuned on 30 real radiographs, and no robustness claim is made.
- **Detection thresholds are unvalidated** against real traffic.
- **The frontend has no security tests** beyond lint and type-check.
