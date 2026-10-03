# PerioVision AI: Verification & Accuracy Audit

- **Date:** 2026-10-02
- **Scope:** `backend/`, `frontend/`, and the installed weights in `backend/weights/` (YOLO11m tooth detector trained on DENTEX; YOLO11m-pose landmark model trained on DenPAR; conformal calibration from the DenPAR validation split).
- **Method:** I read the code and ran it. Every ✅ below was executed and its output checked. Where something could not be executed, the status says so. Two kinds of tests back this report:
  - `backend/tests/`: 91 tests, run without weights (demo mode) and with throwaway keys. They include new attack tests and a regression guard.
  - `backend/tests_live/`: 18 tests that load the **real trained weights** from a temporary, re-signed copy and run them on real radiographs (DenPAR periapical test films and panoramic films from `DP_datasets`). Real weights, keys and data are never modified.
- **Final state:** `tests/` 91 passed · `tests_live/` 18 passed · frontend `tsc`, `eslint` and `vite build` clean · 18 routes crawled in the browser as dentist, auditor and admin with no console errors and no failed API calls.

---

## Part A: Feature completeness

Legend: ✅ fully working (executed) · 🟡 partly working · ❌ missing or fake · ⚪ not verified. Statuses are **after** the fixes in this audit. The "Before" column records what I found.

### Core detection pipeline

| # | Feature | Before | Status | Evidence | Issue | Required fix / done |
|---|---|---|---|---|---|---|
| 1 | CLAHE + normalisation run on uploads | 🟡 | ✅ | `ml/preprocessing/clahe.py:14`; `tests_live::test_clahe_runs_and_changes_the_image` | CLAHE runs and raises local contrast, but only the overlay and demo mode use its output. The live models deliberately receive raw pixels because they were trained on them. Uploads are normalised to 8-bit grey by the upload guard. | **Done:** dead `normalize.py` removed. CLAHE is documented as display and demo enhancement. |
| 2 | Quality gate rejects blurry, low-res and wrong-type images | 🟡 | ✅ | `quality_check.py:13`; `tests_live::test_quality_gate_rejects_degraded_radiographs`, `::test_non_radiograph_is_never_auto_cleared` | Blurred (σ = 12), 200×150 and flat images are rejected. **Done:** in live mode an image in which neither model finds a tooth is rejected (422, "No teeth were found"). A text document and random noise are both rejected (tested). A trained radiograph-vs-other classifier would still catch edge cases such as other X-ray types that contain tooth-like shapes. |
| 3 | YOLO detector loads real weights and returns real boxes | ✅ | ✅ | `registry.py:68`; `tests_live::test_real_signed_models_are_loaded`, `::test_detector_boxes_come_from_the_image` | Boxes differ per image and move 40 px when the image moves 40 px. | — |
| 4 | CEJ / crest landmarks come from the image, not fixed coordinates | ❌ | ✅ | `analysis_service.py:143,175`; `tests_live::test_landmarks_and_bone_loss_are_computed_from_the_image` | **CRITICAL (fixed).** On panoramic films 26 of 29 teeth got *geometric* CEJ/crest points at fixed fractions of the box. | Those teeth are now `not_measured`: no points, no %, no stage. Keypoints shift by 30 px when the film is shifted 30 px (tested). |
| 5 | Bone-loss % computed from real CEJ–crest relative to root length | ❌ | ✅ | `bone_loss.py:14`, `analysis_service.py:206`; `tests_live::test_teeth_without_model_landmarks_get_no_number` | **CRITICAL (fixed).** The fallback geometry gave **17.14 % for every tooth** (0.12/0.70), shown as Stage II. It drove the patient's stage, a grade of B and a "high" risk score of 0.658. | Only model landmarks produce a %. Accuracy re-measured independently, see Part B §5. |
| 6 | Stage follows a documented clinical rule | ✅ | ✅ | `staging.py:26`; `tests_live::test_stage_follows_the_documented_bands` | Stage uses Tonetti et al. 2018 bands (< 15 %, 15–33 %, > 33 %, IV with ≥ 5 teeth lost), with radiographic bone loss standing in for CAL. The **grade** velocity bands (≤ 0.5 / ≤ 2 / > 2 %/yr) are project-defined, not taken from the paper (which uses mm over 5 years). | Document the grade bands as a project choice, or convert to mm when pixel spacing is known. |

