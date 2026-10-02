# PerioVision AI

**Secure, explainable decision support for periodontal bone-loss detection.** PerioVision reads dental radiographs tooth by tooth: it finds each tooth by FDI number, locates the cemento-enamel junction and the alveolar crest, measures bone loss, suggests a periodontitis stage and grade, tracks every tooth across visits, and puts an honest uncertainty range on each finding. Anything doubtful goes to a dentist for sign-off before a signed report can be issued. Around it sits a security layer built for a cybersecurity thesis: AES-256-GCM encryption, RSA-PSS signed models and reports, JWT + TOTP MFA, four-role RBAC with Zero Trust checks on every request, and a hash-chained, Merkle-anchored audit trail.

> **Decision support, clinician in the loop.** Not a certified medical device. Model accuracy is reported only from held-out test data (see the model card). Security controls are *aligned with* HIPAA safeguards, not certified.

![Analysis viewer: a real panoramic X-ray with 26 FDI-numbered teeth, landmarks, per-tooth bone loss, conformal interval and the review banner](docs/reference/screenshots/analysis-viewer.jpg)

| | |
|---|---|
| ![Landing page](docs/reference/screenshots/landing.jpg) | ![Clinician dashboard](docs/reference/screenshots/dashboard.jpg) |
| ![3D dental arch](docs/reference/screenshots/3d-arch.jpg) | ![Progression across visits](docs/reference/screenshots/progression.jpg) |
| ![Six-point periodontal chart](docs/reference/screenshots/perio-chart.jpg) | ![Security Lab: 7 of 7 attacks blocked](docs/reference/screenshots/security-lab.jpg) |

## Features

**Clinical AI (synopsis objectives O1–O5)**
- Image-quality gate, CLAHE, YOLO11m tooth detection with FDI numbers, CEJ / crest / apex landmarks
- Per-tooth bone loss %, Stage I–IV and Grade A–C suggestions (2017 AAP/EFP)
- Grad-CAM heatmaps with a periodontal-region attention check
- Split-conformal uncertainty intervals and stage sets; mandatory clinician review router
- Longitudinal progression with registration-aware tooth matching and reliability flags
- Multimodal risk (clinical + image) with plain-language reasons (documented rule-assisted demo)

**Security (O6)**
- AES-256-GCM with key IDs and rotation for fields, radiographs and reports
- RSA-PSS signed model manifest (unsigned models refused) and signed, QR-verifiable PDF reports
- bcrypt, 15-minute JWT + rotating refresh cookie, TOTP MFA, lockout, rate limits
- Admin / dentist / technician / auditor permission matrix, Zero Trust request guard, decoy records
- Tamper-evident audit log that pinpoints the first edited entry; Security Lab with 7 live attack demos

**Clinical workflow (O7) and chairside tools**
- Login → patient → upload → analysis → review → signed report → audit, in a React app with 3D visuals
- Six-point periodontal chart with clinical-vs-radiographic concordance, EFP care plan with prognosis and referral letter, patient explainer with a "what if" forecast, clinic recall board

## Architecture

```
React app (frontend/) ──HTTPS──▶ Flask API (backend/app)
                                  ├─ Zero Trust guard → RBAC permission → route
                                  ├─ ml/: quality → CLAHE → YOLO11m → landmarks → staging → Grad-CAM → conformal → risk
                                  ├─ security/: AES-GCM · RSA-PSS · JWT/MFA · audit chain · upload guard
                                  └─ MongoDB (or in-memory demo DB) + encrypted blob store + external audit anchors
```
Full diagram and data flow: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Run it (step by step, Windows)

1. **Install the tools** (once):
   - Python 3.11 or newer: https://www.python.org/downloads/ (tick "Add python.exe to PATH")
   - Node.js 20 or newer (LTS): https://nodejs.org/
2. **Open PowerShell in the project folder** (`Dental_progression`).
3. **Create your settings file:**
   ```powershell
   copy .env.example .env
   ```
   Open `.env` and set `DB_MODE=demo`. Generate each secret with `python -c "import secrets; print(secrets.token_hex(32))"` and paste it in. Then fill in the `DEMO_*` accounts. Passwords need 10+ characters with upper- and lower-case letters and a digit, and these accounts are for demos only.
4. **Install everything:**
   ```powershell
   .\run.ps1 setup
   ```
5. **Start the backend** (terminal 1):
   ```powershell
   .\run.ps1 demo
   ```
