# backend/scripts

Command-line tools run from the `backend/` folder. They are not imported by the running app.

| Script | Used for |
|---|---|
| `setup.py`, `setup_local.py` | First-time setup: `.env` with fresh secrets and demo logins, signing key, weight check (`.\run.ps1 setup`) |
| `make_production_env.py`, `create_admin.py` | Production install: `.env.production`, separate keys and weights, first admin account |
| `install_trained_weights.py` | Install models exported from a Colab notebook, back up the old ones, re-sign (`.\run.ps1 install-models`) |
| `sign_model.py` | Sign weights, calibration and metric files and record the model self-check outputs |
| `evaluate_landmarks.py`, `calibrate_conformal.py` | Re-measure the installed landmark model on a labelled test set and recalibrate its uncertainty intervals |
| `train_risk_model_nhanes.py` | Train and validate the clinical risk model on NHANES (clinical-only and gum-health self-report versions); writes `app/ml/fusion/risk_model_nhanes.json`, then run `sign_model.py` |
| `recalibrate_risk_nhanes.py` | Temporal recalibration of the risk models (intercept shift fitted on a random half of NHANES 2013-14, checked on the other half), then run `sign_model.py` |
| `calibrate_panoramic_interval.py` | Asymmetric conformal interval for the panoramic worst-tooth estimate (from validation-film predictions) |
| `convert_denpar.py`, `convert_denpar_twosite.py` | DenPAR labels -> YOLO-pose references (worst site / both sites) |
| `convert_periokpt.py` | perio-KPT labels -> the same references, for the external periapical test (data on access request) |
| `evaluate_detector_external.py`, `evaluate_brar_panoramic.py`, `evaluate_registration.py` | External detector test, panoramic per-tooth check, registration check |
| `seed_demo_data.py` | Fill a database with synthetic demo patients |
| `rotate_keys.py`, `verify_audit.py` | Encryption-key rotation and offline audit-chain verification |
| `generate_api_docs.py`, `make_dev_cert.py` | Regenerate `docs/API.md` / `openapi.json`; self-signed HTTPS certificate for local demos |

**Evaluation tooling (`backend/research/`).** Every number in `docs/RESULTS_WITH_CI.md` and on the Model trust page is
regenerated from saved per-item predictions by `python -m research.compute_ci`; `research.export_predictions`
re-creates those predictions from the raw datasets, and `research.split_audit` checks for leakage. These were removed
in the 2026-10-12 cleanup and restored on 2026-10-20, because without them the published numbers could not be
reproduced from the repository (regenerating the results table now reproduces all 67 rows exactly).
