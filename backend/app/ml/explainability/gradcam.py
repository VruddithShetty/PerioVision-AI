"""Grad-CAM-family heatmaps (LayerCAM weighting) for YOLO (v8 / 11) detections, plus the periodontal
region-of-interest attention check.

`heatmap` explains all detections at once: for every detected tooth we find the
anchor that produced it, sum those class scores, and back-propagate to the three
neck layers that feed the YOLO head (P3/P4/P5). Each layer's gradient-weighted
activation map is upsampled and combined into one heatmap at the original image
resolution. `per_tooth` back-propagates each detection's score on its own, which
is what the per-tooth attention check needs (see per_tooth).

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
NECK_LAYERS = (15, 18, 21)          # fallback only: YOLOv8 layout. The real indices are read from the Detect head.
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
        # The layers that feed the Detect head differ between architectures (YOLOv8: 15/18/21,
        # YOLO11: 16/19/22), so take them from the head itself.
        head = self.net.model[-1]
        head_inputs = getattr(head, "f", None)
        self.layers = tuple(head_inputs) if isinstance(head_inputs, (list, tuple)) else NECK_LAYERS
        if hasattr(head, "kpt_shape"):
            # Pose head: its normal keypoint decoding applies sigmoid_() in place, which breaks backward().
            # The export path decodes the same values out of place. Only this gradient copy is changed.
            head.export = True
        for idx in self.layers:
            layer = self.net.model[idx]
            layer.register_forward_hook(self._capture(idx))

    def _capture(self, idx):
        # Tensor hooks (not module backward hooks) cope with YOLO's in-place operations.
        def hook(_m, _i, output):
            self.activations[idx] = output
            if output.requires_grad:
                output.register_hook(lambda grad: self.gradients.__setitem__(idx, grad))
        return hook

    def _forward(self, image_bgr: np.ndarray, detections: list[dict]):
        """Gradient-enabled forward pass; returns the score tensor of every detection (same order)."""
        torch = self.torch
        h, w = image_bgr.shape[:2]
        rgb = cv2.cvtColor(cv2.resize(image_bgr, (INPUT_SIZE, INPUT_SIZE)), cv2.COLOR_BGR2RGB)
        x = torch.from_numpy(np.ascontiguousarray(rgb.transpose(2, 0, 1))).float().unsqueeze(0) / 255.0
        self.activations.clear()
        self.gradients.clear()
        self.net.zero_grad()
        preds = self.net(x)
        preds = preds[0] if isinstance(preds, (list, tuple)) else preds   # [1, 4 + nc, 8400]
        boxes = preds[0, :4, :].detach().cpu().numpy().T                  # cx, cy, w, h
        anchors = np.stack([boxes[:, 0] - boxes[:, 2] / 2, boxes[:, 1] - boxes[:, 3] / 2,
                            boxes[:, 0] + boxes[:, 2] / 2, boxes[:, 1] + boxes[:, 3] / 2], axis=1)
        sx, sy = INPUT_SIZE / w, INPUT_SIZE / h
        scores = []
        for det in detections:
            b = np.array(det["bbox"], dtype=np.float64) * [sx, sy, sx, sy]
            anchor = int(np.argmax(_iou_matrix(b, anchors)))
            scores.append(preds[0, 4 + int(det.get("class_index", 0)), anchor])
        return scores

    def heatmap(self, image_bgr: np.ndarray, detections: list[dict]) -> np.ndarray | None:
        """All detections at once: one backward pass of their summed scores. HxW float32 in [0, 1], or None."""
        if not detections:
            return None
        with self.torch.enable_grad():
            sum(self._forward(image_bgr, detections)).backward()
        return self._combine(image_bgr.shape[:2])

    def per_tooth(self, image_bgr: np.ndarray, detections: list[dict]) -> list[np.ndarray | None]:
        """One map per detection, each back-propagating ONLY that detection's score (one shared forward pass).

        Faithful per tooth: in the all-teeth map a tooth's box also collects gradient from its neighbours'
        detections. Computed as one batched backward pass (about 2 s for a 4-tooth periapical film on a laptop CPU).
        """
        torch = self.torch
        with torch.enable_grad():
            scores = self._forward(image_bgr, detections)
            if not scores:
                return []
            layers = [i for i in self.layers if i in self.activations]
            try:
                # All teeth in ONE batched backward pass (vector-Jacobian products with identity rows): the same
                # maps as one backward per tooth (max difference 0.0 on a 4-tooth film) in about a quarter of the time.
                grads = torch.autograd.grad(torch.stack(scores), [self.activations[i] for i in layers],
                                            grad_outputs=torch.eye(len(scores)), is_grads_batched=True)
                maps = []
                for k in range(len(scores)):
                    self.gradients = {i: g[k] for i, g in zip(layers, grads)}
                    maps.append(self._combine(image_bgr.shape[:2]))
                return maps
            except RuntimeError:           # an op without batched-gradient support: one backward per tooth
                maps = []
                for i, score in enumerate(scores):
                    self.gradients.clear()     # tensor hooks deliver this backward pass's gradient only
                    score.backward(retain_graph=i < len(scores) - 1)
                    maps.append(self._combine(image_bgr.shape[:2]))
                return maps

    def _combine(self, shape_hw) -> np.ndarray | None:
        torch = self.torch
        h, w = shape_hw
        combined = np.zeros((INPUT_SIZE, INPUT_SIZE), dtype=np.float32)
        for idx in self.layers:
            if idx not in self.gradients or idx not in self.activations:
                continue
            grad, act = self.gradients[idx], self.activations[idx]
            # LayerCAM weighting (Jiang et al., IEEE TIP 2021): each location's activation is weighted by its OWN
            # positive gradient. Classic Grad-CAM averages the gradient over the whole layer first, which on these
            # detectors left a tooth's map no more concentrated on that tooth than chance (16 % of the map inside
            # the tooth's box vs 14 % of the image); LayerCAM puts 82 % there (64 % on panoramic films, whose
            # boxes cover about 1 % of the image). docs/evidence/gradcam_localisation_2026-10-04.json
            cam = torch.relu((torch.relu(grad) * act).sum(dim=1))[0].detach().cpu().numpy()
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
