# notebooks

One-click training on a free Google Colab GPU. Nothing in this folder is imported by the app; each notebook
downloads its own data and writes its weights plus held-out test metrics to Google Drive.

**How to run any of them:** in Colab choose File > Upload notebook, then Runtime > Change runtime type > T4 GPU,
then Runtime > Run all. If Colab disconnects, Run all again: finished steps are skipped and training resumes.

## train_periovision_colab.ipynb

Trains the FDI tooth detector on the public DENTEX dataset with a fixed train / val / test split, reports
test-set metrics, and saves everything to `MyDrive/PerioVision/export/`. Bring that folder back with
`.\run.ps1 install-models -From <folder>`, which backs up the old weights, installs and signs the new ones, and
runs the tests.

## train_landmarks_colab.ipynb

Trains the CEJ / root-apex / bone-crest landmark model on the open DenPAR periapical dataset (CC BY 4.0). It
reports bone-loss error and stage agreement on the DenPAR test split and writes `conformal_calibration.json`
(calibrated on the validation split, coverage measured on the test split). Install the results with
`.\run.ps1 install-models -From <folder>`.

## train_panoramic_colab.ipynb

Trains the panoramic models on open data it downloads itself: a per-jaw bone-loss screen (ToothXpert MM-OPG,
~9,200 films), worst-tooth bone loss and stage (BRAR, 988 films), a per-tooth bone-loss detector (PDCNN,
1,747 films) and an optional fine-tune of the tooth detector (Aga Khan OPG). Every model is tested on held-out
films; results go to `MyDrive/PerioVision/export_panoramic/`. After editing the scripts it embeds, regenerate it
with `python backend/scripts/build_panoramic_notebook.py`.
