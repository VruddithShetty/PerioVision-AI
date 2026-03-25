"""
download_and_retrain.py
=======================
Downloads free dental X-ray datasets and fine-tunes the three
PerioVision AI models for higher accuracy.

USAGE
-----
Step 1 — Install dependencies (if not already done):
    pip install roboflow kaggle gdown

Step 2 — Choose your source and run:

    # Option A: Roboflow Universe (requires free API key)
    python download_and_retrain.py --source roboflow --rf-key YOUR_API_KEY

    # Option B: Kaggle (requires kaggle.json credentials)
    python download_and_retrain.py --source kaggle

    # Option C: Download only (no retrain)
    python download_and_retrain.py --source roboflow --rf-key YOUR_KEY --download-only

    # Option D: Retrain using already-downloaded data
    python download_and_retrain.py --retrain-only

HOW TO GET CREDENTIALS
-----------------------
Roboflow (free):
  1. Go to https://app.roboflow.com  →  Sign up free
  2. Settings → API Keys → copy your Private API key

Kaggle (free):
  1. https://www.kaggle.com/account → Create API Token → downloads kaggle.json
  2. Place kaggle.json at: C:/Users/<you>/.kaggle/kaggle.json
"""

import os
import argparse
import shutil
import glob
from pathlib import Path
from ultralytics import YOLO

# ─────────────────────────────────────────────────────────────────
#  DATASET CONFIGS
# ─────────────────────────────────────────────────────────────────
# These are real public datasets on Roboflow Universe — free to use.
ROBOFLOW_DATASETS = [
    # Dataset 1: Dental X-Rays Object Detection — verified via REST API (version=1)
    # https://universe.roboflow.com/dental-xrays-htswv/dental-x-rays-wwauy
    {
        "workspace": "dental-xrays-htswv",
        "project":   "dental-x-rays-wwauy",
        "version":   1,
        "task":      "detect",       # object detection → tooth detection model
        "dest_dir":  "real_datasets/tooth_detection",
        "yaml_name": "data.yaml",
    },
    # Dataset 2: Dental segmentation (public detection used to fine-tune seg model too)
    # https://universe.roboflow.com/siddesh-m7yvj/dental-xray-detection-thf5f
    {
        "workspace": "siddesh-m7yvj",
        "project":   "dental-xray-detection-thf5f",
        "version":   1,
        "task":      "detect",
        "dest_dir":  "real_datasets/teeth_extra",
        "yaml_name": "data.yaml",
    },
]

# Kaggle dataset (panoramic dental X-ray — detection + segmentation combined)
KAGGLE_DATASET   = "humansintheloop/teeth-segmentation-on-dental-x-ray-images"
KAGGLE_DEST_DIR  = "real_datasets/kaggle_dental"


def get_latest_checkpoint(base_dir):
    pattern = os.path.join(base_dir, "**", "weights", "last.pt")
    files = glob.glob(pattern, recursive=True)
    return max(files, key=os.path.getmtime) if files else None


# ─────────────────────────────────────────────────────────────────
#  DOWNLOAD — ROBOFLOW
# ─────────────────────────────────────────────────────────────────
def download_roboflow(api_key):
    try:
        from roboflow import Roboflow
    except ImportError:
        print("❌ roboflow not installed. Run: pip install roboflow")
        return []

    rf   = Roboflow(api_key=api_key)
    yamls = []

    for ds in ROBOFLOW_DATASETS:
        print(f"\n📥 Downloading: {ds['workspace']}/{ds['project']} (v{ds['version']}) [{ds['task']}]")
        try:
            project  = rf.workspace(ds["workspace"]).project(ds["project"])
            dataset  = project.version(ds["version"]).download(
                "yolov8",
                location=ds["dest_dir"],
                overwrite=False
            )
            yaml_path = os.path.join(dataset.location, ds["yaml_name"])
            if os.path.exists(yaml_path):
                yamls.append({"yaml": yaml_path, "task": ds["task"]})
                print(f"   ✅ Saved to {dataset.location}")
            else:
                print(f"   ⚠️  data.yaml not found at {yaml_path} — skipping")
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            print(f"   ℹ️  This dataset may not exist or may require a paid plan.")
            print(f"   ℹ️  Visit https://universe.roboflow.com and search 'dental xray' for alternatives.")

    return yamls


