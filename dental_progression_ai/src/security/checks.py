import cv2
import os
from security.watermark import XRayWatermarker
from database.xrays import XrayRecordManager

def check_xray_integrity(record_id: str) -> dict:
    """
    Validates the integrity of an X-ray record by checking its fragile watermark.
    """
    xray_mgr = XrayRecordManager()
    record = xray_mgr.get_record(record_id)
    
    if not record:
        return {"error": f"Record {record_id} not found."}
    
    img_path = record.get("image_path")
    if not img_path or not os.path.exists(img_path):
        return {"error": f"Image file not found at {img_path}"}
    
    image = cv2.imread(img_path)
    if image is None:
        return {"error": "Failed to decode image file."}
    
    watermarker = XRayWatermarker()
    v_result = watermarker.verify_watermark(
        image,
        str(record.get("record_id")),
        record.get("signature_hash", "")
    )
    
    integrity_status = "INTACT" if v_result["verified"] else "TAMPERED"
    
    return {
        "record_id": record_id,
        "watermark_verified": v_result["verified"],
        "integrity_status": integrity_status
    }
