# PerioVision AI: Incident Response

What to do when a control fires. Each scenario lists how it surfaces, how to confirm it,
how to contain it, and what to check afterwards.

**This is a design, not a tested operational procedure.** Nothing here has been exercised in
a drill, and there is no on-call rotation.

---

## 0. Before anything

Detection is **pull, not push**. Nobody is paged. Alerts appear at
`GET /api/security/events` when someone opens the security centre. Until that is routed
somewhere a human sees, the first step of every response is *someone noticed*.

Three commands recur:

```bash
# What has detection seen?
curl -H "Authorization: Bearer $TOKEN" https://host/api/security/events

# Is the audit trail itself still sound?
cd backend && python scripts/verify_audit.py

# What is the model registry willing to load?
curl -H "Authorization: Bearer $TOKEN" https://host/api/models/status
```

Never respond by deleting audit entries. The chain is the evidence, and removing an entry
breaks verification for everything after it — retention refuses those stores for this reason.

---

## 1. Compromised clinician account

**Surfaces as** `repeated_login_failures`, `session_device_mismatches`, `mass_patient_access`
or `authorization_probing`.

1. **Confirm** — `GET /api/audit/logs?actor=<id>`. Look for access outside the user's normal
   patients or hours.
2. **Contain** — `PATCH /api/admin/users/<id>` with `{"active": false}`. This revokes every
   live session immediately, not at token expiry.
3. **Scope** — list `PATIENT_VIEWED` and `REPORT_DOWNLOADED` for that actor. Entries carry
   pseudonyms; map them back via the patient record.
4. **Recover** — new password, re-enrol TOTP, reactivate.
5. **After** — if records were read that should not have been, that is a disclosure. Decide
   notification on the scoped list, not on a guess.

## 2. Compromised administrator

As above, plus: an admin can create accounts and change roles.

- Review `USER_CREATED`, `USER_UPDATED`, `USER_LOCKED`, `CARE_TEAM_ADDED` for the period.
- Check for accounts created and then used — `burst_of_administrative_changes` covers the
  creation, not the use.
- An admin **cannot** disable or demote themselves (409), so one administrator cannot lock
  everyone out alone.
- An admin cannot sign off analyses or issue reports, so clinical records could not be
  fabricated through this path.

## 3. Leaked JWT signing key

**Every token is forgeable.** Rotation is the only answer.

1. Generate a new secret; set `JWT_ACTIVE_KID` to a new ID.
2. **Do not** put the leaked key in `JWT_SECRET_KEY_RETIRED` — retiring it keeps forged
   tokens working. Omit it and accept that every user re-authenticates.
3. Restart, then confirm old tokens are refused.
4. Review the audit log for the exposure window: forged tokens still had to pass the session
   check, so look for `AUTH_SESSION_REJECTED` alongside successful access.

The session store is what limits this: a forged token without a matching server-side session
is refused.

## 4. Leaked database credentials

PHI fields and blobs are AES-256-GCM encrypted and **the keys are never in the database**, so
a database copy alone yields ciphertext, pseudonyms and blind indexes.

1. Rotate the MongoDB credentials; restart.
2. Confirm the encryption keys were not also exposed — if `.env` leaked as a whole, treat it
   as §5 as well.
3. Blind indexes allow exact-match confirmation of a guessed name. Not a plaintext dump, but
   not nothing.

## 5. Leaked field-encryption key

The most serious case: PHI is recoverable from any copy of the database or blob store.

1. Add a new key ID, mark it active, keep the old for decryption.
2. `python scripts/rotate_keys.py` to re-encrypt.
3. Retire the old key once nothing references it.
4. Blind indexes and pseudonyms derive from the field key via HKDF, so they change — indexes
   must be rebuilt and historical pseudonyms will not match.
5. Any prior copy stays decryptable with the old key. Rotation protects future data; it does
   not undo a disclosure.

## 6. Model tampering or an unapproved model

**Surfaces as** `model_load_refused` — critical, alerts on the first occurrence.

1. The model was **not loaded**. The pipeline fell back to labelled demo behaviour, so no
   clinical output came from it.
2. `GET /api/models/status` gives the refusal reason: hash mismatch, not approved, downgrade,
   wrong file.
3. **Hash mismatch** → the file changed after signing. Treat the host as compromised; weights
   are mounted read-only, so something had write access it should not have.
4. **Downgrade refused** → someone restored an archived bundle. Check who had filesystem
   access.
5. Restore known-good weights, re-sign, confirm `MODEL_LOADED`.
6. Analyses produced while refused are marked demo mode and already required clinician
   review.

## 7. Audit integrity failure

**Surfaces as** `verify_audit.py` reporting a first-bad entry, or an anchor mismatch.

1. **Do not write to the audit collection.**
2. The report names the first tampered sequence number, the expected hash and the actual one.
3. **Chain broken but anchors intact** → entries were edited after the last anchor. Everything
   up to that anchor is still provable.
4. **Anchors mismatch** → a wholesale rewrite. The anchor store lives outside the database, so
   this is exactly what it exists to catch.
5. Preserve both the collection and `backend/logs/merkle_anchors.jsonl` before anything else.
   They are the evidence.
6. Whoever rewrote the log had direct database access — scope accordingly.

## 8. Decoy record accessed

**Surfaces as** `decoy_record_accessed` — critical, first occurrence.

Decoys are not reachable through any normal workflow, so access is deliberate. The system
already revoked the sessions and locked the account for 60 minutes. Treat as §1 with a
stronger prior: this was enumeration, not a mistake.

## 9. Malicious upload

**Surfaces as** `repeated_upload_rejections`.

The file was rejected before decoding; nothing was stored. Repeated attempts mean someone is
probing the guard. Review the reasons in `UPLOAD_BLOCKED` — if a new file type is getting
further than expected, that is a gap to close.

## 10. Container compromise

1. Stop the container; do not delete it — the filesystem is evidence.
2. The rootfs is read-only and capabilities are dropped, so persistence inside the container
   should not survive a restart.
3. Check whether `/app/storage` or `/app/logs` were modified — those are the writable mounts.
4. Weights and keys are read-only; if either changed, the host itself is compromised.
5. Rotate every secret in `.env`: the process could read all of them.
6. Rebuild from a known-good image rather than restarting the existing one.

---

## Afterwards

- Record what happened and which control caught it — or did not.
- If nothing caught it, that is the finding: add a detection rule or a Security Lab scenario.
- Thresholds tuned during an incident should be revisited once it is over.

## Limitations

- **No alerting.** Everything here starts with a human looking.
- **No automated containment.** Detection never blocks an account.
- **No tested runbook.** None of this has been exercised.
- **No forensic retention policy.** Nothing guarantees evidence is preserved before cleanup.
- **No defined notification path** for a confirmed disclosure.
