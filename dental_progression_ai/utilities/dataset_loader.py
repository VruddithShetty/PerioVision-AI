import os
import cv2
import numpy as np

def load_image(filepath):
    """
    Loads an image from the given standard/absolute filepath.
    Ensures that grayscale is returned if needed or just BGR natively.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Image not found at path: {filepath}")
    
    image = cv2.imread(filepath)
    if image is None:
        raise ValueError(f"Failed to read image at path: {filepath}. It might be corrupted or unsupported.")
        
    return image

def ensure_storage_directories():
    """
    Ensures that the required directories for our image storage exist.
    """
    os.makedirs("storage/xrays", exist_ok=True)
    os.makedirs("storage/annotated_results", exist_ok=True)
