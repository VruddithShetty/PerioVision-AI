"""CLAHE contrast enhancement and perceptual hashing.

The enhanced image keeps the original size, so detections, landmarks and
heatmaps all share one coordinate system.
"""
import cv2
import imagehash
import numpy as np
from PIL import Image

from app import config


def apply_clahe(gray: np.ndarray) -> np.ndarray:
    t = config.THRESHOLDS["preprocessing"]
    clahe = cv2.createCLAHE(clipLimit=t["clahe_clip_limit"], tileGridSize=(t["clahe_tile"], t["clahe_tile"]))
    return clahe.apply(gray)


def preprocess_for_analysis(image_path, target_size=(512, 512)):
    """Older helper: grayscale -> resize -> CLAHE -> float [0, 1]. Kept for scripts."""
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    return apply_clahe(cv2.resize(img, target_size)).astype(np.float32) / 255.0


def compute_phash(image) -> str:
    """Perceptual hash of a file path or a numpy image."""
    if isinstance(image, np.ndarray):
        return str(imagehash.phash(Image.fromarray(image)))
    with Image.open(image) as img:
        return str(imagehash.phash(img))
