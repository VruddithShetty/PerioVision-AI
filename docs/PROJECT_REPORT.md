# PerioVision AI: Project Report

_Version as of 28 September 2026, local branch `restructure/phase-1`, commit 41d25d9 plus this report._

---

## 1. Executive summary

PerioVision AI is a secure, explainable clinical decision-support system for **periodontal bone-loss detection** on dental radiographs. For every tooth it detects the tooth and its FDI number, finds the cemento-enamel junction (CEJ), the alveolar bone crest and the root apex, measures radiographic bone loss, and suggests a periodontitis **stage (I–IV)** and **grade (A–C)** following the 2017 AAP/EFP classification. It then:

- tracks each tooth **across visits**, measuring the rate of bone loss and flagging comparisons it cannot trust;
- shows **where the AI looked** (Grad-CAM) and flags cases where attention is outside the periodontal region;
- puts an **honest uncertainty range** on each measurement (split-conformal prediction) and forces **mandatory dentist review** whenever anything is uncertain;
- combines image findings with **clinical risk factors** (age, smoking, diabetes/HbA1c) into a risk score with plain-language reasons;
- issues **digitally signed, QR-verifiable PDF reports**, only after a dentist signs off.

Around the clinical engine is a security architecture built for a cybersecurity thesis:

- **Protecting data:** AES-256-GCM encryption with key rotation, and RSA-PSS signatures on models and reports.
- **Controlling access:** bcrypt passwords, short-lived JWTs with TOTP multi-factor authentication, four-role RBAC, and a Zero Trust guard that re-checks every request.
- **Detecting tampering:** a hash-chained, Merkle-anchored audit log, an upload guard, adversarial-input screening and decoy (honeypot) records.
- **Demonstrating the defences:** a **Security Lab** that runs live attacks and shows each one being blocked.

A premium React web application with 3D dental visuals exposes the whole workflow. It also adds four **chairside tools for dentists**: a 6-point periodontal chart with clinical-vs-radiographic concordance, an EFP-based care plan, a patient explainer with a "what-if" forecast, and a clinic recall board.

**Current state:** all 7 project phases are complete. There are 74 automated backend tests, all passing, and the frontend type-checks, lints and builds cleanly. Every page was verified in the browser for the dentist, admin and auditor roles.

The main limitations are honest ones:

- both models are trained and measured on held-out test sets (detector 95.8 % mAP@0.5; landmarks bone-loss error 7.6 points, 73 % stage agreement), but landmarks are validated on periapical X-rays only;
- uncertainty is calibrated (91.5 % coverage at 90 %) but wide, so most teeth still go to dentist review;
- the risk score is a transparent rule-assisted demo rather than a trained model.

Section 10 explains each of these.

> Clinical decision-support system. Not a certified medical device; no clinical accuracy is claimed. Security controls are aligned with HIPAA safeguards, not certified.

---

## 2. How the project got here

| Phase | Outcome |
|---|---|
| **0 Audit** | (Original audit document, since superseded by `docs/VERIFICATION_REPORT.md`.) Key findings: the repository is **public** and its history contains ~2,000 radiographs whose file names include what look like real patient names. Other findings: an unauthenticated endpoint could read `.env` and the private signing key; a hard-coded superadmin password; a random-data risk model; the key file could be deleted on a wrong password; inactive MFA; security modules that were never called; three broken UIs; no tests. |
| **1 Restructure** | Moved to `backend/ frontend/ docs/ data/ notebooks/ tools/`. 104 files moved or restored with `git mv`, **nothing deleted**; every move is recorded in the git history. The monolithic server was split into an app factory and blueprints. Hard-coded secrets were moved to `.env`. |
| **2 Must-have features** | Rebuilt the security core, the ML pipeline, uncertainty, progression, risk, encrypted storage, signed reports and the API. |
| **3 Improvements** | Security Lab, demo seeding, CI workflow, and the review queue / model trust / status endpoints. |
| **4 Frontend** | React 18 + TypeScript app: 15 required pages plus 3D scenes. |
| **Extra** | Four chairside clinician tools, added on request. |
| **5 API contract** | OpenAPI spec generated from the code, plus `docs/API.md` built from 48 live calls; contract tests. |
| **6 Docs & quality** | Traceability matrix, architecture, viva cheat sheet, beginner README, optional HTTPS. |
| **7 Verification** | Full test and build run, plus a page-by-page browser walkthrough (superseded by `docs/VERIFICATION_REPORT.md`). |

---

## 3. Architecture

