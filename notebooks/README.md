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

## train_landmarks_twosite_colab.ipynb

Trained the **deployed** two-site landmark model on DenPAR (CC BY 4.0): CEJ and bone crest on both sides of each
tooth plus the apex. Kept as the record of how the deployed model was made.

## train_landmarks_v3_colab.ipynb

The **next** landmark models, on the corrected labels: up to three models (large / medium, 1280 / 1024 px), each
resumable across sessions, plus their ensemble. Chooses on validation films, compares against the deployed model on
the same test teeth and exports to `MyDrive/PerioVision/export_v3/`. Needs the deployed model in
`MyDrive/PerioVision/current/`.

## priority1_eval_colab.ipynb

Evaluation only (no training): DENTEX and MM-OPG split audits and per-film predictions for confidence intervals.

## train_panoramic_colab.ipynb

Trains the panoramic models on open data it downloads itself: a per-jaw bone-loss screen (ToothXpert MM-OPG,
~9,200 films), worst-tooth bone loss and stage (BRAR, 988 films), a per-tooth bone-loss detector (PDCNN,
1,747 films; evaluated and not adopted) and a fine-tune of the tooth detector (Aga Khan OPG;
deployed, also as `train_panoramic_D_colab.ipynb`). Every model is tested on held-out
films; results go to `MyDrive/PerioVision/export_panoramic/`. After editing the scripts it embeds, regenerate it
with `python backend/scripts/build_panoramic_notebook.py`.
