# notebooks

Exploratory analysis and experiments only. Nothing in this folder is imported by the app.

## train_periovision_colab.ipynb

One-click training on a free Google Colab GPU. Open it in Colab (File > Upload notebook), choose Runtime > Change runtime type > T4 GPU, then Runtime > Run all. It downloads the public DENTEX dataset inside Colab, trains the FDI tooth detector with a fixed train/val/test split, reports test-set metrics, and saves everything to `MyDrive/PerioVision/export/`. Bring that folder back with `.\run.ps1 install-models -From <folder>`, which backs up the old weights, installs and signs the new ones, and runs the tests.

## train_landmarks_colab.ipynb

One-click training of the CEJ / root-apex / bone-crest landmark model on the open DenPAR periapical dataset (CC BY 4.0), downloaded inside Colab. It reports bone-loss error and stage agreement on the DenPAR test split, and writes `conformal_calibration.json` (calibrated on the validation split, coverage measured on the test split). Install the results with `.un.ps1 install-models -From <folder>`.
