import os
import json
import joblib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, cohen_kappa_score, classification_report
from sklearn.metrics import confusion_matrix, roc_auc_score
from sklearn.calibration import CalibratedClassifierCV, calibration_curve

# Ensure directories exist
MODEL_DIR = 'weights/risk_model'
os.makedirs(MODEL_DIR, exist_ok=True)

# 1. Dataset Generation
print("Generating synthetic clinical dataset...")
np.random.seed(2024)
N = 5000

# Generate realistic distributions
current_bone_loss = np.random.beta(2, 5, N) * 100
velocity = np.clip(np.random.exponential(2, N), 0, 15)
age = np.clip(np.random.normal(45, 15, N), 18, 90)
tooth_pos = np.random.randint(1, 33, N)
years = np.random.uniform(0.5, 10, N)

noise = np.random.normal(0, 2, N)
prev_bone_loss = np.clip(current_bone_loss - (velocity * years) + noise, 0, 100)

labels = []
for i in range(N):
    cbl = current_bone_loss[i]
    v = velocity[i]
    
    if cbl > 35 or v > 6 or (cbl > 25 and v > 3):
        labels.append('High')
    elif cbl < 15 and v < 1.5:
        labels.append('Low')
    else:
        labels.append('Medium')

X = pd.DataFrame({
    'current_bone_loss_pct': current_bone_loss,
    'progression_velocity': velocity,
    'patient_age': age,
    'tooth_position_code': tooth_pos,
    'prev_bone_loss_pct': prev_bone_loss,
    'years_of_longitudinal_data': years
})
y = np.array(labels)
label_names = ['Low', 'Medium', 'High']

# 2. Train-Test Split (80/20 Stratified)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.20, stratify=y, random_state=42)

# 3. Models to Train and Compare
models = {
    'GradientBoosting': Pipeline([
        ('scaler', StandardScaler()),
        ('clf', GradientBoostingClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, random_state=42))
    ]),
    'RandomForest': Pipeline([
        ('scaler', StandardScaler()),
        ('clf', RandomForestClassifier(n_estimators=200, max_depth=6, min_samples_leaf=5, random_state=42))
    ]),
    'LogisticRegression': Pipeline([
        ('scaler', StandardScaler()),
        ('clf', LogisticRegression(C=1.0, multi_class='multinomial', max_iter=1000, random_state=42))
    ])
}

# 4. Evaluation
report_file = os.path.join(MODEL_DIR, '../risk_model_report.txt')
if os.path.exists(report_file):
    report_file = os.path.join(MODEL_DIR, 'risk_model_report.txt')

best_model_name = None
best_model = None
best_f1 = -1

with open(report_file, 'w') as f:
    f.write("=== CLINICAL RISK PREDICTION MODEL VALIDATION REPORT ===\n\n")
    
    for name, pipeline in models.items():
        print(f"Training {name}...")
        pipeline.fit(X_train, y_train)
        y_pred = pipeline.predict(X_test)
        y_proba = pipeline.predict_proba(X_test)
        
        acc = accuracy_score(y_test, y_pred)
        w_f1 = f1_score(y_test, y_pred, average='weighted')
        kappa = cohen_kappa_score(y_test, y_pred)
        
        # ROC AUC
        roc_auc = roc_auc_score(pd.get_dummies(y_test), y_proba, multi_class='ovr')
        
        f.write(f"MODEL: {name}\n")
        f.write("-" * 50 + "\n")
        f.write(f"Accuracy:      {acc:.4f}\n")
        f.write(f"Weighted F1:   {w_f1:.4f}\n")
        f.write(f"Cohen's Kappa: {kappa:.4f}\n")
        f.write(f"ROC-AUC (ovr): {roc_auc:.4f}\n\n")
        
        f.write("Classification Report:\n")
        f.write(classification_report(y_test, y_pred))
        f.write("\nConfusion Matrix:\n")
        f.write(np.array2string(confusion_matrix(y_test, y_pred, labels=label_names)))
        f.write("\n" + "=" * 50 + "\n\n")
        
        if w_f1 > best_f1:
            best_f1 = w_f1
            best_model_name = name
            best_model = pipeline

