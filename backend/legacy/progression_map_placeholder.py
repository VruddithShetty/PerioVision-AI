import numpy as np
import cv2

def generate_progression_map(history_data):
    """
    Creates a heatmap visualization of bone loss over time.
    """
    # Placeholder for heatmap logic
    h, w = 400, 800
    map_img = np.zeros((h, w, 3), dtype=np.uint8)
    cv2.putText(map_img, "Temporal Bone Loss Map", (200, 200), 
                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    return map_img
