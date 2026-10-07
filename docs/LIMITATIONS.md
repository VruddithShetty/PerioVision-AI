# Limitations, what was done about each, and what closes it

_Last reviewed 2026-10-06. Every number links to a re-runnable file; CIs are in `docs/RESULTS_WITH_CI.md`._

PerioVision is **decision support, not a diagnostic device, and not clinically validated**. Each limitation below
has one of three statuses:

- **FIXED**: the problem was in the project and is corrected, with a regression test.
- **MEASURED**: the limitation is real and cannot be removed with the available data; its size is now measured
  and the app and the text are designed around it.
- **NEEDS DATA**: closing it needs data that does not exist in this project yet; the tooling is ready, so it
  takes one command once the data exists.

| # | Concern | Status |
|---|---|---|
| 1 | Bone loss never tested outside DenPAR | NEEDS DATA (tooling ready) |
| 2 | Reference labels partly produced by our own conversion code | FIXED (a real bug was found) + MEASURED |
| 3 | Stage II is staged correctly only about half of the time | MEASURED |
| 4 | Uncertainty intervals too wide to give a single stage | MEASURED (by design) |
| 5 | Per-tooth progression between visits | FIXED (design: 0 → 84 % of 20-point changes detected) + MEASURED + NEEDS DATA |
| 6 | Landmarks looked 18-20 % off | FIXED (the metric was wrong; real error 4-10 %) |
| 7 | Clinical risk model is weak (AUC 0.65) | MEASURED (role limited by design) |
| 8 | Some numbers could be read as better than they are | FIXED (wording, labels per test type) |
| 9 | Patient overlap unverifiable; no human-agreement baseline | MEASURED + NEEDS DATA (tooling ready) |
| 10 | App refusing good films or failing under load | FIXED (quality gate re-calibrated; model calls serialised) |

## 1. External test of periapical bone loss (NEEDS DATA)

**Problem.** Every periapical number comes from DenPAR's own test split (same source as training). The detector lost
about 5 points at a new hospital, so a drop is likely for bone loss too.

