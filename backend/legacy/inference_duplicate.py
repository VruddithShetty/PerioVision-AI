import os
import cv2
import random
import logging
import numpy as np
from ultralytics import YOLO
import onnxruntime as ort

# Configure logger
logger = logging.getLogger("InferenceModels")

class ToothDetector:
    def __init__(self):
        # Paths
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        custom_weights = os.path.join(base_dir, "models", "weights", "dental_yolov8n.pt")
        
        self.device = "cpu"
        self.imgsz = 512
        self.is_custom = False
        
        if os.path.exists(custom_weights):
            logger.info(f"Loading custom tooth detection model from {custom_weights}")
            self.model = YOLO(custom_weights)
            self.is_custom = True
        else:
            logger.warning(f"Custom tooth model not found at {custom_weights}. Using fallback yolov8n.pt")
            self.model = YOLO(os.path.join(base_dir, "models", "weights", "yolov8n.pt"))
            self.is_custom = False

    def detect_teeth(self, image_array):
        """
        Runs YOLO inference for tooth detection.
        Returns a sorted list of dictionaries with tooth bounding boxes.
        Applies a geometric heuristic fallback for tooth numbering if the model lacks classes,
        and fully synthetic fallbacks if no teeth are detected.
        """
        results = self.model(image_array, conf=0.25, iou=0.45, device=self.device, imgsz=self.imgsz, verbose=False)
        
        detections = []
        if len(results) > 0 and len(results[0].boxes) > 0:
            boxes = results[0].boxes
            for i in range(len(boxes)):
                box = boxes[i].xyxy[0].cpu().numpy().tolist()
                conf = float(boxes[i].conf[0].cpu().numpy())
                cls_id = int(boxes[i].cls[0].cpu().numpy())
                
                x1, y1, x2, y2 = map(float, box)
                cx = (x1 + x2) / 2.0
                cy = (y1 + y2) / 2.0
                
                detections.append({
                    "bbox": [x1, y1, x2, y2],
                    "confidence": conf,
                    "center": [cx, cy],
                    "class_id": cls_id
                })
                
        # Cap at 32 teeth based on highest confidence
        detections = sorted(detections, key=lambda x: x["confidence"], reverse=True)[:32]
        
        # Synthetic Fallback if zero detections
        if not detections:
            logger.warning("No teeth detected. Using synthetic estimated regions.")
            h, w = image_array.shape[:2]
            for quadrant in range(1, 5):
                for t_idx in range(1, 9):
                    tooth_id = quadrant * 10 + t_idx
                    
                    is_bottom = (quadrant == 3 or quadrant == 4)
                    is_right_img = (quadrant == 2 or quadrant == 3)
                    
                    y_center = h * 0.75 if is_bottom else h * 0.25
                    fraction = (t_idx - 0.5) / 8.0
                    offset = fraction * (w / 2.0)
                    
                    x_center = (w / 2.0) + offset if is_right_img else (w / 2.0) - offset
                    
                    x1 = max(0.0, x_center - 20)
                    y1 = max(0.0, y_center - 40)
                    x2 = min(float(w), x_center + 20)
                    y2 = min(float(h), y_center + 40)
                    
                    detections.append({
                        "tooth_id": tooth_id,
                        "tooth_label": f"Estimated {tooth_id}",
                        "bbox": [x1, y1, x2, y2],
                        "confidence": 0.20,
                        "center": [x_center, y_center]
                    })
        else:
            # Assign FDI Numbering
            h, w = image_array.shape[:2]
            names = self.model.names if hasattr(self.model, 'names') else {}
            
            for det in detections:
                if self.is_custom and det["class_id"] in names:
                    try:
                        det["tooth_id"] = int(names[det["class_id"]])
                    except ValueError:
                        det["tooth_id"] = self._heuristic_fdi(det["center"], w, h)
                else:
                    det["tooth_id"] = self._heuristic_fdi(det["center"], w, h)
                    
                det["tooth_label"] = str(det["tooth_id"])

        # Sort left-to-right, top-to-bottom basically by tooth_id
        return sorted(detections, key=lambda x: x["tooth_id"])

    def _heuristic_fdi(self, center, w, h):
        """Geometric heuristic to assign FDI tooth number based on image coordinates."""
        cx, cy = center
        is_bottom = cy > h / 2.0
        is_right_img = cx > w / 2.0
        
        if not is_bottom and not is_right_img: q = 1
        elif not is_bottom and is_right_img: q = 2
        elif is_bottom and is_right_img: q = 3
        else: q = 4
        
        dist_from_center_x = abs(cx - w / 2.0)
        t_idx = int((dist_from_center_x / (w / 2.0)) * 8) + 1
        t_idx = min(8, max(1, t_idx))
        
        return q * 10 + t_idx

    def get_tooth_roi(self, image, tooth_detection):
        """Extracts and returns the image crop for a single tooth with 10% padding."""
        h, w = image.shape[:2]
        x1, y1, x2, y2 = tooth_detection["bbox"]
        
        px = (x2 - x1) * 0.10
        py = (y2 - y1) * 0.10
        
        nx1 = max(0, int(x1 - px))
        ny1 = max(0, int(y1 - py))
        nx2 = min(w, int(x2 + px))
        ny2 = min(h, int(y2 + py))
        
        return image[ny1:ny2, nx1:nx2].copy()

    def draw_detections(self, image, detections):
        """Draws bounding boxes and labels on the image."""
        img_copy = image.copy()
        if len(img_copy.shape) == 2:
            img_copy = cv2.cvtColor(img_copy, cv2.COLOR_GRAY2BGR)
            
        for det in detections:
            x1, y1, x2, y2 = map(int, det["bbox"])
            conf = det["confidence"]
            
            if "Estimated" in det.get("tooth_label", "") or conf <= 0.20:
                color = (0, 255, 255)  # Yellow
            elif conf < 0.50:
                color = (0, 165, 255)  # Orange
            else:
                color = (0, 255, 0)    # Green
                
            cv2.rectangle(img_copy, (x1, y1), (x2, y2), color, 2)
            cv2.putText(img_copy, str(det["tooth_id"]), (x1, max(y1 - 5, 10)), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                        
        return img_copy

class LandmarkDetector:
    def __init__(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        custom_weights = os.path.join(base_dir, "models", "landmark_detection_model", "landmark_cnn.onnx")
        
        self.device = "cpu"
        self.ort_session = None
        self.mode = "heuristic"
        
        if os.path.exists(custom_weights):
            logger.info(f"Loading landmark CNN model from {custom_weights}")
            try:
                self.ort_session = ort.InferenceSession(custom_weights)
                self.mode = "model"
            except Exception as e:
                logger.error(f"Failed to load ONNX model: {e}")
        else:
            logger.warning("Landmark CNN model not found. Using heuristic geometric fallback.")

    def detect_landmarks(self, tooth_roi, tooth_bbox):
        """
        Runs CNN inference to extract CEJ, Root Apex, and Bone Crest.
        Never returns None. Always falls back to geometric estimation.
        """
        x1, y1, x2, y2 = map(float, tooth_bbox)
        cx = (x1 + x2) / 2.0
        h_box = y2 - y1
        w_box = x2 - x1
        
        # Base heuristic values
        landmarks = {
            "cej": [cx, y1 + 0.25 * h_box],
            "root_apex": [cx, y2 - 0.05 * h_box],
            "bone_crest": [cx, y1 + 0.20 * h_box + random.uniform(-5, 5)],
            "confidence": 0.35
        }
        
        if self.mode == "model" and self.ort_session is not None:
            try:
                # Resize input ROI to 128x128
                roi_resized = cv2.resize(tooth_roi, (128, 128))
                
                # Normalize to [0,1]
                input_tensor = roi_resized.astype(np.float32) / 255.0
                
                # Reshape to (1, 1, 128, 128)
                input_tensor = np.expand_dims(np.expand_dims(input_tensor, axis=0), axis=0)
                
                # Run inference
                ort_inputs = {self.ort_session.get_inputs()[0].name: input_tensor}
                ort_outs = self.ort_session.run(None, ort_inputs)
                
                outputs = ort_outs[0][0]  # Shape: (6,) -> [cej_x, cej_y, apex_x, apex_y, crest_x, crest_y]
                
                # Heuristic confidence: 1 - mean(abs(outputs - 0.5)) * 2
                confidence = float(1.0 - np.mean(np.abs(outputs - 0.5)) * 2.0)
                
                # Scale output coords back to original ROI size and add absolute bounding box offset
                pad_x = w_box * 0.10
                pad_y = h_box * 0.10
                offset_x = max(0.0, x1 - pad_x)
                offset_y = max(0.0, y1 - pad_y)
                
                # ROI original dimensions (the crop includes 10% padding as done in get_tooth_roi)
                # But to be safe, we use the actual tooth_roi shape
                roi_h, roi_w = tooth_roi.shape[:2]
                
                landmarks["cej"] = [float(outputs[0] * roi_w + offset_x), float(outputs[1] * roi_h + offset_y)]
                landmarks["root_apex"] = [float(outputs[2] * roi_w + offset_x), float(outputs[3] * roi_h + offset_y)]
                landmarks["bone_crest"] = [float(outputs[4] * roi_w + offset_x), float(outputs[5] * roi_h + offset_y)]
                landmarks["confidence"] = max(0.0, min(1.0, confidence))
                
            except Exception as e:
                logger.error(f"Model landmark detection failed: {e}. Falling back to heuristic.")
                
        return landmarks
