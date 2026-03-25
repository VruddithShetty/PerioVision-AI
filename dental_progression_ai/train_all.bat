@echo off
echo ===================================================
echo Starting High Accuracy Pipeline (100 Epochs each)
echo ===================================================

echo [1/2] Training Custom Landmark Model (Pose)...
python train_models.py --train-pose

echo [2/2] Training Custom Bone Segmentation Model (Seg)...
python train_models.py --train-seg

echo ===================================================
echo Training Complete! Models saved to project root.
echo ===================================================
