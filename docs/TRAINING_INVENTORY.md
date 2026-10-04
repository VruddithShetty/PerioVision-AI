# Training inventory: what was trained, what the app uses, and why

_Checked 2026-10-04 against `backend/weights/manifest.json` (SHA-256) and every export in `~/Downloads`. All
numbers below were re-measured on the deployed files; CIs are in `docs/RESULTS_WITH_CI.md`._

| # | Training (Colab notebook) | Export | In the app? | Held-out result (deployed file) |
|---|---|---|---|---|
| 1 | Tooth detector v1, DENTEX (`train_periovision_colab`) | `export-20260930…zip` | **Replaced** by #6; kept in `weights_backup/20261004-095323/` | Different hospital (AKU, 250 films): F1 with right number 89.6 % (88.3–90.8) |
| 2 | Landmark model, YOLO11m-pose, DenPAR (`train_landmarks_colab`) | `export-20261002…zip` | **Yes**, `dental_landmark_yolov8n-pose.pt` (hash matches export) | DenPAR test: MAE 7.31 points (6.6–8.1), stage agreement 73.4 % (69.3–77.3) |
| 3 | Conformal calibration (same notebook, then recalibrated adaptively on the laptop) | same | **Yes**, the adaptive version; the Colab version is kept as a backup | 90 % interval coverage 92.3 % (90.0–94.5) |
| 4 | Panoramic screen per jaw, MM-OPG (`train_panoramic_colab` A) | `export_panoramic-20261003…zip` | **Yes**, stored as float16 (max difference from float32: 0.009 points) | AUC maxilla 0.850, mandible 0.874 (approximate CIs until the Colab evaluation runs) |
| 5 | Panoramic worst-tooth bone loss, BRAR (B) | same | **Yes**, float16 | MAE 11.37 points (9.4–13.5), stage agreement 68.5 % (60.6–75.4) |
| 6 | Detector fine-tune on AKU folders 1+3 (D) | `export_panoramic-20261004T040402Z…zip` | **Yes** (installed 2026-10-04 09:53, commit `0930bd2`) | AKU folder 2, same hospital: F1 94.5 % (93.0–95.8); DENTEX official disease test: 89.1 % (86.6–91.3) found with the right number |
| 7 | Per-tooth bone-loss detector, PDCNN (C) | `export_panoramic-20261004T082745Z…zip` | **No, deliberately** | See below |
| 8 | Clinical risk model, NHANES (`scripts/train_risk_model_nhanes.py`) | `app/ml/fusion/risk_model_nhanes.json` | **Yes** | AUC 0.650 (0.633–0.668) on a later survey cycle |
| 9 | Two-site landmark model (`train_landmarks_twosite_colab`) | **not yet run / not downloaded** | No | — |

Files in `backend/weights/` that the app does **not** load (left over from earlier versions): `dental_bone_yolov8n-seg.pt`,
`tooth_detection_yolov8n.pt`, `landmark_detection_model/landmark_cnn.pt`, `risk_model/` (replaced by the NHANES
JSON). `yolov8n.pt` is only a fallback if the trained detector is missing.

## Why Model C (PDCNN) is not in the app

On its own held-out 10 %, Model C reaches mAP@0.5 0.82 and labels 78.9 % of teeth correctly. That split is from
the same dataset it trained on. On **149 BRAR patients it never saw** (`docs/evidence/predictions/pdcnn_on_brar_test.csv`),
its most severe tooth grade per film agrees with the expert stage only **52 %** of the time (weighted kappa 0.44).
That is with the most favourable mapping of its four grades to stages, which was picked after seeing the results.
The installed whole-film model (#5) reaches **68.5 %** (kappa 0.70) on the same patients. PDCNN also publishes no
licence. So Model C would make the panoramic result worse and adds a licence risk.
