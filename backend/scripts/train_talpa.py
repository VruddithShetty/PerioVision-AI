import os
import argparse
from ultralytics import YOLO

def main():
    parser = argparse.ArgumentParser(description="Train YOLOv8-pose model for TALPA landmarks")
    parser.add_argument("--data", type=str, default="datasets/pose/data.yaml", help="Path to data.yaml")
    parser.add_argument("--epochs", type=int, default=100, help="Number of training epochs")
    parser.add_argument("--imgsz", type=int, default=640, help="Input image size")
    parser.add_argument("--device", type=str, default="cpu", help="Device (cpu, cuda, 0, etc.)")
    parser.add_argument("--batch", type=int, default=16, help="Batch size")
    parser.add_argument("--project", type=str, default="runs/pose", help="Project folder name")
    parser.add_argument("--name", type=str, default="talpa_yolov8n_pose", help="Run folder name")
    
    args = parser.parse_args()
    
    print("--- TALPA Landmark YOLOv8-pose Training Pipeline ---")
    print(f"Data configuration: {args.data}")
    print(f"Epochs: {args.epochs}")
    print(f"Image Size: {args.imgsz}")
    print(f"Device: {args.device}")
    print(f"Batch Size: {args.batch}")
    print(f"Project: {args.project}")
    print(f"Run Name: {args.name}")
    print("--------------------------------------------------")
    
    # Initialize a YOLOv8-pose model
    # We load the pretrained yolov8n-pose.pt model weights as the starting point.
    # Ultralytics will automatically download the pretrained weights if not found locally.
    model = YOLO("yolov8n-pose.pt")
    
    # Start training
    results = model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        device=args.device,
        batch=args.batch,
        project=args.project,
        name=args.name,
        workers=0 if args.device == 'cpu' else 4 # Turn off multi-processing workers for CPU runs to prevent Windows overhead
    )
    
    print("\n[SUCCESS] Training process completed!")
    print(f"Results and weights saved under: {os.path.join(args.project, args.name)}")

if __name__ == "__main__":
    main()