### Longitudinal progression

| # | Feature | Before | Status | Evidence | Issue | Required fix / done |
|---|---|---|---|---|---|---|
| 7 | Two visits give a real delta | ✅ | ✅ | `progression_service.py:114` | Delta = current − previous stored measurement. | — |
| 8 | Tooth matching verified (rotated / mirrored second film) | ⚪ | ✅ | `tests_live::test_same_film_rotated_registers_and_matches_the_same_teeth`, `::test_mirrored_film_is_not_matched_tooth_for_tooth` | A film rotated 4° and scaled 3 % registers, and every matched tooth lands on the same anatomy. A mirrored film is refused. | Only synthetic perturbations of the same film were testable; see Remaining gaps. |
| 9 | Velocity uses real timestamps | ✅ | ✅ | `tests_live::test_velocity_uses_the_real_visit_dates` | 366 vs 731 days gives exactly half the rate. | — |
| 10 | Misaligned / non-comparable pairs are flagged | ❌ | ✅ | `alignment.py:17,71`; `progression_service.py:114,168`; `tests_live::test_unrelated_radiographs_are_not_compared_as_progression` | **CRITICAL (fixed).** Registration "confidence" was ratio-test matches ÷ 30. Films of **different patients** scored up to 0.97 "success", and a pair one month apart produced **93.9 %/yr → grade C, risk 0.933**. A failed registration scoring 0.5–0.6 also counted as registered. | Confidence now requires ≥ 25 RANSAC inliers, inlier ratio ≥ 0.5, plausible scale and rotation, and post-warp NCC ≥ 0.5. Different film types are refused. A change counts only if \|Δ\| > 2q (q = calibrated error), otherwise it is labelled "no change beyond measurement error". Only reliable, detectable rates drive grade, risk and recall. **Added:** the earlier film's teeth must land on the current film's teeth after registration (median IoU ≥ 0.5). Two different patients filmed on the same imaging plate (DenPAR 152 / 269) passed every feature check through shared scratches and frame marks; the tooth check refuses them (`tests_live::test_films_sharing_imaging_plate_artefacts_are_not_compared`). `scripts/evaluate_registration.py` on 300 different-patient DenPAR pairs: **0 % false acceptance**. On 100 perturbed same-film pairs (stand-ins for follow-ups): 95 % accepted (`docs/evidence/registration_eval_denpar_synthetic_positives_2026-10-02.json`). |

### Explainability

| # | Feature | Before | Status | Evidence | Issue | Required fix / done |
|---|---|---|---|---|---|---|
| 11 | Grad-CAM from real gradients of the real model on the real image | ❌ | 🟡 | `gradcam.py:56`; `analysis_service.py:143`; `tests_live::test_gradcam_is_computed_from_the_model_that_made_the_detection` | **Fixed:** on periapical films the boxes come from the pose model, but Grad-CAM explained the *panoramic detector*, scoring class "11" at those boxes. When pointed at the pose model, Grad-CAM crashed on an in-place op. It now explains the model that made the detection, and the map changes per image (tested). **Still partial:** one combined map covers all teeth, so selecting a different tooth does not change the heatmap. | Optional: per-tooth Grad-CAM (one backward pass per tooth, slower on CPU). |
| 12 | "Low attention validity" comes from a real ROI check | ✅ | ✅ | `gradcam.py:121`; `tests_live::test_roi_attention_is_measured_per_tooth` | Values vary per tooth, and the flag equals `attention < 0.25`. | — |

