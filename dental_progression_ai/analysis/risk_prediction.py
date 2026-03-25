import pandas as pd
from sklearn.ensemble import RandomForestClassifier

class RiskPredictor:
    def __init__(self):
        # A lightweight predictive Random Forest model. 
        # Since we optimize for CPU, Scikit-learn Random forest inference is negligible (<< 10ms)
        self.model = RandomForestClassifier(n_estimators=50, random_state=42)
        self._train_dummy_model()

    def _train_dummy_model(self):
        """
        Trains a small dummy model on simulated rules so that it operates 
        right out of the box without needing external pre-trained pickle files.
        Features: [Current Bone Loss, Progression Rate, Patient Age]
        Target: 0 (Low), 1 (Medium), 2 (High)
        """
        X = [
            [5.0, 0.5, 30],   # Healthy/slow -> Low
            [15.0, 1.0, 45],  # Mild/medium -> Low
            [30.0, 5.0, 50],  # Mod/fast -> Medium
            [45.0, 10.0, 60], # Severe/fast -> High
            [10.0, 0.2, 25],  # Low
            [25.0, 2.0, 55],  # Mod -> Medium
            [60.0, 2.0, 65],  # Severe -> High
            [35.0, 8.0, 35]   # Fast young -> High
        ]
        y = [0, 0, 1, 2, 0, 1, 2, 2]
        self.model.fit(X, y)
        
    def predict_risk(self, current_bone_loss, progression_rate, patient_age):
        """
        Predicts future bone deterioration risk class.
        """
        # Feature array
        X_test = pd.DataFrame([{
            "current_loss": current_bone_loss,
            "prog_rate": progression_rate,
            "age": patient_age
        }])
        
        prediction = self.model.predict(X_test)[0]
        
        mapping = {0: "Low Risk", 1: "Medium Risk", 2: "High Risk"}
        return mapping[prediction]

    def evaluate_all_teeth(self, progression_table, patient_age):
        predictions = {}
        for row in progression_table:
            tooth = row["Tooth"]
            current_loss = float(row.get("Current", 0))
            
            # Parse progression rate
            change_str = row.get("Change", "0")
            if "N/A" in change_str:
                change_val = 0.0
            else:
                change_val = float(change_str.replace('%', '').replace('+', ''))
                
            risk = self.predict_risk(current_loss, change_val, patient_age)
            predictions[tooth] = risk
        return predictions