# ─────────────────────────────────────────────────────────────────
#  DOWNLOAD — KAGGLE
# ─────────────────────────────────────────────────────────────────
def download_kaggle():
    try:
        from kaggle.api.kaggle_api_extended import KaggleApiClient
        import kaggle
    except ImportError:
        print("❌ kaggle not installed. Run: pip install kaggle")
        return []

    dest = KAGGLE_DEST_DIR
    os.makedirs(dest, exist_ok=True)
    print(f"\n📥 Downloading Kaggle dataset: {KAGGLE_DATASET}")
    try:
        import kaggle as k
        k.api.authenticate()
        k.api.dataset_download_files(KAGGLE_DATASET, path=dest, unzip=True)
        print(f"   ✅ Saved to {dest}")
    except Exception as e:
        print(f"   ❌ Kaggle download failed: {e}")
        print("   ℹ️  Make sure your kaggle.json is at C:/Users/<you>/.kaggle/kaggle.json")
        return []

    # Look for data.yaml anywhere in the download
    yamls_found = glob.glob(os.path.join(dest, "**", "*.yaml"), recursive=True)
    if yamls_found:
        print(f"   📄 Found YAML: {yamls_found[0]}")
        return [{"yaml": yamls_found[0], "task": "detect"}]
    else:
        print("   ⚠️  No data.yaml found. Dataset may need manual restructuring.")
        return []


# ─────────────────────────────────────────────────────────────────
#  RETRAIN — pick model and fine-tune
# ─────────────────────────────────────────────────────────────────
TASK_CONFIG = {
    "detect": {
        # Upgraded: yolov8s (small) has 2× more capacity than nano
        "base_model":    "tooth_detection_yolov8n.pt",
        "fallback":      "yolov8s.pt",          # ← yolov8s for max accuracy
        "output_name":   "tooth_detection_yolov8n.pt",
        "project":       "runs/detect",
        "run_name":      "best_retrain",
    },
    "segment": {
        "base_model":    "dental_bone_yolov8n-seg.pt",
        "fallback":      "yolov8s-seg.pt",       # ← yolov8s-seg
        "output_name":   "dental_bone_yolov8n-seg.pt",
        "project":       "runs/segment",
        "run_name":      "best_retrain",
    },
    "pose": {
        "base_model":    "dental_landmark_yolov8n-pose.pt",
        "fallback":      "yolov8s-pose.pt",      # ← yolov8s-pose
        "output_name":   "dental_landmark_yolov8n-pose.pt",
        "project":       "runs/pose",
        "run_name":      "best_retrain",
    },
}

def merge_surrogate_data(yaml_path, task):
    """
    Copies surrogate dataset into the real_datasets folder and forces all labels to class 0.
    """
    surrogate_base = None
    if task == "detect":
        surrogate_base = "custom_datasets/pose"
    elif task == "segment":
        surrogate_base = "custom_datasets/seg"

    if not surrogate_base or not os.path.exists(surrogate_base):
        return yaml_path

    # Clean up any stale labels.cache files to force YOLO to re-scan
    cache_files = glob.glob(os.path.join("real_datasets", "**", "*.cache"), recursive=True)
    for cf in cache_files:
        try: os.remove(cf)
        except: pass

    dest_dir = os.path.dirname(yaml_path)
    for split in ["train", "valid"]:
        src_imgs = os.path.join(surrogate_base, "images", split)
        src_lbls = os.path.join(surrogate_base, "labels", split)
        dst_imgs = os.path.join(dest_dir, split, "images")
        dst_lbls = os.path.join(dest_dir, split, "labels")
        
        if not os.path.exists(src_imgs):
            continue
            
        os.makedirs(dst_imgs, exist_ok=True)
        os.makedirs(dst_lbls, exist_ok=True)
        
        copied = 0
        for f in os.listdir(src_imgs):
            if not f.lower().endswith(('.png', '.jpg', '.jpeg')): continue
            name, ext = os.path.splitext(f)
            src_img = os.path.join(src_imgs, f)
            src_lbl = os.path.join(src_lbls, f"{name}.txt")
            
            dst_img = os.path.join(dst_imgs, f"surr_{f}")
            dst_lbl = os.path.join(dst_lbls, f"surr_{name}.txt")
            
            if not os.path.exists(dst_img):
                shutil.copy2(src_img, dst_img)
                
            if os.path.exists(src_lbl):
                # Rewrite labels to force class 0 for tooth detection and correct columns
                try:
                    with open(src_lbl, 'r') as f_in:
                        lines = f_in.readlines()
                    with open(dst_lbl, 'w') as f_out:
                        for line in lines:
                            parts = line.split()
                            if len(parts) > 0:
                                if task == "detect":
                                    parts[0] = "0"
                                    # Force exactly 5 columns for detection (class, x, y, w, h)
                                    f_out.write(" ".join(parts[:5]) + "\n")
                                else:
                                    f_out.write(" ".join(parts) + "\n")
                except Exception as e:
                    print(f"      ⚠️  Error processing label {src_lbl}: {e}")
            copied += 1
        if copied > 0:
            print(f"   📦 Merged {copied} surrogate images + labels into {split} set ({task})")
    
    # Final check: remove any root real_datasets/train or real_datasets/valid folders
    # that might have been created by mistake in previous versions
    for root_split in ["train", "valid"]:
        root_path = os.path.join("real_datasets", root_split)
        if os.path.exists(root_path) and os.path.isdir(root_path):
            try: shutil.rmtree(root_path)
            except: pass
            
    return yaml_path


