# backend/weights

The trained models ship with the repository, so a fresh clone or GitHub ZIP runs with real AI after
`.un.ps1 setup` (or `make setup`):

| File | Model | Size |
|---|---|---|
| `dental_yolov8n.pt` | YOLO11m tooth detector, FDI numbers (DENTEX, fine-tuned on Aga Khan) | 41 MB |
| `dental_landmark_yolov8n-pose.pt` | YOLO11m-pose CEJ / root apex / bone crest (DenPAR) | 42 MB |
| `panoramic_screen.pt` | ConvNeXt-T, bone loss per jaw on panoramic films (MM-OPG), float16 | 56 MB |
| `panoramic_severity.pt` | ConvNeXt-T, worst-tooth bone loss on panoramic films (BRAR), float16 | 56 MB |
| `*_metrics.json`, `conformal_calibration.json` | held-out test results and the uncertainty calibration the app reads | small |
| `manifest.json` + `.sig` | SHA-256 of every weight file, RSA-PSS signed | small |

**Integrity:** the app refuses any weight file whose hash is not in the signed manifest. The manifest is signed
with the publisher's key; its public half is `backend/keys/model_signing.pub`. `backend/scripts/setup_local.py`
verifies every shipped file with that key first, then creates your own signing key (needed to sign PDF reports)
and re-signs the already-verified weights with it.

**New weights:** train with the notebooks in `notebooks/`, then `.un.ps1 install-models -From <folder>`
(backs up, installs, signs, tests). Retired or local-only weights are not committed (see `.gitignore`).
