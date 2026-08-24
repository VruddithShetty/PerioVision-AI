import cv2
import numpy as np
import imagehash
from PIL import Image

def preprocess_for_analysis(image_path, target_size=(512, 512)):
    """
    Standardizes radiographs: Grayscale, CLAHE enhancement, and resizing.
    """
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None: return None
    
    # 1. Resize
    img = cv2.resize(img, target_size)
    
    # 2. CLAHE (Contrast Limited Adaptive Histogram Equalization)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    enhanced = clahe.apply(img)
    
    # 3. Normalize to [0, 1] for AI models
    normalized = enhanced.astype(np.float32) / 255.0
    return normalized

def compute_phash(image_path):
    """Computes perceptual hash for structural integrity verification."""
    with Image.open(image_path) as img:
        return str(imagehash.phash(img))
