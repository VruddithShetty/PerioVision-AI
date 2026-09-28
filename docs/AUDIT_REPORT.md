# PerioVision AI — Phase 0 Audit Report

- **Date:** 2026-09-28
- **Scope:** everything under `Dental_progression/` (git root) with the app in `dental_progression_ai/`, plus a read-only look at the dataset folder `C:\Users\vrudd\Downloads\DP_datasets`.
- **Method:** I read the source and ran a static import check. I didn't start the server, because importing `server.py` trains and signs a risk model at import time, and `ModelIntegrityVerifier._get_private_key()` **deletes `keys/model_signing.pem`** if the password doesn't match (`src/security/integrity.py:22-32`). Running it would have changed or destroyed files, which Phase 0 forbids.
- **Changes made:** this file only. Nothing was moved, deleted or committed.

> **Reference material missing.** `docs/reference/` does not exist, so the synopsis PDF and PPT were not available. The 7 objectives below come from the master prompt (O1–O7). Please drop `PerioVision_Synopsis.pdf` and `PerioVision_AI.pptx` into `dental_progression_ai/docs/reference/` so the traceability table in Phase 6 can quote the synopsis directly.

---

## 1. Read this first: git state and data exposure

| # | Finding | Severity |
|---|---|---|
| G1 | **5,680 tracked files are deleted in the working tree but not committed.** Most are datasets (`real_datasets/`, `custom_datasets/pose`, `custom_datasets/seg`). The rest are the old Streamlit UI (`web_app/`, `src/ui/`), the Flask template and static files (`web/templates/index.html`, `web/static/*`), `requirements.txt`, `test_pipeline.py`, and old module folders (`analysis/`, `database/`, `image_processing/`, …). They were removed today, and `PROJECT_STRUCTURE.md` describes the result. All of them can still be recovered with `git restore`. | High (risk of losing work) |
| G2 | **The GitHub repo `VruddithShetty/PerioVision-AI` is public** (the unauthenticated GitHub API returns 200). Commit `dc1051b`/`d17198f` contains **1,961 files of `real_datasets/tooth_detection`**. Many file names contain what look like **real patient names and dates**, e.g. `HRISHI_jpg…`, `JENIKA-BHARDWAJ_2013-11-21-pdf_page_1…`, `AGASTYA_jpg…`, `MEDHA_2015-05-25…`. The Roboflow source is CC BY 4.0, but names in file names count as patient identifiers. Deleting the files locally does **not** remove them from GitHub history. | **Critical (privacy)** |
| G3 | The private signing key `keys/model_signing.pem` is untracked **and not git-ignored**, so a `git add .` would publish it. It was **not** found in the pushed history (checked). | High |
| G4 | `dental_progression_ai/.gitignore` is saved as UTF-16. Git can't parse that encoding, so **none of its rules apply**. | Medium |
| G5 | Untracked but present: the new `scripts/`, `models/weights/*.pt` (5 files, ~44 MB), `models/risk_model/*`, `orchestrator.py`, `docs/*.md`, Docker files. Weights should be git-ignored per the target layout. | Info |

Only the user can do these, because they can't be undone from here: make the repo private (or purge history with `git filter-repo` and force-push), and decide whether to keep the cleanup. See §7.

---

## 2. Current folder tree (working copy, datasets and caches omitted)

```
Dental_progression/                      <- git root
├── .gitignore  README.md (modified)  PROJECT_STRUCTURE.md (new)  powershell.bat
└── dental_progression_ai/
    ├── .env  .env.example  .gitignore (UTF-16, broken)
    ├── Dockerfile  docker-compose.yml  pyproject.toml
    ├── server.py            # Flask API (793 lines) — the only runnable backend
    ├── wsgi.py              # entry point, injects hard-coded fallback keys
    ├── orchestrator.py      # BROKEN: imports 9 modules that no longer exist
    ├── evaluate_talpa.py
    ├── docs/  KEY_ROTATION.md  PRODUCTION_DEPLOYMENT.md  README_SECURITY.md  TALPA.md
    ├── keys/  model_signing.pem (private!)  model_signing.pub
    ├── logs/  (empty)
    ├── models/
    │   ├── inference.py     # second, duplicate detector/landmark pipeline (ONNX + YOLO)
    │   ├── weights/  dental_yolov8n.pt  tooth_detection_yolov8n.pt  dental_landmark_yolov8n-pose.pt
    │   │             dental_bone_yolov8n-seg.pt  yolov8n.pt      (no .sig files)
    │   ├── landmark_detection_model/  landmark_cnn.pt  training_log.csv
    │   └── risk_model/  risk_model.pkl  model_metadata.json  *.png
    ├── scripts/  12 training / dataset / setup scripts
    └── src/
        ├── analysis/  progression_velocity_calculator.py (870 lines, TALPA engine)
        ├── core/      alignment bone_loss preprocessing progression progression_map
        │              report risk talpa velocity visualization audit_middleware
        ├── database/  connection doctors patients xrays audit appointments
        │              notifications id_generator talpa_records
        ├── models/    detection.py (YOLO + Grad-CAM)  landmarks.py (YOLO-pose)
        └── security/  encryption integrity merkle rbac session uploads honeypot
                       adversarial watermark headers secrets governance checks
                       orchestrator readiness threat_intel
```