```
React 18 web app (frontend/)
   │  access token in memory · refresh token = httpOnly SameSite=Strict cookie
   ▼  HTTPS (TLS proxy in production; optional self-signed cert locally)
Flask API (backend/app)
   ├─ security headers · CORS allow-list · rate limiting
   ├─ Zero Trust guard: token → session → device → account → RBAC permission (deny by default)
   ├─ api/        thin routes, pydantic validation, envelope {data, meta, error, mode}
   ├─ services/   analysis pipeline · progression · reports · clinical tools · Security Lab · demo seed
   ├─ ml/         quality gate → CLAHE → YOLOv8 (FDI) → CEJ/crest/apex → bone loss & staging
   │              → Grad-CAM + ROI check → conformal interval → OOD/adversarial → review router → risk
   │              registry.py verifies the RSA-PSS signed weight manifest BEFORE loading
   └─ security/   crypto (AES-256-GCM) · model_signing (RSA-PSS) · auth (bcrypt/JWT/TOTP)
                  rbac · zero_trust · audit_log (hash chain + Merkle) · upload_guard · adversarial · honeypot
   ▼
MongoDB (mongomock in demo) · encrypted blob store (radiographs, overlays, PDFs) · audit anchors outside the DB
```

**Technology:** Python 3 / Flask 3, MongoDB (pymongo, mongomock), PyTorch + Ultralytics YOLOv8, OpenCV, scikit-image, cryptography, PyJWT, pyotp, ReportLab, pydantic. On the frontend: React 18, Vite 5, TypeScript (strict), Tailwind, React Router 7, TanStack Query, Zustand, Framer Motion, three.js (@react-three/fiber, drei, postprocessing) and Recharts. All dependencies are pinned, and `npm audit` reports 0 runtime vulnerabilities.

**Modes:** `demo` uses an in-memory database seeded with synthetic patients, shows a visible banner and returns `"mode": "demo"` in every response. `live` uses MongoDB, and the app refuses to start without its secrets.

More detail: `docs/ARCHITECTURE.md`.

---

## 4. Clinical AI: objectives O1–O5

### O1 Bone-loss detection
- **Quality gate** (`ml/preprocessing/quality_check.py`): checks resolution, sharpness (Laplacian variance at 1024 px), contrast and exposure. The outcome is reject, warn (the case goes to review) or pass. Thresholds were calibrated on real panoramic radiographs.
- **CLAHE** contrast enhancement, at the original resolution so all coordinates stay aligned.
- **YOLOv8 detection** (`ml/detection/yolo_detector.py`): the trained detector has 32 classes named by FDI number (11–48), so a tooth's class *is* its tooth number. This fixed the old "11 + i" numbering. Teeth without a model-assigned number are labelled as estimates.
- **Landmarks** (`ml/landmarks/cej_abc_extractor.py`): a YOLOv8-pose model predicts CEJ, apex and crest. When it finds no confident match, a labelled geometric fallback is used and the case goes to review.
- **Bone loss** (`ml/measurement/bone_loss.py`): the CEJ→crest vector is projected onto the CEJ→apex axis and expressed as a % of root length. It is also given in mm when DICOM pixel spacing is known.
- **Staging and grading** (`ml/measurement/staging.py`):
  - Stage: I < 15 %, II 15–33 %, III > 33 %, and IV when at least 5 teeth have been lost to periodontitis.
  - Grade: from the observed progression rate, or from % bone loss divided by age.
  - Risk factors can raise the grade: smoking ≥ 10 per day or HbA1c ≥ 7 % → C.
- **Per-tooth output:** id, bbox, CEJ, ABC, apex, bone loss %, mm, stage, confidence, uncertainty, ROI attention and flags.

### O2 Longitudinal progression (`services/progression_service.py`)
- Every analysis is stored per patient and per visit date.
- Teeth are matched by FDI number. Otherwise they are matched by position after registering the two radiographs (ORB features plus an affine transform).
- The service computes delta, velocity (% per month and per year) and a label: stable, progressing, rapidly progressing or improved.
- A comparison is marked **unreliable, never silently computed**, when registration is poor or missing, a positional match lacks good registration, landmarks were estimated, or the visits are less than 30 days apart.

### O3 Explainability (`ml/explainability/`)
- **Grad-CAM** in a single backward pass over the YOLOv8 neck layers (P3–P5), stored as a transparent RGBA layer so the viewer can fade it with an opacity slider.
- **ROI attention check:** the share of the attention inside each tooth box that falls in the periodontal band (CEJ to crest). A low share raises `low_attention_validity` and sends the case to review.

