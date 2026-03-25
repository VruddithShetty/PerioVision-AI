import cv2
import numpy as np

# Color thresholds for disease severity
RISK_COLORS = {
    "Healthy":  (0, 200, 0),    # Green
    "Mild":     (0, 200, 200),  # Yellow
    "Moderate": (0, 165, 255),  # Orange
    "Severe":   (0, 0, 220),    # Red
    "Low Risk":    (0, 200, 0),
    "Medium Risk": (0, 165, 255),
    "High Risk":   (0, 0, 220),
}

def bone_loss_to_severity(loss_pct):
    if loss_pct < 15:
        return "Healthy"
    elif loss_pct < 30:
        return "Mild"
    elif loss_pct < 50:
        return "Moderate"
    else:
        return "Severe"

def generate_progression_map(image, tooth_detections, bone_loss_metrics, velocity_metrics, prediction_results):
    """
    Draws a color-coded longitudinal progression map overlaid on the radiograph.
    Returns the annotated image (BGR numpy array).
    """
    overlay = image.copy()
    output = image.copy()
    
    for det in tooth_detections:
        tooth_id = det["tooth_number"]
        tooth_key = f"tooth_{tooth_id}"
        x1, y1, x2, y2 = [int(c) for c in det["box"]]
        
        # Determine color from prediction or bone loss severity
        if tooth_key in prediction_results:
            risk_level = prediction_results[tooth_key].get("risk_level", "Low Risk")
            color = RISK_COLORS.get(risk_level, (200, 200, 200))
        elif tooth_key in bone_loss_metrics:
            severity = bone_loss_to_severity(bone_loss_metrics[tooth_key])
            color = RISK_COLORS.get(severity, (200, 200, 200))
        else:
            color = (180, 180, 180)  # Gray for unknown
        
        # Semi-transparent filled rectangle
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
        
    # Blend overlay transparently
    cv2.addWeighted(overlay, 0.35, output, 0.65, 0, output)
    
    # Draw borders and labels on final output
    for det in tooth_detections:
        tooth_id = det["tooth_number"]
        tooth_key = f"tooth_{tooth_id}"
        x1, y1, x2, y2 = [int(c) for c in det["box"]]
        
        if tooth_key in prediction_results:
            risk_level = prediction_results[tooth_key].get("risk_level", "Low Risk")
            color = RISK_COLORS.get(risk_level, (200, 200, 200))
        elif tooth_key in bone_loss_metrics:
            severity = bone_loss_to_severity(bone_loss_metrics[tooth_key])
            color = RISK_COLORS.get(severity, (200, 200, 200))
        else:
            color = (180, 180, 180)
        
        cv2.rectangle(output, (x1, y1), (x2, y2), color, 2)
        
        # Print tooth ID and bone loss % on the rectangle
        loss_pct = bone_loss_metrics.get(tooth_key, None)
        velocity = velocity_metrics.get(tooth_key, None)
        
        label_lines = [f"T{tooth_id}"]
        if loss_pct is not None:
            label_lines.append(f"{loss_pct:.0f}%")
        if velocity is not None:
            label_lines.append(f"{velocity:+.1f}%/yr")
        
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.38
        text_thickness = 1
        y_offset = y1 + 13
        for line in label_lines:
            cv2.putText(output, line, (x1 + 2, y_offset), font, font_scale, (255, 255, 255), text_thickness + 1)
            cv2.putText(output, line, (x1 + 2, y_offset), font, font_scale, (0, 0, 0), text_thickness)
            y_offset += 14
    
    # Draw a legend in the top-right corner
    legend_items = [("Healthy", (0, 200, 0)), ("Mild", (0, 200, 200)), ("Moderate", (0, 165, 255)), ("Severe", (0, 0, 220))]
    lx = output.shape[1] - 110
    ly = 10
    for label, color in legend_items:
        cv2.rectangle(output, (lx, ly), (lx + 16, ly + 14), color, -1)
        cv2.putText(output, label, (lx + 20, ly + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)
        ly += 20
    
    return output
