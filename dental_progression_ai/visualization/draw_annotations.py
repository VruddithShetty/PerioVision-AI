import cv2

def get_color_for_loss(loss_pct):
    """
    Returns BGR color based on severity of bone loss %.
    Green -> Healthy (< 15%)
    Yellow -> Mild (15-25%)
    Orange -> Moderate (25-40%)
    Red -> Severe (> 40%)
    """
    if loss_pct < 15:
        return (0, 255, 0)      # Green
    elif loss_pct < 25:
        return (0, 255, 255)    # Yellow
    elif loss_pct < 40:
        return (0, 165, 255)    # Orange (BGR)
    else:
        return (0, 0, 255)      # Red

def draw_findings_on_image(image, detections, landmarks, bone_loss):
    """
    Overlays tooth bounding boxes, landmarks, and bone loss percentages.
    """
    annotated = image.copy()
    
    for det in detections:
        t_num = det["tooth_number"]
        x1, y1, x2, y2 = det["box"]
        loss_pct = bone_loss.get(t_num, 0.0)
        
        color = get_color_for_loss(loss_pct)
        
        # Draw bounding box
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        
        # Draw tooth number & percentage
        label = f"T{t_num} ({loss_pct}%)"
        cv2.putText(annotated, label, (x1, max(y1-10, 0)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        
        # Draw landmarks if available
        if t_num in landmarks:
            pts = landmarks[t_num]
            cej = pts["cej"]
            apex = pts["root_apex"]
            bone = pts["bone_crest"]
            
            # Draw Points
            cv2.circle(annotated, cej, 3, (255, 0, 0), -1)    # Blue CEJ
            cv2.circle(annotated, apex, 3, (0, 255, 255), -1) # Yellow Apex
            cv2.circle(annotated, bone, 3, (0, 0, 255), -1)   # Red Bone Crest
            
            # Draw lines
            cv2.line(annotated, cej, apex, (255, 255, 255), 1) # White total root line
            cv2.line(annotated, cej, bone, (0, 0, 255), 2)     # Red defect line
            
    return annotated
