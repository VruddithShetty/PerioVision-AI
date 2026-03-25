import os
import numpy as np
from ultralytics import YOLO
import cv2

class BoneSegmentationModel:
    def __init__(self, model_path="dental_bone_yolov8n-seg.pt"):
        # Load the custom trained YOLOv8-Seg model
        if not os.path.exists(model_path):
            print(f"Warning: Custom segmentation model {model_path} not found. Fallback not available.")
            self.model = None
        else:
            self.model = YOLO(model_path)

    def generate_bone_masks(self, image, detections):
        """
        Implementation of custom YOLOv8-Seg for mask generation.
        Returns a dictionary mapping tooth_number to a boolean mask array matching the image shape.
        """
        masks_dict = {}
        
        # Initialize empty masks for all detected teeth (fallback if no seg mask found)
        for det in detections:
            masks_dict[det["tooth_number"]] = np.zeros(image.shape[:2], dtype=bool)
            
        if self.model is None:
            return masks_dict
            
        # Run inference on the whole image once
        results = self.model(image, stream=False, verbose=False)
        
        if len(results) == 0:
            return masks_dict
            
        result = results[0]
        
        if not hasattr(result, 'masks') or result.masks is None:
            return masks_dict
            
        boxes = result.boxes.xyxy.cpu().numpy()
        masks = result.masks.data.cpu().numpy() # Shape [N, H, W]
        
        # Resize masks to original image shape if they aren't already
        img_h, img_w = image.shape[:2]
        
        # We need to map the segmentation detections to the tooth detections
        for det in detections:
            tooth_num = det["tooth_number"]
            tx1, ty1, tx2, ty2 = det["box"]
            t_center_x = (tx1 + tx2) / 2
            t_center_y = (ty1 + ty2) / 2
            
            best_match_idx = -1
            min_dist = float('inf')
            
            for i, pbox in enumerate(boxes):
                px1, py1, px2, py2 = pbox
                p_center_x = (px1 + px2) / 2
                p_center_y = (py1 + py2) / 2
                
                dist = np.sqrt((t_center_x - p_center_x)**2 + (t_center_y - p_center_y)**2)
                if dist < min_dist and dist < ((tx2-tx1)/1.5): # Ensure overlapping
                    min_dist = dist
                    best_match_idx = i
                    
            if best_match_idx != -1:
                mask = masks[best_match_idx]
                # Resize mask to original image dimensions. YOLO masks are often 160x160 natively.
                mask_resized = cv2.resize(mask, (img_w, img_h), interpolation=cv2.INTER_NEAREST)
                masks_dict[tooth_num] = mask_resized.astype(bool)
                
        return masks_dict
