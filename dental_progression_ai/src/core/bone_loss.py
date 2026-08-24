import numpy as np

def compute_bone_loss(landmarks_dict):
    """
    Calculates percentage bone loss for each tooth based on CEJ, 
    Bone Crest, and Root Apex landmarks.
    
    Formula: (Vector CEJ->Crest ⋅ Vector CEJ->Apex) / |CEJ->Apex|^2
    Clamped between 0 and 100%.
    """
    results = {}
    for tooth_id, pts in landmarks_dict.items():
        try:
            cej = np.array(pts["cej"])
            apex = np.array(pts["root_apex"])
            crest = np.array(pts["bone_crest"])
            
            # Vectors from CEJ
            v_root = apex - cej
            v_loss = crest - cej
            
            # Projection of v_loss onto v_root
            # We use dot product to ensure we only count loss in the direction of the apex
            root_len_sq = np.dot(v_root, v_root)
            if root_len_sq == 0:
                results[tooth_id] = {"bone_loss_pct": 0.0, "status": "Invalid Landmarks"}
                continue
                
            projection_ratio = np.dot(v_loss, v_root) / root_len_sq
            bl_pct = projection_ratio * 100
            
            results[tooth_id] = {
                "bone_loss_pct": round(max(0.0, min(100.0, bl_pct)), 2),
                "status": "Healthy" if bl_pct < 15 else ("Gingivitis" if bl_pct < 30 else "Periodontitis")
            }
        except Exception:
            results[tooth_id] = {"bone_loss_pct": 0.0, "status": "Analysis Error"}
    return results
