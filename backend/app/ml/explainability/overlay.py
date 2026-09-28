"""Images for the viewer and the PDF: annotated radiograph and a transparent Grad-CAM layer.

The Grad-CAM layer is an RGBA PNG (colour = attention, alpha = attention
strength), so the UI can place it over the radiograph with an opacity slider
instead of baking the heatmap into the image.
"""
from __future__ import annotations

import cv2
import numpy as np

SEVERITY_COLOURS = {  # BGR
    "I": (80, 200, 120), "II": (40, 190, 240), "III": (40, 120, 255), "IV": (60, 60, 230), None: (200, 200, 200),
}


def annotated_image(gray: np.ndarray, teeth: list[dict]) -> np.ndarray:
    canvas = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR) if gray.ndim == 2 else gray.copy()
    scale = max(1.0, min(canvas.shape[:2]) / 800.0)
    thick = max(1, int(round(2 * scale)))
    for t in teeth:
        colour = SEVERITY_COLOURS.get(t.get("stage"), SEVERITY_COLOURS[None])
        x1, y1, x2, y2 = map(int, t["bbox"])
        cv2.rectangle(canvas, (x1, y1), (x2, y2), colour, thick)
        cej, crest, apex = t.get("cej"), t.get("abc"), t.get("root_apex")
        if cej and crest:
            cv2.line(canvas, tuple(map(int, cej)), tuple(map(int, crest)), (0, 0, 255), thick)
        for pt, c in ((cej, (255, 255, 0)), (crest, (0, 0, 255)), (apex, (255, 0, 255))):
            if pt:
                cv2.circle(canvas, tuple(map(int, pt)), thick + 2, c, -1)
        bl = t.get("bone_loss_pct")
        label = f"{t['tooth_id']}: {bl:.0f}%" if bl is not None else str(t["tooth_id"])
        cv2.putText(canvas, label, (x1, max(12, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45 * scale, colour, thick)
    return canvas


def heatmap_layer(heatmap: np.ndarray) -> np.ndarray:
    """RGBA image: JET colour map with alpha proportional to attention."""
    heat8 = np.uint8(np.clip(heatmap, 0, 1) * 255)
    colour = cv2.applyColorMap(heat8, cv2.COLORMAP_JET)
    alpha = np.uint8(np.clip(heatmap * 1.4, 0, 1) * 255)
    return np.dstack([colour, alpha])


def encode_png(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise ValueError("PNG encoding failed")
    return buf.tobytes()


# Backward-compatible name used by older code
def draw_findings_on_image(image, detections, landmarks, bone_loss):
    teeth = []
    for d in detections or []:
        lm = (landmarks or {}).get(d.get("tooth_id"), {})
        teeth.append({"tooth_id": d.get("tooth_id"), "bbox": d.get("bbox"), "cej": lm.get("cej"),
                      "abc": lm.get("bone_crest"), "root_apex": lm.get("root_apex"),
                      "bone_loss_pct": (bone_loss or {}).get(d.get("tooth_id"), {}).get("bone_loss_pct")})
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return annotated_image(gray, teeth)
