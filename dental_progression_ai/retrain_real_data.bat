@echo off
echo =====================================================
echo  PerioVision AI — Real Dataset Download and Retrain
echo =====================================================
echo.
echo STEP 1: Installing required packages...
pip install roboflow kaggle --quiet

echo.
echo STEP 2: Enter your Roboflow API key below
echo  (Get one FREE at https://app.roboflow.com ^> Settings ^> API Keys)
echo.
set /p RF_KEY="Roboflow API Key: "

echo.
echo STEP 3: Downloading real dental datasets from Roboflow Universe...
python download_and_retrain.py --source roboflow --rf-key %RF_KEY% --download-only

echo.
echo STEP 4: Starting retraining on real data (this will take 2-6 hours on CPU)...
echo  Tip: You can run this overnight. Models auto-save on completion.
python download_and_retrain.py --retrain-only --epochs 150 --batch 8

echo.
echo =====================================================
echo  Training complete! Models saved to project root.
echo  Restart the Streamlit app: streamlit run web_app/streamlit_app.py
echo =====================================================
pause
