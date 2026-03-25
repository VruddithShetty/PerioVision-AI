import os
import argparse
from ultralytics import YOLO

def train_yolo(dataset_yaml, epochs=100, batch_size=16, img_sz=512):
    """
    Trains a YOLOv8 Nano model on a specified dataset.
    Optimizes hyperparameters for highest mAP (accuracy) and fine-tuning.
    """
    print(f"--- Starting YOLOv8 Training Pipeline ---")
    print(f"Dataset configuration: {dataset_yaml}")
    print(f"Epochs: {epochs} | Batch: {batch_size} | Img Size: {img_sz}")
    
    # 1. Initialize the base YOLOv8 nano model
    model = YOLO('yolov8n.pt')
    
    # 2. Train the model
    # We use augmented hyperparams here to combat overfitting and maximize accuracy
    results = model.train(
        data=dataset_yaml,
        epochs=epochs,
        imgsz=img_sz,
        batch=batch_size,
        patience=20,          # Early stopping to prevent overfitting
        optimizer='auto',
        lr0=0.01,             # Initial learning rate
        lrf=0.01,             # Final learning rate fraction
        warmup_epochs=3.0,
        momentum=0.937,
        weight_decay=0.0005,
        box=7.5,              # Box loss gain (higher means better bounding box precision)
        cls=0.5,              # Class loss gain
        dfl=1.5,              # Distribution Focal Loss gain
        close_mosaic=10,      # Disable mosaic augmentation for final 10 epochs
        hsv_h=0.015,          # Hue augmentation
        hsv_s=0.7,            # Saturation augmentation
        hsv_v=0.4,            # Value augmentation
        degrees=15.0,         # Rotation augmentation (teeth can be slightly angled)
        translate=0.1,
        scale=0.5,
        shear=0.0,
        perspective=0.0,
        flipud=0.0,           # No up/down flip for teeth
        fliplr=0.5,           # Left/Right flip is safe
        mosaic=1.0,           # Mosaic augmentation helps detect small objects (like teeth)
        mixup=0.1,
        copy_paste=0.0,
        workers=8,            # Dataloader workers
        device='cpu'          # Change to '0' if you are running this on a GPU system (e.g. Colab)
    )
    
    print("\n--- Training Complete ---")
    print("The best model weights have been saved in the 'runs/detect/train/weights/best.pt' file.")
    print("You can copy 'best.pt' and rename it to 'tooth_detection_yolov8n.pt' for your production application.")


import glob

def get_latest_checkpoint(base_dir):
    """Finds the most recently modified last.pt file in the given base directory."""
    search_pattern = os.path.join(base_dir, '**', 'weights', 'last.pt')
    checkpoints = glob.glob(search_pattern, recursive=True)
    if not checkpoints:
        return None
    return max(checkpoints, key=os.path.getmtime)

def train_yolo_pose(dataset_yaml, epochs=10, batch_size=8, img_sz=512, resume=False):
    """
    Trains a custom YOLOv8-Pose model on our surrogate dental landmark dataset.
    """
    print(f"--- Starting Custom YOLO-Pose Training ---")
    
    if resume:
        print("Attempting to resume from previous pose training session...")
        last_weight_path = get_latest_checkpoint("runs/pose")
        if last_weight_path and os.path.exists(last_weight_path):
            print(f"Found latest checkpoint: {last_weight_path}")
            model = YOLO(last_weight_path)
            results = model.train(resume=True)
        else:
            print(f"ERROR: Cannot resume. Could not find any checkpoint in runs/pose")
            return
    else:
        # Start from a pose model
        model = YOLO('yolov8n-pose.pt') 
        
        # Train for a few epochs (demo)
        results = model.train(
            data=dataset_yaml,
            epochs=epochs,
            imgsz=img_sz,
            batch=batch_size,
            device='cpu',
            project='runs/pose',
            name='custom_dental_landmarks'
        )
    
    import shutil
    save_dir = getattr(results, 'save_dir', 'runs/pose/custom_dental_landmarks')
    best_weight_path = os.path.join(str(save_dir), 'weights', 'best.pt')
    
    if os.path.exists(best_weight_path):
        shutil.copy(best_weight_path, "dental_landmark_yolov8n-pose.pt")
        print("Saved custom pose model to dental_landmark_yolov8n-pose.pt")
    else:
        print(f"ERROR: Could not find best.pt at {best_weight_path}")

