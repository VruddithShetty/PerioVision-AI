import cv2
import numpy as np

class RadiographAligner:
    def __init__(self, method="affine"):
        self.method = method # "affine" or "homography"

    def align_images(self, source_image, target_image, source_landmarks, target_landmarks):
        """
        Aligns the source_image (older X-ray) to match the target_image (newer X-ray).
        Uses detected landmarks for geometric alignment.
        """
        src_pts = []
        dst_pts = []
        
        # Match landmarks by tooth ID
        for tooth_id in target_landmarks:
            if tooth_id in source_landmarks:
                # Add all available landmark points for this tooth
                for key in ["cej", "root_apex", "bone_crest"]:
                    if key in target_landmarks[tooth_id] and key in source_landmarks[tooth_id]:
                        src_pts.append(source_landmarks[tooth_id][key])
                        dst_pts.append(target_landmarks[tooth_id][key])
                        
        if len(src_pts) < 3:
            # Not enough points for affine transformation, return original
            print("Warning: Not enough corresponding landmarks found for alignment.")
            return source_image
            
        src_pts = np.float32(src_pts)
        dst_pts = np.float32(dst_pts)
        
        if self.method == "affine" or len(src_pts) < 4:
            # Requires at least 3 points. Uses cv2.estimateAffinePartial2D
            matrix, inliers = cv2.estimateAffinePartial2D(src_pts, dst_pts)
            if matrix is not None:
                aligned_image = cv2.warpAffine(source_image, matrix, (target_image.shape[1], target_image.shape[0]))
                return aligned_image
            else:
                return source_image
        else:
            # Homography requires at least 4 points
            matrix, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
            if matrix is not None:
                aligned_image = cv2.warpPerspective(source_image, matrix, (target_image.shape[1], target_image.shape[0]))
                return aligned_image
            else:
                return source_image
