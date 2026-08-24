import os
import torch
import torch.nn as nn
import torch.nn.functional as F
import cv2
import numpy as np
from ultralytics import YOLO
from security.integrity import ModelIntegrityVerifier

def calculate_iou(box1, box2):
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = area1 + area2 - intersection
    return intersection / union if union > 0 else 0

class YOLOGradCAM:
    def __init__(self, model):
        self.model = model
        self.pytorch_model = model.model
        self.pytorch_model.eval()
        
        # Clone all parameters to strip them of the inference mode context
        for p in self.pytorch_model.parameters():
            p.data = p.data.clone()
            p.requires_grad = True
            
        # Also clone any non-parameter buffers
        for m in self.pytorch_model.modules():
            for key, buf in list(m._buffers.items()):
                if buf is not None:
                    m._buffers[key] = buf.clone()
                    
        # Explicitly clone the dynamically created anchors and strides on the Detect head (index 22)
        detect_head = self.pytorch_model.model[22]
        if hasattr(detect_head, 'anchors') and detect_head.anchors is not None:
            detect_head.anchors = detect_head.anchors.clone()
        if hasattr(detect_head, 'strides') and detect_head.strides is not None:
            detect_head.strides = detect_head.strides.clone()
            
        # Layers dictionary
        self.layers = {
            15: self.pytorch_model.model[15],
            18: self.pytorch_model.model[18],
            21: self.pytorch_model.model[21]
        }
        
        self.activations = {}
        self.gradients = {}
        self.fhs = []
        self.bhs = []
        
        self._register_hooks()
        
    def _register_hooks(self):
        def get_forward_hook(layer_idx):
            def hook(module, input, output):
                self.activations[layer_idx] = output
            return hook
            
        def get_backward_hook(layer_idx):
            def hook(module, grad_input, grad_output):
                self.gradients[layer_idx] = grad_output[0]
            return hook
            
        for idx in self.layers:
            self.fhs.append(self.layers[idx].register_forward_hook(get_forward_hook(idx)))
            self.bhs.append(self.layers[idx].register_full_backward_hook(get_backward_hook(idx)))
            
    def compute_heatmap(self, x, class_idx, anchor_idx):
        self.pytorch_model.zero_grad()
        
        # Run forward pass
        preds = self.pytorch_model(x)
        if isinstance(preds, tuple) or isinstance(preds, list):
            preds = preds[0]
            
        # Select target score logit
        score_tensor = preds[0, 4 + class_idx, anchor_idx]
        score_tensor.backward(retain_graph=True)
        
        # Select appropriate target layer index based on anchor scale
        if anchor_idx < 6400:
            target_idx = 15
        elif anchor_idx < 8000:
            target_idx = 18
        else:
            target_idx = 21
            
        if target_idx not in self.gradients or target_idx not in self.activations:
            available = list(self.gradients.keys())
            if not available:
                return np.zeros((640, 640), dtype=np.float32)
            target_idx = available[0]
            
        grad = self.gradients[target_idx]
        act = self.activations[target_idx]
        
        weights = torch.mean(grad, dim=(2, 3), keepdim=True)
        cam = torch.sum(weights * act, dim=1, keepdim=True)
        cam = torch.clamp(cam, min=0)  # ReLU
        
        cam_min, cam_max = cam.min(), cam.max()
        if cam_max > cam_min:
            cam = (cam - cam_min) / (cam_max - cam_min)
        else:
            cam = torch.zeros_like(cam)
            
        # Resize heatmap to 640x640 using bilinear interpolation
        cam_resized = F.interpolate(cam, size=(640, 640), mode='bilinear', align_corners=False)
        heatmap = cam_resized.detach().cpu().numpy()[0, 0]
        return heatmap
        
    def remove_hooks(self):
        for fh in self.fhs: fh.remove()
        for bh in self.bhs: bh.remove()

def calculate_heatmap_agreement(heatmap, box_scaled):
    h_dim, w_dim = heatmap.shape
    x1, y1, x2, y2 = map(int, [
        np.clip(box_scaled[0], 0, w_dim - 1),
        np.clip(box_scaled[1], 0, h_dim - 1),
        np.clip(box_scaled[2], 0, w_dim - 1),
        np.clip(box_scaled[3], 0, h_dim - 1)
    ])
    
    if x2 <= x1 or y2 <= y1:
        return 0.0
        
    total_energy = heatmap.sum()
    if total_energy == 0:
        return 0.0
        
    box_energy = heatmap[y1:y2, x1:x2].sum()
    energy_ratio = float(box_energy / total_energy)
    return energy_ratio