def train_yolo_seg(dataset_yaml, epochs=10, batch_size=8, img_sz=512, resume=False):
    """
    Trains a custom YOLOv8-Seg model on our surrogate dental segmentation dataset.
    """
    print(f"--- Starting Custom YOLO-Seg Training ---")
    
    if resume:
        print("Attempting to resume from previous seg training session...")
        # Note: the user log mentioned the path was created as runs/segment/runs/seg...
        # So we search both runs/seg and runs/segment
        last_weight_path = get_latest_checkpoint("runs/seg") or get_latest_checkpoint("runs/segment")
        if last_weight_path and os.path.exists(last_weight_path):
            print(f"Found latest checkpoint: {last_weight_path}")
            model = YOLO(last_weight_path)
            results = model.train(resume=True)
        else:
            print(f"ERROR: Cannot resume. Could not find any checkpoint for segmentation")
            return
    else:
        # Start from a seg model
        model = YOLO('yolov8n-seg.pt') 
        
        # Train for a few epochs (demo)
        results = model.train(
            data=dataset_yaml,
            epochs=epochs,
            imgsz=img_sz,
            batch=batch_size,
            device='cpu',
            project='runs/seg',
            name='custom_dental_bone'
        )
    
    import shutil
    save_dir = getattr(results, 'save_dir', 'runs/seg/custom_dental_bone')
    best_weight_path = os.path.join(str(save_dir), 'weights', 'best.pt')
    
    if os.path.exists(best_weight_path):
        shutil.copy(best_weight_path, "dental_bone_yolov8n-seg.pt")
        print("Saved custom seg model to dental_bone_yolov8n-seg.pt")
    else:
        print(f"ERROR: Could not find best.pt at {best_weight_path}")


def download_roboflow_dataset(api_key, workspace, project, version):
    """
    Downloads a dataset directly from Roboflow if requested.
    """
    print("Attempting to download dataset from Roboflow...")
    try:
        from roboflow import Roboflow
        rf = Roboflow(api_key=api_key)
        project_ref = rf.workspace(workspace).project(project)
        dataset = project_ref.version(version).download("yolov8")
        print(f"Dataset downloaded to: {dataset.location}")
        return os.path.join(dataset.location, "data.yaml")
    except ImportError:
        print("ERROR: Please 'pip install roboflow' to use this feature.")
        return None
    except Exception as e:
        print(f"ERROR downloading from Roboflow: {e}")
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train YOLOv8 for Dental Radiographs")
    
    parser.add_argument('--dataset', type=str, help="Local path to data.yaml file")
    
    # Roboflow arguments
    parser.add_argument('--rf-key', type=str, help="Roboflow API Key")
    parser.add_argument('--rf-workspace', type=str, help="Roboflow Workspace ID")
    parser.add_argument('--rf-project', type=str, help="Roboflow Project Name")
    parser.add_argument('--rf-version', type=int, help="Roboflow Dataset Version Number")
    
    # Training arguments
    parser.add_argument('--epochs', type=int, default=100, help="Number of training epochs")
    parser.add_argument('--batch', type=int, default=16, help="Batch size")
    
    # Custom training flags
    parser.add_argument('--train-pose', action='store_true', help="Train the custom YOLO-Pose landmark model")
    parser.add_argument('--train-seg', action='store_true', help="Train the custom YOLO-Seg bone model")
    parser.add_argument('--resume', action='store_true', help="Resume an interrupted training session")
    
    args = parser.parse_args()
    
    data_yaml_path = None
    
    if args.rf_key and args.rf_workspace and args.rf_project and args.rf_version:
        data_yaml_path = download_roboflow_dataset(args.rf_key, args.rf_workspace, args.rf_project, args.rf_version)
    elif args.dataset:
        data_yaml_path = args.dataset
    elif args.train_pose or args.train_seg:
        # Don't require --dataset if we are doing the custom surrogate training
        pass
    else:
        print("ERROR: You must provide either a local --dataset yaml path OR Roboflow credentials OR --train-pose/--train-seg")
        exit(1)
        
    if args.train_pose:
        pose_yaml = os.path.abspath("custom_datasets/pose/dataset.yaml")
        if os.path.exists(pose_yaml) or args.resume:
            train_yolo_pose(pose_yaml, epochs=100, batch_size=8, resume=args.resume)
        else:
            print(f"ERROR: Pose dataset not found at {pose_yaml}. Run generate_custom_datasets.py first.")
            
    if args.train_seg:
        seg_yaml = os.path.abspath("custom_datasets/seg/dataset.yaml")
        if os.path.exists(seg_yaml) or args.resume:
            train_yolo_seg(seg_yaml, epochs=100, batch_size=8, resume=args.resume)
        else:
            print(f"ERROR: Seg dataset not found at {seg_yaml}. Run generate_custom_datasets.py first.")
            
    if not args.train_pose and not args.train_seg and data_yaml_path and os.path.exists(data_yaml_path):
        train_yolo(data_yaml_path, epochs=args.epochs, batch_size=args.batch)