**Done.** A second public periapical dataset with the same kind of labels was found: **perio-KPT**
(Zenodo [10.5281/zenodo.14711842](https://zenodo.org/records/14711842), 192 periapical films from Peru, the UK and
India, CEJ and bone level on the mesial and distal side, root limits; CC BY-NC-SA 2.0, fine for a thesis). Downloads
need an access request from a university account. `scripts/convert_periokpt.py` turns its labels into PerioVision
references (worst site, same rule as DenPAR) and **checks the keypoint order on the data** before anything is scored
(test: `tests/test_convert_periokpt.py`).

**Closes with.** (1) Request access on the Zenodo page with your university e-mail. (2) Then:

```bash
python scripts/convert_periokpt.py --images <perio-KPT>/0_Baseline/images --labels <perio-KPT>/0_Baseline/labels --out ~/Downloads/periokpt_ref
DB_MODE=demo python scripts/evaluate_landmarks.py --images ~/Downloads/periokpt_ref/images --labels ~/Downloads/periokpt_ref/labels --out ../docs/evidence/periokpt_external_eval.json --per-tooth-csv ../docs/evidence/predictions/periokpt_external_per_tooth.csv
```

Report the result whatever it is: a drop on external data is expected and is itself a finding.

## 2. Reference labels (FIXED + MEASURED)

**Problem.** DenPAR provides loose CEJ points, apex points and bone-level lines; `convert_denpar.py` assigns them to
teeth and picks each tooth's crest and worst site.

**Found and fixed.** When a tooth had a single annotated CEJ, the converter could take the crest from the *other* side
of the tooth: 11.1 % / 13.9 % / 10.2 % of train / val / test teeth. The crest now comes from the CEJ's own side
(3 / 5 / 4 borderline teeth remain). Regression test: `tests/test_convert_denpar.py` fails on the old code.
All periapical numbers were re-measured on the corrected reference (bone-loss error 6.64 points, stage agreement
75.9 %) and the uncertainty was recalibrated on it.

**Measured.** With the fix in place, changing the conversion distance (15 / 25 / 35 px) moves the reference bone loss
by 0.3-0.4 points on average and changes the stage of about 2 % of teeth, so the reference is set by the
specialists' annotations, not by tuning.

**Still open.** No dentist has looked at the converted labels. `python -m research.make_review_set --mode label-check`
builds a 60-tooth pack (20 per stage) with the reference points drawn on; a dentist marks each as right or wrong
(about 30 minutes). The share marked wrong is the label error rate.

## 3. Stage II (MEASURED)

Stage recall on the corrected reference: stage I 85.4 %, **stage II 52.1 %** (95 % CI 43-61), stage III 81.7 %.
Severe teeth called stage I: **0.9 %** (1 of 115). The stage II band is 18 points wide and the typical error is about
6 points, so many stage II teeth sit near a boundary. A bias correction fitted on validation was tested and **rejected**:
on split halves of validation it made the error worse, and its stage gains only traded stage I recall for stage II / III.
How the app copes: every tooth carries a stage *set* from the calibrated interval (e.g. "II or III"), not a single
stage, and any set with more than one stage goes to dentist review. The instructions for use say to treat a stage II
suggestion as "check clinically".

## 4. Interval width (MEASURED, by design)

At the 90 % level the intervals cover 92.8 % of test teeth (86.1 % of severe teeth), with a mean width of about 39
points; 7.6 % of teeth get a single-stage set. Narrower intervals would only be honest with a more accurate model.
The app does not hide this: wide intervals send the case to a dentist rather than guessing. This is the intended
behaviour of a decision-support tool whose error is the size of a stage band.

## 5. Progression (FIXED + MEASURED + NEEDS DATA)

**Found and fixed (2026-10-07, `docs/PROGRESSION.md`).** The old rule required a change larger than both visits'
accuracy intervals (about 39 points), although a tooth's constant offset cancels between visits; on 303 simulated
changes it detected none. Changes are now compared side with side against a repeatability threshold (4.6 / 6.2
points) calibrated on validation re-takes, and registration accepts 99 % of realistic re-takes (was 79.5 %) with
0 of 300 different-patient pairs accepted. Tests: `tests/test_progression_paired.py`, `tests/test_registration_fallback.py`.

**Measured (bench, test films).** Specificity on unchanged re-takes 94.9 % (91.4-97.1); sensitivity 12 / 39 / 66 /
84 % for simulated losses of 5 / 10 / 15 / 20 points of root length. 90 % sensitivity is not reached: the landmark
model follows only about half of a simulated crest shift. For comparison, the only published multicentre study of
direct progression detection on real serial radiographs reports 79.5 % accuracy and 69 % sensitivity.

**Still open.** No real follow-up radiographs have been tested. **Closes with** 20-50 real pairs of the same patient's
films taken months apart: `python scripts/evaluate_registration.py --pairs pairs.csv`, then the bench summary on them.
In the thesis, describe progression as "detects large changes with a 5 % false-alarm rate on a simulation bench",
not "tracks slow progression".

## 6. Landmark error (FIXED: the metric was misleading)

The 18-21 % CEJ / crest error compared predictions with the worst site, which is often on the other side of the
tooth. Against the annotated point on the same side, the two-site model's errors are **CEJ 6.2 %, crest 10.3 %, apex
4.5 %** of root length (medians 4.3 / 5.6 / 3.5 %). The app draws the points of the side it measured.

## 7. Clinical risk model (MEASURED, role limited by design)

AUC 0.650 (0.633-0.668) on a later NHANES cycle; Brier 0.226 against 0.240 for the base rate; predictions run 4-10
points high on that cycle. Its role in the app is limited on purpose: the combined risk level is the **higher** of the
clinical level and the radiograph's measured stage, so the clinical model can add a warning but can never hide what
the radiograph shows. It does not change stage or grade (grade modifiers follow the 2017 AAP/EFP rules directly). In
the thesis, present it as context from routinely recorded factors, not as a predictor.

## 8. Numbers that could be over-read (FIXED)

Every row in `docs/RESULTS_WITH_CI.md` now names its test type (same-source held-out, same-hospital held-out,
cross-source external, temporal hold-out). In particular:
- The panoramic external AUC 0.96 on PDCNN films separates periodontitis films from non-periodontitis films. It is not
  a severity result.
- The deployed detector's 94.5 % is on unseen films from the hospital it was fine-tuned on. The only different-hospital
  detector number is 89.6 % (previous detector).
- Small samples are flagged (96 films, 149 patients).

## 9. Patient overlap and human agreement (MEASURED + NEEDS DATA)

DenPAR, DENTEX and MM-OPG publish no patient IDs. Pixel-identical and near-identical films across splits were searched
for (`research.split_audit`); the 5 DenPAR films found are excluded from every reported test number. Two different
films of the same patient cannot be ruled out without IDs; BRAR (one film per patient) and NHANES (separate survey
cycles) are verified patient-level.

**Human baseline.** `python -m research.make_review_set --mode blind` builds a 60-tooth blind pack. Two dentists grade
it independently, then `python -m research.agreement --csv ratings.csv` reports dentist-vs-dentist and model-vs-dentist
agreement with CIs and says whether the model falls inside the human range. About 30 minutes per dentist.

## 10. Robustness of the running app (FIXED, 2026-10-07)

Found while pushing 300 real films through the app's API to build demonstration sets:

- **The quality gate refused good periapical films.** Its blur limit (sharpness < 10) had been set on panoramic films.
  It refused 4.5 % of real DenPAR test films (5.8 % of training films), although the model's bone-loss error on
  exactly those films was lower than average (3.9 vs 6.8 points). The reject limit is now 3: every one of the 1,000
  real DenPAR films passes, films blurred with sigma >= 6 (sharpness <= 3.4) are still refused, and anything between
  3 and 25 still gets the blur warning and goes to review. Test: `tests/test_quality_gate_periapical.py`.
- **Two model calls at once could crash.** The start-up self-check ran a model in a background thread while the first
  analysis used the same model; YOLO models are not thread-safe, and the self-check failed with a tensor-size
  mismatch (the same could happen with two simultaneous analyses on the threaded development server). All model
  calls now hold one lock (`app/ml/inference_lock.py`). Test: `tests/test_model_lock.py`.

## What is fully in place

- 139 unit tests and 34 live tests on the real models pass; every weight, calibration and metrics file is signed and
  checked at start-up.
- A retrain on the corrected labels is ready: `notebooks/train_landmarks_v3_colab.ipynb`. It compares itself
  against the deployed model on the same films and installs nothing unless the difference is real.
