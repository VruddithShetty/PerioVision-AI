import cv2
import numpy as np

def preprocess_for_analysis(image_path, target_size=(512, 512)):
    """
    Preprocess an X-ray image for the AI Dental Pipeline.
    Steps:
      1. Load image and convert to grayscale
      2. Apply CLAHE contrast enhancement
      3. Apply Gaussian blur for noise removal
      4. Perform edge enhancement (unsharp masking)
      5. Resize to target dimension (default 512x512)
    """
    # Load in grayscale
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"Could not load image at {image_path}")

    # Step 2: CLAHE for contrast enhancement
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced_img = clahe.apply(img)

    # Step 3: Gaussian blur to denoise
    blurred_img = cv2.GaussianBlur(enhanced_img, (5, 5), 0)

    # Step 4: Edge enhancement (Unsharp masking)
    # create a slightly more blurred version
    gaussian_2 = cv2.GaussianBlur(blurred_img, (0, 0), 2.0)
    # Add weighted difference between blurred and original back to blurred
    edge_enhanced = cv2.addWeighted(blurred_img, 1.5, gaussian_2, -0.5, 0)
    
    # Step 5: Resize to 512x512
    resized_img = cv2.resize(edge_enhanced, target_size, interpolation=cv2.INTER_AREA)
    
    # Return 3-channel version of the grayscale so plotting/YOLO works seamlessly
    return cv2.cvtColor(resized_img, cv2.COLOR_GRAY2BGR)

