import cv2
import numpy as np

def draw_findings_on_image(image, detections, landmarks, bone_loss):
    """
    Overlays AI detections and bone loss metrics onto the radiograph.
    """
    canvas = image.copy()
    if len(canvas.shape) == 2:
        canvas = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)
        
    for det in (detections or []):
        box = det.get("box") or det.get("bbox")
        if not box or len(box) < 4:
            continue
        x1, y1, x2, y2 = map(int, box)
        tid = det.get("tooth_number")
        
        # Draw Box
        cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 255, 0), 2)
        
        # Draw Bone Loss Text
        bl_dict = bone_loss.get(tid) or bone_loss.get(str(tid)) or bone_loss.get(int(tid)) if isinstance(bone_loss, dict) else None
        if not isinstance(bl_dict, dict):
            bl_dict = {}
        bl = bl_dict.get("bone_loss_pct", 0.0)
        cv2.putText(canvas, f"T{tid}: {bl}%", (x1, y1 - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        
    # Draw Landmarks
    for tid, pts in (landmarks or {}).items():
        if isinstance(pts, dict):
            for p_name, coord in pts.items():
                if coord and len(coord) >= 2:
                    cv2.circle(canvas, tuple(map(int, coord)), 3, (255, 0, 0), -1)
            
    return canvas
