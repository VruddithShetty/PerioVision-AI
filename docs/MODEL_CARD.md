# Model Card: PerioVision AI

## Intended use

Decision support for dental professionals reviewing panoramic or periapical radiographs. The system suggests per-tooth radiographic bone loss, a periodontitis stage/grade *suggestion*, progression between visits and a relative risk score. Every output is reviewed by a dentist. It is **not** a diagnostic device and is not for use without clinician oversight.

## Components

| Component | File | What it is | Status |
|---|---|---|---|
| Tooth detector | `weights/dental_yolov8n.pt` (file name kept for compatibility) | YOLO11m at 1280 px, 32 classes named by FDI number (11-48) | **Deployed since 2026-10-04: trained on DENTEX, then fine-tuned on Aga Khan University folders 1 and 3** (`notebooks/train_panoramic_D_colab.ipynb`). Held-out results: Aga Khan folder 2 (96 unseen films, same hospital) tooth-level F1 with the right number **94.5 %**; DENTEX official disease test, diseased teeth found with the right number **89.1 %**. The previous DENTEX-only detector (63-film DENTEX test: precision 94.1 %, recall 94.5 %, mAP50 95.8 %, F1 94.8 %) is kept as `weights_backup/20261004-095323/`. CIs: `docs/RESULTS_WITH_CI.md` |
| Landmark model | `weights/dental_landmark_yolov8n-pose.pt` (file name kept for compatibility) | YOLO11m-pose at 1024 px, 3 keypoints per tooth (CEJ, root apex, bone crest) | Trained on DenPAR (1000 periapical X-rays, specialist-verified labels) with `notebooks/train_landmarks_colab.ipynb`. on 200 held-out DenPAR periapical test X-rays (615 teeth): 99.0 % tooth recall, pose mAP@0.5 96.9 %, bone-loss mean absolute error 7.64 percentage points (median 5.11), 73.1 % stage agreement; 90 % conformal intervals reached 91.5 % coverage |
| Grad-CAM (LayerCAM weighting) | `ml/explainability/gradcam.py` | Class-activation maps over the P3-P5 neck layers of the model that made the detection (detector on panoramic films, pose model on periapical films). Each location is weighted by its own positive gradient (LayerCAM, Jiang et al., IEEE TIP 2021) | **Why LayerCAM:** with classic Grad-CAM (layer-averaged gradients) a single tooth's map put only 16 % of its mass inside that tooth's box, the same as chance (14 %); LayerCAM puts 82 % there (64 % on a panoramic film, where a box covers about 1 % of the image) (`docs/evidence/gradcam_localisation_2026-10-04.json`). **Views:** all teeth (stored with every analysis) and only the selected tooth (on demand, `GET /api/analyses/{id}/teeth/{tooth}/gradcam`, about 1-2 s on a CPU). **Attention check:** on films where bone loss is reported (periapical) each tooth is judged by its own map; on 129 DenPAR test teeth this flags 3.1 % (4.7 % with the all-teeth map; 6.2 % of teeth change flag; median attention 0.63) for about 2 s extra per film (all teeth in one batched backward pass, identical to one pass per tooth) (`docs/evidence/gradcam_attention_per_tooth_denpar40_2026-10-04.json`). The 0.25 threshold is an engineering default, not a validated cut-off |
| Staging/grading | `ml/measurement/staging.py` | 2017 AAP/EFP bands applied to radiographic bone loss | Rule-based |
| Conformal uncertainty | `ml/uncertainty/`, `weights/conformal_calibration.json` | **Normalised (adaptive)** split-conformal intervals on bone-loss %: half-width = q × σ(x), σ grows with the disagreement between the normal and mirrored readings | **Recalibrated 2026-10-05, asymmetric**: σ fitted on half of DenPAR validation, and each side of the interval gets its own quantile (α/2) from the other half's signed errors, because the model underestimates severe bone loss. On the 578 DenPAR test teeth: coverage **93.4 %** at the 90 % target; by reference stage I 98.5 %, II 96.2 %, **III 81.2 %** (symmetric intervals gave 76.9 % on stage III). The guarantee is on average over teeth, not per stage: severe teeth are still under-covered. Periapical only. Earlier files are kept as timestamped backups |
| Risk | `ml/fusion/multimodal_risk.py`, `ml/fusion/risk_model_nhanes.json` | Logistic regression on age, sex, smoking (status, cigarettes/day), diabetes, HbA1c | **Trained** on NHANES 2009-2012 (n = 7,417), tested on a later cycle of the same survey, NHANES 2013-2014 (n = 3,855; temporal hold-out, not an external population): ROC AUC 0.650 (0.645 without HbA1c), Brier 0.226 vs 0.240 for prevalence alone. Outcome: moderate/severe periodontitis (CDC/AAP). Predictions run high on 2013-14 because prevalence fell from 44 % to 39 %: calibration in the large +5.0 points; people in the high band (mean predicted 0.70) had 54.7 % prevalence; deciles in `docs/RESULTS_WITH_CI.md`. Read the probability as a relative ranking. Boosted trees and splines gave no gain (AUC 0.652 / 0.649). The logistic model does not read the radiograph and does not predict progression. **Fusion** (`fuse_with_radiograph`): the combined level is the higher of the clinical level and the radiographic level (measured periapical stage or the panoramic whole-film stage: I low, II moderate, III/IV high; measurable rapid progression high). A documented rule, not a learned weight, because no public dataset links radiographs to periodontitis outcomes |

