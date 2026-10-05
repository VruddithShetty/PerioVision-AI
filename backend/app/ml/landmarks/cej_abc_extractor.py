"""CEJ, root-apex and alveolar-bone-crest (ABC) keypoints per detected tooth.

The YOLO-pose model predicts, for each tooth, three keypoints in this order:
CEJ, root apex, bone crest (see scripts/convert_denpar.py). It runs on
the same full-resolution image as the detector, so keypoints and detection
boxes share one coordinate system and are matched by box overlap (IoU).

Teeth the whole-image pass misses (common on panoramic images, where teeth are small) are
re-run on a zoomed crop of the tooth and its neighbours (`keypoint_model_crop`). On periapical
films, where the panoramic detector finds few teeth, `detect_teeth` lets the keypoint model find
the teeth itself.

If a tooth still has no matching pose prediction, or its keypoints are below the
confidence threshold, it gets geometric placeholder points marked
`landmark_source = "heuristic_fallback"`. Those points are NOT a measurement (they give
the same ~17 % for every tooth), so the analysis reports such teeth as "not measured"
with no bone-loss %, stage or interval (see analysis_service.measured).
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


def _pct(k) -> float | None:
    from app.ml.measurement.bone_loss import bone_loss_for_tooth

    return bone_loss_for_tooth({"cej": k[0, :2], "root_apex": k[1, :2], "bone_crest": k[2, :2]})["bone_loss_pct"]


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
        self._gradcam = None

    @property
    def available(self) -> bool:
        return self.model is not None

    def gradcam_heatmap(self, image_bgr: np.ndarray, detections: list[dict]):
        """Grad-CAM of THIS model (used when it, not the panoramic detector, found the teeth)."""
        from app.ml.detection.yolo_detector import ToothDetectionModel

        return ToothDetectionModel.gradcam_heatmap(self, image_bgr, detections)

    def gradcam_per_tooth(self, image_bgr: np.ndarray, detections: list[dict]):
        from app.ml.detection.yolo_detector import ToothDetectionModel

        return ToothDetectionModel.gradcam_per_tooth(self, image_bgr, detections)

    def _raw(self, image_bgr: np.ndarray):
        results = self.model(image_bgr, conf=0.05, verbose=False)
        if not results or results[0].keypoints is None or results[0].boxes is None:
            return np.zeros((0, 4)), np.zeros((0, 3, 3)), np.zeros(0)
        return (results[0].boxes.xyxy.cpu().numpy().copy(), results[0].keypoints.data.cpu().numpy().copy(),
                results[0].boxes.conf.cpu().numpy().copy())

    def _predict(self, image_bgr: np.ndarray, offset=(0.0, 0.0), tta: bool = True) -> list[tuple]:
        """Pose predictions as [(box_xyxy, kpts[3, 3], box_conf, tta_disagreement_pct)] in full-image coordinates.

        Test-time augmentation: the film is also read mirrored left-right (bone loss is mirror-invariant).
        A tooth found in both passes gets the average of the two keypoint sets, and the difference between
        the two bone-loss readings (percentage points) is kept as a per-tooth difficulty signal that the
        adaptive conformal interval scales with. On DenPAR, averaging lowered the bone-loss error on both
        the validation (8.39 -> 8.23) and test (7.57 -> 7.28) splits. A tooth seen in only one pass keeps
        that pass's keypoints and a disagreement of None (treated as the hardest case).
        """
        boxes, kpts, confs = self._raw(image_bgr)
        dis = [None] * len(boxes)
        if tta and config.THRESHOLDS["landmarks"].get("tta_mirror", True) and len(boxes):
            w = image_bgr.shape[1]
            mb, mk, _mc = self._raw(np.ascontiguousarray(image_bgr[:, ::-1]))
            if len(mb):
                mb = np.stack([w - mb[:, 2], mb[:, 1], w - mb[:, 0], mb[:, 3]], 1)   # back to original x
                mk[:, :, 0] = w - mk[:, :, 0]
                used = set()
                for i in range(len(boxes)):
                    j, best = max(((j, _iou(boxes[i], mb[j])) for j in range(len(mb)) if j not in used),
                                  key=lambda t: t[1], default=(None, 0.0))
                    if j is None or best < 0.5:
                        continue
                    used.add(j)
                    a, b = _pct(kpts[i]), _pct(mk[j])
                    kpts[i] = (kpts[i] + mk[j]) / 2.0
                    dis[i] = abs(a - b) if a is not None and b is not None else None
        ox, oy = offset
        boxes[:, [0, 2]] += ox
        boxes[:, [1, 3]] += oy
        kpts[:, :, 0] += ox
        kpts[:, :, 1] += oy
        return list(zip(boxes, kpts, confs, dis))

    @staticmethod
    def _landmarks_from(k, source: str, match_iou: float | None = None, disagreement: float | None = None) -> dict | None:
        confs = [float(k[j, 2]) if k.shape[1] > 2 else 0.0 for j in range(3)]
        if min(confs) < config.THRESHOLDS["landmarks"]["min_keypoint_confidence"]:
            return None
        out = {
            **{name: [round(float(k[j, 0]), 1), round(float(k[j, 1]), 1)] for j, name in enumerate(KEYPOINT_ORDER)},
            "landmark_source": source,
            "landmark_confidence": round(float(np.mean(confs)), 3),
            "keypoint_confidences": dict(zip(KEYPOINT_ORDER, [round(c, 3) for c in confs])),
            "tta_disagreement_pct": None if disagreement is None else round(float(disagreement), 3),
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
        for box, k, c, dis in sorted(self._predict(image_bgr), key=lambda p: p[0][0]):
            if c < t["min_confidence"]:
                continue
            lm = self._landmarks_from(k, "keypoint_model", disagreement=dis)
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
            for i, (pbox, _k, _c, _d) in enumerate(preds):
                if i in used:
                    continue
                iou = _iou(det["bbox"], pbox)
                if iou > best_iou:
                    best_i, best_iou = i, iou
            if best_i >= 0 and best_iou >= t["match_iou"]:
                lm = self._landmarks_from(preds[best_i][1], "keypoint_model", best_iou, preds[best_i][3])
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
        # one pass per crop (no mirror): this path is unvalidated, and doubling ~30 crops is too slow on CPU
        preds = self._predict(image_bgr[cy1:cy2, cx1:cx2], offset=(cx1, cy1), tta=False)
        best_iou, best_k, best_d = max(((_iou(bbox, b), k, d) for b, k, _c, d in preds), key=lambda p: p[0],
                                       default=(0.0, None, None))
        if best_k is None or best_iou < config.THRESHOLDS["landmarks"]["match_iou"]:
            return None
        return self._landmarks_from(best_k, "keypoint_model_crop", best_iou, best_d)
