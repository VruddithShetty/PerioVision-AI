# Data splits, leakage checks and the external test set

_Priority 1, items 1 and 3. Written 2026-10-04. Raw outputs are in `docs/evidence/split_audit_*.json`. Re-run
everything with the commands at the end._

## Why this matters

If the same patient (or the same film) is in both training and test, the test score measures memory, not
generalisation. The check has to be done at **patient** level, because one patient can have several films.
Most public dental datasets do not publish patient IDs. Where they don't, the best available check is to look
for the same film appearing twice (pixel-identical or re-exported copies). That catches duplicated films, but
it **cannot** catch two different films of the same patient. This limit is stated for each dataset below.

## Per dataset

| Dataset (task) | Split used | Patient IDs? | Patient-overlap check | Duplicate-film check | Verdict |
|---|---|---|---|---|---|
| **BRAR** (panoramic worst-tooth bone loss) | 70 / 15 / 15, seed 0, stratified by level: **690 / 149 / 149 films** | Yes: one film per patient (`patient_image_<n>`) | **PASS**: 988 patients, max 1 film each, 0 shared across splits | **PASS**: 0 identical; 69 look-alike candidates, 0 confirmed | Patient-level split, verified |
| **DenPAR** (periapical landmarks, bone loss, calibration) | Official split: 650 / 150 / 200 films (649 train after conversion) | **No** | Unverifiable | **FAIL**: 5 films appear in two splits (below) | Small leak; test results reported with and without the 2 affected test films |
| **AKU** (external test of the detector) | External only: 250 films, 3 folders | No | Unverifiable | **PASS**: no duplicates inside AKU; 0 matches against the 30,602 team detection-training images (1,202 look-alike candidates, 0 confirmed) | Previous detector: never trained on it (different-hospital test). Deployed detector: fine-tuned on folders 1+3, folder 2 held out (same-hospital test) |
| **DENTEX** (detector training / test) | 508 / 63 / 63, seed 42 (split file on Google Drive) | No | Unverifiable | **PENDING**: Colab, `notebooks/priority1_eval_colab.ipynb` | Not yet checked |
| **MM-OPG** (panoramic screen) | Official train / test (450 test films); validation 894 films drawn from train | No | Unverifiable | **PENDING**: Colab, `notebooks/priority1_eval_colab.ipynb` (`images.zip` on this laptop is incomplete) | Not yet checked |
| **NHANES** (clinical risk) | Train 2009–2012 cycles, test 2013–14 cycle | Yes (SEQN) | **PASS by design**: each NHANES cycle samples different people | n/a (tabular) | Patient-level, temporal |

### DenPAR: films found in two splits

Found by `research.split_audit` (pixel-identical SHA-256, or identical at 128 px with correlation 1.0):

| Film A | Film B | Effect |
|---|---|---|
| train `164.jpg` | **test `166.jpg`** | A test film the model was trained on |
| val `853.jpg` | **test `852.jpg`** | A test film that also helped set the conformal interval |
| train `1029.jpg` | val `1028.jpg` | Validation (model selection, calibration) saw a training film |
| train `29.jpg` | val `158.jpg` | same |
| train `903.jpg` | val `899.jpg` | same |

There are also four duplicate pairs **inside** training (`1099/1100`, `1198/1217`, `1256/1257`, `2/4`). They
don't leak, but they give those films double weight.

This is a property of the published DenPAR split, not of this project's code. Two of 200 test films are
affected, so the effect on the headline numbers is small. `docs/RESULTS_WITH_CI.md` reports every DenPAR
metric both with and without the two films. **For the next training run**, drop `166.jpg` and `852.jpg` from
test and `1028`, `158`, `899` from validation (or move them to train), retrain, and recalibrate.

## External test set (AKU): documentation and "never used" evidence

