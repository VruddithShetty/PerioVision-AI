import numpy as np
from models.landmark_detection_model.inference import LandmarkDetectionModel

class LandmarkDetector:
    def __init__(self, model_path="dental_landmark_yolov8n-pose.pt"):
        self.detector = LandmarkDetectionModel(model_path=model_path)

    def extract_landmarks(self, image, tooth_detections):
        """
        Extracts anatomical landmarks including CEJ, Root Apex, Bone Crest, 
        and computes the tooth centerline.
        """
        # The underlying model expects the raw image and the bounding boxes of detected teeth
        base_landmarks = self.detector.detect_landmarks(image, tooth_detections)
        
        enhanced_landmarks = {}
        for tooth_id, pts in base_landmarks.items():
            # Calculate centerline (segment from root_apex to cej)
            cej = pts.get("cej", (0, 0))
            apex = pts.get("root_apex", (0, 0))
            crest = pts.get("bone_crest", (0, 0))
            
            # Format to list as required by specification
            tooth_key = f"tooth_{tooth_id}"
            enhanced_landmarks[tooth_key] = {
                "cej": list(cej),
                "root_apex": list(apex),
                "bone_crest": list(crest),
                "centerline": [list(cej), list(apex)] # A line segment
            }
            
        return enhanced_landmarks
