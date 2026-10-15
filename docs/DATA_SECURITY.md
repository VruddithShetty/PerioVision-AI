# PerioVision AI: Data Security

The classification below is not a document that describes the code — it is generated from
`app/security/retention.py`, which is the same list the application enforces. A test checks
that every store the application writes to appears here, so the two cannot drift.

---

## 1. Classification

| Store | Class | Holds | Protection | Retention | Purgeable |
|---|---|---|---|---|---|
| `patients` | **Patient** | name, contact, notes, risk factors | AES-256-GCM per field + blind index | while active | No |
| `analyses` | **Patient** | per-tooth measurements, staging, risk | blobs AES-256-GCM | with the patient | No |
| `reports` | **Patient** | PDF hash, RSA-PSS signature | PDF blob AES-256-GCM | with the patient | No |
| `perio_charts` | **Patient** | pocket depths, recession, bleeding | scoped by authorization | with the patient | No |
| `corrections` | **Patient** | clinician corrections to model output | pseudonymous | retraining provenance | No |
| `uploads` | **Patient** | radiograph metadata + blob reference | blob AES-256-GCM | TTL, then purgeable | **Yes** |
| `doctors` | Confidential | accounts, bcrypt hashes, TOTP secrets | hashed / at rest | while the account exists | No |
| `audit_logs` | Confidential | who, what, when, resource, result | hash-chained, pseudonymous | indefinite | **Never** |
| `merkle_roots` | Confidential | anchored roots | HMAC-authenticated | indefinite | **Never** |
| `sessions` | Internal | session IDs, fingerprints, refresh IDs | no PHI | 30 days after last use | **Yes** |
| `security_decoys` | Internal | decoy patient records | as real records | while deployed | No |
| `meta` | Internal | counters, schema markers | none | indefinite | No |

Only **one** patient-class store is purgeable: `uploads`, and only when the upload never
became an analysis. Everything clinical is excluded by design.

## 2. Encryption

- **Fields** — `patient_name`, `contact_number`, `notes` are AES-256-GCM with the field name
  as associated data, so a ciphertext cannot be moved from one field to another.
- **Blobs** — radiographs, overlays and report PDFs, each with its purpose as AAD. A
  radiograph cannot be served as a report.
- **Search** — an HMAC blind index on a key derived separately via HKDF, so exact-match
  lookup survives encryption without the encryption key doing double duty.
- **Logs and analytics** — patients appear as `P-xxxxxxxxxx` pseudonyms, derived with a
  third HKDF key. No audit entry contains a name, contact number or note.

## 3. Retention

Two operations, and the distinction is the point:

```
plan()   reports what is due.  Changes nothing.
purge()  removes it.           Runs only when called. Nothing schedules it.
```

Clinical records are the evidence behind a diagnosis and any report issued from it, so
removing them is a practice decision taken with the plan in hand — not a nightly job.

`assert_purgeable(store)` refuses three categories:

- **Protected** — `audit_logs`, `merkle_roots`. These are a hash chain: deleting an old
  entry does not reclaim space, it breaks verification for every entry after it and makes
  the trail look tampered with. A conventional "delete older than N days" sweep applied
  across all collections would destroy the one control that proves nothing else was
  destroyed.
- **Clinical and account stores** — refused with the reason, not silently skipped.
- **Unclassified stores** — a store nobody has classified is refused rather than assumed
  safe, so adding a collection cannot quietly opt it into deletion.

## 4. Orphaned blobs

The leak retention was built to close. An upload record carries a TTL; nothing acted on it,
and `storage_service` had no delete path at all. The record expired and the encrypted
radiograph stayed on disk indefinitely — PHI outliving the record that pointed at it.

`orphaned_blobs()` walks `analyses`, `uploads` and `reports`, collects every referenced blob
ID, and reports the files on disk that nothing points at. `purge()` removes rows first and
blobs second, so the two never disagree about what is still referenced. A radiograph an
analysis still references is kept — there is a test for exactly that.

## 5. Patient isolation

Every patient-scoped route reaches `load_patient_or_404`, which returns a record only if the
caller owns it or is on its care team. Admins see all patients; auditors see none.

Out-of-scope records return **404 with a body identical to a genuine miss**. A 403 would
confirm the record exists, turning any patient endpoint into an enumeration oracle.

## 6. What this does not do

- **No automatic deletion.** Nothing is scheduled. If nobody calls `purge()`, nothing is
  removed — deliberate, but it means retention only happens when someone makes it happen.
- **No right-to-erasure workflow.** Removing one patient on request is not implemented;
  it would need a cascade across six stores and the blob store, and a decision about what
  happens to signed reports that referenced them.
- **No backup policy.** Backups are a deployment concern and nothing here covers them.
- **Secure deletion is unlink, not overwrite.** On a journalling filesystem or SSD the
  ciphertext may survive physically. The data is encrypted, so this is defence in depth
  rather than a gap, but it is not cryptographic erasure.
