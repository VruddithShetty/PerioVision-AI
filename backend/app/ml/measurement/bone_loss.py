"""Per-tooth radiographic bone loss from CEJ, alveolar-crest and root-apex landmarks.

Bone loss % = the CEJ->crest vector projected onto the CEJ->apex (root) axis,
as a fraction of root length, clamped to 0-100 %. Projecting onto the root axis
ignores sideways landmark jitter. When the image carries a pixel spacing
(DICOM PixelSpacing), the CEJ-to-crest distance is also reported in mm;
otherwise `cej_to_crest_mm` is None and only the percentage is used.
"""
from __future__ import annotations

import numpy as np


def bone_loss_for_tooth(pts: dict, pixel_spacing_mm: float | None = None) -> dict:
    try:
        cej = np.asarray(pts["cej"], dtype=float)
        apex = np.asarray(pts["root_apex"], dtype=float)
        crest = np.asarray(pts["bone_crest"], dtype=float)
    except (KeyError, TypeError, ValueError):
        return {"bone_loss_pct": None, "status": "landmarks_missing"}

    root = apex - cej
    root_len_sq = float(np.dot(root, root))
    if root_len_sq <= 1e-6:
        return {"bone_loss_pct": None, "status": "invalid_landmarks"}
    ratio = float(np.dot(crest - cej, root)) / root_len_sq
    pct = round(max(0.0, min(100.0, ratio * 100.0)), 2)
    cej_crest_px = float(np.linalg.norm(crest - cej))
    return {
        "bone_loss_pct": pct,
        "status": "ok",
        "cej_to_crest_px": round(cej_crest_px, 1),
        "root_length_px": round(float(np.sqrt(root_len_sq)), 1),
        "cej_to_crest_mm": round(cej_crest_px * pixel_spacing_mm, 2) if pixel_spacing_mm else None,
    }


def compute_bone_loss(landmarks_dict: dict, pixel_spacing_mm: float | None = None) -> dict:
    return {tooth_id: bone_loss_for_tooth(pts, pixel_spacing_mm) for tooth_id, pts in landmarks_dict.items()}
