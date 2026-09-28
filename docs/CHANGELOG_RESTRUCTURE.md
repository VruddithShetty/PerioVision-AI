# Restructure Changelog

Every file move, restore and code change made while restructuring the project. Nothing was deleted: moved files keep their git history (`git mv`), and untracked files were moved on disk. A full copy of the pre-restructure folder was taken first.

## Phase 1 (2026-09-28), branch `restructure/phase-1`

### Decisions applied
- **New project root = repository root** (`Dental_progression/`). The app now lives in `backend/`, docs in `docs/`, and the React app goes in `frontend/`. The old `dental_progression_ai/` folder is now empty.
- **Kept the earlier cleanup.** The datasets, old UIs and old module folders deleted from the working tree before this restructure (see `docs/AUDIT_REPORT.md` section 1, G1) stay removed. They remain in git history. The one exception is the Streamlit UI, which was restored into `tools/streamlit_prototype/` as allowed by the master prompt.
- **Datasets stay outside the repo** (`C:\Users\vrudd\Downloads\DP_datasets`). Nothing was copied in.

### File moves
| From | To | How |
|---|---|---|
| `dental_progression_ai/scripts/convert_to_yolopose.py` | `backend/scripts/convert_to_yolopose.py` | move (untracked) |
| `dental_progression_ai/scripts/download_real_data.py` | `backend/scripts/download_real_data.py` | move (untracked) |
| `dental_progression_ai/scripts/export_model.py` | `backend/scripts/export_model.py` | move (untracked) |
| `dental_progression_ai/scripts/generate_custom_datasets.py` | `backend/scripts/generate_custom_datasets.py` | move (untracked) |
| `dental_progression_ai/scripts/migrate_encryption.py` | `backend/scripts/migrate_encryption.py` | move (untracked) |
| `dental_progression_ai/scripts/setup.py` | `backend/scripts/setup.py` | move (untracked) |
| `dental_progression_ai/scripts/train_landmark_detection.py` | `backend/scripts/train_landmark_detection.py` | move (untracked) |
| `dental_progression_ai/scripts/train_models.py` | `backend/scripts/train_models.py` | move (untracked) |
| `dental_progression_ai/scripts/train_risk_model.py` | `backend/scripts/train_risk_model.py` | move (untracked) |
| `dental_progression_ai/scripts/train_talpa.py` | `backend/scripts/train_talpa.py` | move (untracked) |
| `dental_progression_ai/scripts/train_tooth_detection.py` | `backend/scripts/train_tooth_detection.py` | move (untracked) |
| `dental_progression_ai/scripts/validate_dataset.py` | `backend/scripts/validate_dataset.py` | move (untracked) |
| `dental_progression_ai/models/weights/dental_bone_yolov8n-seg.pt` | `backend/weights/dental_bone_yolov8n-seg.pt` | move (untracked) |
| `dental_progression_ai/models/weights/dental_landmark_yolov8n-pose.pt` | `backend/weights/dental_landmark_yolov8n-pose.pt` | move (untracked) |
| `dental_progression_ai/models/weights/dental_yolov8n.pt` | `backend/weights/dental_yolov8n.pt` | move (untracked) |
| `dental_progression_ai/models/weights/tooth_detection_yolov8n.pt` | `backend/weights/tooth_detection_yolov8n.pt` | move (untracked) |
| `dental_progression_ai/models/weights/yolov8n.pt` | `backend/weights/yolov8n.pt` | move (untracked) |
| `dental_progression_ai/models/risk_model/calibration_plot.png` | `backend/weights/risk_model/calibration_plot.png` | move (untracked) |
| `dental_progression_ai/models/risk_model/feature_importance.png` | `backend/weights/risk_model/feature_importance.png` | move (untracked) |
| `dental_progression_ai/models/risk_model/model_metadata.json` | `backend/weights/risk_model/model_metadata.json` | move (untracked) |
| `dental_progression_ai/models/risk_model/risk_model.pkl` | `backend/weights/risk_model/risk_model.pkl` | move (untracked) |
| `dental_progression_ai/models/landmark_detection_model/landmark_cnn.pt` | `backend/weights/landmark_detection_model/landmark_cnn.pt` | move (untracked) |
| `dental_progression_ai/models/landmark_detection_model/training_log.csv` | `backend/weights/landmark_detection_model/training_log.csv` | move (untracked) |
| `dental_progression_ai/keys/model_signing.pem` | `backend/keys/model_signing.pem` | move (untracked) |
| `dental_progression_ai/keys/model_signing.pub` | `backend/keys/model_signing.pub` | move (untracked) |
| `dental_progression_ai/server.py` | `backend/legacy/server_monolith.py` | git mv |
| `dental_progression_ai/wsgi.py` | `backend/wsgi.py` | git mv |
| `dental_progression_ai/src/security/encryption.py` | `backend/app/security/crypto.py` | git mv |
| `dental_progression_ai/src/security/integrity.py` | `backend/app/security/model_signing.py` | git mv |
| `dental_progression_ai/src/security/merkle.py` | `backend/app/security/audit_log.py` | git mv |
| `dental_progression_ai/src/security/rbac.py` | `backend/app/security/rbac.py` | git mv |
| `dental_progression_ai/src/security/uploads.py` | `backend/app/security/upload_guard.py` | git mv |
| `dental_progression_ai/src/security/adversarial.py` | `backend/app/security/adversarial.py` | git mv |
| `dental_progression_ai/src/security/watermark.py` | `backend/app/security/watermark.py` | git mv |
| `dental_progression_ai/src/security/honeypot.py` | `backend/app/security/honeypot.py` | git mv |
| `dental_progression_ai/src/security/secrets.py` | `backend/app/security/secrets.py` | git mv |
| `dental_progression_ai/src/security/governance.py` | `backend/app/security/governance.py` | git mv |
| `dental_progression_ai/src/security/checks.py` | `backend/app/security/checks.py` | git mv |
| `dental_progression_ai/src/security/orchestrator.py` | `backend/app/security/incident_response.py` | git mv |
| `dental_progression_ai/src/security/readiness.py` | `backend/app/security/readiness.py` | git mv |
| `dental_progression_ai/src/security/threat_intel.py` | `backend/app/security/threat_intel.py` | git mv |
| `dental_progression_ai/src/security/session.py` | `backend/app/security/session.py` | git mv |
| `dental_progression_ai/src/security/headers.py` | `tools/streamlit_prototype/security_headers.py` | git mv |
| `dental_progression_ai/src/core/audit_middleware.py` | `backend/app/security/audit_middleware.py` | git mv |
| `dental_progression_ai/src/database/connection.py` | `backend/app/models/connection.py` | git mv |
| `dental_progression_ai/src/database/doctors.py` | `backend/app/models/doctors.py` | git mv |
| `dental_progression_ai/src/database/patients.py` | `backend/app/models/patients.py` | git mv |
| `dental_progression_ai/src/database/xrays.py` | `backend/app/models/xrays.py` | git mv |
| `dental_progression_ai/src/database/audit.py` | `backend/app/models/audit.py` | git mv |
| `dental_progression_ai/src/database/appointments.py` | `backend/app/models/appointments.py` | git mv |
| `dental_progression_ai/src/database/notifications.py` | `backend/app/models/notifications.py` | git mv |
| `dental_progression_ai/src/database/id_generator.py` | `backend/app/models/id_generator.py` | git mv |
| `dental_progression_ai/src/database/talpa_records.py` | `backend/app/models/talpa_records.py` | git mv |
| `dental_progression_ai/src/database/__init__.py` | `backend/app/models/__init__.py` | git mv |
| `dental_progression_ai/src/core/preprocessing.py` | `backend/app/ml/preprocessing/clahe.py` | git mv |
| `dental_progression_ai/src/core/alignment.py` | `backend/app/ml/preprocessing/alignment.py` | git mv |
| `dental_progression_ai/src/models/detection.py` | `backend/app/ml/detection/yolo_detector.py` | git mv |
| `dental_progression_ai/src/models/landmarks.py` | `backend/app/ml/landmarks/cej_abc_extractor.py` | git mv |
| `dental_progression_ai/src/core/bone_loss.py` | `backend/app/ml/measurement/bone_loss.py` | git mv |
| `dental_progression_ai/src/core/visualization.py` | `backend/app/ml/explainability/overlay.py` | git mv |
| `dental_progression_ai/src/core/risk.py` | `backend/app/ml/fusion/multimodal_risk.py` | git mv |
| `dental_progression_ai/src/core/progression.py` | `backend/app/services/progression_service.py` | git mv |
| `dental_progression_ai/src/analysis/progression_velocity_calculator.py` | `backend/app/services/progression_velocity.py` | git mv |
| `dental_progression_ai/src/analysis/__init__.py` | `backend/app/services/__init__.py` | git mv |
| `dental_progression_ai/src/core/report.py` | `backend/app/services/report_service.py` | git mv |
| `dental_progression_ai/src/core/progression_map.py` | `backend/legacy/progression_map_placeholder.py` | git mv |
| `dental_progression_ai/src/core/velocity.py` | `backend/legacy/velocity_duplicate.py` | git mv |
| `dental_progression_ai/src/core/talpa.py` | `backend/legacy/talpa_engine_duplicate.py` | git mv |
| `dental_progression_ai/orchestrator.py` | `backend/legacy/orchestrator_broken.py` | move (untracked) |
| `dental_progression_ai/models/inference.py` | `backend/legacy/inference_duplicate.py` | move (untracked) |
| `dental_progression_ai/evaluate_talpa.py` | `backend/scripts/evaluate_talpa.py` | move (untracked) |
| `dental_progression_ai/pyproject.toml` | `backend/pyproject.toml` | move (untracked) |
| `dental_progression_ai/Dockerfile` | `backend/Dockerfile` | move (untracked) |
| `dental_progression_ai/docker-compose.yml` | `docker-compose.yml` | move (untracked) |
| `dental_progression_ai/.env.example` | `.env.example` | move (untracked) |
| `dental_progression_ai/.env` | `.env` | move (untracked) |
| `dental_progression_ai/.gitignore` | `backend/.gitignore.utf16-original` | move (untracked) |
| `dental_progression_ai/README.md` | `backend/README.md` | move (untracked) |
| `dental_progression_ai/docs/KEY_ROTATION.md` | `docs/KEY_ROTATION.md` | move (untracked) |
| `dental_progression_ai/docs/PRODUCTION_DEPLOYMENT.md` | `docs/PRODUCTION_DEPLOYMENT.md` | move (untracked) |
| `dental_progression_ai/docs/README_SECURITY.md` | `docs/README_SECURITY.md` | move (untracked) |
| `dental_progression_ai/docs/TALPA.md` | `docs/TALPA.md` | move (untracked) |
| `dental_progression_ai/docs/AUDIT_REPORT.md` | `docs/AUDIT_REPORT.md` | move (untracked) |
| `dental_progression_ai/.streamlit/config.toml` | `tools/streamlit_prototype/.streamlit/config.toml` | git restore + git mv |
| `dental_progression_ai/src/ui/main.py` | `tools/streamlit_prototype/src_ui/main.py` | git restore + git mv |
| `dental_progression_ai/src/ui/pg_analytics.py` | `tools/streamlit_prototype/src_ui/pg_analytics.py` | git restore + git mv |
| `dental_progression_ai/src/ui/pg_auth.py` | `tools/streamlit_prototype/src_ui/pg_auth.py` | git restore + git mv |
| `dental_progression_ai/src/ui/pg_dashboard.py` | `tools/streamlit_prototype/src_ui/pg_dashboard.py` | git restore + git mv |
| `dental_progression_ai/src/ui/pg_patients.py` | `tools/streamlit_prototype/src_ui/pg_patients.py` | git restore + git mv |
| `dental_progression_ai/src/ui/pg_report_vault.py` | `tools/streamlit_prototype/src_ui/pg_report_vault.py` | git restore + git mv |
| `dental_progression_ai/src/ui/pg_risk_watchlist.py` | `tools/streamlit_prototype/src_ui/pg_risk_watchlist.py` | git restore + git mv |
| `dental_progression_ai/src/ui/pg_tooth_timeline.py` | `tools/streamlit_prototype/src_ui/pg_tooth_timeline.py` | git restore + git mv |
| `dental_progression_ai/src/ui/pg_xray_comparison.py` | `tools/streamlit_prototype/src_ui/pg_xray_comparison.py` | git restore + git mv |
| `dental_progression_ai/src/ui/styles.py` | `tools/streamlit_prototype/src_ui/styles.py` | git restore + git mv |
| `dental_progression_ai/web_app/pg_analytics.py` | `tools/streamlit_prototype/web_app/pg_analytics.py` | git restore + git mv |
| `dental_progression_ai/web_app/pg_appointments.py` | `tools/streamlit_prototype/web_app/pg_appointments.py` | git restore + git mv |
| `dental_progression_ai/web_app/pg_auth.py` | `tools/streamlit_prototype/web_app/pg_auth.py` | git restore + git mv |
| `dental_progression_ai/web_app/pg_dashboard.py` | `tools/streamlit_prototype/web_app/pg_dashboard.py` | git restore + git mv |
| `dental_progression_ai/web_app/pg_notifications.py` | `tools/streamlit_prototype/web_app/pg_notifications.py` | git restore + git mv |
| `dental_progression_ai/web_app/pg_patients.py` | `tools/streamlit_prototype/web_app/pg_patients.py` | git restore + git mv |
| `dental_progression_ai/web_app/pg_profile.py` | `tools/streamlit_prototype/web_app/pg_profile.py` | git restore + git mv |
| `dental_progression_ai/web_app/streamlit_app.py` | `tools/streamlit_prototype/web_app/streamlit_app.py` | git restore + git mv |
| `dental_progression_ai/web_app/ui_styles.py` | `tools/streamlit_prototype/web_app/ui_styles.py` | git restore + git mv |
| `dental_progression_ai/requirements.txt` | `backend/requirements.legacy.txt` | restored from git (reference) |

