"""Intensity normalisation helpers shared by the pipeline."""
import cv2
import numpy as np


def to_gray_uint8(img: np.ndarray) -> np.ndarray:
    if img.ndim == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if img.dtype != np.uint8:
        img = img.astype(np.float64)
        img -= img.min()
        img = (img / img.max() * 255) if img.max() > 0 else img
        img = img.astype(np.uint8)
    return img


def to_unit_float(img: np.ndarray) -> np.ndarray:
    """Scale an 8-bit image to float32 in [0, 1]."""
    return img.astype(np.float32) / 255.0
