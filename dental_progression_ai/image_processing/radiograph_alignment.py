import cv2
import numpy as np

def align_radiographs(base_image, timepoint_image):
    """
    Align a historical radiograph (timepoint_image) to an older/base radiograph (base_image)
    using ORB feature detection and Homography.
    """
    # Convert to grayscale if not already
    gray_base = cv2.cvtColor(base_image, cv2.COLOR_BGR2GRAY) if len(base_image.shape) == 3 else base_image
    gray_time = cv2.cvtColor(timepoint_image, cv2.COLOR_BGR2GRAY) if len(timepoint_image.shape) == 3 else timepoint_image

    # Initialize ORB detector
    MAX_FEATURES = 5000
    orb = cv2.ORB_create(MAX_FEATURES)

    # Detect keypoints and compute descriptors
    keypoints1, descriptors1 = orb.detectAndCompute(gray_base, None)
    keypoints2, descriptors2 = orb.detectAndCompute(gray_time, None)

    if descriptors1 is None or descriptors2 is None:
        print("Feature extraction failed, returning original image.")
        return timepoint_image

    # Match features (using Brute-Force with Hamming distance)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = bf.match(descriptors1, descriptors2)

    # Sort matches by distance
    matches = sorted(matches, key=lambda x: x.distance)

    # Keep top 15% of matches
    keep_fraction = 0.15
    num_good_matches = int(len(matches) * keep_fraction)
    matches = matches[:num_good_matches]

    if len(matches) < 4:
        # Not enough matches for homography
        print("Not enough matches to compute homography, returning original.")
        return timepoint_image

    # Extract coordinates of good matches
    points1 = np.zeros((len(matches), 2), dtype=np.float32)
    points2 = np.zeros((len(matches), 2), dtype=np.float32)

    for i, match in enumerate(matches):
        points1[i, :] = keypoints1[match.queryIdx].pt
        points2[i, :] = keypoints2[match.trainIdx].pt

    # Find Homography (mapping points2 onto points1)
    # Using RANSAC to exclude outliers
    homography, mask = cv2.findHomography(points2, points1, cv2.RANSAC, 5.0)

    if homography is None:
        print("Homography computation failed.")
        return timepoint_image

    # Apply Homography to align timepoint_image to base_image space
    height, width = gray_base.shape
    aligned_time_img = cv2.warpPerspective(timepoint_image, homography, (width, height))

    return aligned_time_img
