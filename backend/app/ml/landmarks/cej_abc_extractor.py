"""CEJ, root-apex and alveolar-bone-crest (ABC) keypoints per detected tooth.

The YOLOv8-pose model predicts, for each tooth, three keypoints in this order:
CEJ, root apex, bone crest (see scripts/convert_to_yolopose.py). It runs on
the same full-resolution image as the detector, so keypoints and detection
boxes share one coordinate system and are matched by box overlap (IoU).

Teeth the whole-image pass misses (common on panoramic images, where teeth are small) are
re-run on a zoomed crop of the tooth and its neighbours (`keypoint_model_crop`). On periapical
films, where the panoramic detector finds few teeth, `detect_teeth` lets the keypoint model find
the teeth itself.

If a tooth still has no matching pose prediction, or its keypoints are below the
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

    def _predict(self, image_bgr: np.ndarray, offset=(0.0, 0.0)) -> list[tuple]:
        """Pose predictions as [(box_xyxy, kpts[3, 3], box_conf)] in full-image coordinates."""
        results = self.model(image_bgr, conf=0.05, verbose=False)
        if not results or results[0].keypoints is None or results[0].boxes is None:
            return []
        kpts = results[0].keypoints.data.cpu().numpy().copy()    # [n, 3, 3] -> x, y, conf
        boxes = results[0].boxes.xyxy.cpu().numpy().copy()
        confs = results[0].boxes.conf.cpu().numpy()
        ox, oy = offset
        boxes[:, [0, 2]] += ox
        boxes[:, [1, 3]] += oy
        kpts[:, :, 0] += ox
        kpts[:, :, 1] += oy
        return list(zip(boxes, kpts, confs))

    @staticmethod
    def _landmarks_from(k, source: str, match_iou: float | None = None) -> dict | None:
        confs = [float(k[j, 2]) if k.shape[1] > 2 else 0.0 for j in range(3)]
        if min(confs) < config.THRESHOLDS["landmarks"]["min_keypoint_confidence"]:
            return None
        out = {
            **{name: [round(float(k[j, 0]), 1), round(float(k[j, 1]), 1)] for j, name in enumerate(KEYPOINT_ORDER)},
            "landmark_source": source,
            "landmark_confidence": round(float(np.mean(confs)), 3),
            "keypoint_confidences": dict(zip(KEYPOINT_ORDER, [round(c, 3) for c in confs])),
        }
        if match_iou is not None:
            out["match_iou"] = round(match_iou, 3)
        return out

    def detect_teeth(self, image_bgr: np.ndarray) -> list[tuple[dict, dict]]:
        """Periapical path: the keypoint model finds each tooth AND its landmarks in one pass.

        Returns [(detection, landmarks)] ordered left to right. A periapical film shows a few teeth
        without the context needed for FDI numbering, so teeth get positional ids (P1, P2, ...).
        """
        if self.model is None:
            return []
        t = config.THRESHOLDS["detection"]
        out = []
        for box, k, c in sorted(self._predict(image_bgr), key=lambda p: p[0][0]):
            if c < t["min_confidence"]:
                continue
            lm = self._landmarks_from(k, "keypoint_model")
            if lm is None:
                continue
            det = {"tooth_id": f"P{len(out) + 1}", "tooth_id_source": "positional_estimate",
                   "bbox": [round(float(v), 1) for v in box], "confidence": round(float(c), 3),
                   "low_confidence": bool(c < t["low_confidence"])}
            out.append((det, lm))
        return out

    def detect_landmarks(self, detections: list[dict], image_bgr: np.ndarray) -> dict:
        """Return {tooth_id: {cej, root_apex, bone_crest, landmark_source, landmark_confidence, ...}}.

        1. Run the keypoint model on the whole image and match its teeth to the detector's by IoU.
        2. A tooth it did not match (typical on panoramic images, where each tooth is small) is
           re-examined on a zoomed crop of the tooth and its neighbours, which resembles the
           periapical films the model was trained on ("keypoint_model_crop").
        3. Only if both fail does the labelled geometric fallback apply.
        """
        t = config.THRESHOLDS["landmarks"]
        preds = self._predict(image_bgr) if self.model is not None and detections else []
        H, W = image_bgr.shape[:2]

        out, used = {}, set()
        for det in detections:
            best_i, best_iou = -1, 0.0
            for i, (pbox, _k, _c) in enumerate(preds):
                if i in used:
                    continue
                iou = _iou(det["bbox"], pbox)
                if iou > best_iou:
                    best_i, best_iou = i, iou
            if best_i >= 0 and best_iou >= t["match_iou"]:
                lm = self._landmarks_from(preds[best_i][1], "keypoint_model", best_iou)
                if lm is not None:
                    used.add(best_i)
                    out[det["tooth_id"]] = lm
                    continue
            lm = self._crop_landmarks(det["bbox"], image_bgr, W, H) if self.model is not None else None
            out[det["tooth_id"]] = lm or heuristic_landmarks(det["bbox"])
        return out

    def _crop_landmarks(self, bbox, image_bgr: np.ndarray, W: int, H: int) -> dict | None:
        x1, y1, x2, y2 = bbox
        bw, bh = x2 - x1, y2 - y1
        cx1, cx2 = int(max(0, x1 - 0.9 * bw)), int(min(W, x2 + 0.9 * bw))
        cy1, cy2 = int(max(0, y1 - 0.15 * bh)), int(min(H, y2 + 0.15 * bh))
        if cx2 - cx1 < 16 or cy2 - cy1 < 16:
            return None
        preds = self._predict(image_bgr[cy1:cy2, cx1:cx2], offset=(cx1, cy1))
        best_iou, best_k = max(((_iou(bbox, b), k) for b, k, _c in preds), key=lambda p: p[0], default=(0.0, None))
        if best_k is None or best_iou < config.THRESHOLDS["landmarks"]["match_iou"]:
            return None
        return self._landmarks_from(best_k, "keypoint_model_crop", best_iou)