print(f"\nBest Model: {best_model_name} with Weighted F1: {best_f1:.4f}")

# 5. Selection Requirement
if best_f1 < 0.88:
    raise ValueError(f"Best model ({best_model_name}) failed to meet the minimum clinical requirement. Weighted F1: {best_f1:.4f} < 0.88")

# 6. Feature Importance
try:
    classifier = best_model.named_steps['clf']
    if hasattr(classifier, 'feature_importances_'):
        importances = classifier.feature_importances_
    elif hasattr(classifier, 'coef_'):
        importances = np.mean(np.abs(classifier.coef_), axis=0)
    else:
        importances = np.zeros(X.shape[1])
        
    indices = np.argsort(importances)[::-1]
    sorted_features = [X.columns[i] for i in indices]
    
    plt.figure(figsize=(10, 6))
    plt.title(f"Feature Importances ({best_model_name})")
    plt.bar(range(X.shape[1]), importances[indices], align="center", color='teal')
    plt.xticks(range(X.shape[1]), sorted_features, rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig(os.path.join(MODEL_DIR, 'feature_importance.png'))
    plt.close()
    print("Saved feature importance chart.")
except Exception as e:
    print(f"Could not generate feature importance plot: {e}")

# 7. Calibration
print("Calibrating best model...")
calibrated_model = CalibratedClassifierCV(best_model, cv=5, method='sigmoid')
calibrated_model.fit(X_train, y_train)

# Plot reliability diagram (calibration curve)
# Note: calibration_curve supports binary, so we'll do One-vs-Rest for the 'High' class
y_test_binary = (y_test == 'High').astype(int)
y_prob_calibrated = calibrated_model.predict_proba(X_test)[:, list(calibrated_model.classes_).index('High')]
y_prob_uncalibrated = best_model.predict_proba(X_test)[:, list(best_model.classes_).index('High')]

prob_true_cal, prob_pred_cal = calibration_curve(y_test_binary, y_prob_calibrated, n_bins=10)
prob_true_uncal, prob_pred_uncal = calibration_curve(y_test_binary, y_prob_uncalibrated, n_bins=10)

plt.figure(figsize=(8, 8))
plt.plot([0, 1], [0, 1], "k:", label="Perfectly calibrated")
plt.plot(prob_pred_cal, prob_true_cal, "s-", label=f"Calibrated ({best_model_name})", color='teal')
plt.plot(prob_pred_uncal, prob_true_uncal, "s-", label=f"Uncalibrated ({best_model_name})", color='orange')
plt.ylabel("Fraction of positives")
plt.xlabel("Mean predicted probability")
plt.title("Reliability Diagram (Class: High Risk)")
plt.legend(loc="lower right")
plt.grid(True, alpha=0.3)
plt.savefig(os.path.join(MODEL_DIR, 'calibration_plot.png'))
plt.close()
print("Saved calibration reliability diagram.")

# 8. Cross-Validation
print("Running 10-fold Stratified K-Fold Cross Validation...")
cv = StratifiedKFold(n_splits=10, shuffle=True, random_state=42)
cv_scores = cross_val_score(best_model, X, y, cv=cv, scoring='accuracy')
mean_acc = np.mean(cv_scores)
std_acc = np.std(cv_scores)

print(f"CV Accuracy: {mean_acc:.4f} ± {std_acc:.4f}")
if mean_acc <= 0.88:
    raise ValueError(f"Cross-validation mean accuracy {mean_acc:.4f} failed to exceed 0.88 threshold.")

# 9. Saving Model & Metadata
model_path = os.path.join(MODEL_DIR, 'risk_model.pkl')
joblib.dump(calibrated_model, model_path)
print(f"Saved calibrated model to {model_path}")

metadata = {
    'feature_names': list(X.columns),
    'label_names': label_names,
    'threshold_high': 0.5, # Default thresholds for calibrated probabilities
    'threshold_low': 0.5
}
with open(os.path.join(MODEL_DIR, 'model_metadata.json'), 'w') as f:
    json.dump(metadata, f, indent=4)
print("Saved model metadata.")

print("\n--- Training & Validation Complete ---")