## Performance

### Tooth detector (measured)

Trained on the public [DENTEX](https://huggingface.co/datasets/ibrahimhamamci/DENTEX) `quadrant_enumeration` set (CC BY-NC-SA 4.0). It was split once with seed 42 into 508 training, 63 validation and 63 **test** X-rays, plus any team-dataset images added by notebook cell 4b (training only). Training stopped early at epoch 67; the best weights are from epoch 37. The test images were never used for training or model selection. Per-tooth results are in `backend/weights/detector_test_metrics.json` (kept with the weights, not committed).

| Metric (test set) | Value |
|---|---|
| Box precision | 0.941 |
| Box recall | 0.945 |
| mAP@0.5 | 0.958 |
| mAP@0.5:0.95 | 0.561 |
| Tooth-level precision / recall / F1 (correct FDI number, IoU ≥ 0.5, conf ≥ 0.25) | 0.943 / 0.953 / 0.948 |

The weakest teeth (mAP@0.5:0.95 of about 0.47-0.49) are the upper canines and premolars (13, 14, 15, 23, 24). The strongest are the lower first and second molars (36, 46, 37). On one unseen low-resolution image from the team's dataset (512 × 256), the full pipeline found 26 teeth, all with model-assigned FDI numbers; the previous detector found 2.

### Tooth detector: external test, then adaptation

**Step 1. Different hospital, no adaptation (previous DENTEX-only detector).** All **250** panoramic films from Aga Khan University (Zenodo 10538750, 6,615 specialist-outlined teeth): detection recall **91.7 %** (95 % CI 90.6–92.8), precision **93.2 %** (92.3–94.1), correct FDI number for **96.9 %** of detected teeth, tooth-level F1 with the right number **89.6 %** (88.3–90.8); film-level bootstrap (`docs/evidence/detector_external_aku_all250_2026-10-04.json`, `docs/RESULTS_WITH_CI.md`). An earlier run reported 91.0 % on 154 films because the script skipped folder 2, whose label folder is spelled `annnotations`; see `docs/DATA_SPLITS.md`. Root-apex points on the same films (748 teeth): median error 7.4 % of tooth length; the panoramic shortfall is in CEJ / crest placement.

**Step 2. Adaptation (deployed detector).** The detector was then fine-tuned on Aga Khan folders 1 and 3 (154 films;
70 / 15 / 15 split of those films for training, model selection and a check) and tested on **folder 2, 96 films it
never saw** (2,580 teeth): tooth-level F1 with the right number rose from 87.4 % to **94.5 %** on the same films. On
the DENTEX official disease test (1,600 diseased teeth) the share found with the right number fell from 91.2 % to
**89.1 %** (some forgetting). Evidence: `docs/evidence/detector_finetune_comparison_2026-10-04.json`, re-measured in
`docs/evidence/detector_finetuned_aku_folder2_2026-10-04.json`.

**What this means for the claims.** Folder 2 is the same hospital and machine as the fine-tuning films, so 94.5 % is
a *held-out* result, not a *different-hospital* result. The only different-hospital number for this project is
Step 1's 89.6 %, measured with the previous detector. A new different-hospital test set would be needed to make
that claim for the deployed detector.

### Panoramic whole-film models: external test (cross-source)

Both whole-film models were run on **all 1,747 PDCNN panoramic films** (github.com/PuckBlink/PDCNN), a source neither
was trained on; none of them duplicates a BRAR film (`docs/evidence/split_audit_pdcnn_vs_brar.json`). PDCNN labels
each film periodontitis yes / no (1,173 / 574). Screen AUC **0.963** (0.955-0.971), worst-tooth estimate AUC
**0.953** (0.943-0.961); at the deployed thresholds the screen flags 92.1 % of periodontitis films and clears
85.4 % of the others. **Read with care:** the label (periodontitis yes / no for the whole film) is an easier
separation than the models' own targets, so this is higher than the same-source MM-OPG result (AUC 0.85 / 0.87)
and says nothing about stage accuracy; and an overlap between PDCNN and the MM-OPG training films could not be
checked because the local MM-OPG archive is incomplete. Per-film output: `docs/evidence/predictions/pdcnn_wholefilm_external.csv`.

### Panoramic whole-film models (patient level, measured)

Per-tooth bone loss is withheld on panoramic films; two whole-image ConvNeXt-T models (1024 x 512) give a
patient-level estimate instead (`app/ml/panoramic/whole_film.py`, trained with `notebooks/train_panoramic_colab.ipynb`).

| Model | Training data | Held-out test | Result |
|---|---|---|---|
| Generalised bone loss, per jaw | ToothXpert MM-OPG, 8,047 films (894 validation) | official 450-film test split | maxilla AUC **0.850** (sensitivity 69 %, specificity 81 %); mandible AUC **0.874** (80 % / 75 %) |
| Worst-tooth bone loss % | BRAR, 690 films (fine-tuned from the screen model; 149 validation) | 149 BRAR films | MAE **11.4** points (median 8.0; predicting the mean: 18.0); stage agreement **68.5 %**; grade agreement 65.1 %; 90 % interval asymmetric (-14.9 / +35.8 points, from validation films' signed errors), coverage 91.3 % overall and 83.3 % on stage III films (the symmetric ±26.5 interval: 90.6 % / 74.1 %) |

Compared with the per-tooth landmark route on panoramic films (18.6 points, 46 % stage agreement), this is clearly
better, but the interval is wide, so no film gets a single-stage set and every panoramic case goes to review. It tends
to underestimate very severe cases (regression toward the mean). Thresholds, interval and test metrics shown in the
app are read from the metrics files. Raw outputs: `docs/evidence/panoramic_*_metrics_2026-10-03.json`.

### Landmarks and bone loss (measured)

Trained on [DenPAR](https://zenodo.org/records/16645076) (CC BY 4.0), official split 649 / 150 / 200 radiographs; per-tooth keypoints were derived with `backend/scripts/convert_denpar.py` (each tooth's worst site). Results on the 200 test radiographs (615 teeth):

| Metric (DenPAR test set) | Value |
|---|---|
| Pose mAP@0.5 / mAP@0.5:0.95 | 0.969 / 0.831 |
| Tooth recall (IoU ≥ 0.5) | 0.990 |
| Keypoint error, % of root length (CEJ / apex / crest) | 18.0 / 6.8 / 17.5 |
| Bone-loss MAE / median absolute error (percentage points) | 7.64 / 5.11 |
| Teeth within 5 / 10 points | 48.9 % / 77.2 % |
| Stage agreement (I / II / III) | 73.1 % |

**Deployed pipeline (2026-10-02, with mirrored test-time augmentation, the keypoints of the normal and mirrored readings averaged):** on the 576 matched DenPAR test teeth, MAE **7.37** (median 4.96), within 5 / 10 points 51.2 % / 79.5 %, stage agreement **73.3 %**, keypoint error CEJ / apex / crest 17.8 / 5.9 / 17.4 % of root length. Output: `docs/evidence/denpar_test_eval_tta_adaptive_2026-10-02.json` (also served to the About page as `weights/pipeline_test_metrics.json`).

Before test-time augmentation, independent re-measurement on 2026-10-02 through the app's own code path (`scripts/evaluate_landmarks.py`, all 200 test films, 575 matched teeth): MAE **7.71**, median 5.19, within 10 points 77.2 %, stage agreement **72.4 %**, 90 % interval coverage **91.3 %**, reference stage inside the prediction set 98.3 %. Raw output: `docs/evidence/denpar_test_eval_2026-10-02.json`.

Validation split: MAE 8.33, stage agreement 66.4 %. The CEJ and crest are often placed near the middle of the tooth because the worst-site labels switch between the mesial and distal sides; bone loss is measured along the root axis, which largely absorbs that offset. Predicting both sites separately is future work.

### Uncertainty (measured)

Recalibrated 2026-10-05 (`scripts/calibrate_conformal.py`, asymmetric, normalised). Held-out DenPAR test teeth:

| Target | Coverage, all teeth | Stage I | Stage II | Stage III (severe) | Mean width (points) |
|---|---|---|---|---|---|
| 80 % | 81.9 % | 91.2 % | 83.7 % | 62.2 % | 24.0 |
| **90 % (deployed)** | **93.7 %** | 98.5 % | 96.2 % | **81.8 %** | 41.5 |
| 95 % | 97.6 % | 99.6 % | 98.7 % | 92.3 % | 58.6 |

(Calibration-script test pass, 575 teeth; the app-path evaluation on 578 teeth gives 93.4 % overall and 81.2 % on
stage III, `docs/RESULTS_WITH_CI.md`.) Conformal coverage holds **on average**, not for every subgroup: severe
teeth, which the model underestimates by about 7 points on average, stay below 90 %. At 90 % only 61 of 578 test
teeth (10.6 %) get a single-stage set, so nearly every case goes to a dentist, by design. **Severe (stage III)
teeth called stage I: 7.6 % (11 of 144)**, the most dangerous error; the panoramic whole-film estimate does this
for 3.7 % (2 of 54) of stage III films.

**Panoramic X-rays: bone loss is not reported.** External test on 240 BRAR panoramic films (expert worst-tooth bone loss, 80 per severity level): worst-tooth error 18.6 points, patient stage agreement 46 %, correlation 0.54 (13.5 points / 56 % even after recalibration on half the data). Panoramic films therefore get tooth detection and FDI numbering plus the whole-film patient estimate above, never per-tooth numbers. Every tooth is "not validated on panoramic", and the case asks for a periapical film. The landmark model is not run at all on panoramic films (it took about 20 of the 28 s per film on a laptop CPU and its output was discarded), and a missing calibration file can no longer switch panoramic per-tooth numbers back on. `landmarks.measure_unvalidated_image_types` in `config/thresholds.json` turns measurement back on for research only.

## Uncertainty behaviour

- With a calibration file, every tooth gets a bone-loss interval at the configured coverage (default 90 %) and a stage *prediction set*. More than one stage in the set sends the case to review.
- Without a calibration file, every tooth shows the full 0-100 % interval and every stage. The case is marked `uncalibrated` and must be reviewed by a dentist.
- Panoramic films: the whole-film worst-tooth estimate carries its own split-conformal 90 % interval (asymmetric: 14.9 points down, 35.8 up). When that interval allows more than one stage (all 149 BRAR test films), the review router flags `panoramic_stage_ambiguous`, so the uncertainty system itself, not only the film-type rule, sends panoramic cases to review. A film routed to the panoramic path but shaped like a periapical film (long/short side ratio below 1.6; every panoramic training film is 1.66 or more) gets no whole-film estimate and is flagged `film_shape_not_panoramic`.
- Other triggers for mandatory review: borderline image quality, out-of-distribution or perturbed images, Grad-CAM attention outside the periodontal band, teeth that could not be measured, low detection confidence, demo mode.
- Images in which no tooth is found are rejected outright (not a dental radiograph).
- Progression: a change between two visits only counts when the radiographs register to each other (RANSAC inliers, plausible scale/rotation, image correlation after warping), are the same film type, and the change exceeds 2 × q (with q = 18.6 points, about 37 points). Smaller changes are labelled "no change beyond measurement error" and never drive the grade, risk score or recall interval. With today's landmark accuracy, per-tooth progression over a year or two is therefore usually **not** detectable. The seeded demo patients use planted synthetic bone levels that skip this check, and the Progression, Care plan and Patient explainer pages show a "Synthetic demo data" banner whenever they are built from them.
- Risk score: trained on NHANES (see Components). Without age (30+), sex (male / female), smoking status and cigarettes/day (smokers) it returns "insufficient data" instead of a number. Without HbA1c it uses the validated model that omits HbA1c.

## Preprocessing contract (do not "fix" without retraining)

What each model sees in the live app must equal what it saw in training. Checked 2026-10-05 against the training
scripts / notebooks and the checkpoints' own `train_args`.

| Model | Training input | Live input | Match |
|---|---|---|---|
| Tooth detector (YOLO11m) | DENTEX / AKU films as stored, Ultralytics letterbox at **1280 px**, no CLAHE | upload decoded to 8-bit grey, copied to 3 channels, `model(image)` at the checkpoint's own `imgsz` = **1280** | yes |
| Landmark model (YOLO11m-pose) | DenPAR JPEGs as stored, letterbox at **1024 px**, no CLAHE | same as above, `imgsz` = **1024**; plus a mirrored pass (TTA, averaged) | yes (TTA is inference-only and is part of the evaluated pipeline) |
| Whole-film screen / severity (ConvNeXt-T) | grey film, `cv2.resize` INTER_AREA to `input_size`, /255, mean 0.449, std 0.226, 3 channels | identical code path (`whole_film._input`), sizes read from the signed metrics file | yes |
| Risk model | NHANES variables as defined in `train_risk_model_nhanes.py` | same feature function (`multimodal_risk.features`) | yes |

**CLAHE is display-only on purpose.** No model was trained on CLAHE-enhanced images, so feeding it to them would be
a train/test mismatch. CLAHE only builds the annotated overlay the dentist looks at.

**Grad-CAM runs at 640 px** (not 1024 / 1280) to keep explanations fast on a CPU. Its maps are matched to the
predicted teeth by box overlap, and their localisation was measured at that size (82 % of a tooth's map inside its
box, `docs/evidence/gradcam_localisation_2026-10-04.json`). Running it at the inference size would add about 4-5 s
per film.

## Versioning, self-check and rollback

- **Everything that changes an output is signed.** `weights/manifest.json` (RSA-PSS) covers the four model files, the
  conformal calibration, the whole-film metrics files (decision thresholds and conformal margins), the evidence
  summary shown on the Model Trust page, the self-check expectations and the risk model's coefficients
  (`external/risk_model_nhanes.json`). Each is verified when it is loaded; a file that fails is refused and its
  output withheld (no per-tooth numbers without a signed calibration, no risk score without signed coefficients,
  no whole-film estimate without a signed metrics file).
- **Self-check (drift / broken-deploy alarm).** `app/ml/canary.py` runs every model on fixed seeded synthetic inputs
  at startup (in the background, which also warms the models up) and compares the outputs with the ones recorded
  when the weights were signed (`weights/canary_expected.json`, written by `scripts/sign_model.py`). A mismatch is
  written to the audit log, shown in System status on the dashboard, and adds `model_self_check_failed` to every
  analysis's review reasons. It proves "same model, same maths as when signed"; clinical accuracy is checked on real
  films by `tests_live/`.
- **Rollback.** `scripts/install_trained_weights.py` moves every file it replaces (weights and their metric /
  calibration files) to `backend/weights_backup/<timestamp>/`. A backup folder is itself a valid install source:
  `.\run.ps1 install-models -From backend\weights_backup\<timestamp>` restores it, re-signs, records the self-check
  outputs and runs the tests. Restart the backend afterwards.
- **No verified model outside demo mode = no analysis.** If the tooth detector is missing or fails its signature in a
  production deployment, `POST /api/analyses` returns 503 "cannot be analysed" and logs `ANALYSIS_REFUSED_NO_MODEL`;
  the demo heuristic is only ever used in demo mode, where every result is labelled demo.
- **Demo mode is in-memory.** Everything added in demo mode is erased when the backend restarts; the dashboard's
  System status and the banner on every page say so.

## Known limitations

- Radiographic bone loss is only a proxy for clinical attachment loss. Stage IV needs the clinician-entered count of teeth lost to periodontitis.
- The mm measurements need DICOM pixel spacing. Otherwise only percentages are used.
- Radiograph registration between visits uses ORB features. Its acceptance thresholds were set on DenPAR films (unrelated pairs vs. the same film re-exposed); they have not yet been checked on real follow-up pairs of the same patient.
- Interval width follows the mirrored-reading disagreement, which only weakly predicts the error (rank correlation about 0.17), so some hard teeth still get narrow intervals. Coverage is balanced on average: 91.0 % on the easier half of teeth and 93.4 % on the harder half.
- Analysis runs the landmark model twice (normal and mirrored), about 2 × the time on CPU.
- The models were trained on small datasets of unknown demographic mix, so performance on other populations or devices is unknown.

## Ethical notes

No real patient data is stored in the repository. An early public commit contained a radiograph set whose file names include personal names; it is gone from the working tree but remains in the git history until the owner rewrites history (see `docs/PROJECT_REPORT.md`, phase 0).
