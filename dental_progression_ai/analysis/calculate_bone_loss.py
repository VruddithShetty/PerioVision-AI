import math

def calculate_distance(p1, p2):
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

def compute_bone_loss(landmarks):
    """
    Computes Bone Loss Percentage:
    Bone Loss % = (CEJ to Bone Distance / CEJ to Root Apex Distance) × 100
    """
    bone_loss_results = {}
    
    for tooth_num, points in landmarks.items():
        cej = points["cej"]
        apex = points["root_apex"]
        bone_crest = points["bone_crest"]
        
        # Calculate CEJ to Apex Distance (Total root length reference)
        cej_to_apex_dist = calculate_distance(cej, apex)
        
        # Calculate CEJ to Bone Crest Distance (Defect depth)
        cej_to_bone_dist = calculate_distance(cej, bone_crest)
        
        if cej_to_apex_dist > 0:
            bone_loss_pct = (cej_to_bone_dist / cej_to_apex_dist) * 100.0
            bone_loss_results[tooth_num] = round(bone_loss_pct, 1)
        else:
            bone_loss_results[tooth_num] = 0.0
            
    return bone_loss_results