There is **no frontend** (the React app doesn't exist, and the old HTML/Streamlit UIs are deleted). There are **no tests**, **no CI**, and **no `requirements.txt`** (the Dockerfile still `COPY`s it, so the Docker build fails).

---

## 3. Objectives and features: status

Legend: ✅ implemented · 🟡 partial / present but not wired or not trustworthy · ❌ missing

### O1 — Bone-loss detection
| Feature | Status | Evidence / notes |
|---|---|---|
| CLAHE + normalisation | ✅ | `src/core/preprocessing.py:6-22` |
| Image-quality gate (blur, contrast, resolution) | ❌ | Nothing rejects or warns on bad radiographs |
| YOLOv8 tooth detection | 🟡 | `src/models/detection.py:143-262`. Weights exist, but **tooth numbers are fake**: `"tooth_number": str(11 + i)` (line 239) numbers teeth by detection order, not FDI class |
| CEJ + ABC landmark extraction | 🟡 | `src/models/landmarks.py`. YOLO-pose with 3 keypoints. Likely coordinate mismatch: detection runs on the original image, while landmarks run on the 512×512 float [0,1] preprocessed image, and the two are then IoU-matched. Most teeth probably fall back to `heuristic_fallback` (fixed ratios of the box). *Inferred from code, not run.* |
| Bone-loss % per tooth | ✅ | `src/core/bone_loss.py` (CEJ→crest projected on CEJ→apex) |
| Stage I–IV / Grade A–C | 🟡 | Grade A–C in `src/analysis/progression_velocity_calculator.py:202` and `src/core/talpa.py`. **No Stage I–IV**: the labels are "Healthy/Gingivitis/Periodontitis" at 15/30% (`bone_loss.py:34`), which isn't Tonetti staging |
| Per-tooth output (id, bbox, CEJ, ABC, %, stage, confidence) | 🟡 | `/api/analyze` returns id, %, severity, grade, risk and flags, but **no bbox, CEJ/ABC points, stage or confidence** (`server.py:537-546`) |

### O2 — Longitudinal progression
| Feature | Status | Evidence / notes |
|---|---|---|
| Store every analysis per patient/visit | ✅ | `src/database/xrays.py:create_record` |
| Match teeth across visits | 🟡 | By string tooth id only. Since ids are detection order (O1), matching is unreliable. No spatial fallback |
| Delta + velocity | ✅ | `src/core/progression.py`, `progression_velocity_calculator.py` (a large, well-structured engine) |
| Labels stable / progressing / rapid / improved | 🟡 | Only "Stable / Progressing / Unknown" (`progression.py:68-70`). No "rapid" or "improved" |
| Register radiographs before comparing | 🟡 | `src/core/alignment.py` has ORB/ECC and landmark alignment, but `/api/analyze` never calls it. Only `calibrate_pixels_per_mm` is used |
| Flag unreliable comparisons | 🟡 | `estimated` / `proxy_mm` flags exist. Historical visits always use a **proxy mm = 2 + bl%/10** (`server.py:139`) |

### O3 — Explainability (Grad-CAM)
| Feature | Status | Evidence / notes |
|---|---|---|
| Grad-CAM per prediction | 🟡 | `YOLOGradCAM` in `detection.py:22-121` computes heatmaps, but **they aren't stored or returned**. Only a scalar `heatmap_agreement` survives |
| Overlay in UI with opacity slider | ❌ | No UI; no overlay image saved |
| Low-attention-validity → review | 🟡 | `reliability_flag = "attention_mismatch"` when agreement < 0.45 (`detection.py:227`), but nothing routes it to review |

### O4 — Uncertainty (conformal prediction)
| Feature | Status | Evidence |
|---|---|---|
| Split-conformal calibration, prediction sets, coverage | ❌ | No conformal code anywhere |
| `review_router` (mandatory clinician review) | ❌ | — |
| Calibration/coverage report | ❌ | `models/risk_model/calibration_plot.png` exists but comes from a synthetic-data model |

### O5 — Multimodal risk fusion
| Feature | Status | Evidence / notes |
|---|---|---|
| Inputs age, smoking, diabetes, HbA1c + image features | 🟡 | Smoking cpd and HbA1c are used only as grade escalators. The risk model features are bl%, velocity, age, tooth position, prev bl%, years. No diabetes flag, and **smoking/HbA1c aren't model inputs** |
| Risk category + probability | 🟡 | `src/core/risk.py` returns low/med/high + probabilities, **but the model is trained on `np.random.rand` features with random labels** (`risk.py:36-40`) whenever the signed pkl fails to load. `scripts/train_risk_model.py` also uses synthetic data. The outputs are effectively random |
| Plain-language top factors (SHAP/coefficients) | ❌ | — |

### O6 — Cybersecurity mechanisms
| Control | Status | Evidence / notes |
|---|---|---|
| AES-256-GCM at rest, random nonce | 🟡 | `src/security/encryption.py:44-47` is correct, but it covers only patient name, contact and notes. **Radiographs, annotated images and PDF reports are written to disk in plaintext** |
| Key management / rotation | 🟡 | Key from env. No key id on ciphertexts, so rotation isn't possible without re-encrypting everything. `docs/KEY_ROTATION.md` describes a process the code doesn't support |
| TLS/HTTPS | ❌ | `app.run(... debug=True)` over HTTP (`server.py:793`) |
| bcrypt | ✅ | `src/database/doctors.py:12-16` (12 rounds) |
| JWT access + refresh | ❌ | No JWT. Uses a Flask cookie session |
| TOTP MFA with QR enrolment | 🟡 | `verify_totp` exists and the login checks it, but **nothing ever sets `two_factor_enabled=True`** and there's no enrolment/QR endpoint, so MFA is never active |
| Account lockout | ✅ | 5 failures → 15 min (`doctors.py:77-80`) |
| Rate limiting | 🟡 | flask-limiter: 60/min default, 5/min login, 10/min analyze. In-memory store. `/api/register` is only default-limited |
| RBAC admin/dentist/technician/auditor | 🟡 | `src/security/rbac.py` has a **hierarchical** viewer/doctor/admin/superadmin, not the 4 required roles. No technician/auditor role. Checks are hand-written per route, with no decorator or permission matrix |
| Zero Trust per-request verification | ❌ | Role is read from the session cookie, and some routes trust it without a DB re-check |
| Model signing RSA-PSS + refuse unsigned | 🟡 | `src/security/integrity.py` implements RSA-4096 PSS sign/verify, but **YOLO models load even when verification fails**: it only `print`s (`detection.py:159-164`, `landmarks.py:278-284`). **No `.sig` files exist** for any weight. The risk model is **re-signed automatically at startup** after retraining on random data, which defeats the purpose |
| Report hash + signature + /verify | 🟡 | `src/core/report.py:15-28` signs only `record_id:timestamp` (not the report content) and prints a **truncated** signature. No verify endpoint. No QR |
| Hash-chained audit log + Merkle root + verify | 🟡 | `src/security/merkle.py`. See security findings S5–S8 |
| Log every event, never plaintext PHI | 🟡 | `audit_action` decorator on most routes, but it logs **email, IP and user agent in plaintext** (`src/core/audit_middleware.py:37-48`) |
| Upload guard (magic bytes, size, EXIF strip, traversal) | 🟡 | Inline magic-byte check in `server.py:342-351`. `SecureUploadValidator` (`src/security/uploads.py`) exists but **is never used**. No EXIF/DICOM tag stripping; DICOM `PatientName` is even stored and returned |
| Security headers / CORS allow-list | ❌ | `src/security/headers.py` targets Streamlit (meta tags, which aren't real headers). Flask sends none. No CORS config |
| NoSQL injection protection | 🟡 | Most lookups cast to `int()`, but `request.json` values like `email` go straight into `find_one({"email": email})`, so a dict such as `{"$ne": null}` would pass |
| Adversarial-input checks | 🟡 | `src/security/adversarial.py` exists (FFT + Laplacian) but **is never called** |
| Pseudonymised IDs, HIPAA-aligned mapping | 🟡 | Sequential integer patient ids. Docs say "HIPAA Hardened"/"compliant", which the prompt forbids claiming |

### O7 — Secure clinical decision-support workflow
| Step | Status |
|---|---|
| Login (+MFA) | 🟡 (MFA inactive) |
| Select/create patient | ✅ API only |
| Upload → quality gate | 🟡 (no quality gate) |
| Analysis | 🟡 |
| Explainability + uncertainty | ❌ |
| Progression | 🟡 |
| Risk | 🟡 (random model) |
| Clinician review / sign-off | ❌ |
| Signed report | 🟡 |
| Audit trail | 🟡 |
| **UI for any of it** | ❌ (`GET /` renders a deleted template, so it returns a 500 error) |

### Phase 3 improvements
Review queue ❌ · Security Lab ❌ · Model Trust dashboard ❌ · PDF report 🟡 (`src/core/report.py`) · DEMO MODE 🟡 (`DB_MODE=demo` → mongomock, `src/database/connection.py:37-42`; no seed script, no demo banner or flag) · Health endpoint ❌ (the Dockerfile healthcheck hits `/health`, which doesn't exist) · Tests/CI ❌ · Central config for thresholds ❌ (thresholds are hard-coded across files).

---

## 4. Security findings

Ordered by severity. The items the prompt asked me to check come first.

| # | Checked item | Result | Evidence |
|---|---|---|---|
| S1 | Deterministic AES-CBC / static or reused IV | **No CBC.** Random 96-bit GCM nonces are used for writes. `encrypt_deterministic` derives the nonce from HMAC(key, plaintext), so equal plaintexts give equal ciphertexts. It's unused today but a latent risk. The key derivation silently SHA-256-hashes any malformed key instead of failing. | `encryption.py:23-38, 55-60` |
| S2 | Unauthenticated encryption | **OK.** AES-GCM is authenticated. An unused Fernet instance is also created. | `encryption.py:40-42` |
| S3 | Hard-coded keys / secrets | **Yes, several.** Superadmin `superadmin@periovision.ai / SuperAdminPass!123` is seeded on every start (`server.py:195-209`). Fallback `FIELD_ENCRYPTION_KEY=0123…cdef`, watermark key and signing password are in `wsgi.py:12-17`. `MODEL_SIGNING_PASSWORD` defaults to `"default_secure_pass"` (`integrity.py:20`). The watermark fallback key is in `watermark.py:18`. Mongo root password and all keys are in `docker-compose.yml:12-38`. | — |
| S4 | Weak JWT settings | **No JWT exists.** Flask `secret_key` falls back to a random value per process, so sessions die on restart and break across multiple workers (`server.py:153`). | — |
| S5 | Merkle root not anchored / not verified | **Weak.** The anchor is a local file (`logs/merkle_anchor.log`) on the same host, so an attacker who can edit the DB can edit it too. If the file is missing, verification falls back to the DB copy the attacker controls. `publish_root` is **never called** anywhere, so there's no periodic anchoring. `/api/audit-log/verify` **ignores `matches_published_root`**. Once any entry is appended after a publish, the root always mismatches (false alarm). | `merkle.py:55-133`, `server.py:682-702` |
| S6 | Hash-chain verification gap | **Entry 0 (genesis) is never re-hashed.** The loop starts at `i=1`, so tampering with the first entry goes undetected. | `merkle.py:90` |
| S7 | Audit-log race | `sequence_number` is read-then-insert with no unique index, so concurrent requests can fork the chain. | `merkle.py:39-52` |
| S8 | PHI/PII in logs | Email, IP and user agent are stored in plaintext in the audit metadata. The honeypot logger prints patient names. | `audit_middleware.py:37-48`, `honeypot.py:43` |
| S9 | GeoIP / IP data leakage | **No external lookup** (a previous leak was removed). The "geo" check is a fake mapping from first octet to country. It depends on Streamlit and is never called. It trusts `X-Forwarded-For` blindly. | `session.py:35-78` |
| S10 | Static / predictable honeypot | **Predictable.** Fixed name prefixes `VIP_OVERRIDE_`, `SYS_ADMIN_TEST_`, `SEC_VAULT_01_` and notes `"CONFIDENTIAL HIGH VALUE TARGET"` make the decoys easy to spot. They use `random` (not `secrets`). `create_honeypot_patient()` is **never called**, so no honeypot exists. A breach **permanently locks** the account (525,600 min), which anyone who can get a victim to open a record could abuse. | `honeypot.py`, `security/orchestrator.py:16-19` |
| S11 | Missing rate limiting | Partial (see O6). The in-memory store resets per process. `/api/image` and `/api/register` have only the default limit. | `server.py:155-160` |
| S12 | Upload input validation | Partial. There's an inline magic-byte check, but the file is saved to disk **before** validation. `.dcm` is trusted by extension alone (`_is_dicom_file`). No pixel-dimension limit (decompression bomb). No EXIF/DICOM tag stripping. The `/api/analyze` direct-upload path **skips validation entirely** (`server.py:404-409`). | — |
| S13 | **Arbitrary file read** | `GET /api/image?path=…` needs **no login**, and any relative path without `..`, `/`, `\` or `:` passes the check, so `?path=.env` or `?path=keys/model_signing.pem` would return the secret files. | `server.py:645-666` |
| S14 | **Broken access control (IDOR)** | `/api/patients/<id>/history` returns any patient's records to any logged-in user (no owner check). `/api/analyze` accepts any `patient_id`. `/api/dicom-metadata/<upload_id>` needs no login. Unassigned patients (`doctor_id: None`) are visible to every doctor. | `server.py:370-384, 757-772`, `rbac.py:30` |
| S15 | Model-integrity bypass | Unsigned or tampered YOLO weights still load (they only print a warning). The risk model is re-trained and **re-signed at startup** with the private key held by the app. `_get_private_key` **deletes the key pair** when the password is wrong, then generates a new one. | `detection.py:159-164`, `risk.py:25-41`, `integrity.py:22-47` |
| S16 | Error leakage | Many routes return `str(e)` to the client. `debug=True` in `server.py` enables the Werkzeug debugger, which allows remote code execution if exposed. | `server.py:243, 273, 600, 793` |
| S17 | Report signature is cosmetic | It signs `record_id:timestamp` rather than the PDF bytes, and shows a truncated signature, so a report can't be verified. `sign_model(report_path)` writes a `.sig` next to the PDF, but nothing verifies it. | `report.py:15-28`, `server.py:623-624` |
| S18 | Dependency pinning | `pyproject.toml` uses `>=` or no version at all. No lock file. | — |
| S19 | CSRF vs API | CSRFProtect is on for a JSON API with no frontend to fetch the token. `/api/login` will reject clients that don't first call `/api/csrf-token`. | `server.py:154` |

---

## 5. Tech-stack conflicts and dead code

1. **Three UIs, zero working.** The Flask template UI (`web/`) and the Streamlit UI (`web_app/`, `src/ui/`) are deleted, and `docker-compose.yml` still starts `streamlit run main.py` on port 8501. `src/security/session.py` and `headers.py` still `import streamlit`.
2. **Two inference pipelines.** `src/models/{detection,landmarks}.py` (used by `server.py`) duplicates `models/inference.py` (ONNX + YOLO + heuristic FDI, used only by the broken `orchestrator.py`).
3. **Three velocity/grading implementations.** `src/analysis/progression_velocity_calculator.py` (main), `src/core/velocity.py` (a second `ProgressionVelocityCalculator` class with the same name) and `src/core/talpa.py` (`TALPAEngine`, with different grade thresholds in % rather than mm).
4. **Two tooth detectors.** `dental_yolov8n.pt` and `tooth_detection_yolov8n.pt`, plus a generic `yolov8n.pt` fallback that silently detects COCO objects (not teeth) if dental weights are missing. The segmentation model `dental_bone_yolov8n-seg.pt` is never used.
5. **Broken modules.** `orchestrator.py` imports 9 modules that no longer exist. `scripts/train_tooth_detection.py:20` and `scripts/train_landmark_detection.py:16` import the deleted `utilities.dataset_loader`.
6. **Import-time side effects.** `database/connection.py` connects on import and scans the repo for secrets. `server.py` seeds users, loads 2 YOLO models and trains a model on import, so tests can't import it cheaply.
7. **Two sources of risk model.** `src/core/risk.py` reads `storage/models/risk_model/risk_model.pkl`, while `scripts/train_risk_model.py` writes `models/risk_model/risk_model.pkl`.
8. **Unused security modules.** `uploads.py`, `adversarial.py`, `honeypot.create_*`, `session.py`, `threat_intel.py`, `governance.py`, `readiness.py` and `audit.check_inference_rate_limit` are never called from any route.
9. **Docs overclaim.** "HIPAA Hardened", "HIPAA-compliant", "Enterprise Production", "Version 1.0 (Production)". The prompt requires "aligned with", research prototype.
10. **Framework:** Flask + MongoDB + PyTorch/YOLOv8 + OpenCV, which matches the synopsis stack. Keep it.

---

## 6. Datasets (read-only survey of `C:\Users\vrudd\Downloads\DP_datasets\datasets`)

~33k JPG, ~17k TXT labels, ~15k `.npy`, 6 YAML files. Nothing was copied.

| Folder | What it is |
|---|---|
| `detection/` | YOLO detection with FDI classes `11…48` (`dental_yolo.yaml`), split into `yolo_train/` and `yolo_val/` |
| `pose/`, `pose_subset/` | YOLO-pose, 1 class `tooth`, `kpt_shape [3,3]` (CEJ, apex, crest). `pose_subset/data_subset.yaml` hard-codes an absolute path into the old `custom_datasets` folder |
| `segmentation/` | YOLO-seg, 1 class `tooth` |
| `real/tooth_detection/` | Roboflow "dental-x-rays-wwauy" v1, **CC BY 4.0**, 1 class `Premolars`. Same set whose patient-named files are on public GitHub (G2) |

This matters for O1. The FDI-class detection dataset exists, so the detector *can* output real tooth numbers instead of `11 + i`. Which labels each `.pt` was actually trained on needs checking in Phase 2.

---

## 7. Plan

### Decisions only Sid can make (before Phase 1)
1. **Public repo with patient-named images (G2).** Recommended: make the GitHub repo private now (GitHub → Settings → Danger zone). If it must stay public, the history has to be rewritten with `git filter-repo` and force-pushed. That can't be undone, so it needs your explicit go-ahead.
2. **The uncommitted cleanup (G1).** Recommended: keep it. In Phase 1 I'll commit the removals with `git rm`, restore the old Streamlit UI from git into `tools/streamlit_prototype/` (the prompt allows this), restore `requirements.txt` as a starting point, and log every path in `docs/CHANGELOG_RESTRUCTURE.md`. Datasets stay out of the repo, and `docs/DATASETS.md` will point to `DP_datasets` and public sources.
3. **Where the new layout lives.** Recommended: make the git root (`Dental_progression/`) the project root with `backend/`, `frontend/` and `docs/`, and move `dental_progression_ai/*` into `backend/` with `git mv`. The alternative is to build the new layout inside `dental_progression_ai/`.

### Phase 1 → 7 outline (once the above is settled)
- **P1 Structure:** `git mv` into `backend/app/{api,services,ml,security,models,schemas}`, add `frontend/`, fix `.gitignore` (UTF-8, ignore `keys/*.pem`, weights, data, `.env`), and add `requirements.txt` (pinned), `Makefile`, `.env.example` and a folder README each. Remove hard-coded secrets.
- **P2 Features:** quality gate · FDI tooth ids from the detector · a consistent coordinate space for landmarks · Tonetti stage + grade · per-tooth full output · stored Grad-CAM overlays + attention flag · split-conformal + `review_router` · honest risk model (logistic/GBM with documented data, or labelled "rule-assisted demo") with plain-language reasons · AES-GCM for images and reports with key ids · JWT access/refresh · working MFA enrolment · 4-role RBAC decorators · a Zero-Trust request guard · strict model-signature enforcement · content-signed reports + `/verify` · fixed audit chain (genesis, unique seq, anchored roots, verify pinpoints the first bad entry) · a real upload guard · headers and CORS · closing S13/S14.
- **P3:** review queue, Security Lab, Model Trust, PDF, `seed_demo_data.py` + `"mode": "demo"`, `/api/health`, pytest + CI, a central `config`.
- **P4:** React 18 + Vite + TS frontend, 15 pages.
- **P5–P7:** API envelope + OpenAPI at `/api/docs`, docs/traceability/viva sheet, full test + build + demo run, final checklist.

### Blocking inputs I'll need later
- The synopsis PDF and PPT in `docs/reference/`.
- The labels and classes each `.pt` file was trained on, or permission to retrain on `DP_datasets` (needs a GPU for reasonable time).
- A real calibration split for conformal prediction (can come from the `DP_datasets` validation split).
- Real clinical risk data if the risk model is to be anything other than "rule-assisted demo".