### O4 Uncertainty (`ml/uncertainty/`)
- **Split-conformal prediction** on bone-loss %. The threshold is the ⌈(n+1)(1−α)⌉-th smallest calibration error, and coverage is configurable (default 90 %).
- **Stage prediction sets:** every stage whose band overlaps the interval. More than one stage means review.
- **Out-of-distribution checks:** brightness, contrast, aspect ratio, no teeth detected, and adversarial triggers.
- **Review router:** any of these makes the case "Mandatory clinician review": uncalibrated uncertainty, an ambiguous stage, low quality, an OOD or adversarial image, off-target attention, heuristic landmarks, low confidence, or demo mode. A signed report is blocked until a dentist signs off.
- Calibration is written to `weights/conformal_calibration.json` by `scripts/calibrate_conformal.py`, which reserves half the scores to measure the coverage actually achieved.

### O5 Multimodal risk fusion (`ml/fusion/multimodal_risk.py`)
- **Inputs:** age, smoking status and cigarettes per day, diabetes, HbA1c; mean and max bone loss, number of affected teeth, and progression velocity.
- **Output:** low, moderate or high, a score, and the top contributing factors in plain language (exact linear contributions, the SHAP idea for a linear model).
- **Honesty:** no outcome dataset exists, so this is a documented **rule-assisted demo** with hand-set weights that follow the direction of the literature. Every response, page and report says so.

---

## 5. Cybersecurity: objective O6

| Control | Implementation | What it defends against |
|---|---|---|
| **AES-256-GCM** | `security/crypto.py`. Fresh random 96-bit nonce per message; key IDs in every ciphertext; key ring, KMS-style key file and a `rotate_keys.py` script; HKDF-separated keys for the blind index and pseudonyms; purpose-bound associated data for files | Theft or silent modification of PHI, radiographs and reports |
| **RSA-PSS signatures** | `security/model_signing.py`, `ml/registry.py`, `scripts/sign_model.py`. Signed SHA-256 manifest of all weights; the registry refuses to load unsigned or altered files and logs `MODEL_LOAD_REFUSED`. Report PDFs are hashed and signed, carry a QR code, and are checked at `/api/reports/verify` | Model tampering, forged or edited reports |
| **bcrypt + password policy + lockout** | `security/auth.py`, `models/doctors.py`. Cost 12; 5 failures → 15-minute lock | Password cracking, brute force |
| **JWT access + refresh** | 15-minute access token bound to a device fingerprint and a server-side session. The 7-day refresh token is an httpOnly cookie, rotated on every use; **reuse revokes the session** | Stolen or replayed tokens |
| **TOTP MFA** | QR enrolment, 6-digit codes, replay protection | Stolen passwords |
| **RBAC** | `security/rbac.py`. Admin, dentist, technician and auditor with an explicit permission matrix, plus object-level patient access (owner or care team). Auditors never see PHI; admins make no clinical decisions | Privilege misuse, IDOR |
| **Zero Trust guard** | `security/zero_trust.py`. Every request re-checks token, session, device, account state and permission. **Routes without a rule are denied** | Forgotten checks, revoked users, lateral movement |
| **Tamper-evident audit log** | `security/audit_log.py`, `scripts/verify_audit.py`. The hash chain includes the genesis entry, sequence numbers are unique, and Merkle roots are anchored every 20 entries with an HMAC key outside the database. Verification names the **first tampered entry**. Logs contain no PHI (pseudonyms and hashed IPs only) | Undetected log edits, deletions or full rewrites |
| **Upload guard** | `security/upload_guard.py`. Size, extension and magic bytes; pixel limits; re-encoding strips EXIF; DICOM patient tags are removed; random names | Disguised malware, decompression bombs, metadata leaks, path traversal |
| **Adversarial screening** | `security/adversarial.py`. Noise-residual test calibrated on 30 real radiographs: 0 false alarms, catches ±8 grey-level perturbation | Manipulated inputs |
| **Decoy records** | `security/honeypot.py`. Realistic, unflagged decoys tracked by HMAC tag; opening one revokes sessions and locks the account for 60 minutes | ID enumeration, insider browsing |
| **Secure coding** | Pydantic schemas (unknown fields rejected, which blocks NoSQL operator injection), a CSP of `default-src 'none'`, nosniff, frame DENY, no-referrer, HSTS on HTTPS, a CORS allow-list, generic error messages, debug off, pinned dependencies | OWASP Top 10 classes |
| **TLS** | TLS proxy in production. `scripts/make_dev_cert.py` plus `TLS_CERT`/`TLS_KEY` give local HTTPS | Eavesdropping |
| **Privacy** | Pseudonymised patient IDs (`P-…`), encrypted identity fields with blind-index search, and a HIPAA-aligned mapping in `docs/SECURITY.md` | Unnecessary PHI exposure |

