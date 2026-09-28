"""CEJ, root-apex and alveolar-bone-crest (ABC) keypoints per detected tooth.

The YOLOv8-pose model predicts, for each tooth, three keypoints in this order:
CEJ, root apex, bone crest (see scripts/convert_to_yolopose.py). It runs on
the same full-resolution image as the detector, so keypoints and detection
boxes share one coordinate system and are matched by box overlap (IoU).

If a tooth has no matching pose prediction, or its keypoints are below the
confidence threshold, a geometric fallback is used and clearly marked
`landmark_source = "heuristic_fallback"` with confidence 0.3; the review router
treats those teeth as uncertain.
"""
from __future__ import annotations

import numpy as np

from app import config
from app.ml.registry import registry

KEYPOINT_ORDER = ("cej", "root_apex", "bone_crest")


def _iou(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def heuristic_landmarks(bbox) -> dict:
    x1, y1, x2, y2 = bbox
    cx, h = (x1 + x2) / 2, (y2 - y1)
    return {
        "cej": [round(cx, 1), round(y1 + 0.28 * h, 1)],
        "root_apex": [round(cx, 1), round(y2 - 0.02 * h, 1)],
        "bone_crest": [round(cx, 1), round(y1 + 0.40 * h, 1)],
        "landmark_source": "heuristic_fallback",
        "landmark_confidence": 0.3,
    }


class LandmarkDetectionModel:
    def __init__(self):
        self.model = registry().get("landmarks")

    @property
    def available(self) -> bool:
        return self.model is not None

    def detect_landmarks(self, detections: list[dict], image_bgr: np.ndarray) -> dict:
        """Return {tooth_id: {cej, root_apex, bone_crest, landmark_source, landmark_confidence, ...}}."""
        t = config.THRESHOLDS["landmarks"]
        preds = []
        if self.model is not None and detections:
            results = self.model(image_bgr, conf=0.05, verbose=False)
            if results and results[0].keypoints is not None and results[0].boxes is not None:
                kpts = results[0].keypoints.data.cpu().numpy()    # [n, 3, 3] -> x, y, conf
                boxes = results[0].boxes.xyxy.cpu().numpy()
                preds = list(zip(boxes, kpts))

        out, used = {}, set()
        for det in detections:
            best_i, best_iou = -1, 0.0
            for i, (pbox, _k) in enumerate(preds):
                if i in used:
                    continue
                iou = _iou(det["bbox"], pbox)
                if iou > best_iou:
                    best_i, best_iou = i, iou
            if best_i >= 0 and best_iou >= t["match_iou"]:
                k = preds[best_i][1]
                confs = [float(k[j, 2]) if k.shape[1] > 2 else 0.0 for j in range(3)]
                if min(confs) >= t["min_keypoint_confidence"]:
                    used.add(best_i)
                    out[det["tooth_id"]] = {
                        **{name: [round(float(k[j, 0]), 1), round(float(k[j, 1]), 1)]
                           for j, name in enumerate(KEYPOINT_ORDER)},
                        "landmark_source": "keypoint_model",
                        "landmark_confidence": round(float(np.mean(confs)), 3),
                        "keypoint_confidences": dict(zip(KEYPOINT_ORDER, [round(c, 3) for c in confs])),
                        "match_iou": round(best_iou, 3),
                    }
                    continue
            out[det["tooth_id"]] = heuristic_landmarks(det["bbox"])
        return out
