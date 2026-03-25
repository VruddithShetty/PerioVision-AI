import os
from ultralytics import YOLO

class ToothDetectionModel:
    def __init__(self, model_path="tooth_detection_yolov8n.pt"):
        # Defaulting to an available generic nano model for CPU efficiency if specific weights absent
        # In production this would be tooth_detection_yolov8n.pt
        if not os.path.exists(model_path):
            print(f"Custom model {model_path} not found, falling back to basic yolov8n.pt")
            model_path = "yolov8n.pt"
            
        self.model = YOLO(model_path)
    
    def detect_teeth(self, image_path):
        """
        Runs YOLOv8-nano inference on the image.
        Returns a list of dictionaries detailing the detected teeth.
        """
        # Run inference (will use CPU implicitly based on environment or small model size)
        results = self.model(image_path, stream=False, verbose=False)
        
        detections = []
        if len(results) > 0:
            result = results[0]
            boxes = result.boxes
            
            # Simulated dummy tooth numbering (11 to 48 quadrant logic based on x coordinate layout)
            # A true model would classify the numbers directly. We'll assign heuristic logical numbers based on sorted X position.
            sorted_indices = boxes.xyxy[:, 0].argsort()
            base_tooth = 11
            
            for rank, idx in enumerate(sorted_indices):
                box = boxes[idx]
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                conf = box.conf[0].cpu().numpy()
                
                # Assign dummy heuristic tooth numbering
                assigned_num = base_tooth + rank
                if assigned_num > 18 and assigned_num < 21: assigned_num = 21 + (assigned_num - 19)
                if assigned_num > 28 and assigned_num < 31: assigned_num = 31 + (assigned_num - 29)
                if assigned_num > 38 and assigned_num < 41: assigned_num = 41 + (assigned_num - 39)
                
                detections.append({
                    "tooth_number": str(assigned_num)[:2],  # Keep 2 digits
                    "box": [int(x1), int(y1), int(x2), int(y2)],
                    "confidence": float(conf)
                })
                
        return detections