def retrain(yaml_path, task, epochs=150, batch=8):
    cfg = TASK_CONFIG.get(task)
    if not cfg:
        print(f"⚠️  Unknown task '{task}' — skipping.")
        return

    print("\n🔀 Merging surrogate dataset to boost training size...")
    yaml_path = merge_surrogate_data(yaml_path, task)

    base_model = cfg["base_model"] if os.path.exists(cfg["base_model"]) else cfg["fallback"]
    print(f"\n🏋️  Retraining [{task}] — model: {base_model}  data: {yaml_path}")
    print(f"    Epochs: {epochs}  Batch: {batch}  Device: CPU  EarlyStopping: DISABLED")

    model = YOLO(base_model)
    results = model.train(
        data=yaml_path,
        epochs=epochs,
        imgsz=640,
        batch=batch,
        device="cpu",
        patience=0,             # ← DISABLE early stopping — run all epochs
        optimizer="AdamW",
        lr0=0.0005,             # ← Lower LR for more careful fitting
        lrf=0.001,
        warmup_epochs=5,
        weight_decay=0.0005,
        augment=True,
        degrees=15,             # ← More rotation for dental radiographs
        fliplr=0.5,
        flipud=0.0,
        mosaic=1.0,
        mixup=0.3,              # ← More mixup prevents overfitting
        copy_paste=0.3,         # ← Copy-paste adds synthetic variety
        close_mosaic=20,
        hsv_h=0.02,
        hsv_s=0.7,
        hsv_v=0.4,
        project=cfg["project"],
        name=cfg["run_name"],
        exist_ok=True,
    )

    save_dir = getattr(results, "save_dir", None) or os.path.join(cfg["project"], cfg["run_name"])
    best_pt  = os.path.join(str(save_dir), "weights", "best.pt")
    if os.path.exists(best_pt):
        shutil.copy(best_pt, cfg["output_name"])
        print(f"   ✅ Saved best model → {cfg['output_name']}")
    else:
        print(f"   ⚠️  best.pt not found at {best_pt}")


# ─────────────────────────────────────────────────────────────────
#  RETRAIN FROM EXISTING DOWNLOADED DATA
# ─────────────────────────────────────────────────────────────────
def retrain_from_existing(epochs, batch):
    print("\n🔍 Scanning real_datasets/ for data.yaml files...")
    yaml_files = glob.glob("real_datasets/**/*.yaml", recursive=True)

    if not yaml_files:
        print("❌ No datasets found in real_datasets/. Run without --retrain-only first.")
        return

    # Map task by directory name
    task_hints = {"pose": "pose", "seg": "segment", "detect": "detect", "bone": "segment", "landmark": "pose"}
    for yaml_path in yaml_files:
        task = "detect"  # default
        path_lower = yaml_path.lower()
        for hint, t in task_hints.items():
            if hint in path_lower:
                task = t
                break
        print(f"   📄 {yaml_path}  →  task={task}")
        retrain(yaml_path, task, epochs=epochs, batch=batch)


# ─────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download dental datasets and retrain DentalAI Pro models")

    parser.add_argument("--source",        choices=["roboflow", "kaggle"], default="roboflow",
                        help="Dataset source (default: roboflow)")
    parser.add_argument("--rf-key",        type=str, default="",
                        help="Roboflow private API key (required for --source roboflow)")
    parser.add_argument("--epochs",        type=int, default=150,
                        help="Training epochs (default: 150)")
    parser.add_argument("--batch",         type=int, default=8,
                        help="Batch size (default: 8, reduce to 4 if RAM is low)")
    parser.add_argument("--download-only", action="store_true",
                        help="Only download — do not retrain")
    parser.add_argument("--retrain-only",  action="store_true",
                        help="Skip download — retrain from already-downloaded data in real_datasets/")

    args = parser.parse_args()

    print("=" * 60)
    print("  PerioVision AI — Dataset Downloader & Retrainer")
    print("=" * 60)

    yaml_configs = []

    if not args.retrain_only:
        if args.source == "roboflow":
            if not args.rf_key:
                print("\n❌ --rf-key is required for Roboflow. Get your free key at https://app.roboflow.com")
                exit(1)
            yaml_configs = download_roboflow(args.rf_key)
        elif args.source == "kaggle":
            yaml_configs = download_kaggle()

    if args.download_only:
        print("\n✅ Download complete. Run again without --download-only to retrain.")
        exit(0)

    if args.retrain_only:
        retrain_from_existing(args.epochs, args.batch)
    else:
        for cfg in yaml_configs:
            retrain(cfg["yaml"], cfg["task"], args.epochs, args.batch)

    print("\n" + "=" * 60)
    print("  All done! Updated .pt files are in the project root.")
    print("  Restart the Streamlit app to use the new models.")
    print("=" * 60)