| Item | Value | Source |
|---|---|---|
| Dataset | Aga Khan University OPG teeth segmentation & numbering, Zenodo 10.5281/zenodo.10538750, CC BY 4.0 | `docs/DATASETS.md` |
| Films | **250** (folder 1: 35, folder 2: 96, folder 3: 119) | counted 2026-10-04 |
| Reference teeth | **6,615** specialist-outlined teeth with FDI numbers | `detector_external_aku_all250_2026-10-04.json` |
| Patients | **Not published** in the archive; one film per patient cannot be confirmed. Check the Zenodo record / paper and fill in. | PLACEHOLDER |
| Site / device | Pakistan; Orthophos XG (per `docs/DATASETS.md`) | |

> **Update 2026-10-04 (later the same day).** The *deployed* detector is now fine-tuned on AKU folders 1 and 3
> (commit `0930bd2`). The evidence below holds for the **previous DENTEX-only detector** (`b73f30db…`, kept in
> `weights_backup/20261004-095323/`) and for its 89.6 % different-hospital result. For the deployed detector, AKU
> folder 2 (96 films) is a held-out test from the same hospital: no film in it duplicates a folder 1 or 3 film
> (`split_audit_aku_vs_team_detection.json` found no duplicates among all 250), but patients cannot be checked
> because AKU publishes no patient IDs.

Evidence that AKU was never used to train, tune or set thresholds for the **previous** detector:

1. **Timeline.** The deployed detector (`weights/dental_yolov8n.pt`, SHA-256 `b73f30db…71bb96`, matching the
   signed manifest) was written on 2026-09-30 05:42 and committed in `6416246`. The only code that trains on AKU
   (notebook D, `dental_yolov8n_aku.pt`) was added on 2026-10-03. Its output was never installed: the manifest
   holds no such file.
2. **Image overlap.** 0 of 250 AKU films match any of the 30,602 images in the team detection set that notebook
   cell 4b can add to training (`split_audit_aku_vs_team_detection.json`). DENTEX comes from a different
   institution and is checked in the Colab notebook.
3. **Thresholds.** The detector's `min_confidence: 0.25` in `config/thresholds.json` is unchanged since commit
   `1b61bc6` (2026-09-28), before any AKU work. It is also the value recorded with the DENTEX test metrics. The
   AKU result was committed in `a4985bd` together with threshold changes, but those changes concern only
   landmarks (`tta_mirror`, `measure_unvalidated_image_types`) and progression (`min_tooth_overlap`), not
   the detector. The IoU 0.5 match rule is the standard evaluation definition, not a tuned value.
4. **Apex check.** `panoramic_apex_aku` used the first 40 AKU films as an evaluation only. Nothing was fitted.

### Correction to the reported external number

The earlier external run reported **91.0 %** tooth-level F1 on **154** films. In the AKU archive, folder 2 names
its label folder `annnotations` (three n), so the script silently skipped those 96 films. With all **250** films
the deployed detector scores **89.6 %** (see `docs/RESULTS_WITH_CI.md` for the CI). Folder 2 is the hardest
(87.4 %). The script now reads both spellings, and `--folders "folder 1" "folder 3"` reproduces the old run.
Use the 250-film number from now on.

## How to make a patient-level split for new data

When a dataset **does** have patient IDs (for example a partner clinic's films), make the split by patient:

```bash
python -m research.split_audit make --manifest images.csv --out split.json --seed 0
```

`images.csv` needs columns `image,patient_id` and optionally `stratum` (e.g. severity level). All of a
patient's films go to one split, strata stay balanced, and the result is verified before it is written.

## Re-run the checks

From `backend/` on the laptop:

```bash
python -m research.split_audit audit --dataset brar --root ~/Downloads/BRAR/data --show-names --out ../docs/evidence/split_audit_brar.json
python -m research.split_audit audit --dataset denpar --root ~/Downloads/DenPAR/Dataset --show-names --out ../docs/evidence/split_audit_denpar.json
python -m research.split_audit audit --dataset folder --root ~/Downloads/OPG-AKU/Niihhaa-Dataset-4ac91db/dataset --against "yolo:~/Downloads/DP_datasets/datasets/detection" --out ../docs/evidence/split_audit_aku_vs_team_detection.json
```

Never use `--show-names` on the team detection set: its file names contain what look like personal names.
DENTEX and MM-OPG are checked in Colab: `notebooks/priority1_eval_colab.ipynb` (inference only, no training).