**Security Lab** (`services/security_lab.py`, Security Lab page). It runs seven real attacks against throwaway material: a tampered model file; an edited audit entry, including a full chain rewrite; replayed, forged and `alg:none` JWTs; disguised uploads; an edited report; adversarial noise; and tampered ciphertext. **7 of 7 attacks were blocked.**

**Bugs found and fixed along the way:**
- The old adversarial detector flagged *every* real X-ray.
- The old genesis audit entry was never verified.
- Unauthenticated file read of `.env` and the private key.
- Access-denied replies were missing the `mode` field (caught by the contract tests).

---

## 6. The clinical workflow: objective O7

Login (+ MFA) → select or create a patient → upload the radiograph (upload guard + quality preview) → analysis → review the teeth in the viewer (radiograph layers, dental chart, 3D arch, uncertainty bar, risk gauge) → progression timeline → the review queue, where a dentist approves, corrects or rejects (corrections are stored for retraining) → signed PDF report → public QR verification → every step in the audit trail.

This was verified end to end both in the browser and in `tests/test_api.py::test_end_to_end_workflow`.

---

## 7. Web application

- **Design:** a dark clinical theme (navy, cyan/teal, amber for review, red for critical), glass cards, and the Syne, Inter and JetBrains Mono fonts. Pages have smooth transitions and skeleton, empty and error states. The app is keyboard accessible, and every page respects role permissions.
- **3D (three.js):**
  - a procedural molar hero with a shield, particles and bloom;
  - a clickable 3D dental arch with gums, synced with the 2D viewer;
  - an audit hash chain where tampered blocks turn red;
  - a trust orb with a tooth at its core.

  The scenes are lazy-loaded, with static fallbacks for devices without WebGL, weak devices and reduced-motion settings.
- **Dental interactives:** a drag-to-reveal panoramic scanner, a staging explorer with an animated tooth cross-section (enamel, CEJ, periodontal ligament, pulp, bone, gingiva), a pan/zoom radiograph viewer with 5 layers and a Grad-CAM opacity slider, an FDI odontogram, a per-tooth panel with the conformal interval bar, and a before/after visit slider.
- **Pages (15 required, plus 4 extra):**
  - Required: landing, login + MFA, dashboard, patients, new analysis, analysis viewer, progression, review queue, model trust, security center, Security Lab, reports, admin, about/architecture, and the 404 and access-denied pages.
  - Extra: public report verification.

---

## 8. Chairside tools for dentists (beyond the synopsis)

| Tool | What it does |
|---|---|
| **Periodontal chart** | Fast 6-site probing entry for 32 teeth (probing depth, recession, bleeding, plaque, mobility, furcation) with auto-advance, pocket graphs, copy-forward, and "deepened ≥ 2 mm" markers. Computes CAL, BOP %, plaque %, sites ≥ 4/6 mm and the clinical stage. **Clinical–radiographic concordance** compares probing and the X-ray AI tooth by tooth and explains disagreements (for example, a possible angular defect). |
| **Care plan** | Combined stage and grade with its reasons; an EFP S3 step-wise therapy checklist; a per-tooth prognosis map (simplified Kwok & Caton); a risk-based recall interval (3, 4 or 6 months) with the next due date; a ready-to-send periodontist referral letter. |
| **Patient explainer** | A plain-language chairside screen with a smile summary and tooth cross-section, and a **what-if** simulator: quit smoking, lower HbA1c, clean between the teeth daily, keep recalls. It shows a 10-year projection and is clearly labelled as an illustration. |
| **Recall board** | A clinic-wide list of overdue, due-soon and scheduled maintenance visits, ranked by risk, with referral flags. |

---

## 9. Quality, testing and documentation

**Automated tests:** 74 backend tests, all passing, in `backend/tests/`.

| Area | Tests |
|---|---|
| Crypto | Round trip, nonce uniqueness (200 samples), tamper detection, associated-data binding, key rotation, weak-key refusal |
| Signing | Sign and verify, no key overwrite, wrong password keeps the key, manifest tamper, forged manifest, registry refusal |
| Audit chain | Clean chain, modified entry pinpointed, genesis checked, deletion, consistent rewrite caught by the anchor, forged anchor |
| Upload guard | EXE or PDF disguised as an image, traversal names, size and pixel limits, EXIF stripping |
| ML logic | Bone-loss geometry, staging, grade modifiers, conformal quantile formula and **empirical coverage (0.88–0.93 at 90 %)**, prediction sets, review router, progression labels and unreliability, quality gate, adversarial detection, risk monotonicity |
| API security | Envelope and headers, CORS, deny by default, generic errors, lockout, NoSQL injection, tampered, expired and other-device tokens, refresh-token reuse, logout, full MFA flow, RBAC matrix, patient isolation, honeypot |
| End to end | Upload → analysis → progression → blocked report → sign-off → signed PDF → verify → tampered PDF fails → audit intact and PHI-free |
| Phase 3 + clinical + contract | Security Lab 7/7, demo seed, chart indices, concordance, prognosis, recall, care plan API, OpenAPI completeness |

