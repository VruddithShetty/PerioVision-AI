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
| Conformal uncertainty | `ml/uncertainty/`, `weights/conformal_calibration.json` | Split-conformal intervals on bone-loss % | **Calibrated** on DenPAR validation teeth (n = 450); radius 18.6 points at 90 %, coverage measured on the test split 91.5 %. Periapical only |
| Risk | `ml/fusion/multimodal_risk.py` | Hand-weighted logistic score | **Rule-assisted demo**, not trained on outcome data |

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

Validation split: MAE 8.33, stage agreement 66.4 %. The CEJ and crest are often placed near the middle of the tooth because the worst-site labels switch between the mesial and distal sides; bone loss is measured along the root axis, which largely absorbs that offset. Predicting both sites separately is future work.

### Uncertainty (measured)

| Target coverage | Radius q (points) | Coverage on DenPAR test teeth |
|---|---|---|
| 80 % | 12.10 | 82.3 % |
| 90 % (deployed) | 18.56 | 91.5 % |
| 95 % | 26.53 | 96.4 % |

At 90 % only 10.5 % of test teeth get a single-stage prediction set, so most teeth are routed to a dentist. That's conservative by design.

**Not validated on panoramic X-rays.** There the landmark model runs on zoomed crops; such teeth are flagged `landmarks_not_validated` and always reviewed.

## Uncertainty behaviour

- With a calibration file, every tooth gets a bone-loss interval at the configured coverage (default 90 %) and a stage *prediction set*. More than one stage in the set sends the case to review.
- Without a calibration file, every tooth shows the full 0-100 % interval and every stage. The case is marked `uncalibrated` and must be reviewed by a dentist.
- Other triggers for mandatory review: borderline image quality, out-of-distribution or perturbed images, Grad-CAM attention outside the periodontal band, heuristic landmarks, low detection confidence, demo mode.

## Known limitations

- Radiographic bone loss is only a proxy for clinical attachment loss. Stage IV needs the clinician-entered count of teeth lost to periodontitis.
- The mm measurements need DICOM pixel spacing. Otherwise only percentages are used.
- Radiograph registration between visits uses ORB features. Poor overlap marks comparisons as unreliable instead of hiding them.
- The models were trained on small datasets of unknown demographic mix, so performance on other populations or devices is unknown.

## Ethical notes

No real patient data is stored in the repository. The earlier public commit that contained a patient-named image set is described in `docs/AUDIT_REPORT.md` (G2), and it needs owner action.
