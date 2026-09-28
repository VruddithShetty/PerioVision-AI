"""Grad-CAM for YOLOv8 detections, plus the periodontal region-of-interest attention check.

One backward pass explains all detections at once: for every detected tooth we
find the anchor that produced it, sum those class scores, and back-propagate to
the three neck layers that feed the YOLO head (P3/P4/P5). Each layer's
gradient-weighted activation map is upsampled and combined into one heatmap at
the original image resolution.

`roi_attention` then asks, per tooth: how much of the attention inside the
tooth's box falls on the periodontal region (the band between the CEJ and the
alveolar crest)? A low share means the model "looked" somewhere clinically
irrelevant, and the case is flagged `low_attention_validity` for review.
"""
from __future__ import annotations

import copy
import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)

INPUT_SIZE = 640
NECK_LAYERS = (15, 18, 21)          # outputs feeding the Detect head in YOLOv8 n/s/m/l/x
LAYER_ANCHOR_RANGES = ((0, 6400), (6400, 8000), (8000, 8400))  # 80x80, 40x40, 20x20 grids at 640 px


def _iou_matrix(box: np.ndarray, anchors_xyxy: np.ndarray) -> np.ndarray:
    x1 = np.maximum(box[0], anchors_xyxy[:, 0])
    y1 = np.maximum(box[1], anchors_xyxy[:, 1])
    x2 = np.minimum(box[2], anchors_xyxy[:, 2])
    y2 = np.minimum(box[3], anchors_xyxy[:, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area_a = (box[2] - box[0]) * (box[3] - box[1])
    area_b = (anchors_xyxy[:, 2] - anchors_xyxy[:, 0]) * (anchors_xyxy[:, 3] - anchors_xyxy[:, 1])
    return inter / np.maximum(area_a + area_b - inter, 1e-9)


class YOLOGradCAM:
    """Keeps its own gradient-enabled copy of the network so the inference model is untouched."""

    def __init__(self, yolo_model):
        import torch

        self.torch = torch
        self.net = copy.deepcopy(yolo_model.model).float().eval()
        for p in self.net.parameters():
            p.requires_grad_(True)
        self.activations, self.gradients = {}, {}
        for idx in NECK_LAYERS:
            layer = self.net.model[idx]
            layer.register_forward_hook(self._capture(idx))

    def _capture(self, idx):
        # Tensor hooks (not module backward hooks) cope with YOLO's in-place operations.
        def hook(_m, _i, output):
            self.activations[idx] = output
            if output.requires_grad:
                output.register_hook(lambda grad: self.gradients.__setitem__(idx, grad))
        return hook

    def heatmap(self, image_bgr: np.ndarray, detections: list[dict]) -> np.ndarray | None:
        """Return an HxW float32 heatmap in [0, 1] aligned with `image_bgr`, or None."""
        if not detections:
            return None
        torch = self.torch
        h, w = image_bgr.shape[:2]
        rgb = cv2.cvtColor(cv2.resize(image_bgr, (INPUT_SIZE, INPUT_SIZE)), cv2.COLOR_BGR2RGB)
        x = torch.from_numpy(np.ascontiguousarray(rgb.transpose(2, 0, 1))).float().unsqueeze(0) / 255.0

        self.activations.clear()
        self.gradients.clear()
        self.net.zero_grad()
        with torch.enable_grad():
            preds = self.net(x)
            preds = preds[0] if isinstance(preds, (list, tuple)) else preds   # [1, 4 + nc, 8400]
            boxes = preds[0, :4, :].detach().cpu().numpy().T                  # cx, cy, w, h
            anchors = np.stack([boxes[:, 0] - boxes[:, 2] / 2, boxes[:, 1] - boxes[:, 3] / 2,
                                boxes[:, 0] + boxes[:, 2] / 2, boxes[:, 1] + boxes[:, 3] / 2], axis=1)
            sx, sy = INPUT_SIZE / w, INPUT_SIZE / h
            target = 0
            for det in detections:
                b = np.array(det["bbox"], dtype=np.float64) * [sx, sy, sx, sy]
                anchor = int(np.argmax(_iou_matrix(b, anchors)))
                target = target + preds[0, 4 + int(det.get("class_index", 0)), anchor]
            target.backward()

        combined = np.zeros((INPUT_SIZE, INPUT_SIZE), dtype=np.float32)
        for idx in NECK_LAYERS:
            if idx not in self.gradients or idx not in self.activations:
                continue
            grad, act = self.gradients[idx], self.activations[idx]
            weights = grad.mean(dim=(2, 3), keepdim=True)
            cam = torch.relu((weights * act).sum(dim=1))[0].detach().cpu().numpy()
            if cam.max() > 0:
                cam = cam / cam.max()
            combined = np.maximum(combined, cv2.resize(cam.astype(np.float32), (INPUT_SIZE, INPUT_SIZE)))
        if combined.max() <= 0:
            return None
        return cv2.resize(combined, (w, h), interpolation=cv2.INTER_LINEAR)


def periodontal_roi(bbox, cej, crest, margin_fraction: float) -> tuple[int, int, int, int]:
    """Band spanning CEJ to crest (plus a margin) across the tooth's width."""
    x1, y1, x2, y2 = bbox
    top, bottom = sorted([cej[1], crest[1]])
    margin = margin_fraction * max(1, (y2 - y1))
    return int(x1), int(max(y1, top - margin)), int(x2), int(min(y2, bottom + margin))


def roi_attention(heatmap: np.ndarray | None, bbox, roi) -> float | None:
    """Share of the attention inside the tooth box that lands in the periodontal ROI."""
    if heatmap is None:
        return None
    h, w = heatmap.shape
    x1, y1, x2, y2 = [int(np.clip(v, 0, lim - 1)) for v, lim in zip(bbox, (w, h, w, h))]
    rx1, ry1, rx2, ry2 = [int(np.clip(v, 0, lim - 1)) for v, lim in zip(roi, (w, h, w, h))]
    box_energy = float(heatmap[y1:y2 + 1, x1:x2 + 1].sum())
    if box_energy <= 1e-9:
        return 0.0
    return round(float(heatmap[ry1:ry2 + 1, rx1:rx2 + 1].sum()) / box_energy, 3)