### Code changes (needed so the moved code runs, plus safety fixes)
| File | Change | Why |
|---|---|---|
| `backend/app/**`, `backend/scripts/*.py` | Imports rewritten from the old `src/` top-level names (`security.*`, `database.*`, `core.*`, `models.*`, `analysis.*`) to `app.security.*`, `app.models.*`, `app.ml.*`, `app.services.*` | New package layout |
| `backend/app/config.py` (new) | Central paths (`weights/`, `keys/`, `storage/`, `logs/`), mode (`demo`/`live`), Flask settings; loads the root `.env` | Old code used working-directory-relative paths that broke when started from another folder |
| `backend/app/__init__.py` (new) | `create_app()` factory; registers blueprints; seeds demo/bootstrap accounts **from `.env` only** | Replaces the import-time setup in the old `server.py`, which also seeded a hard-coded superadmin password |
| `backend/app/api/*.py` (new) | The old `server.py` routes split into `auth`, `patients`, `radiographs`, `analysis`, `progression`, `reports`, `audit`, `security` and `health` blueprints. Same URLs and responses | Thin route handlers |
| `backend/app/services/analysis_service.py` (new) | The analysis pipeline moved out of the `/api/analyze` route unchanged | Business logic out of routes |
| `backend/app/services/container.py` (new) | Lazily created managers/models | Importing the app no longer loads YOLO or trains a model |
| `backend/app/extensions.py` (new) | Shared CSRF and rate limiter | Needed by the factory and blueprints |
| `backend/wsgi.py` | Rewritten: uses `create_app()`. **Removed hard-coded fallback keys**. Binds to 127.0.0.1 and debug is off unless `FLASK_DEBUG=1` | Secrets never in code; the old monolith ran with `debug=True` |
| `.env` (root, gitignored) | Moved from `dental_progression_ai/.env`. The three values previously hard-coded in `wsgi.py` were appended unchanged (`FIELD_ENCRYPTION_KEY`, `WATERMARK_SECRET_KEY`, `MODEL_SIGNING_PASSWORD`) | Keeps the existing signing key and any encrypted data readable. They are marked weak demo values to rotate in Phase 2 |
| `backend/app/security/model_signing.py` | No default password. A wrong password now **raises an error instead of deleting and regenerating `model_signing.pem`**. Keys are read from `backend/keys/` | The old code silently destroyed the private key |
| `backend/app/api/radiographs.py` | `/api/image` now requires login and only serves files inside `backend/storage/`. `/api/dicom-metadata` requires login. libmagic removed | Fixes audit S13 (unauthenticated `.env`/key read) and part of S14. `import magic` hangs on this machine (python-magic and python-magic-bin both installed), which also froze the old server at startup |
| `backend/app/security/upload_guard.py` | `import magic` made lazy | Same hang |
| `backend/app/security/session.py` | Streamlit import made lazy; unused `requests` import removed | The module is importable without Streamlit |
| `backend/app/services/progression_service.py` | Removed `sys.path` hack | Package imports now work |
| `backend/app/api/health.py` (new) | `GET /` returns JSON (the HTML template was deleted earlier). Added `GET /api/health` and `/health` (the Dockerfile healthcheck already expected it) | `/` used to return a 500 error |
| Old `/admin/dashboard` route | Not carried over | It rendered the deleted HTML template. The admin UI comes in Phase 4 |
| `backend/scripts/*.py` | `models/weights/` changed to `weights/`. Output folders moved under `weights/`. `setup.py` no longer writes placeholder secrets | New layout; secrets never in code |
| `.gitignore` (root) | Rewritten. Ignores `.env`, private keys, weights, runtime storage/logs and datasets. Keeps `.pub` and folder READMEs | The private key was one `git add .` away from being published |
| `backend/.gitignore` | The old `dental_progression_ai/.gitignore` converted from UTF-16 to UTF-8 (same rules). Original copy kept in the pre-restructure backup | Git ignored the UTF-16 file entirely |
| `docker-compose.yml` | All secrets removed (read from `.env`). Streamlit service removed. Ports bound to 127.0.0.1. Build context `./backend` | Secrets never in code |
| `backend/Dockerfile`, `backend/.dockerignore` | Exposes only 5000, sets `HOST=0.0.0.0`; keys, weights and storage kept out of the image | Smaller, safer image |
| `backend/requirements.txt`, `requirements-dev.txt` (new) | Pinned to versions installed on the dev machine. Dropped Streamlit, Plotly, Kaggle, ONNX and libmagic from the runtime set. `requirements.legacy.txt` is the old file restored for reference | The old `requirements.txt` was deleted but the Dockerfile still needed it |
| `backend/pyproject.toml` | Dependencies now read from `requirements.txt`; pytest config added | One source of truth |
| `Makefile`, `run.ps1` (new) | `setup`, `backend`, `frontend`, `test`, `demo` targets; `run.ps1` is the Windows equivalent (make isn't installed on this machine) | Beginner-friendly commands |
| `backend/tests/` (new) | `conftest.py`, `test_app_smoke.py`, `test_crypto.py` | First automated checks |
| Folder `README.md` files (new) | One per folder in the new layout | Master prompt Phase 1 |
| `README.md`, `backend/README.md`, `PROJECT_STRUCTURE.md` | Updated for the new layout. Overclaims ("production-level") removed | Accuracy |

### Known issues deliberately left for Phase 2
- `/api/patients/<id>/history` still has no ownership check (S14), and RBAC still uses the old roles.
- The risk model still retrains on random data when its signature can't be verified (S15). Its path is still `backend/storage/models/risk_model/`, separate from `backend/weights/risk_model/` written by `scripts/train_risk_model.py`. They weren't merged, to avoid overwriting your trained `.pkl`.
- YOLO weights still load when unsigned (only a warning is printed).
- `scripts/train_landmark_detection.py` needs `utilities.dataset_loader.DentalDatasetLoader`, which never existed in git history, so it exits with a clear message. `scripts/train_tooth_detection.py` has the same optional import and skips synthetic generation. A real loader for `DP_datasets` is part of the Phase 2 ML work.
- `backend/legacy/` and `tools/streamlit_prototype/` import old module paths and are not runnable by design.


## Phase 2 (2026-09-28): must-have features

### Files retired to `legacy/` (nothing deleted)
| From | To | How |
|---|---|---|
| `backend/app/security/audit_middleware.py` | `backend/legacy/security/audit_middleware.py` | git mv (retired in Phase 2) |
| `backend/app/security/checks.py` | `backend/legacy/security/checks.py` | git mv (retired in Phase 2) |
| `backend/app/security/governance.py` | `backend/legacy/security/governance.py` | git mv (retired in Phase 2) |
| `backend/app/security/readiness.py` | `backend/legacy/security/readiness.py` | git mv (retired in Phase 2) |
| `backend/app/security/threat_intel.py` | `backend/legacy/security/threat_intel.py` | git mv (retired in Phase 2) |
| `backend/app/security/session.py` | `backend/legacy/security/session_geo_fingerprint.py` | git mv (retired in Phase 2) |
| `backend/app/security/incident_response.py` | `backend/legacy/security/incident_response.py` | git mv (retired in Phase 2) |
| `backend/app/security/watermark.py` | `backend/legacy/security/watermark.py` | git mv (retired in Phase 2) |
| `backend/app/models/xrays.py` | `backend/legacy/models/xrays.py` | git mv (retired in Phase 2) |
| `backend/app/models/appointments.py` | `backend/legacy/models/appointments.py` | git mv (retired in Phase 2) |
| `backend/app/models/notifications.py` | `backend/legacy/models/notifications.py` | git mv (retired in Phase 2) |
| `backend/app/models/id_generator.py` | `backend/legacy/models/id_generator.py` | git mv (retired in Phase 2) |
| `backend/app/models/talpa_records.py` | `backend/legacy/models/talpa_records.py` | git mv (retired in Phase 2) |
| `backend/app/services/progression_velocity.py` | `backend/legacy/services/talpa_progression_velocity.py` | git mv (retired in Phase 2) |
| `backend/scripts/migrate_encryption.py` | `backend/legacy/scripts/migrate_encryption_cbc.py` | move (untracked; retired in Phase 2) |
| `docs/README_SECURITY.md` | `docs/legacy/README_SECURITY_v1.md` | move (outdated; superseded in Phase 2) |
| `docs/PRODUCTION_DEPLOYMENT.md` | `docs/legacy/PRODUCTION_DEPLOYMENT_v1.md` | move (outdated; superseded in Phase 2) |
| `docs/KEY_ROTATION.md` | `docs/legacy/KEY_ROTATION_v1.md` | move (outdated; superseded in Phase 2) |
| `backend/scripts/train_risk_model.py` | `backend/legacy/scripts/train_risk_model_synthetic.py` | move (trained on random synthetic data; replaced by the documented rule-assisted model) |

The Phase 1 smoke test (`backend/tests/test_app_smoke.py`, cookie-session based) was replaced by `tests/test_api.py`; a copy is in the local scratch backup.

### New or rewritten code
| Area | Files | What changed |
|---|---|---|
| Encryption | `app/security/crypto.py` | AES-256-GCM with key IDs (`enc:v1:<kid>:...`), key ring and KMS-style key file, rotation helpers, file/blob encryption bound to its purpose, HKDF-separated blind-index and pseudonym keys. Weak keys are refused instead of silently hashed. The deterministic-nonce mode (audit S1) was removed |
| Authentication | `app/security/auth.py`, `app/models/doctors.py`, `app/api/auth.py` | JWT access (15 min) + rotating refresh cookie with reuse detection, server-side sessions, device binding, TOTP MFA with QR enrolment and replay protection, password policy, lockout. Cookie sessions and CSRF removed |
| Access control | `app/security/rbac.py`, `app/security/zero_trust.py` | Roles admin/dentist/technician/auditor with an explicit permission matrix; every route declares `@secured(permission)` or `@public`, and unclassified routes are denied. Object-level patient checks (fixes S14 IDOR) |
| Audit | `app/security/audit_log.py` | Genesis entry verified (S6), unique sequence (S7), no PHI (S8), HMAC-authenticated Merkle anchors every 20 entries in a separate store (S5), verification pinpoints the first tampered entry |
| Model integrity | `app/security/model_signing.py`, `app/ml/registry.py`, `scripts/sign_model.py` | Signed SHA-256 manifest. The registry refuses unsigned or altered weights and logs it (S15). The risk model no longer retrains itself |
| Uploads | `app/security/upload_guard.py`, `app/api/radiographs.py` | Size, extension, magic bytes, pixel limits, EXIF stripped by re-encoding, DICOM PHI tags removed, random IDs, encrypted temp storage (S12) |
| Decoys | `app/security/honeypot.py` | Realistic unflagged decoys tracked by HMAC tag; access revokes sessions and locks the account for 60 min (S10) |
| Adversarial | `app/security/adversarial.py` | The old metric flagged every real X-ray (high-frequency ratio about 0.997 on all images). Replaced by a noise-residual test calibrated on 30 real radiographs: 0 false alarms, catches ±8 grey-level sign noise |
| API | `app/api/*.py`, `app/api/docs.py`, `app/__init__.py`, `app/schemas/` | New REST routes with the `{data, meta, error, mode}` envelope, pydantic validation, security headers, CORS allow-list, safe errors, OpenAPI at `/api/docs` |
| Quality gate | `app/ml/preprocessing/quality_check.py` | Resolution, sharpness, contrast, exposure; reject or warn. Thresholds calibrated on real radiographs |
| Detection | `app/ml/detection/yolo_detector.py` | Tooth IDs come from the model's FDI classes (fixes the old `11 + i` numbering). Duplicate classes are resolved by confidence |
| Landmarks | `app/ml/landmarks/cej_abc_extractor.py` | Runs on the same full-resolution image as the detector (fixes the coordinate mismatch). Heuristic fallback is labelled |
| Measurement | `app/ml/measurement/bone_loss.py`, `staging.py` | % + mm (with pixel spacing), Tonetti stage I-IV and grade A-C with smoking/HbA1c modifiers |
| Explainability | `app/ml/explainability/gradcam.py`, `overlay.py` | One-pass Grad-CAM stored as an RGBA layer; periodontal-ROI attention check raises `low_attention_validity` |
| Uncertainty | `app/ml/uncertainty/*`, `scripts/calibrate_conformal.py` | Split-conformal intervals and stage sets, OOD checks, review router. Uncalibrated state is explicit |
| Risk | `app/ml/fusion/multimodal_risk.py` | Replaced the random-data model with a documented rule-assisted logistic score with plain-language reasons |
| Progression | `app/services/progression_service.py` | Matching by FDI number, then by position after registration; velocity %/month and %/year; stable/progressing/rapid/improved; unreliable comparisons are flagged |
| Pipeline, storage, reports | `app/services/analysis_service.py`, `storage_service.py`, `report_service.py`, `app/models/analyses.py` | End-to-end pipeline with a labelled demo mode, encrypted blobs, review sign-off (approve/correct/reject, corrections stored), signed PDF with QR + `/api/reports/verify` |
| Config | `backend/config/thresholds.json` | Every threshold in one file |
| Scripts | `scripts/sign_model.py`, `verify_audit.py`, `rotate_keys.py`, `calibrate_conformal.py` | New CLI tools |
| Tests | `backend/tests/*` | 59 tests: crypto, signing, audit chain, upload guard, ML logic, conformal coverage, progression, API security, end-to-end |
| Docs | `docs/SECURITY.md`, `MODEL_CARD.md`, `DATASETS.md`, `KEY_ROTATION.md` | New. Outdated docs moved to `docs/legacy/` |

### Changes to local, gitignored files
- `.env`: added a random `JWT_SECRET_KEY` and `AUDIT_ANCHOR_KEY`, a key ring (new random active key `k2`, old weak key kept as `k1` for reading), and demo accounts for the admin/technician/auditor roles.
- `backend/weights/manifest.json` + `.sig`: your existing weights were signed with your existing key (`scripts/sign_model.py`).

### Honest results from live checks
- A live run on a DP_datasets panoramic image worked end to end: both models verified and loaded, Grad-CAM produced, case routed to review. But the detector found only 2 teeth at confidence 0.25, and the keypoint model returned one box covering many teeth, so landmarks fell back to the heuristic. **The trained weights need retraining on better data.**
- Conformal calibration on `pose/valid` matched 0 teeth, because those labels are generated boxes, not per-tooth annotations. No calibration file was written, so the app reports "uncalibrated" and sends every case to review.

## Phase 3 (2026-09-28): improvements

No files were moved or retired in this phase.

| Item | Files | Notes |
|---|---|---|
| Clinician review queue | `app/api/progression.py` (from Phase 2) | Approve / correct / reject; corrections stored in `corrections` and audit-logged |
| Security Lab | `app/services/security_lab.py`, routes in `app/api/security.py` | 7 safe simulations on throwaway material: tampered model, edited audit entry (plus a full rewrite), replayed/forged/`alg:none` JWT, disguised uploads, edited report, adversarial noise, tampered ciphertext. All 7 defended. Lab runs do not write to the real audit chain except one `SECURITY_LAB_RUN` entry |
| Model Trust data | `GET /api/models/trust` (Phase 2) | Coverage report or an honest "uncalibrated" message, flagged share and reasons, model signature status |
| Signed PDF reports | Phase 2 | Unchanged |
| Demo mode | `app/ml/synthetic.py`, `app/services/demo_seed.py`, `scripts/seed_demo_data.py`, `data/sample/*.png` | Synthetic radiographs with planted bone levels; demo landmark estimator recovers them within ~1-3 %. Demo mode auto-seeds 4 synthetic patients, 9 visits, 2 sign-offs and 1 signed report at startup (`SEED_DEMO_DATA=0` turns it off). Demo files go to `backend/storage/blobs-demo/`, emptied at each demo start |
| Health / status | `GET /api/health`, `/api/system/status`, `/api/dashboard` | Status widget data: DB, model signatures, audit chain, calibration |
| Tests + CI | `backend/tests/test_phase3.py`, `.github/workflows/ci.yml`, `[tool.ruff]` in `backend/pyproject.toml` | 64 tests pass locally. CI runs ruff (error-level rules) + pytest. Ruff is not installed on this machine, so lint has only been checked by a local unused-import scan, not by ruff itself |
| Config thresholds | `backend/config/thresholds.json` (Phase 2) | Unchanged |
| Analysis pipeline | `app/services/analysis_service.py` | Adds a `force_demo` switch (used by the seeder), better demo tooth finder, and demo crest estimation |

## Phase 4 (2026-09-28): React frontend

No existing files were moved. New: everything under `frontend/` (except its README, which was rewritten), plus a frontend job in `.github/workflows/ci.yml`.

| Area | Files | Notes |
|---|---|---|
| Stack | `frontend/package.json` (+ lock) | React 18.3, Vite 5, TypeScript 5.6 strict, Tailwind 3, React Router 7.18 (patched release; 6.x had two moderate advisories), TanStack Query 5, Zustand 5, Framer Motion 11, three.js 0.169 + @react-three/fiber 8 + drei 9 + postprocessing 2, Recharts 2, lucide-react. All pinned; `npm audit --omit=dev` reports 0 vulnerabilities |
| Shell | `src/app`, `src/components/layout` | Lazy-loaded routes, role-filtered sidebar, demo banner, auth and permission guards, page transitions |
| Auth | `src/store/auth.ts`, `src/api/client.ts` | Access token in memory only; silent refresh via the httpOnly refresh cookie; one shared refresh request |
| Design system | `src/components/ui`, `src/styles`, `tailwind.config.js` | Dark clinical theme (navy, cyan/teal, amber = review, red = critical), glass cards, Syne / Inter / JetBrains Mono |
| Dental visuals | `src/components/dental` | Animated tooth cross-section, drag-to-reveal panoramic scanner, staging explorer, pan/zoom radiograph viewer with 5 layers + Grad-CAM opacity, FDI odontogram, tooth panel with conformal interval bar, before/after slider |
| 3D | `src/three` | Procedural molar hero with shield, particles and bloom; clickable dental arch with gums; audit hash chain (tampered blocks turn red); tooth-core trust orb. Lazy chunk; static fallback on no-WebGL, weak devices or reduced motion |
| Pages | `src/pages/*` | Landing, login + MFA, dashboard, patients, new analysis, analysis viewer, progression, review queue, model trust, security center, security lab, reports, public verify, admin, about/architecture, 404, access denied |
| Backend tweaks | `backend/app/config.py`, `services/report_service.py`, `services/progression_service.py` | Report QR codes now open the frontend verify page (`PUBLIC_VERIFY_URL`). Positional tooth matches count as reliable when the radiograph registration succeeded |

Checks: `npx tsc` 0 errors, `eslint` 0 errors, `npm run build` succeeds, backend 64 tests pass. Clicked through the landing page, login, dashboard, patients, review queue, analysis viewer (2D, chart, 3D), progression, Security Lab (7/7 attacks blocked) and Security Center (chain verified) against the demo backend.

## Extra: chairside clinician tools (2026-09-28, requested by Sid)

| Tool | Backend | Frontend | What it does |
|---|---|---|---|
| Periodontal chart | `app/services/clinical_service.py` (`summarize_chart`, `concordance`), `app/api/clinical.py`, `PerioChartStore` in `app/models/analyses.py`, `PerioChartIn` schema | `pages/clinical/PerioChartPage.tsx` | 32-tooth, 6-site probing grid (probing depth, recession, bleeding, plaque, mobility, furcation) with auto-advancing entry, pocket graphs, copy-forward, "deepened ≥ 2 mm" markers. Computes CAL, BOP %, plaque %, sites ≥ 4/6 mm and the clinical stage (interdental CAL), and cross-checks each tooth against the X-ray AI stage (**clinical–radiographic concordance**) with hints for discordant teeth |
| Care plan | `care_plan`, `tooth_prognosis`, `recall_interval` | `pages/clinical/CarePlanPage.tsx` | Combines X-ray and chart into a stage/grade suggestion, EFP S3 step-wise therapy checklist, per-tooth prognosis map (simplified Kwok & Caton), risk-based recall interval (3/4/6 months) with next due date, and a ready-to-send periodontist referral letter |
| Patient explainer | reads the care plan | `pages/clinical/PatientExplainerPage.tsx` | Chairside, plain-language screen: what the stage means, smile summary, tooth cross-section, and a "what if" simulator (quit smoking, HbA1c, daily interdental cleaning, keeping recalls) with a 10-year illustrative projection. Clearly labelled as a conversation aid, not a prediction |
| Recall board | `GET /api/recall` | `pages/clinical/RecallBoardPage.tsx` | Clinic-wide list of overdue, due-soon and scheduled maintenance visits, ranked by risk, with referral flags |

Also: new permissions `chart:read`, `chart:write`, `care:read` (RBAC matrix and `docs/SECURITY.md` updated); demo teeth now get estimated FDI numbers (`demo_fdi_estimate`) so demo charts can be compared; demo seed adds perio charts (with two deliberately discordant teeth) and staggered visit dates. 6 new backend tests (70 total pass). Frontend type-check, lint and build are clean.

## Phase 5 (2026-09-28): API and data contract

| Item | Files | Notes |
|---|---|---|
| OpenAPI 3.0 at `GET /api/docs` | `backend/app/api/docs.py` | Built from the URL map, the Zero Trust decorators (`x-permission` / public) and the pydantic request schemas, so it can't drift from what is enforced. Includes the envelope schema, 401/403/422 responses, multipart uploads and binary downloads |
| `docs/API.md` + `docs/openapi.json` | `backend/scripts/generate_api_docs.py` | Regenerate with `cd backend && python scripts/generate_api_docs.py`. It runs the app in demo mode with throwaway keys and records 48 real request/response examples across 50 operations (long tokens and lists are trimmed) |
| Contract tests | `backend/tests/test_contract.py` | Every `/api` route is classified (public or a permission) and documented; request bodies come from the validation schemas; every JSON reply has `{data, meta, error, mode}` |
| Bug fix | `backend/app/security/zero_trust.py` | Access-denied replies (401/403 from the Zero Trust guard) were missing the `mode` field. Found by the contract test |
| Already true since Phase 2 | — | Consistent envelope, radiographs/overlays/reports stored AES-256-GCM encrypted, pseudonymised IDs (`P-…`) in logs and analytics |

74 backend tests pass.

## Phase 6 (2026-09-28): quality, docs, traceability

| Item | Files |
|---|---|
| Traceability: 7 objectives + 13 security tools → module → API → UI page → test | `docs/TRACEABILITY.md` |
| Architecture diagram, request lifecycle, trust boundaries | `docs/ARCHITECTURE.md` |
| Viva cheat sheet: modules in plain language, likely examiner questions | `docs/VIVA_CHEAT_SHEET.md` |
| Beginner README: pitch, features, architecture, step-by-step setup, demo tour, troubleshooting, honest limitations | `README.md` |
| Optional local HTTPS | `backend/scripts/make_dev_cert.py`, `backend/wsgi.py` (`TLS_CERT` / `TLS_KEY`), `.env.example` |
| Formatter/lint configs and shortcuts | `[tool.black]` + `[tool.ruff]` in `backend/pyproject.toml`, `black`/`ruff` in `requirements-dev.txt`, `lint` and `docs` targets in `Makefile` and `run.ps1` |

Test coverage required by the master prompt is in place: measurement, conformal coverage, progression, crypto (round trip, tamper, nonce uniqueness), RSA sign/verify, JWT expiry, RBAC matrix, audit-chain tamper detection, upload guard, API integration and an end-to-end happy path. 74 backend tests pass; the frontend type-checks, lints and builds cleanly.
