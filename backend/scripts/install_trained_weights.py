"""Install models trained in notebooks/train_periovision_colab.ipynb, then sign them.

Usage (from backend/):
    python scripts/install_trained_weights.py --from C:/Users/you/Downloads/export
Backs up everything it replaces (weights AND their metric / calibration files) to
backend/weights_backup/<timestamp>/, copies in whichever model files the folder holds (tooth detector, landmark
model, panoramic whole-film models), checks each one loads with the expected task / FDI class names /
architecture, copies the metric files and conformal_calibration.json next to them, re-signs weights/manifest.json
and records the model self-check outputs.

ROLLBACK: every backup folder is itself a valid --from folder, so a worse new model is undone with
    .\\run.ps1 install-models -From backend/weights_backup/<timestamp>
(which in turn backs up the model it removes). Restart the backend afterwards.
"""
import argparse
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))  # backend/

from app import config  # noqa: E402
from app.security.model_signing import Signer, SigningError  # noqa: E402

FILES = {"dental_yolov8n.pt": "detect", "dental_landmark_yolov8n-pose.pt": "pose",
         "panoramic_screen.pt": "whole_film", "panoramic_severity.pt": "whole_film"}
METRIC_FILES = ("detector_test_metrics.json", "landmark_test_metrics.json", "conformal_calibration.json",
                "panoramic_screen_metrics.json", "panoramic_severity_metrics.json", "pipeline_test_metrics.json")
FDI = {f"{q}{n}" for q in (1, 2, 3, 4) for n in range(1, 9)}


def check(path: str, task: str) -> str | None:
    if task == "whole_film":
        import torch

        from app.ml.panoramic.whole_film import _network

        name = os.path.basename(path)[:-3]
        metrics_path = os.path.join(os.path.dirname(path), f"{name}_metrics.json")
        if not os.path.exists(metrics_path):
            return f"{name}_metrics.json (architecture, thresholds, conformal radius) is missing"
        metrics = json.load(open(metrics_path, encoding="utf-8"))
        try:
            _network(metrics["arch"], 2 if name == "panoramic_screen" else 1).load_state_dict(
                torch.load(path, map_location="cpu", weights_only=True))
        except Exception as exc:
            return f"does not load as {metrics.get('arch')}: {type(exc).__name__}"
        return None
    from ultralytics import YOLO
    model = YOLO(path)
    if model.task != task:
        return f"expected a {task} model, got {model.task}"
    if task == "detect" and set(map(str, model.names.values())) != FDI:
        return "class names are not the 32 FDI tooth numbers"
    if task == "pose" and list(model.model.yaml.get("kpt_shape", [])) != [3, 3]:
        return "keypoint shape is not [3, 3] (CEJ, apex, crest)"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", required=True, help="the downloaded export folder")
    args = ap.parse_args()
    weights = str(config.WEIGHTS_DIR)
    found = [f for f in FILES if os.path.exists(os.path.join(args.src, f))]
    if not found:
        print(f"ERROR: no {' or '.join(FILES)} in {args.src}")
        return 2
    for f in found:
        problem = check(os.path.join(args.src, f), FILES[f])
        if problem:
            print(f"ERROR: {f}: {problem}. Nothing was changed.")
            return 2
    backup = os.path.join(os.path.dirname(weights), "weights_backup", time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(backup, exist_ok=True)
    for f in found:
        if os.path.exists(os.path.join(weights, f)):
            shutil.move(os.path.join(weights, f), os.path.join(backup, f))
        shutil.copy2(os.path.join(args.src, f), os.path.join(weights, f))
        print(f"installed {f} (old copy in weights_backup/{os.path.basename(backup)}/)")
    for m in METRIC_FILES:
        if os.path.exists(os.path.join(args.src, m)) and os.path.exists(os.path.join(weights, m)):
            shutil.copy2(os.path.join(weights, m), os.path.join(backup, m))   # keep weights and metrics together
    for m in METRIC_FILES:
        if os.path.exists(os.path.join(args.src, m)):
            shutil.copy2(os.path.join(args.src, m), os.path.join(weights, m))
            data = json.load(open(os.path.join(weights, m), encoding="utf-8"))
            print(m, {k: v for k, v in data.items() if not isinstance(v, (dict, list))})
    try:
        Signer().sign_manifest(weights)
        try:                                     # record the self-check outputs of the new models, then re-sign
            from app.ml import canary
            from app.services import container

            container.reset_models()
            canary.record()
        except Exception as exc:
            print(f"WARNING: self-check outputs not recorded ({exc}); run scripts/sign_model.py")
        Signer().sign_manifest(weights)
    except SigningError as e:
        print(f"ERROR signing: {e}. The app will refuse the new files until they are signed.")
        return 1
    print("Signed weights/manifest.json. Restart the backend to load the new models.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
