# Final verification: 2026-09-28

## What was run

| Check | Result |
|---|---|
| Backend test suite (`cd backend && python -m pytest`) | **74 passed** |
| Frontend strict type-check (`npx tsc -p tsconfig.app.json --noEmit`) | **0 errors** |
| Frontend lint (`npm run lint`) | **0 errors, 0 warnings** |
| Frontend production build (`npm run build`) | **succeeds** |
| Demo backend + frontend started; every route opened as **dentist** (17 routes) | all load, no error states; `/app/admin` and `/app/security-lab` correctly show *Access denied* for the dentist role; unknown route shows the 404 page |
| Same as **admin** | Admin (users, keys & signing, thresholds), Security center, Security lab, Dashboard load; "Verify chain" → *Chain intact: 36 entries and 1 Merkle anchor verified* |
| Same as **auditor** (earlier in the session) | Security lab "Run all attacks" → **7 / 7 attacks blocked**; hash-chain verification intact |
| Clinical workflow in the UI | Analysis viewer (decrypted radiograph shown) → Review & sign off (Approve) → "Signed off by Demo Dentist" → Signed report generated → public `/verify/<id>` → **"Authentic, unaltered report"** |
| Upload → analysis via the API | covered by `tests/test_api.py::test_end_to_end_workflow`; the upload page itself loads in the UI (the browser pane cannot drive a native file picker) |

## Objectives and features

| # | Objective / feature | Status | Evidence |
|---|---|---|---|
| O1 | Quality gate, CLAHE, YOLOv8 FDI detection, CEJ/crest landmarks, bone loss %, Stage/Grade, per-tooth output | ✅ | `backend/app/ml/*`, `services/analysis_service.py`; viewer page. Detector 95.8 % mAP@0.5 (DENTEX test); landmarks: bone-loss MAE 7.64 points, 73.1 % stage agreement (DenPAR test). See the model card |
| O2 | Longitudinal progression with registration-aware matching, velocity, labels, unreliable flags | ✅ | `services/progression_service.py`, Progression page, `test_ml_logic.py` |
| O3 | Grad-CAM heatmap, opacity slider, ROI attention flag → review | ✅ (live model only) | `ml/explainability/gradcam.py`, viewer heatmap layer. In demo mode no heatmap exists because no model ran |
| O4 | Split-conformal intervals, stage sets, review router, coverage report | ✅ | `ml/uncertainty/*`, Model trust page. Calibrated on DenPAR validation teeth; 91.5 % coverage at the 90 % target on the test split |
| O5 | Multimodal risk with plain-language reasons | ✅ (rule-assisted demo) | `ml/fusion/multimodal_risk.py`; honest label everywhere. Needs an outcome dataset to become a trained model |
| O6 | AES-256-GCM + rotation, TLS (optional dev cert), bcrypt, JWT + refresh, TOTP MFA, lockout, rate limit, RBAC, Zero Trust, signed models, signed reports + verify, audit chain + Merkle anchors + CLI, upload guard, headers, CORS, validation, adversarial screen, pseudonyms, HIPAA-aligned mapping | ✅ | `backend/app/security/*`, `docs/SECURITY.md`, `docs/TRACEABILITY.md`, security tests |
| O7 | End-to-end secure workflow | ✅ | UI walkthrough above + `test_end_to_end_workflow` |
| P3 | Review queue, Security Lab, Model Trust, PDF reports, demo mode + seed, health/status, tests + CI, config thresholds | ✅ | see changelog Phase 3 |
| P4 | React frontend: 15 required pages + 3D, reduced-motion fallback, role-aware UI | ✅ | `frontend/src/pages/*`, `frontend/src/three/*` |
| P5 | Envelope, OpenAPI at `/api/docs`, `docs/API.md` with real examples, encrypted storage, pseudonymised IDs | ✅ | `app/api/docs.py`, `docs/API.md`, `docs/openapi.json`, `test_contract.py` |
| P6 | Traceability, tests, lint/format configs, README, viva sheet | ✅ | `docs/TRACEABILITY.md`, `README.md`, `docs/VIVA_CHEAT_SHEET.md` |
| Extra | Perio chart + concordance, care plan, patient explainer, recall board | ✅ | `services/clinical_service.py`, `pages/clinical/*`, `test_clinical.py` |

### What is ❌ or limited, and what you must supply

1. **Panoramic landmarks:** both models are trained and measured, but the landmark model has only been validated on periapical X-rays. On panoramic images it runs on zoomed crops, and those teeth are flagged for review. **Next:** a panoramic keypoint dataset (for example BoneLoss-PAN769, access request).
3. **Risk model:** needs longitudinal outcome data (who progressed) to train and validate. Until then it stays a labelled rule-assisted demo.
4. **Synopsis wording:** `docs/reference/` is still empty. Add the PDF and PPT so the traceability table can quote them.
5. **Public GitHub history** still contains the patient-named Roboflow images (audit finding G2). **Needed:** make the repository private or rewrite history (owner action).

## HOW TO RUN

```powershell
# once
copy .env.example .env          # set DB_MODE=demo, secrets and DEMO_* accounts (see README)
.\run.ps1 setup

# every time (two terminals)
.\run.ps1 demo                  # backend  → http://127.0.0.1:5000  (API docs: /api/docs)
.\run.ps1 frontend              # web app  → http://localhost:5173
```

Sign in with a `DEMO_*_EMAIL` / `DEMO_*_PASSWORD` pair from `.env` (dentist, technician, auditor, admin). **Demo accounts are for demonstrations only.**

Checks: `.\run.ps1 test` · `.\run.ps1 lint` · `cd frontend; npm run build` · regenerate API docs: `.\run.ps1 docs`.

## Top 5 things to do manually next

1. **Make the GitHub repository private** (or rewrite its history) because of the patient-named images, then commit the restructure from branch `restructure/phase-1` and push it.
2. **Retrain the models on clinician-annotated data** (e.g. DENTEX plus your own CEJ/crest/apex annotations) on a GPU, then `python scripts/sign_model.py` to sign the new weights.
3. **Calibrate uncertainty** on a held-out annotated split with `python scripts/calibrate_conformal.py …`, and add real metrics to `docs/MODEL_CARD.md` only after that.
4. **Replace the demo secrets:** generate new `FIELD_ENCRYPTION_KEYS` (then `python scripts/rotate_keys.py`), a new `MODEL_SIGNING_PASSWORD` with a fresh key pair, and remove the `DEMO_*` accounts for any non-demo use.
5. **Add the synopsis and slides to `docs/reference/`** and screenshots to the README, then rehearse with `docs/VIVA_CHEAT_SHEET.md`.
