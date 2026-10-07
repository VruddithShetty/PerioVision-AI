# PerioVision AI

**Secure, explainable decision support for periodontal bone-loss detection.** PerioVision reads dental radiographs tooth by tooth: it finds each tooth by FDI number, locates the cemento-enamel junction and the alveolar crest, measures bone loss, suggests a periodontitis stage and grade, tracks every tooth across visits, and puts an honest uncertainty range on each finding. Anything doubtful goes to a dentist for sign-off before a signed report can be issued. Around it sits a security layer built for a cybersecurity thesis: AES-256-GCM encryption, RSA-PSS signed models and reports, JWT + TOTP MFA, four-role RBAC with Zero Trust checks on every request, and a hash-chained, Merkle-anchored audit trail.

> **Decision support, clinician in the loop.** Not a certified medical device. Model accuracy is reported only from held-out test data (see the model card). Security controls are *aligned with* HIPAA safeguards, not certified.

![Analysis viewer: FDI-numbered teeth, landmarks, conformal interval and the review banner (screenshot taken before panoramic bone-loss numbers were switched off; they are now shown for periapical films only)](docs/reference/screenshots/analysis-viewer.jpg)

| | |
|---|---|
| ![Landing page](docs/reference/screenshots/landing.jpg) | ![Clinician dashboard](docs/reference/screenshots/dashboard.jpg) |
| ![3D dental arch](docs/reference/screenshots/3d-arch.jpg) | ![Progression across visits](docs/reference/screenshots/progression.jpg) |
| ![Six-point periodontal chart](docs/reference/screenshots/perio-chart.jpg) | ![Security Lab: 7 of 7 attacks blocked](docs/reference/screenshots/security-lab.jpg) |

## Features

