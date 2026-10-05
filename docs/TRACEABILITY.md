# Traceability: synopsis objectives → code → API → UI → tests

Every objective and every security tool named in the synopsis, and where it lives. Paths are relative to the repository root; backend modules are under `backend/app/`, pages under `frontend/src/pages/`, tests under `backend/tests/`.

> The synopsis PDF/PPT were not in `docs/reference/` when this was written, so objective wording follows the master prompt (O1–O7). Put the files in `docs/reference/` and check the wording.

## Objectives

| Objective | Backend module(s) | API endpoint(s) | UI page(s) | Test file(s) |
|---|---|---|---|---|
| **O1 Bone-loss detection**: quality gate, CLAHE, YOLOv8 FDI detection, CEJ/crest landmarks, bone loss %, Stage I–IV / Grade A–C, per-tooth output | `ml/preprocessing/quality_check.py`, `ml/preprocessing/clahe.py`, `ml/detection/yolo_detector.py`, `ml/landmarks/cej_abc_extractor.py`, `ml/measurement/bone_loss.py`, `ml/measurement/staging.py`, `services/analysis_service.py` | `POST /api/radiographs`, `POST /api/analyses`, `GET /api/analyses/{id}` | `new-analysis/NewAnalysisPage`, `analysis/AnalysisViewerPage` (radiograph, dental chart, 3D arch, tooth panel) | `test_ml_logic.py` (geometry, staging, grade, quality gate), `test_api.py::test_end_to_end_workflow`, `test_phase3.py` (demo pipeline accuracy) |
| **O2 Longitudinal progression**: per-visit storage, tooth matching (FDI, then position after registration), delta and velocity, stable / progressing / rapid / improved, unreliable comparisons flagged | `services/progression_service.py`, `ml/preprocessing/alignment.py`, `models/analyses.py` | `GET /api/patients/{id}/progression` | `progression/ProgressionPage` (before/after slider, trend lines, velocity chips, reliability warnings) | `test_ml_logic.py` (labels, matching, unreliable flags), `test_phase3.py` (seeded progression) |
| **O3 Explainability (Grad-CAM)**: heatmap per analysis (all teeth, stored) plus an on-demand map for the selected tooth only, opacity slider, periodontal-ROI attention check → `low_attention_validity` → review | `ml/explainability/gradcam.py`, `ml/explainability/overlay.py`, `ml/uncertainty/review_router.py` | `GET /api/analyses/{id}/image/gradcam`, `GET /api/analyses/{id}/teeth/{tooth}/gradcam` | `analysis/AnalysisViewerPage` (Grad-CAM layer + opacity, ROI layer, attention % in tooth panel) | `test_ml_logic.py::test_review_router_flags`, `test_api.py::test_per_tooth_gradcam_needs_a_verified_model_and_rbac`, `tests_live::test_per_tooth_gradcam_explains_only_the_selected_tooth` |
| **O4 Uncertainty (conformal)**: split-conformal intervals, stage prediction sets, configurable coverage, review router, calibration report | `ml/uncertainty/conformal.py`, `ml/uncertainty/calibration.py`, `ml/uncertainty/ood.py`, `ml/uncertainty/review_router.py`, `scripts/calibrate_conformal.py` | `GET /api/models/trust`, review status in `GET /api/analyses/{id}` | `analysis/AnalysisViewerPage` (interval bar, stage set), `model-trust/ModelTrustPage`, `review/ReviewQueuePage` | `test_ml_logic.py` (quantile formula, coverage on held-out data, prediction sets) |
| **O5 Multimodal risk fusion**: age, sex, smoking, diabetes, HbA1c (clinical model trained on NHANES, AUC 0.65) fused with the radiograph's measured evidence (periapical stage, panoramic whole-film estimate, measurable progression) → combined low/moderate/high, probability, plain-language reasons | `ml/fusion/multimodal_risk.py` (`predict_patient_risk` + `fuse_with_radiograph`; the fusion is a documented rule: the higher level wins) | `POST /api/analyses` (risk block with `fusion`), `GET /api/analyses/{id}`, dashboard risk mix | `analysis/AnalysisViewerPage` (combined level, clinical vs radiograph, gauge + factors), `patients/PatientsPage` (risk-factor form), signed PDF report | `test_ml_logic.py::test_risk_is_monotonic_and_explained`, `::test_risk_fuses_clinical_and_radiograph_evidence`, `tests_live::test_panoramic_films_get_a_validated_whole_film_estimate` |
| **O6 Cybersecurity mechanisms** | see the security table below | | `security/SecurityCenterPage`, `security-lab/SecurityLabPage`, `admin/AdminPage`, `login/LoginPage` | see below |
| **O7 Secure clinical decision support**: login + MFA → patient → upload → quality gate → analysis → explainability + uncertainty → progression → risk → review sign-off → signed report → audit | `services/analysis_service.py`, `services/report_service.py`, `api/*` | full workflow | Dashboard → Patients → New analysis → Viewer → Progression → Review → Reports → Security center | `test_api.py::test_end_to_end_workflow` |