6. **Start the web app** (terminal 2):
   ```powershell
   .\run.ps1 frontend
   ```
7. **Open http://localhost:5173** and sign in with a `DEMO_*_EMAIL` / `DEMO_*_PASSWORD` from your `.env`.

On macOS/Linux use `make setup`, `make demo`, `make frontend`, `make test`.

**Ports:** backend `5000`, frontend `5173`. **API docs:** http://127.0.0.1:5000/api/docs (OpenAPI) and [docs/API.md](docs/API.md).
**Tests:** `.\run.ps1 test` (backend) and `cd frontend; npm run build; npm run lint`.

### Demo tour
1. Landing page: drag the scan bar across the panoramic X-ray; move the staging slider.
2. Sign in as the **dentist**: Dashboard → Patients → *Demo Patient B* → Progression, Perio chart (see the discordant teeth), Care plan, Explain to patient.
3. Open an analysis: switch between Radiograph, Dental chart and 3D arch; click teeth.
4. Review queue: correct a tooth and sign off; then generate a **Signed report** and verify it.
5. Sign in as the **auditor**: Security center → Verify chain; Security lab → Run all attacks.

### Optional: real models and HTTPS
- Train on a free Colab GPU with `notebooks/train_periovision_colab.ipynb`, then run `.\run.ps1 install-models -From <export folder>` (installs, signs, tests). Or put weights in `backend/weights/` and run `cd backend; python scripts/sign_model.py`. Unsigned files are refused.
- Calibrate uncertainty on a held-out, per-tooth-annotated set: `python scripts/calibrate_conformal.py --images … --labels …`.
- Live deployment (fresh secrets, real MongoDB, production server): see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).
- Local HTTPS: `python scripts/make_dev_cert.py`, then set `TLS_CERT=keys/dev-tls.crt` and `TLS_KEY=keys/dev-tls.key` in `.env`.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Cannot reach the PerioVision server` in the browser | The backend isn't running: start `.\run.ps1 demo` first. |
| Backend exits saying a key is missing | Fill in `JWT_SECRET_KEY`, `AUDIT_ANCHOR_KEY` and `FIELD_ENCRYPTION_KEY` in `.env` (demo mode tolerates missing ones). |
| Login says "Invalid email or password" | Use the exact `DEMO_*` values from `.env`; demo data resets on every backend restart. |
| "Account locked" | 5 wrong passwords lock an account for 15 minutes; restart the demo backend to reset. |
| Everything says "Mandatory clinician review" / "uncalibrated" | Expected until the model is calibrated on annotated data; see the model card. |
| 3D scenes don't show | Your device has no WebGL, few CPU cores, or reduced motion on; a static image is shown instead. |
| `.\run.ps1` is blocked | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or run the commands inside `run.ps1` by hand. |

## Known limitations (honest)

- Measured on held-out test sets ([docs/MODEL_CARD.md](docs/MODEL_CARD.md)): tooth detector 95.8 % mAP@0.5 (DENTEX panoramic); landmark model 99 % tooth recall, bone-loss error 7.6 points, 73 % stage agreement, 91.5 % conformal coverage (DenPAR periapical). Landmarks are not validated on panoramic X-rays, so those are always flagged for review.
- Uncertainty intervals are honest but wide (±18.6 points at 90 %), so most teeth still go to dentist review.
- The risk score is a documented rule-assisted demo, not a trained model.
- Demo mode uses an in-memory database; nothing persists after a restart.
- The development server is HTTP unless you enable the local certificate; production needs a TLS reverse proxy.

## Documentation

[Audit report](docs/AUDIT_REPORT.md) · [Restructure changelog](docs/CHANGELOG_RESTRUCTURE.md) · [Architecture](docs/ARCHITECTURE.md) · [Security](docs/SECURITY.md) · [API](docs/API.md) · [Traceability](docs/TRACEABILITY.md) · [Model card](docs/MODEL_CARD.md) · [Datasets](docs/DATASETS.md) · [Key rotation](docs/KEY_ROTATION.md) · [Viva cheat sheet](docs/VIVA_CHEAT_SHEET.md)

## Repository layout

```
backend/    Flask API: app/ (api, services, ml, security, models, schemas), scripts/, tests/, weights/, keys/
frontend/   React 18 + Vite + TypeScript web app
docs/       all documentation (reference/ holds the synopsis and slides)
data/       local data, gitignored (sample/ = synthetic demo images)
notebooks/  experiments only
tools/      optional extras (streamlit_prototype/ = the old UI, frozen)
```
