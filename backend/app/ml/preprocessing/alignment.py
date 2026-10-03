import cv2
import numpy as np
import logging

try:
    from skimage.metrics import structural_similarity as ssim
except ImportError:
    ssim = None

logger = logging.getLogger("RadiographAligner")

class RadiographAligner:
    """
    Handles robust temporal alignment of dental radiographs using 
    both Feature-based (ORB/ECC) and Landmark-based methods.
    """
    MIN_INLIERS = 25
    MIN_INLIER_RATIO = 0.5
    SCALE_RANGE = (0.8, 1.25)
    MAX_ROTATION_DEG = 20.0
    MIN_NCC = 0.5

    def __init__(self, method="affine"):
        self.method = method
        self.orb = cv2.ORB_create(nfeatures=1500)
        self.alignment_status = "unavailable"
        self.last_alignment_confidence = 0.0
        
        # FLANN matcher
        FLANN_INDEX_LSH = 6
        index_params = dict(algorithm=FLANN_INDEX_LSH, table_number=6, key_size=12, multi_probe_level=1)
        search_params = dict(checks=50)
        self.flann = cv2.FlannBasedMatcher(index_params, search_params)

    def detect_metal_artifacts(self, image):
        """
        Scans for high-intensity saturated pixel clusters (>250) and sharp local gradient
        outliers characteristic of metallic dental restorations/fillings.
        """
        if image is None:
            return {"metal_artifact_detected": False, "saturated_pixel_ratio": 0.0, "extreme_gradient_ratio": 0.0}
        gray = image if len(image.shape) == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        saturated_mask = (gray >= 250).astype(np.uint8)
        saturated_ratio = float(np.sum(saturated_mask) / gray.size)

        # Gradient check for high-contrast metal borders
        sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        grad_mag = np.sqrt(sobelx**2 + sobely**2)
        extreme_grad_ratio = float(np.sum(grad_mag > 1500) / gray.size)

        has_metal = saturated_ratio > 0.005 and extreme_grad_ratio > 0.002
        return {
            "metal_artifact_detected": has_metal,
            "saturated_pixel_ratio": round(saturated_ratio, 4),
            "extreme_gradient_ratio": round(extreme_grad_ratio, 4)
        }

    def align_by_features(self, reference_image, moving_image):
        """Standard feature-based alignment using ORB with metal artifact check."""
        ref_gray = reference_image if len(reference_image.shape) == 2 else cv2.cvtColor(reference_image, cv2.COLOR_BGR2GRAY)
        mov_gray = moving_image if len(moving_image.shape) == 2 else cv2.cvtColor(moving_image, cv2.COLOR_BGR2GRAY)

        metal_check_ref = self.detect_metal_artifacts(ref_gray)
        metal_check_mov = self.detect_metal_artifacts(mov_gray)
        metal_artifact = metal_check_ref["metal_artifact_detected"] or metal_check_mov["metal_artifact_detected"]
        
        kp1, des1 = self.orb.detectAndCompute(ref_gray, None)
        kp2, des2 = self.orb.detectAndCompute(mov_gray, None)
        
        # Registration is accepted only if it is geometrically consistent AND the registered images
        # actually look alike. Counting descriptor matches alone is not enough: radiographs of two
        # different patients routinely give 30+ ratio-test matches (repetitive enamel / bone texture).
        # On DenPAR periapical films, unrelated pairs gave <= 10 RANSAC inliers (inlier ratio <= 0.43);
        # the same film re-exposed (rotated, scaled, noisy) gave >= 77 inliers, ratio >= 0.94, NCC >= 0.98.
        # NOT yet validated on real follow-up pairs of the same patient (none available).
        info = {"alignment_status": "failed", "alignment_confidence": 0.0, "low_alignment_confidence": True,
                "metal_artifact_detected": metal_artifact, "ratio_test_matches": 0, "ransac_inliers": 0,
                "inlier_ratio": 0.0, "scale": None, "rotation_deg": None, "ncc_after_warp": None, "reason": None}
        matrix = None
        if des1 is None or des2 is None or len(des1) < 8 or len(des2) < 8:
            info["reason"] = "too few image features"
        else:
            matches = self.flann.knnMatch(des2, des1, k=2)
            good = [m[0] for m in matches if len(m) == 2 and m[0].distance < 0.75 * m[1].distance]
            info["ratio_test_matches"] = len(good)
            if len(good) < self.MIN_INLIERS:
                info["reason"] = "too few matching features"
            else:
                src = np.float32([kp2[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
                dst = np.float32([kp1[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
                matrix, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=5.0)
                if matrix is None:
                    info["reason"] = "no consistent transform"
                else:
                    n_in = int(inliers.sum())
                    scale = float(np.hypot(matrix[0, 0], matrix[1, 0]))
                    angle = float(np.degrees(np.arctan2(matrix[1, 0], matrix[0, 0])))
                    h, w = ref_gray.shape
                    aligned = cv2.warpAffine(mov_gray, matrix, (w, h), flags=cv2.INTER_LINEAR)
                    valid = cv2.warpAffine(np.ones_like(mov_gray), matrix, (w, h)) > 0
                    ncc = None
                    if valid.mean() >= 0.3:
                        a, b = ref_gray[valid].astype(float), aligned[valid].astype(float)
                        if a.std() > 0 and b.std() > 0:
                            ncc = float(np.corrcoef(a, b)[0, 1])
                    info.update({"ransac_inliers": n_in, "inlier_ratio": round(n_in / len(good), 3),
                                 "scale": round(scale, 3), "rotation_deg": round(angle, 1),
                                 "ncc_after_warp": round(ncc, 3) if ncc is not None else None})
                    problems = [msg for bad, msg in (
                        (n_in < self.MIN_INLIERS, f"only {n_in} geometrically consistent matches"),
                        (n_in / len(good) < self.MIN_INLIER_RATIO, "most matches are inconsistent"),
                        (not self.SCALE_RANGE[0] <= scale <= self.SCALE_RANGE[1], f"implausible scale {scale:.2f}"),
                        (abs(angle) > self.MAX_ROTATION_DEG, f"implausible rotation {angle:.0f} degrees"),
                        (ncc is None or ncc < self.MIN_NCC, "registered images do not look alike"),
                    ) if bad]
                    if problems:
                        info["reason"] = "; ".join(problems)
                    else:
                        # Confidence = how alike the registered images are (normalised cross-correlation).
                        info.update({"alignment_status": "success", "alignment_confidence": round(ncc, 3),
                                     "low_alignment_confidence": False})
                        self.alignment_status = "success"
                        self.last_alignment_confidence = ncc
                        self.last_alignment_info = info
                        return aligned, matrix
        self.alignment_status = "failed"
        self.last_alignment_confidence = 0.0
        self.last_alignment_info = info
        return moving_image, np.eye(2, 3, dtype=np.float32)

    def align_by_landmarks(self, source_image, target_image, source_landmarks, target_landmarks):
        """Aligns source (older) to target (newer) using specific dental landmarks."""
        src_pts = []
        dst_pts = []
        for tid in target_landmarks:
            if tid in source_landmarks:
                for key in ["cej", "root_apex", "bone_crest"]:
                    if key in target_landmarks[tid] and key in source_landmarks[tid]:
                        src_pts.append(source_landmarks[tid][key])
                        dst_pts.append(target_landmarks[tid][key])
        
        if len(src_pts) >= 3:
            src_pts, dst_pts = np.float32(src_pts), np.float32(dst_pts)
            matrix, _ = cv2.estimateAffinePartial2D(src_pts, dst_pts)
            if matrix is not None:
                return cv2.warpAffine(source_image, matrix, (target_image.shape[1], target_image.shape[0]))
        return source_image

    def create_overlay(self, img1, img2):
        """Generates a checkerboard comparison."""
        h, w = img1.shape[:2]
        blend = np.zeros_like(img1)
        bs = 64
        for y in range(0, h, bs):
            for x in range(0, w, bs):
                if ((x // bs) + (y // bs)) % 2 == 0:
                    blend[y:y+bs, x:x+bs] = img1[y:y+bs, x:x+bs]
                else:
                    blend[y:y+bs, x:x+bs] = img2[y:y+bs, x:x+bs]
        return blend

    def calibrate_pixels_per_mm(self, image, detected_teeth, dicom_pixel_spacing=None, user_calibration_reference=None):
        """
        Calibration hierarchy:
        1. DICOM PixelSpacing metadata (if available)
        2. User-provided / patient-specific calibration reference
        3. Premolar-width fallback (~7mm assumed), explicitly tagged
        """
        # Priority 1: DICOM PixelSpacing metadata
        if dicom_pixel_spacing is not None:
            try:
                row_sp = float(dicom_pixel_spacing[0])
                if row_sp > 0:
                    px_per_mm = 1.0 / row_sp
                    return float(px_per_mm), 1.0, "dicom_metadata"
            except (IndexError, TypeError, ValueError):
                pass

        # Priority 2: Patient-specific / User calibration reference
        if user_calibration_reference is not None and isinstance(user_calibration_reference, (int, float)) and user_calibration_reference > 0:
            return float(user_calibration_reference), 0.95, "user_reference"

        # Check for restorations in image
        has_restoration = False
        if image is not None:
            metal_res = self.detect_metal_artifacts(image)
            has_restoration = metal_res["metal_artifact_detected"]

        # Priority 3: Fallback premolar width assumption (~7mm)
        premolars = {14, 15, 24, 25, 34, 35, 44, 45}
        pixel_widths = []
        
        for tooth in detected_teeth:
            tid_raw = tooth.get("tooth_number")
            bbox = tooth.get("bbox") or tooth.get("box")
            try:
                tid = int(tid_raw)
            except (ValueError, TypeError):
                tid = tid_raw
            if tid in premolars and bbox is not None:
                width = abs(bbox[2] - bbox[0])
                if width > 0:
                    pixel_widths.append(width)
                    
        if len(pixel_widths) < 2 or has_restoration:
            if len(pixel_widths) < 2 and not has_restoration:
                return None, 0.0, "unavailable"
            default_px_per_mm = 15.0
            status_tag = "restoration_altered_fallback_15px" if has_restoration else "fallback_assumed_premolar_7mm"
            return default_px_per_mm, 0.40, status_tag
            
        avg_width_px = np.mean(pixel_widths)
        pixels_per_mm = avg_width_px / 7.0
        calibration_confidence = min(1.0, 0.5 + 0.1 * len(pixel_widths))
        
        return float(pixels_per_mm), float(calibration_confidence), "available"

    def compute_true_cej_abc_distance(self, cej_px, abc_px, pixels_per_mm):
        """Returns distance in real millimetres."""
        if pixels_per_mm <= 0:
            return 0.0
        dist_px = np.linalg.norm(np.array(cej_px) - np.array(abc_px))
        return float(dist_px / pixels_per_mm)
