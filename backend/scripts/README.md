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
| `seed_demo_data.py` | Fill a database with synthetic demo patients |
| `rotate_keys.py`, `verify_audit.py` | Encryption-key rotation and offline audit-chain verification |
| `generate_api_docs.py`, `make_dev_cert.py` | Regenerate `docs/API.md` / `openapi.json`; self-signed HTTPS certificate for local demos |

The dataset converters, external evaluations and thesis analysis scripts (`backend/research/`) that produced the
numbers in `docs/` were removed from the working tree in the final cleanup (2026-10-12). They are in git history:
`git checkout 6bbad02 -- backend/research backend/scripts` restores them.