### Uncertainty

| # | Feature | Before | Status | Evidence | Issue | Required fix / done |
|---|---|---|---|---|---|---|
| 13 | Real calibration set, script and output | ✅ | ✅ | `weights/conformal_calibration.json` (450 scores, DenPAR validation); `scripts/calibrate_conformal.py`; `docs/evidence/denpar_test_eval_2026-10-02.json` | The file was produced in Colab. The local script used a different path (it counted fallback teeth and skipped the periapical path). | Script now uses the app's `locate_teeth` + `measured` and writes the adaptive calibration. **Re-run 2026-10-02** on DenPAR validation, verified on test. The Colab file is kept as `conformal_calibration.backup-20261002-153536.json`. |
| 14 | Prediction sets change with input difficulty | ❌ | ✅ | `conformal.py:38`; `tests_live::test_conformal_intervals_use_the_calibrated_q` | Was: every tooth got ±q (18.6). Keypoint confidence was tried as the difficulty signal and **rejected**: rank correlation with error 0.14, no gain on hard teeth. **Done:** the mirrored-reading disagreement is the difficulty signal (rank correlation 0.17), with normalised split conformal: σ fitted on half of DenPAR validation, q on the other half. On the DenPAR test split: coverage 92.2 %, 91.0 % on easier and 93.4 % on harder teeth (was 94.1 % / 88.5 %). Widths range from about ±14 to ±40. Tests: `tests/test_ml_logic.py::test_adaptive_interval_scales_with_difficulty`, `tests_live::test_conformal_intervals_use_the_calibrated_q`. |
| 15 | Coverage on Model Trust comes from an evaluation run | ✅ | ✅ | `ModelTrustPage.tsx` reads `/api/models/trust`; independent re-run (Part B §5) | Claimed 91.5 %; re-measured **91.3 %** on the 575 DenPAR test teeth. | — |

### Multimodal risk fusion

| # | Feature | Before | Status | Evidence | Issue | Required fix / done |
|---|---|---|---|---|---|---|
| 16 | Risk responds to smoking / diabetes / HbA1c, and its factors change | ✅ | ✅ | `tests/test_ml_logic.py::test_risk_responds_to_each_clinical_toggle`; `tests_live::test_risk_changes_with_clinical_inputs_on_a_real_analysis` | — | — |
| 17 | Untrained model labelled "rule-based demo" | 🟡 | ✅ | `multimodal_risk.py`, `risk_model_nhanes.json`, `scripts/train_risk_model_nhanes.py` | **CRITICAL (fixed):** missing age became 30, missing bone loss became 0 %, and a probability was still shown. | Missing inputs → `status: insufficient_data`. **Replaced the hand-set weights with a trained model:** logistic regression on NHANES 2009-2012 (n = 7,417), validated on NHANES 2013-2014 (n = 3,855): AUC 0.650, Brier 0.226 (prevalence only 0.240). Tests check that the probability equals the stored coefficients exactly. Honest scope: a clinical-profile risk of moderate/severe periodontitis, not radiograph-based and not progression. |

### Security (attacked, not just read)

