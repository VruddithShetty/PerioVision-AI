import os
import argparse
from ultralytics import YOLO

def main():
    parser = argparse.ArgumentParser(description="Evaluate YOLOv8-pose model for TALPA landmarks")
    parser.add_argument("--model", type=str, default="runs/pose/talpa_yolov8n_pose/weights/best.pt", help="Path to trained model weights")
    parser.add_argument("--data", type=str, default="datasets/pose/data.yaml", help="Path to data.yaml")
    parser.add_argument("--imgsz", type=int, default=640, help="Image size")
    parser.add_argument("--device", type=str, default="cpu", help="Device (cpu, cuda, etc.)")
    
    args = parser.parse_args()
    
    print("--- TALPA Landmark YOLOv8-pose Evaluation Pipeline ---")
    print(f"Model path: {args.model}")
    print(f"Data configuration: {args.data}")
    print(f"Image Size: {args.imgsz}")
    print(f"Device: {args.device}")
    print("------------------------------------------------------")
    
    if not os.path.exists(args.model):
        print(f"[ERROR] Model weights not found at: {args.model}")
        print("Please train the model first or specify the correct path using --model.")
        return
        
    model = YOLO(args.model)
    
    # Run validation / evaluation
    metrics = model.val(
        data=args.data,
        imgsz=args.imgsz,
        device=args.device,
        split='val'
    )
    
    print("\nEvaluation Summary:")
    # Print mAP metrics for box and pose
    # mAP50, mAP50-95
    box_map50 = metrics.box.map50
    box_map = metrics.box.map
    pose_map50 = metrics.pose.map50
    pose_map = metrics.pose.map
    
    print(f"  Box Detection mAP50: {box_map50:.4f}")
    print(f"  Box Detection mAP50-95: {box_map:.4f}")
    print(f"  Pose Keypoints mAP50: {pose_map50:.4f}")
    print(f"  Pose Keypoints mAP50-95: {pose_map:.4f}")
    print("\n[SUCCESS] Model evaluation complete!")

if __name__ == "__main__":
    main()