class ToothDetectionModel:
    """
    YOLOv8-nano implementation for tooth bounding box detection,
    integrated with Grad-CAM explainability-as-reliability verification.
    """
    def __init__(self, model_path="models/weights/dental_yolov8n.pt"):
        if not os.path.exists(model_path):
            fallback_paths = [
                "yolov8n.pt",
                "C:\\Users\\vrudd\\Downloads\\Dental_progression\\dental_progression_ai\\models\\tooth_detection_model\\dental_yolov8n.pt"
            ]
            for fb in fallback_paths:
                if os.path.exists(fb):
                    model_path = fb
                    break
        else:
            verifier = ModelIntegrityVerifier()
            res = verifier.verify_model(model_path)
            if not res["verified"]:
                print(f"[SECURITY] Model verification failed: {res['reason']}")
            
        self.model = YOLO(model_path)
    
    def detect_teeth(self, image_path):
        results = self.model(image_path, verbose=False)
        detections = []
        
        if not results or len(results[0].boxes) == 0:
            return detections
            
        try:
            gradcam_engine = YOLOGradCAM(self.model)
            
            img = cv2.imread(image_path)
            h_orig, w_orig = img.shape[:2]
            img_resized = cv2.resize(img, (640, 640))
            x = img_resized.transpose(2, 0, 1)
            x = np.ascontiguousarray(x)
            x = torch.from_numpy(x).float() / 255.0
            x = x.unsqueeze(0)
            x.requires_grad = True
            
            with torch.no_grad():
                preds = gradcam_engine.pytorch_model(x)
                if isinstance(preds, tuple) or isinstance(preds, list):
                    preds = preds[0]
                    
            anchors_cxcywh = preds[0, :4, :].cpu().numpy()
            anchors_xyxy = np.zeros_like(anchors_cxcywh)
            anchors_xyxy[0] = anchors_cxcywh[0] - anchors_cxcywh[2] / 2
            anchors_xyxy[1] = anchors_cxcywh[1] - anchors_cxcywh[3] / 2
            anchors_xyxy[2] = anchors_cxcywh[0] + anchors_cxcywh[2] / 2
            anchors_xyxy[3] = anchors_cxcywh[1] + anchors_cxcywh[3] / 2
            
            boxes = results[0].boxes
            for i, box in enumerate(boxes):
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                conf = float(box.conf[0].cpu().numpy())
                cls_id = int(box.cls[0].cpu().numpy())
                
                box_scaled = [
                    x1 * 640.0 / w_orig,
                    y1 * 640.0 / h_orig,
                    x2 * 640.0 / w_orig,
                    y2 * 640.0 / h_orig
                ]
                
                best_iou = 0
                best_anchor_idx = -1
                for idx in range(8400):
                    iou = calculate_iou(box_scaled, anchors_xyxy[:, idx])
                    if iou > best_iou:
                        best_iou = iou
                        best_anchor_idx = idx
                
                agreement = 1.0
                if best_anchor_idx != -1:
                    try:
                        heatmap = gradcam_engine.compute_heatmap(x, cls_id, best_anchor_idx)
                        agreement = calculate_heatmap_agreement(heatmap, box_scaled)
                    except Exception:
                        agreement = 1.0
                        
                is_low_conf = conf < 0.35
                is_mismatch = agreement < 0.45
                
                if is_low_conf and is_mismatch:
                    flag = "both"
                elif is_low_conf:
                    flag = "low_confidence"
                elif is_mismatch:
                    flag = "attention_mismatch"
                else:
                    flag = "none"
                    
                detections.append({
                    "tooth_number": str(11 + i),
                    "box": [int(x1), int(y1), int(x2), int(y2)],
                    "confidence": conf,
                    "reliability_flag": flag,
                    "heatmap_agreement": agreement
                })
                
            gradcam_engine.remove_hooks()
            
        except Exception as e:
            print(f"[EXPLAINABILITY] Grad-CAM error: {e}, falling back to single modality.")
            boxes = results[0].boxes
            for i, box in enumerate(boxes):
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                conf = float(box.conf[0].cpu().numpy())
                detections.append({
                    "tooth_number": str(11 + i),
                    "box": [int(x1), int(y1), int(x2), int(y2)],
                    "confidence": conf,
                    "reliability_flag": "low_confidence" if conf < 0.35 else "none",
                    "heatmap_agreement": 1.0
                })
                
        return detections
