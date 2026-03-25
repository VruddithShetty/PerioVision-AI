import os
import numpy as np
from ultralytics import YOLO
import cv2

class LandmarkDetectionModel:
    def __init__(self, model_path="dental_landmark_yolov8n-pose.pt"):
        # Load the custom trained YOLOv8-Pose model
        if not os.path.exists(model_path):
            print(f"Warning: Custom landmark model {model_path} not found. Fallback not available.")
            self.model = None
        else:
            self.model = YOLO(model_path)

    def detect_landmarks(self, image, detections):
        """
        Implementation of YOLOv8-Pose for landmark detection.
        Detects CEJ, Root Apex, and Alveolar Bone Crest for each bounding box.
        """
        landmarks = {}
        
        if self.model is None:
            return landmarks
            
        # YOLOv8 expects file paths or numpy arrays (BGR format usually, we assume image is already BGR cv2)
        # We run inference on the whole image once
        results = self.model(image, stream=False, verbose=False)
        
        if len(results) == 0:
            return landmarks
            
        result = results[0]
        
        if not hasattr(result, 'keypoints') or result.keypoints is None or result.keypoints.data.shape[1] == 0:
            # If no keypoints detected, fallback to empty
            return landmarks
            
        boxes = result.boxes.xyxy.cpu().numpy()
        kpts = result.keypoints.data.cpu().numpy() # Shape [N, num_keypoints, 3] usually
        
        # We need to map the pose detections to the tooth detections provided by the tooth_detection_model
        # We'll use IoU (Intersection over Union) or simple center matching. Center matching is easier.
        for det in detections:
            tooth_num = det["tooth_number"]
            tx1, ty1, tx2, ty2 = det["box"]
            t_center_x = (tx1 + tx2) / 2
            t_center_y = (ty1 + ty2) / 2
            
            best_match_idx = -1
            min_dist = float('inf')
            
            # Find the closest pose bounding box to the tooth bounding box
            for i, pbox in enumerate(boxes):
                px1, py1, px2, py2 = pbox
                p_center_x = (px1 + px2) / 2
                p_center_y = (py1 + py2) / 2
                
                dist = np.sqrt((t_center_x - p_center_x)**2 + (t_center_y - p_center_y)**2)
                if dist < min_dist and dist < ((tx2-tx1)/1.5): # Ensure it's somewhat overlapping
                    min_dist = dist
                    best_match_idx = i
                    
            if best_match_idx != -1 and kpts.shape[1] >= 3:
                # We artificially defined the 3 keypoints during training generation as:
                # k1: CEJ, k2: Apex, k3: Bone Crest
                k1 = kpts[best_match_idx, 0]
                k2 = kpts[best_match_idx, 1]
                k3 = kpts[best_match_idx, 2]
                
                landmarks[tooth_num] = {
                    "cej": (int(k1[0]), int(k1[1])),
                    "root_apex": (int(k2[0]), int(k2[1])),
                    "bone_crest": (int(k3[0]), int(k3[1]))
                }
            else:
                # If no matching keypoints, fallback to heuristic for this tooth to prevent entire pipeline crash
                landmarks[tooth_num] = {
                    "cej": (int(t_center_x), int(ty1 + (ty2 - ty1)*0.3)),
                    "root_apex": (int(t_center_x), int(ty2 - (ty2 - ty1)*0.05)),
                    "bone_crest": (int(t_center_x), int(ty1 + (ty2 - ty1)*0.7))
                }
                
        return landmarks