| # | Attack | Status | Evidence |
|---|---|---|---|
| 18 | Same plaintext encrypted twice gives different ciphertext (random nonce) | ✅ | `crypto.py:117` (`os.urandom(12)`); `tests/test_crypto.py`: 200 encryptions, 200 distinct nonces; flipped bit → `InvalidTag` |
| 19 | One byte of a weight file changed → refused and logged | ✅ | `tests_live::test_a_one_byte_change_to_the_weights_is_refused_and_logged`: landmark model unavailable, `MODEL_LOAD_REFUSED` in the audit log; restored copy loads again |
| 20 | Expired, forged, unsigned (`alg=none`) and wrong-type JWTs rejected | ✅ | `tests/test_api.py` (expired, tampered, other device), `tests/test_attacks.py::test_forged_tokens_are_rejected` |
| 21 | Technician approving a real analysis is blocked server-side | ✅ | `tests/test_attacks.py::test_technician_cannot_sign_off_even_with_a_real_analysis`: 403 and review history unchanged |
| 22 | Audit entry edited in the database is pinpointed | ✅ | `tests/test_attacks.py::test_audit_entry_edited_in_the_database_is_pinpointed_by_verify_chain`: `/api/audit/verify` reports `first_tampered_seq` = the edited entry |
| 23 | Non-image renamed `.jpg` / `.png` rejected by content | ✅ | `tests/test_upload_guard.py` (PE executable as `.png`, PDF as `.jpg`), `tests/test_api.py::test_disguised_upload_is_blocked` (415) |
| 24 | Passwords stored as bcrypt | ✅ | `tests/test_attacks.py::test_passwords_are_stored_as_bcrypt_hashes` (`$2b$`, `checkpw` succeeds, no plaintext) |
| 25 | MFA cannot be skipped via the API | ✅ | `tests/test_attacks.py::test_mfa_cannot_be_skipped_by_calling_the_api_directly` and `::test_privileged_roles_must_enrol_mfa_before_anything_else`. **Done:** `REQUIRE_MFA_ROLES` (default `admin,dentist` in live mode, off in demo mode) blocks every endpoint except the user's own account settings until MFA is enrolled. The server enforces this from the database, and the UI redirects the user to Security center. |

### Reports & frontend

| # | Feature | Before | Status | Evidence | Issue | Required fix / done |
|---|---|---|---|---|---|---|
| 26 | PDF signature verifies; an edited PDF fails | ✅ | ✅ | `tests/test_api.py::test_end_to_end_workflow` | — | — |
| 27 | Report numbers equal the stored or UI numbers | ❌ | ✅ | `report_service.py:164`; same test now decodes the PDF text | **Fixed:** a dentist's correction was stored, but the **signed PDF still printed only the model's value**. | The PDF now prints the stored model value and a "Clinician corrections" table. The test asserts both. |
| 28 | Every page reachable and loads without console errors | ✅ | ✅ | Browser crawl of 18 routes as dentist, auditor and admin | No console errors; every `/api` call returned 200. Technician-only views were not crawled separately. | — |
| 29 | Every number comes from an API response | ❌ | ✅ | `AboutPage.tsx:14`, `PatientExplainerPage.tsx:25`, `ToothPanel.tsx`, `LandingPage.tsx`; `tests/test_no_fake_numbers.py` | **CRITICAL (fixed):** the About page had typed-in accuracy figures. The patient explainer invented HbA1c 7.5 for diabetics, 10 cigarettes/day, per-grade "typical" rates and habit multipliers, then showed patients **"Tooth at risk in about N years"**. It also counted unmeasured teeth as "healthy" and defaulted an unknown stage to Stage I. The tooth panel drew 0 % for unmeasured teeth. The landing card showed "interval 19–29 %", while the real interval is ±18.6. | About reads the new public `/api/models/metrics`. The explainer forecasts only from a reliable, detectable measured rate and otherwise says so. Habit advice is in words only. The landing card is labelled "Illustration" with no numbers. |
| 30 | 3D scenes render on a mid-range laptop and degrade with reduced motion | ⚪ | ⚪ | `three/SceneGate.tsx` has a reduced-motion / no-WebGL fallback in code | **Not verified:** I could not test a mid-range laptop or the reduced-motion OS setting from here. | Open the landing page with "reduce motion" on and check that the static fallback appears. |

---

## Part B: Accuracy audit (no estimates)

### 1. Smells found (file:line at time of audit) and what was done

