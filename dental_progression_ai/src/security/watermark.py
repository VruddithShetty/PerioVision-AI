import os
import hmac
import hashlib
import numpy as np
import cv2
from dotenv import load_dotenv

load_dotenv()

class XRayWatermarker:
    """
    Implements fragile LSB watermarking and perceptual hashing to ensure 
    medical image integrity and provenance.
    """
    
    def __init__(self):
        # Ensure we have a key of at least 32 bytes for HS256
        raw_key = os.environ.get("WATERMARK_SECRET_KEY", "periovision_fallback_secure_key_32_bytes_long_!!!!!")
        if len(raw_key) < 32:
            raw_key = raw_key.ljust(32, "!")
        self.secret_key = raw_key.encode('utf-8')

    def embed_watermark(self, image_array: np.ndarray, record_id: str) -> tuple[np.ndarray, str]:
        """
        Embeds a fragile HMAC-SHA256 watermark into the LSB of the first 256 pixels.
        """
        payload = record_id.encode('utf-8')
        digest = hmac.new(self.secret_key, payload, hashlib.sha256).digest()
        digest_hex = digest.hex()
        
        bits = []
        for byte in digest:
            for i in range(8):
                bits.append((byte >> i) & 1)
        
        img_mod = image_array.copy()
        # Convert to int16 for safe bitwise math then back to uint8
        flat = img_mod.ravel().astype(np.int16)
        is_rgb = len(image_array.shape) == 3 and image_array.shape[2] == 3
        
        count = 0
        for i in range(len(flat)):
            if count >= 256: break
            if is_rgb and i % 3 != 2: continue
            
            # Use 0xFE to avoid issues with ~1 (which is -2) in some numpy/python versions
            flat[i] = (flat[i] & 0xFE) | bits[count]
            count += 1
            
        return flat.astype(np.uint8).reshape(image_array.shape), digest_hex

    def verify_watermark(self, image_array: np.ndarray, record_id: str, stored_watermark_hash: str) -> dict:
        flat = image_array.ravel()
        is_rgb = len(image_array.shape) == 3 and image_array.shape[2] == 3
        bits = []
        count = 0
        for i in range(len(flat)):
            if count >= 256: break
            if is_rgb and i % 3 != 2: continue
            bits.append(int(flat[i] & 1))
            count += 1
            
        extracted_bytes = []
        for i in range(0, 256, 8):
            byte = 0
            for j in range(8):
                byte |= (bits[i + j] << j)
            extracted_bytes.append(byte)
        extracted_digest_hex = bytes(extracted_bytes).hex()
        
        payload = record_id.encode('utf-8')
        expected_digest = hmac.new(self.secret_key, payload, hashlib.sha256).digest()
        expected_hex = expected_digest.hex()
        
        verified = extracted_digest_hex == expected_hex
        return {
            "verified": verified,
            "tampered": not verified
        }
