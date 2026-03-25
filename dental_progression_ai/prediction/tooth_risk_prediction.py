class ToothRiskPredictor:
    def __init__(self):
        # We simulate a lightweight model using heuristics or a pre-defined logic since it's a simple predictive layer
        # In a real scenario, this could load a scikit-learn RandomForestClassifier
        pass

    def predict_risk(self, current_bone_loss, progression_velocity, age=None, history_pattern=None):
        """
        Predicts future deterioration risk.
        Returns "Low Risk", "Medium Risk", or "High Risk".
        """
        # Feature heuristics
        # If bone loss is already severe (>50%), any progression is high risk.
        # If progression > 5% per year, it's fast -> high risk.
        # If progression > 2% per year -> medium risk.
        
        if current_bone_loss >= 50 or progression_velocity >= 5.0:
            return "High Risk"
        elif current_bone_loss >= 30 or progression_velocity >= 2.0:
            return "Medium Risk"
        else:
            return "Low Risk"

    def predict_all_teeth(self, bone_loss_metrics, velocity_metrics, patient_info=None):
        """
        Runs risk prediction on all teeth.
        """
        predictions = {}
        
        for tooth_key, current_loss in bone_loss_metrics.items():
            velocity = velocity_metrics.get(tooth_key, 0.0) # default 0 velocity if no history
            age = patient_info.get("age", 40) if patient_info else 40
            
            risk_level = self.predict_risk(current_loss, velocity, age)
            prompt_sentence = f"Tooth {tooth_key.replace('tooth_', '')} -> {risk_level} probability of severe bone loss based on current {current_loss}% loss and {velocity}%/yr progression."
            
            predictions[tooth_key] = {
                "risk_level": risk_level,
                "description": prompt_sentence
            }
            
        return predictions