| Where | What | Action |
|---|---|---|
| `cej_abc_extractor.py:36` `heuristic_landmarks()` used as a measurement in `analysis_service.py` | Constant 17.14 % bone loss, Stage II | (b) not measured: no %, stage, interval or landmarks |
| `analysis_service.py` `demo_landmarks()` | Same constant when no crest was found in demo images | (b) `demo_unmeasured` |
| `alignment.py:70` `confidence = matches / 30` | Fake registration confidence | (a) RANSAC inliers + plausibility + NCC; tested on real films |
| `progression_service.py` | Velocity from noise (Δ within error) drove grade C | (a) \|Δ\| > 2q rule; `usable_velocities()` |
| `clinical_service.py` `rapid = raw_label …` | Unreliable comparisons shortened recall | (a) only reliable, detectable labels |
| `multimodal_risk.py:48,54-55` `age or 30`, `bone_loss or 0` | Default inputs → plausible score | (b) `insufficient_data` |
| `clinical_service.py:122` `bone_loss_pct or 0.0` | Unmeasured tooth → "favourable" prognosis | (b) "not assessable" |
| `report_service.py:88` | "None % / None %" in the PDF | (b) "not measured" + teeth measured count |
| `PatientExplainerPage.tsx` `DEFAULT_RATE`, `multiplier()`, `hba1c ?? 7.5`, `cigs ?? 10`, `bone_loss ?? 0`, `stage ?? "I"` | Invented forecast shown to patients | (a)/(b) rewritten |
| `ToothPanel.tsx:58` `bone_loss_pct ?? 0` | Unmeasured drawn as 0 % | (b) "Not measured" |
| `AboutPage.tsx:94` | Typed-in accuracy | (a) `/api/models/metrics` |
| `LandingPage.tsx:172` | Sample result contradicting the real ±18.6 | Relabelled "Illustration", numbers removed |
| `demo_seed.py:93` `random.Random(42)` | Synthetic perio charts | Kept: demo only, now tagged `source: synthetic_demo` |
| `synthetic.py:25`, `calibration.py:46`, `security_lab.py` | Seeded RNG | Legitimate (synthetic images, data split, attack simulation); marked `audit-ok` |
| `HeroScene.tsx:74` `Math.random` | Star-field animation | Not a result; allowed (scan limited to pages and components) |
| `yolo_detector.py:80` Grad-CAM `except` → `None` | Swallowed error | Acceptable: returns `None` → "n/a" and `gradcam_available: false`, never a number |

### 2. Fix strategy
Every fake value above was either (a) replaced by a real computation with a test proving it changes with input, or (b) replaced by an explicit "not measured", "insufficient data" or "not assessable" state in both the API and the UI. None became 0, 50 % or another default.

### 3. Regression guard
`backend/tests/test_no_fake_numbers.py`:
- Seeded records must carry `source: "synthetic_demo"` and `mode: "demo"`; uploads carry `source: "uploaded_radiograph"`. No `mode: "live"` record may be tagged synthetic. The live variant is in `tests_live::test_live_api_response_is_live_and_not_synthetic`.
- A static scan fails the build if these patterns return: `bone_loss_pct ?? 0`, a default `probability`, `DEFAULT_RATE`, an `hba1c ?? (…)` default, `Math.random` in pages or components, typed accuracy on the About page, `bone_loss … or 0` in the backend, unseeded RNG in `app/ml`, or the geometric fallback used as a measurement.

### 4. Demo banner
- UI: `AppLayout.tsx:80` reads "**Demo mode — synthetic data, not clinical** · in-memory database …"; each demo analysis shows the same badge.
- API: every envelope carries `"mode": "demo"`, and every analysis carries `mode` and `source`.
- Note: the backend can run with an in-memory demo DB **and** the real models, as it does now. Uploaded films then give `mode: "live"` analyses; the banner says so.

### 5. Independent accuracy re-measurement (not trusted from the metrics files)
`scripts/evaluate_landmarks.py` runs the **app's own path** on the 200 DenPAR **test** films, which were not used to compute q. Output: `docs/evidence/denpar_test_eval_2026-10-02.json`.