**Frontend:** TypeScript strict with 0 errors, ESLint with 0 errors, and a clean production build. The 3D code is split into its own lazy chunk.

**CI:** `.github/workflows/ci.yml` runs ruff and pytest on the backend, and lint and build on the frontend.

**Browser verification:** every route was checked as dentist, admin and auditor. Role denials and the 404 page behave correctly. The walkthrough covered sign-off → signed report → "Authentic, unaltered report".

**Documentation in `docs/`:**

| Document | Contents |
|---|---|
| `ARCHITECTURE.md` | Diagram, request flow and trust boundaries |
| `SECURITY.md` | Threat model, permission matrix and HIPAA-aligned mapping |
| `API.md` | 48 live request/response examples, plus `openapi.json` |
| `TRACEABILITY.md` | Objective → module → API → UI page → test |
| `MODEL_CARD.md` | Intended use, component status, limitations |
| `DATASETS.md` | Datasets in use and how to plug in new ones |
| `KEY_ROTATION.md` | Steps for rotating encryption and signing keys |

---

## 10. Honest limitations

1. **Landmarks validated on periapical X-rays only.** The landmark model (YOLO11m-pose on DenPAR) reached 99.0 % tooth recall, bone-loss MAE 7.64 points and 73.1 % stage agreement on 200 held-out periapical X-rays; on panoramic images it is applied to zoomed crops and those teeth are always reviewed. Earlier state: The tooth detector was retrained (YOLO11m on public DENTEX data, free Colab GPU). It scores 94.1 % precision, 94.5 % recall, 95.8 % mAP@0.5 and 94.8 % tooth-level F1 on 63 held-out test X-rays, and it found 26 teeth on a real image where the old model found 2. The keypoint model still predicts one box spanning many teeth, so landmarks fall back to labelled estimates; its training labels were generated geometrically, not drawn by clinicians.
2. **Uncertainty is calibrated but wide.** Conformal calibration on DenPAR validation teeth gives 91.5 % coverage on the test split at the 90 % target, with a radius of 18.6 points, so only about 10 % of teeth get a single-stage answer and the rest are reviewed.
3. **Risk model is a rule-assisted demo**, because there is no outcome data.
4. **Accuracy is claimed only where it was measured.** Detector metrics come from the DENTEX test split, landmark and bone-loss metrics from the DenPAR test split; nothing is claimed for panoramic landmark accuracy.
5. **Demo mode is in-memory**, so its data resets on restart. The development server is HTTP unless the local certificate is used.
6. **Decoy records** are hidden from normal lists by a system owner ID that someone with direct database access could notice. They are designed against API-level probing.
7. **The public repository history** still contains the patient-named Roboflow images (audit finding G2).
8. **The synopsis PDF and PPT** were never provided, so objective wording follows the master prompt.

---

## 11. How to run

```powershell
copy .env.example .env      # DB_MODE=demo, secrets, DEMO_* accounts (see README)
.\run.ps1 setup
.\run.ps1 demo              # backend  → http://127.0.0.1:5000  (OpenAPI: /api/docs)
.\run.ps1 frontend          # web app  → http://localhost:5173
```

Sign in with a `DEMO_*` account from `.env`; these accounts are for demos only. The other shortcuts are `.\run.ps1 test`, `.\run.ps1 lint` and `.\run.ps1 docs`.

---

## 12. Recommended next steps

1. **Make the GitHub repository private** (or rewrite its history), then push branch `restructure/phase-1`.
2. **Retrain the detector and keypoint models on clinician-annotated radiographs** (for example DENTEX plus per-tooth CEJ, crest and apex annotations) on a GPU, then sign the new weights with `scripts/sign_model.py`.
3. **Calibrate uncertainty** on a held-out annotated split with `scripts/calibrate_conformal.py`. Only then report real metrics in the model card.
4. **Collect longitudinal outcome data** to replace the rule-assisted risk score with a validated model.
5. **Replace the demo secrets** (new encryption key ring plus `rotate_keys.py`, a new signing key pair and password), remove the demo accounts, and deploy behind a TLS reverse proxy with MongoDB authentication.
6. Add the synopsis and slides to `docs/reference/`, add screenshots to the README.