## Security tools named in the synopsis

| Tool | Backend module | API | UI | Tests |
|---|---|---|---|---|
| **AES-256** (GCM, random 96-bit nonce, key IDs, rotation) | `security/crypto.py`, `services/storage_service.py`, `scripts/rotate_keys.py` | patient fields, `POST /api/radiographs`, image and report downloads | Admin → Keys & signing | `test_crypto.py` (round trip, nonce uniqueness, tamper, AAD binding, rotation, weak keys) |
| **RSA signatures** (RSA-PSS over the model manifest and report hashes) | `security/model_signing.py`, `ml/registry.py`, `services/report_service.py`, `scripts/sign_model.py` | `GET /api/models/status`, `POST /api/reports`, `GET/POST /api/reports/verify` | Model trust, Reports, public Verify page | `test_model_signing.py`, `test_api.py::test_end_to_end_workflow` (verify + tampered PDF) |
| **JWT** (15-min access, rotating refresh cookie, reuse detection, device binding) | `security/auth.py`, `api/auth.py`, `security/zero_trust.py` | `/api/auth/login`, `/api/auth/refresh`, `/api/auth/logout` | Login | `test_api.py` (expired, tampered, other device, refresh reuse, logout) |
| **MFA** (TOTP, QR enrolment, replay protection) | `security/auth.py`, `models/doctors.py` | `/api/auth/mfa`, `/api/auth/mfa/enroll`, `/confirm`, `/disable` | Login (6-digit step), Security center → MFA | `test_api.py::test_mfa_enrolment_and_login` |
| **RBAC** (admin, dentist, technician, auditor; matrix; object-level patient access) | `security/rbac.py`, `security/zero_trust.py` | every route (`x-permission` in `/api/docs`), `GET /api/security/rbac-matrix` | Sidebar filtering, access-denied page, Security center → RBAC matrix | `test_api.py::test_rbac_matrix_is_enforced`, `test_patient_isolation_between_dentists`, `test_contract.py` |
| **bcrypt** (cost 12, password policy, lockout) | `security/auth.py`, `models/doctors.py` | `POST /api/auth/login` | Login lockout message | `test_api.py::test_login_failures_are_generic_and_lock_out` |
| **Hashed audit log** (hash chain incl. genesis, anchored Merkle roots, pinpoint first tampered entry, no PHI) | `security/audit_log.py`, `scripts/verify_audit.py` | `GET /api/audit/logs`, `GET /api/audit/verify`, `POST /api/audit/anchor` | Security center (3D hash chain, verify, anchor) | `test_audit_chain.py`, Security Lab `audit-tamper` (`test_phase3.py`) |
| **HTTPS / TLS** | `wsgi.py` (TLS_CERT / TLS_KEY), `scripts/make_dev_cert.py`, HSTS in `app/__init__.py` | all | n/a | manual: run with a dev certificate (see README). The development server is HTTP by default; production needs a TLS reverse proxy |
| Zero Trust (per-request verification, deny by default) | `security/zero_trust.py` | all protected routes | n/a | `test_api.py::test_unclassified_route_is_denied_by_default`, `test_contract.py` |
| Upload guard (magic bytes, size, pixels, EXIF/DICOM strip) | `security/upload_guard.py` | `POST /api/radiographs` | New analysis (blocked-file message) | `test_upload_guard.py`, `test_api.py::test_disguised_upload_is_blocked` |
| Adversarial / OOD screening | `security/adversarial.py`, `ml/uncertainty/ood.py` | analysis result | Viewer → Integrity card | `test_ml_logic.py::test_adversarial_noise_is_detected` |
| Honeypot (decoy records) | `security/honeypot.py` | patient routes | n/a | `test_api.py::test_honeypot_access_locks_the_account` |
| Security Lab (attack simulations) | `services/security_lab.py` | `/api/security-lab/*` | Security lab | `test_phase3.py` |

## Extra clinician tools (beyond the synopsis)

| Tool | Backend | API | UI | Tests |
|---|---|---|---|---|
| Periodontal chart + clinical/radiographic concordance | `services/clinical_service.py` | `/api/patients/{id}/perio-charts` | `clinical/PerioChartPage` | `test_clinical.py` |
| Care plan (EFP steps, prognosis, recall, referral letter) | `services/clinical_service.py` | `/api/patients/{id}/care-plan` | `clinical/CarePlanPage` | `test_clinical.py` |
| Patient explainer with what-if forecast | (reads the care plan) | `/api/patients/{id}/care-plan` | `clinical/PatientExplainerPage` | frontend build |
| Recall board | `api/clinical.py` | `GET /api/recall` | `clinical/RecallBoardPage` | `test_clinical.py::test_recall_board` |