**Clinical AI (synopsis objectives O1–O5)**
- Image-quality gate, CLAHE, YOLO11m tooth detection with FDI numbers, CEJ / crest / apex landmarks
- Per-tooth bone loss %, Stage I–IV and Grade A–C suggestions (2017 AAP/EFP)
- Grad-CAM-family heatmaps with LayerCAM weighting (5× better localisation on a tooth than classic Grad-CAM, measured), for all teeth or for one selected tooth, and a per-tooth periodontal-attention check
- Adaptive split-conformal uncertainty (each tooth's interval widens when its normal and mirrored readings disagree), stage sets, mandatory clinician review router
- Longitudinal progression: registration that must line up the teeth themselves, then a same-site comparison with a repeatability threshold calibrated on re-take pairs (bench: 95 % of unchanged teeth stay silent, 84 % of 20-point losses detected; see [docs/PROGRESSION.md](docs/PROGRESSION.md))
- Risk fusion: a clinical model trained on CDC NHANES (tested on a later cycle of the same survey, plain-language odds ratios) combined with the radiograph's measured stage by a documented rule
- Panoramic films: tooth detection and FDI numbering (tested on another hospital's films: 89.6 % with the previous detector; the deployed one, fine-tuned on that hospital, 94.5 % on its unseen films) plus a whole-film estimate tested on held-out films of its training datasets (bone loss per jaw, worst-tooth bone loss and stage, with its own conformal interval that drives review); per-tooth bone loss is measured on periapical films only. About 11 s per panoramic film on a laptop CPU
- No invented numbers: anything unmeasured shows as "not measured" or "insufficient data", enforced by a build-time test

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
**Tests:** `.\run.ps1 test` (backend) and `cd frontend; npm run build; npm run lint`. With trained weights in `backend/weights/`, `cd backend; python -m pytest tests_live -q` also checks the real models on real radiographs (see `docs/VERIFICATION_REPORT.md`).

### Demo tour
1. Landing page: drag the scan bar across the panoramic X-ray; move the staging slider.
2. Sign in as the **dentist**: Dashboard → Patients → *Demo Patient B* → Progression, Perio chart (see the discordant teeth), Care plan, Explain to patient.
3. Open an analysis: switch between Radiograph, Dental chart and 3D arch; click teeth.
4. Review queue: correct a tooth and sign off; then generate a **Signed report** and verify it.
5. Sign in as the **auditor**: Security center → Verify chain; Security lab → Run all attacks.

### Optional: real models and HTTPS
- Train on a free Colab GPU with the notebooks in `notebooks/` (tooth detector, landmarks, panoramic models; see `notebooks/README.md`), then run `.\run.ps1 install-models -From <export folder>` (installs, signs, tests). Or put weights in `backend/weights/` and run `cd backend; python scripts/sign_model.py`. Unsigned files are refused.
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

## Results

**In one line:** on held-out periapical X-rays PerioVision measures radiographic bone loss to within 6.6 percentage
points on average and agrees with the specialist's stage for 76 % of teeth, refers every uncertain tooth to a dentist,
and is decision support, not a diagnosis; it has not yet been validated at another clinic or on real follow-up X-rays.

All numbers are on films the models never trained on, with 95 % confidence intervals; full tables in
[docs/RESULTS_WITH_CI.md](docs/RESULTS_WITH_CI.md), failure analysis in [docs/ANALYSES.md](docs/ANALYSES.md).

| Task | Result (95 % CI) | Tested on | What this means |
|---|---|---|---|
| Find each tooth and give its FDI number (panoramic) | 89.6 % (88.3-90.8) | 250 films from a hospital the detector was not trained on | About 9 in 10 teeth are found and correctly numbered at a new hospital |
| Same, after fine-tuning on part of that hospital's films | 94.5 % (93.0-95.8) | 96 unseen films, same hospital | Adapting to a new site's images helps a lot |
| Bone loss per tooth (periapical) | 6.6 points error (5.9-7.5) | 553 teeth, 199 DenPAR test films | Half of teeth are within 4 points of the specialist; the average miss is 6.6 points |
| Periodontitis stage per tooth (periapical) | 76 % exact (72-79), 98 % within one stage | same | Stage I and III are mostly right; stage II only about half the time |
| Uncertainty range at 90 % | covers 93 % (90-95) | same | The stated range really contains the specialist's value about 9 times in 10 |
| Bone loss per jaw (panoramic screen) | AUC 0.85 / 0.87 (approximate CI 0.81-0.89 / 0.84-0.91) | 450 films | Good at flagging which jaws need a closer look |
| Worst tooth's bone loss (panoramic) | 11.4 points error (9.5-13.5), 68.5 % stage | 149 patients | Patient-level estimate only; per-tooth numbers are not given on panoramic films |
| Change between two visits (bench) | 95 % of unchanged teeth stay silent; 84 % of 20-point losses flagged | simulated re-takes and bone loss, 100 test films | Large changes are caught; small yearly changes are not, and real follow-up X-rays are still untested |
| Clinical risk from age, sex, smoking, diabetes | AUC 0.65 (0.63-0.67) | 3,855 people, later survey cycle | Context only; it never overrides what the X-ray shows |

## Known limitations (honest)

- Measured on held-out data ([docs/MODEL_CARD.md](docs/MODEL_CARD.md); re-run commands in [docs/VERIFICATION_REPORT.md](docs/VERIFICATION_REPORT.md)): tooth detector: 89.6 % (95 % CI 88.3–90.8) found-and-correctly-numbered on 250 films from a hospital it was not trained on; after fine-tuning on part of that hospital's films, 94.5 % on its 96 unseen films (the deployed model) and 89.1 % of diseased teeth on the DENTEX official test; periapical bone-loss error 6.6 points (95 % CI 5.9–7.5), 76 % stage agreement, 93 % interval coverage (DenPAR test, two-site landmark model, corrected reference; see [docs/LIMITATIONS.md](docs/LIMITATIONS.md)).
- Panoramic films get no per-tooth bone-loss numbers (not accurate enough against expert grading of 240 films). Instead whole-film models give a patient-level estimate: bone loss per jaw (test AUC 0.85 / 0.87) and the worst tooth's bone loss (error 11 points, 69 % stage agreement).
- Uncertainty intervals are honest but wide (on average ±19 points at 90 %), so most teeth still go to dentist review.
- Risk: the clinical model (trained on NHANES, AUC 0.65) does not read the radiograph; the radiograph's measured stage is combined with it by a documented rule (the higher level wins), not a learned weight. Neither part predicts future progression.
- Progression: a change counts when the same side of a tooth moves by more than 4.6-6.2 points (repeatability, calibrated on validation re-takes). On a bench of simulated re-takes and simulated bone loss: 95 % specificity, sensitivity 84 % at 20, 66 % at 15 and 39 % at 10 points of root length. Not yet tested on real follow-up radiographs ([docs/PROGRESSION.md](docs/PROGRESSION.md)). The demo patients' trends use planted synthetic values and are labelled as such on every page.
- Demo mode uses an in-memory database; nothing persists after a restart.
- The development server is HTTP unless you enable the local certificate; production needs a TLS reverse proxy.

## Documentation

[Architecture](docs/ARCHITECTURE.md) · [Security](docs/SECURITY.md) · [API](docs/API.md) · [Deployment](docs/DEPLOYMENT.md) · [Model card](docs/MODEL_CARD.md) · [Datasets](docs/DATASETS.md) · [Verification report](docs/VERIFICATION_REPORT.md) · [Instructions for use](docs/INSTRUCTIONS_FOR_USE.md) · [Key rotation](docs/KEY_ROTATION.md) · [Traceability](docs/TRACEABILITY.md) · [Project report](docs/PROJECT_REPORT.md) · [All docs](docs/README.md)

## Repository layout

```
backend/        Flask API
  app/          api/ (routes) · services/ (workflow) · ml/ (models, uncertainty, risk) · security/ · models/ (DB) · schemas/
  config/       thresholds.json: every clinical / ML threshold in one place
  scripts/      training, evaluation, calibration, signing and setup tools
  tests/        fast test suite (no weights needed) · tests_live/: checks with the real trained models
  weights/      model files (not in git; see weights/README.md) · keys/: signing keys (not in git)
frontend/       React 18 + Vite + TypeScript web app
notebooks/      one-click Colab training notebooks
docs/           documentation, evidence/ (raw evaluation outputs), reference/screenshots/
data/           local data, gitignored (sample/ = synthetic demo images)
run.ps1 · Makefile · docker-compose.yml   run / build / deploy entry points
```
