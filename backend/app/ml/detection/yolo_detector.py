"""YOLOv8 tooth detection with FDI tooth numbers.

The trained detector (`weights/dental_yolov8n.pt`) has 32 classes named with
FDI numbers ("11" ... "48"), so each box's class *is* its tooth number. If the
loaded model has non-FDI class names, teeth are numbered by position and marked
`tooth_id_source = "positional_estimate"` so the UI and progression matching
know the ID is not reliable.

The model is only obtained through the signed-model registry. When it is
unavailable the detector returns `available = False` and the pipeline switches
to labelled demo mode instead of guessing.
"""
from __future__ import annotations

import numpy as np

from app import config
from app.ml.registry import registry

FDI_TEETH = {f"{q}{n}" for q in (1, 2, 3, 4) for n in range(1, 9)}


class ToothDetectionModel:
    def __init__(self):
        self.model = registry().get("tooth_detector")
        self._gradcam = None

    @property
    def available(self) -> bool:
        return self.model is not None

    def detect_teeth(self, image_bgr: np.ndarray) -> list[dict]:
        if self.model is None:
            return []
        t = config.THRESHOLDS["detection"]
        results = self.model(image_bgr, conf=t["min_confidence"], verbose=False)
        if not results or results[0].boxes is None or len(results[0].boxes) == 0:
            return []
        names = self.model.names
        boxes = results[0].boxes
        xyxy = boxes.xyxy.cpu().numpy()
        conf = boxes.conf.cpu().numpy()
        cls = boxes.cls.cpu().numpy().astype(int)

        detections = []
        for i in range(len(xyxy)):
            label = str(names.get(int(cls[i]), cls[i]))
            detections.append({
                "tooth_id": label if label in FDI_TEETH else None,
                "tooth_id_source": "model_fdi_class" if label in FDI_TEETH else "positional_estimate",
                "class_index": int(cls[i]),
                "bbox": [round(float(v), 1) for v in xyxy[i]],
                "confidence": round(float(conf[i]), 3),
                "low_confidence": bool(conf[i] < t["low_confidence"]),
            })

        # Keep only the most confident box per FDI number (duplicates are usually overlapping boxes).
        best: dict[str, dict] = {}
        others = []
        for d in detections:
            if d["tooth_id"] is None:
                others.append(d)
            elif d["tooth_id"] not in best or d["confidence"] > best[d["tooth_id"]]["confidence"]:
                best[d["tooth_id"]] = d
        others.sort(key=lambda d: (d["bbox"][1] > image_bgr.shape[0] / 2, d["bbox"][0]))
        for n, d in enumerate(others, start=1):
            d["tooth_id"] = f"T{n}"
        return sorted(best.values(), key=lambda d: d["tooth_id"]) + others

    def gradcam_heatmap(self, image_bgr: np.ndarray, detections: list[dict]):
        """Grad-CAM heatmap for all detections (None if unavailable). Errors never break analysis."""
        if self.model is None or not detections:
            return None
        from app.ml.explainability.gradcam import YOLOGradCAM

        try:
            if self._gradcam is None:
                self._gradcam = YOLOGradCAM(self.model)
            return self._gradcam.heatmap(image_bgr, detections)
        except Exception as exc:  # explainability failure is reported, not hidden
            import logging

            logging.getLogger(__name__).warning("Grad-CAM failed: %s", exc)
            return None
