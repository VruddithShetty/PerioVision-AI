class TALPAEngine:
    """
    Temporal Analysis of Longitudinal Periodontal Attachment (TALPA) Engine.
    Implements the 2017 AAP/EFP Periodontal Grading criteria (A, B, C).
    """
    
    @staticmethod
    def compute_grade(bone_loss_pct: float, age: int, velocity_per_year: float = None) -> str:
        """
        Computes the AAP/EFP Grade.
        Uses Direct Evidence if velocity_per_year is available.
        Uses Indirect Evidence (% bone loss / age) if no historical velocity exists.
        """
        if velocity_per_year is not None:
            # DIRECT EVIDENCE: 5-year progression
            five_year_loss = velocity_per_year * 5
            
            # Map 2mm to approx 10% bone loss for root length equivalency
            if five_year_loss <= 0:
                return "Grade A"
            elif 0 < five_year_loss < 10.0:
                return "Grade B"
            else:
                return "Grade C"
        else:
            # INDIRECT EVIDENCE: % bone loss / age
            if age <= 0:
                age = 1  # prevent division by zero
                
            ratio = bone_loss_pct / age
            
            if ratio < 0.25:
                return "Grade A"
            elif 0.25 <= ratio <= 1.0:
                return "Grade B"
            else:
                return "Grade C"
