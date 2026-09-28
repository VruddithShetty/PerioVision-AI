# backend/weights

Trained model weight files (`*.pt`, `*.pkl`). This folder is gitignored because the files are large. Put `dental_yolov8n.pt` and `dental_landmark_yolov8n-pose.pt` here; without them the app runs in clearly labelled demo mode. From Phase 2 every weight needs a matching `.sig` signature (see `scripts/sign_model.py`).