| Metric | Claimed (`landmark_test_metrics.json`) | Re-measured |
|---|---|---|
| Teeth found (IoU ≥ 0.5) | 99.0 % | 96.5 % (575/596). 2 of 200 films were routed through the panoramic path. |
| Bone-loss MAE | 7.64 pts | **7.71 pts** (median 5.19) |
| Within 10 pts | 77.2 % | 77.2 % |
| Stage agreement | 73.1 % | **72.4 %** |
| 90 % conformal coverage | 91.5 % | **91.3 %** (q = 18.56) |
| Reference stage inside prediction set | — | 98.3 % |
| Prediction-set sizes (1 / 2 / 3 stages) | — | 63 / 333 / 179: only 11 % of teeth get a single stage |

**After this audit's accuracy work** (mirrored test-time augmentation + adaptive calibration; `docs/evidence/denpar_test_eval_tta_adaptive_2026-10-02.json`): MAE **7.37** (median 4.96), within 5 / 10 points 51.2 % / 79.5 %, stage agreement **73.3 %**, coverage **92.2 %** (easier / harder half 91.0 % / 93.4 %), average half-width 19.0, set sizes 65 / 322 / 189. Averaging the two readings lowered the error on both the validation (8.39 → 8.23) and test splits, so the gain is not a test-set artefact.
| CEJ / crest / apex error (% of root length) | 17.95 / 17.51 / 6.76 | 18.01 / 17.57 / 6.66 |

**Panoramic films:** measured externally on BRAR (above): worst-tooth error 18.6 points, stage agreement 46 %. Panoramic bone-loss numbers are therefore withheld; detection and numbering remain.

---

## Part C: Final verdict

