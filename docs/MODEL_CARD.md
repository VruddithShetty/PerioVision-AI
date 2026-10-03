# Model Card: PerioVision AI

## Intended use

Decision support for dental professionals reviewing panoramic or periapical radiographs. The system suggests per-tooth radiographic bone loss, a periodontitis stage/grade *suggestion*, progression between visits and a relative risk score. Every output is reviewed by a dentist. It is **not** a diagnostic device and is not for use without clinician oversight.

## Components

| Component | File | What it is | Status |
|---|---|---|---|
| Tooth detector | `weights/dental_yolov8n.pt` (file name kept for compatibility) | YOLO11m at 1280 px, 32 classes named by FDI number (11-48) | Trained on a free Colab T4 GPU with `notebooks/train_periovision_colab.ipynb`. Test set (63 held-out DENTEX panoramic X-rays): **precision 94.1 %, recall 94.5 %, mAP50 95.8 %, mAP50-95 56.1 %**; tooth-level F1 94.8 % (right FDI number, IoU ≥ 0.5) |
| Landmark model | `weights/dental_landmark_yolov8n-pose.pt` (file name kept for compatibility) | YOLO11m-pose at 1024 px, 3 keypoints per tooth (CEJ, root apex, bone crest) | Trained on DenPAR (1000 periapical X-rays, specialist-verified labels) with `notebooks/train_landmarks_colab.ipynb`. on 200 held-out DenPAR periapical test X-rays (615 teeth): 99.0 % tooth recall, pose mAP@0.5 96.9 %, bone-loss mean absolute error 7.64 percentage points (median 5.11), 73.1 % stage agreement; 90 % conformal intervals reached 91.5 % coverage |
| Grad-CAM | `ml/explainability/gradcam.py` | Gradient-weighted activation maps over the detector's P3-P5 neck layers | Works on the signed detector |
| Staging/grading | `ml/measurement/staging.py` | 2017 AAP/EFP bands applied to radiographic bone loss | Rule-based |
| Conformal uncertainty | `ml/uncertainty/`, `weights/conformal_calibration.json` | **Normalised (adaptive)** split-conformal intervals on bone-loss %: half-width = q × σ(x), σ grows with the disagreement between the normal and mirrored readings | **Calibrated** 2026-10-02 on DenPAR validation (σ fitted on 221 teeth, q on the other 221); on the 576 test teeth: coverage 92.2 % at the 90 % target, average half-width 19.0 points (from about ±14 on consistent teeth to ±40 on inconsistent ones). Periapical only. The previous fixed-width file is kept as a backup |
| Risk | `ml/fusion/multimodal_risk.py`, `ml/fusion/risk_model_nhanes.json` | Logistic regression on age, sex, smoking (status, cigarettes/day), diabetes, HbA1c | **Trained** on NHANES 2009-2012 (n = 7,417), temporally validated on NHANES 2013-2014 (n = 3,855): ROC AUC 0.650 (0.645 without HbA1c), Brier 0.226 vs 0.240 for prevalence alone. Outcome: moderate/severe periodontitis (CDC/AAP). Predictions run 4-10 points high on 2013-14 because prevalence fell from 44 % to 39 %. Boosted trees and splines gave no gain (AUC 0.652 / 0.649). It does not use the radiograph and does not predict progression |

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

### Tooth detector: external test (different hospital and machine)

154 panoramic films from Aga Khan University (Zenodo 10538750, 4,035 specialist-outlined teeth): detection recall **93.8 %**, precision **94.1 %**, correct FDI number for **96.9 %** of detected teeth, tooth-level F1 with the right number **91.0 %** (`docs/evidence/detector_external_aku_2026-10-03.json`). Root-apex points on the same films (748 teeth): median error 7.4 % of tooth length; the panoramic shortfall is in CEJ / crest placement.

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

| Target coverage | Radius q (points) | Coverage on DenPAR test teeth |
|---|---|---|
| 80 % | 12.10 | 82.3 % |
| 90 % (deployed) | 18.56 | 91.5 % |
| 95 % | 26.53 | 96.4 % |

At 90 % only 10.5 % of test teeth get a single-stage prediction set, so most teeth are routed to a dentist. That's conservative by design.

**Panoramic X-rays: bone loss is not reported.** External test on 240 BRAR panoramic films (expert worst-tooth bone loss, 80 per severity level): worst-tooth error 18.6 points, patient stage agreement 46 %, correlation 0.54 (13.5 points / 56 % even after recalibration on half the data). Panoramic films therefore get tooth detection and FDI numbering only. Every tooth is "not validated on panoramic", and the case asks for a periapical film. `landmarks.measure_unvalidated_image_types` in `config/thresholds.json` turns measurement back on for research only.

## Uncertainty behaviour

- With a calibration file, every tooth gets a bone-loss interval at the configured coverage (default 90 %) and a stage *prediction set*. More than one stage in the set sends the case to review.
- Without a calibration file, every tooth shows the full 0-100 % interval and every stage. The case is marked `uncalibrated` and must be reviewed by a dentist.
- Other triggers for mandatory review: borderline image quality, out-of-distribution or perturbed images, Grad-CAM attention outside the periodontal band, teeth that could not be measured, low detection confidence, demo mode.
- Images in which no tooth is found are rejected outright (not a dental radiograph).
- Progression: a change between two visits only counts when the radiographs register to each other (RANSAC inliers, plausible scale/rotation, image correlation after warping), are the same film type, and the change exceeds 2 × q (with q = 18.6 points, about 37 points). Smaller changes are labelled "no change beyond measurement error" and never drive the grade, risk score or recall interval. With today's landmark accuracy, per-tooth progression over a year or two is therefore usually **not** detectable.
- Risk score: trained on NHANES (see Components). Without age (30+), sex (male / female), smoking status and cigarettes/day (smokers) it returns "insufficient data" instead of a number. Without HbA1c it uses the validated model that omits HbA1c.

## Known limitations

- Radiographic bone loss is only a proxy for clinical attachment loss. Stage IV needs the clinician-entered count of teeth lost to periodontitis.
- The mm measurements need DICOM pixel spacing. Otherwise only percentages are used.
- Radiograph registration between visits uses ORB features. Its acceptance thresholds were set on DenPAR films (unrelated pairs vs. the same film re-exposed); they have not yet been checked on real follow-up pairs of the same patient.
- Interval width follows the mirrored-reading disagreement, which only weakly predicts the error (rank correlation about 0.17), so some hard teeth still get narrow intervals. Coverage is balanced on average: 91.0 % on the easier half of teeth and 93.4 % on the harder half.
- Analysis runs the landmark model twice (normal and mirrored), about 2 × the time on CPU.
- The models were trained on small datasets of unknown demographic mix, so performance on other populations or devices is unknown.

## Ethical notes

No real patient data is stored in the repository. An early public commit contained a radiograph set whose file names include personal names; it is gone from the working tree but remains in the git history until the owner rewrites history (see `docs/PROJECT_REPORT.md`, phase 0).
