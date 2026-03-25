import math

class ProgressionVelocityCalculator:
    def __init__(self):
        pass

    def calculate_distance(self, pt1, pt2):
        if not pt1 or not pt2:
            return 0.0
        return math.sqrt((pt2[0] - pt1[0])**2 + (pt2[1] - pt1[1])**2)

    def calculate_bone_loss(self, landmarks):
        """
        Calculates standardized bone loss based on extracted landmarks.
        Returns a dictionary mapping tooth_id to bone loss percentage.
        Distance A = CEJ -> Root Apex
        Distance B = CEJ -> Bone Crest
        Loss = (DistanceB / DistanceA) * 100
        """
        bone_loss_metrics = {}
        
        for tooth_key, pts in landmarks.items():
            cej = pts.get("cej")
            apex = pts.get("root_apex")
            crest = pts.get("bone_crest")
            
            if cej and apex and crest:
                dist_a = self.calculate_distance(cej, apex)
                dist_b = self.calculate_distance(cej, crest)
                
                if dist_a > 0:
                    loss_pct = (dist_b / dist_a) * 100
                    # Clamp between 0 and 100
                    loss_pct = max(0, min(100, loss_pct))
                    
                    # Store purely the tooth number integer as string or the full key
                    tooth_id = tooth_key.replace("tooth_", "")
                    bone_loss_metrics[f"tooth_{tooth_id}"] = round(loss_pct, 2)
                    
        return bone_loss_metrics

    def calculate_progression_velocity(self, previous_loss_metrics, current_loss_metrics, time_difference_years):
        """
        Calculates progression velocity in % per year.
        Formula: (Current - Previous) / TimeDifference
        """
        velocities = {}
        
        if time_difference_years <= 0:
            return velocities
            
        for tooth_key, current_loss in current_loss_metrics.items():
            if tooth_key in previous_loss_metrics:
                prev_loss = previous_loss_metrics[tooth_key]
                
                # Velocity: positive means deterioration (more loss)
                velocity = (current_loss - prev_loss) / time_difference_years
                velocities[tooth_key] = round(velocity, 2)
                
        return velocities