### 1. Pass/fail count
**28 of 30 checklist items pass fully (✅), 1 is partial (🟡: #11, one Grad-CAM map for all teeth) and 1 is not verified (⚪: #30, 3D on the exhibition laptop).** At the start of the audit, 8 items were ❌.

### 2. CRITICAL list (fake or estimated numbers reaching the user)

| # | Finding | Status |
|---|---|---|
| C1 | Geometric fallback landmarks gave a constant 17.14 % bone loss, Stage II, feeding stage, grade and risk (26 of 29 teeth on a real panoramic film) | **Fixed**: surfaced as "not measured" |
| C2 | Unrelated patients' films registered as "success"; noise read as 93.9 %/yr progression → grade C, risk 0.93 | **Fixed**: real registration check plus the measurement-error rule |
| C3 | Risk score computed with invented age (30) and bone loss (0 %) when inputs were missing | **Fixed**: surfaced as `insufficient_data` |
| C4 | Patient explainer: invented HbA1c, cigarettes, yearly rates and multipliers → "Tooth at risk in about N years"; unmeasured teeth counted healthy; unknown stage shown as Stage I | **Fixed**: forecasts only from measured rates; otherwise says it can't forecast |
| C5 | Unmeasured tooth drawn as 0 % (tooth panel) and given "favourable" prognosis | **Fixed**: "not measured" / "not assessable" |
| C6 | Accuracy typed into the About page; landing card interval contradicting the real ±18.6 | **Fixed**: read from `/api/models/metrics`; landing card labelled illustration |
| C7 | Grad-CAM on periapical films explained a model that did not make the detection | **Fixed**: explains the pose model |
| C8 | Signed PDF hid the dentist's corrected values | **Fixed**: both values printed |

**Still open: none.** No remaining code path shows a fake or defaulted number as a result.

### 3. Remaining gaps (need input or data from you)

| Gap | What to supply |
|---|---|
| **Panoramic bone loss is now measured externally, and it is not good enough to show** | **Measured** on 240 expert-graded panoramic films from BRAR (CC BY 4.0, 80 per severity level; `scripts/evaluate_brar_panoramic.py`, `docs/evidence/brar_panoramic_eval_2026-10-02.json`). Worst-tooth error 18.6 points; patient stage agreement 46 %; correlation 0.54. Recalibrating on half of BRAR only reached 13.5 points / 56 % on the other half. So panoramic films now get detection and FDI numbering but **no bone-loss numbers** (`measure_unvalidated_image_types: false`), and the case says to take a periapical film. Part of the gap is definitional: BRAR records 0 % for 75 % of its mild cases, i.e. it counts only loss beyond the normal 1–2 mm. **To measure on panoramic films, you need** CEJ / crest / apex points drawn on ≥ 100 panoramic films. No public, commercially usable set exists: BoneLoss-PAN769 lacks apex points and is non-commercial on request; the only full set (607 films) is unreleased. |
| Registration not yet run on *real* follow-up pairs (false acceptance already measured at 0 / 300 on real different-patient pairs) | **≥ 20 pairs of the same patient's radiographs taken months apart.** No public source allows commercial use. Options: a partner clinic (de-identified), or PhysioNet "Multimodal dental dataset" (free registration plus data-use agreement; repeat visits; research and validation only). Then run `python scripts/evaluate_registration.py --pairs pairs.csv --make-negatives 300 --out ../docs/evidence/registration_eval.json`. |
| Risk model predicts *current* disease from clinical factors, not *future progression* | Now trained and validated on NHANES (public domain). A progression model needs patients followed for years with repeated exams. No public dataset with radiographs exists; the closest public option is the US VA Dental Longitudinal Study (access by application). |
| **Licence check before selling** | DENTEX (detector training) is published under two licences: CC BY 4.0 on Zenodo, CC BY-NC-SA elsewhere. Get written confirmation from its authors, or retrain on the CC BY release only. All other data used is CC BY 4.0 or public domain (see `docs/DATASETS.md`). |
| Edge cases of non-radiographs (#2) | Images without teeth are now rejected. To also catch other X-ray types that contain tooth-like shapes, supply about 500 negative images to train a small classifier. |
| 3D on mid-range hardware (#30) | 5 minutes on the exhibition laptop with "reduce motion" on and off. |

### 4. Re-run instructions
From `backend/`:

```bash
python -m pytest -q
```
91 tests, demo mode. Includes attacks and the no-fake-numbers guard.

```bash
python -m pytest tests_live -q
```
18 tests with the real weights, on temporary signed copies. Needs `backend/weights/`, `~/Downloads/DenPAR/pose_dataset` and the panoramic folder; override the paths with `PERIOVISION_REAL_WEIGHTS`, `PERIOVISION_DENPAR_DIR` and `PERIOVISION_PANORAMIC_DIR`.

```bash
DB_MODE=demo python scripts/evaluate_landmarks.py --images <pose>/images/test --labels <pose>/labels/test --out ../docs/evidence/eval.json
```
Re-measures MAE, stage agreement and coverage on any labelled split (about 15 min on CPU for 200 films). Run it on a split that was **not** used for calibration.

After a new training run:

```bash
.\run.ps1 install-models -From <export folder>
```
Then recalibrate on the validation split and verify on test (this keeps a backup of the old file):

```bash
python scripts/calibrate_conformal.py --images <pose>/images/val --labels <pose>/labels/val --test-images <pose>/images/test --test-labels <pose>/labels/test --source "<where the labels came from>"
```

Then publish the deployed-pipeline metrics shown on the About page, and run the three commands above again:

```bash
python scripts/evaluate_landmarks.py --images <pose>/images/test --labels <pose>/labels/test --out ../docs/evidence/eval.json --metrics-out weights/pipeline_test_metrics.json
```

From `frontend/`:

```bash
npx tsc -p tsconfig.app.json --noEmit
```
```bash
npm run lint
```
```bash
npm run build
```
