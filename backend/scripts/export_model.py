import os
import argparse
from ultralytics import YOLO

def main():
    parser = argparse.ArgumentParser(description="Export YOLOv8-pose model for PerioVision AI production")
    parser.add_argument("--model", type=str, default="runs/pose/talpa_yolov8n_pose/weights/best.pt", help="Path to trained model weights")
    parser.add_argument("--format", type=str, default="onnx", help="Export format (onnx, engine, openvino, etc.)")
    parser.add_argument("--imgsz", type=int, default=640, help="Export input image size (single int or [h, w])")
    
    args = parser.parse_args()
    
    print("--- TALPA Landmark Model Exporter ---")
    print(f"Model to export: {args.model}")
    print(f"Format: {args.format}")
    print(f"Image Size: {args.imgsz}")
    print("-------------------------------------")
    
    if not os.path.exists(args.model):
        print(f"[ERROR] Model weights not found at: {args.model}")
        print("Please train the model first or specify the correct path using --model.")
        return
        
    model = YOLO(args.model)
    
    # Export the model
    print(f"Exporting model to {args.format}...")
    exported_path = model.export(format=args.format, imgsz=args.imgsz)
    
    print("\n[SUCCESS] Model export complete!")
    print(f"Exported model location: {exported_path}")

if __name__ == "__main__":
    main()
