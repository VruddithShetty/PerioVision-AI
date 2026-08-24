import os
import joblib
import pandas as pd
import numpy as np
import datetime
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from security.integrity import ModelIntegrityVerifier

class RiskPredictor:
    """
    Predicts tooth loss risk based on longitudinal bone loss trends 
    and clinical patient data.
    """
    
    def __init__(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.model_dir = os.path.join(base_dir, "..", "storage", "models", "risk_model")
        os.makedirs(self.model_dir, exist_ok=True)
        self.model_path = os.path.join(self.model_dir, "risk_model.pkl")
        
        self.class_mapping = {0: "Low", 1: "Medium", 2: "High"}
        self.verifier = ModelIntegrityVerifier()
        
        if os.path.exists(self.model_path):
            try:
                self.model = self.verifier.safe_load_sklearn_model(self.model_path)
            except Exception:
                self._train_initial_model()
        else:
            self._train_initial_model()

    def _train_initial_model(self):
        """Trains a starter GBM model on synthetic data."""
        # Synthetic data generation logic...
        X = np.random.rand(100, 6)
        y = np.random.randint(0, 3, 100)
        self.model = GradientBoostingClassifier(n_estimators=100)
        self.model.fit(X, y)
        joblib.dump(self.model, self.model_path)
        self.verifier.sign_model(self.model_path)

    def predict_tooth_risk(self, features_dict):
        """
        Calculates risk for a single tooth.
        """
        # Feature extraction and model inference...
        X_in = np.array([[
            features_dict.get("current_bl", 0) or features_dict.get("mean_bone_loss_pct", 0),
            features_dict.get("velocity", 0) or features_dict.get("calc_velocity", 0),
            features_dict.get("age", 40),
            features_dict.get("pos", 11) or features_dict.get("max_bone_loss_pct", 0),
            features_dict.get("prev_bl", 0),
            features_dict.get("years", 1)
        ]])
        
        idx = int(self.model.predict(X_in)[0])
        probs = self.model.predict_proba(X_in)[0]
        
        return {
            "level": self.class_mapping[idx],
            "confidence": float(np.max(probs)),
            "probabilities": {self.class_mapping[i]: float(probs[i]) for i in range(3)}
        }

    def predict_risk(self, features_dict):
        res = self.predict_tooth_risk(features_dict)
        return {
            "risk_level": res["level"],
            "confidence": res["confidence"],
            "probabilities": res["probabilities"]
        }

    def predict_risk_probabilities(self, features_dict):
        res = self.predict_tooth_risk(features_dict)
        probs = res["probabilities"]
        return [probs["Low"], probs["Medium"], probs["High"]]
