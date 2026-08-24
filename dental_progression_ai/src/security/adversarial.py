import cv2
import numpy as np
import logging
from skimage.restoration import denoise_tv_chambolle

class AdversarialInputDetector:
    """
    Detects adversarial perturbations using frequency domain analysis 
    and pixel-level statistics.
    """
    
    def __init__(self, threshold_hf=0.15, threshold_laplacian=500.0):
        self.threshold_hf = threshold_hf
        self.threshold_laplacian = threshold_laplacian
        self.logger = logging.getLogger(__name__)

    def _analyze_frequency_domain(self, image: np.ndarray) -> float:
        """Analyzes high-frequency energy ratio which spikes in gradient attacks."""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
            
        dft = cv2.dft(np.float32(gray), flags=cv2.DFT_COMPLEX_OUTPUT)
        dft_shift = np.fft.fftshift(dft)
        
        magnitude = 20 * np.log(cv2.magnitude(dft_shift[:,:,0], dft_shift[:,:,1]) + 1)
        
        # Center is low freq, edges are high freq
        rows, cols = gray.shape
        crow, ccol = rows//2, cols//2
        
        # Create a mask to filter out low frequencies (center)
        mask = np.ones((rows, cols), np.uint8)
        r = 30 # radius for low freq circle
        cv2.circle(mask, (ccol, crow), r, 0, -1)
        
        hf_energy = np.mean(magnitude * mask)
        total_energy = np.mean(magnitude)
        
        return float(hf_energy / total_energy)

    def detect_adversarial(self, image: np.ndarray) -> dict:
        """
        Runs multiple statistical checks to detect non-natural perturbations.
        """
        hf_ratio = self._analyze_frequency_domain(image)
        
        # Check Laplacian variance (sharpness/noise)
        lap_var = cv2.Laplacian(image, cv2.CV_64F).var()
        
        is_suspicious = False
        triggers = []
        
        if hf_ratio > self.threshold_hf:
            is_suspicious = True
            triggers.append("High-frequency anomaly detected (potential gradient attack)")
            
        if lap_var > self.threshold_laplacian:
            is_suspicious = True
            triggers.append("Abnormal pixel variance detected")
            
        return {
            "is_suspicious": is_suspicious,
            "triggers": triggers,
            "metrics": {
                "hf_ratio": round(hf_ratio, 4),
                "laplacian_var": round(lap_var, 2)
            }
        }

    def denoise_if_suspicious(self, image: np.ndarray, detection_res: dict) -> np.ndarray:
        """Applies Total Variation (TV) denoising if an attack is suspected."""
        if not detection_res["is_suspicious"]:
            return image
            
        self.logger.info("Applying defensive denoising to suspect image.")
        # TV Denoising is effective at stripping adversarial noise while preserving edges
        denoised = denoise_tv_chambolle(image, weight=0.1, channel_axis=-1 if len(image.shape)==3 else None)
        return (denoised * 255).astype(np.uint8)
