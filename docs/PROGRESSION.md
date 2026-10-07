# Progression detection: method, evidence and limits

_2026-10-07. Raw results: `docs/evidence/progression_bench.json`, `docs/evidence/registration_bench.json`,
per-site rows in `docs/evidence/predictions/progression_{val,test}.csv`. Re-run commands at the end._

## The question

Between two periapical radiographs of the same patient, did a tooth lose bone? The difficulty is not measuring bone
loss once; it is telling a real change from the difference two measurements of an unchanged tooth would show anyway.

## What the literature says

- The only multicentre deep-learning study of progression on serial radiographs (panoramic, three university
  hospitals, 1,378 patients with films at least a year apart) reached **79.5 % accuracy, 69 % sensitivity and 90 %
  specificity** with direct (two-film) assessment. The ~90 % figure (89.6 %) that study reports is for the
  **indirect** estimate (bone loss / age), which is the AAP/EFP grade PerioVision already computes
  ([J Periodontal Implant Sci, 2025](https://jpis.org/DOIx.php?id=10.5051%2Fjpis.2504860243)).
- Digital subtraction radiography detects small bone changes far better than reading two films side by side, but it
  depends on reproducible projection geometry. Registration is "the biggest challenge" in that literature
  ([review](https://www.researchgate.net/publication/233748534_Literature_review_Digital_Subtraction_Radiography_in_Dentistry);
  [lesion detection in vitro](https://pubmed.ncbi.nlm.nih.gov/10863402/)).

So a validated 90 % for direct progression detection would be beyond the published state of the art, and it cannot
be claimed without real follow-up pairs with known change. What can be done is to remove the design limits, then
measure honestly what is left.

## What was wrong before (2026-10-06)

1. **The wrong noise.** A change counted only above the two visits' **accuracy** intervals added together (about
   2 × 19 = 39 points). Accuracy includes each tooth's constant offset from the specialist reference, which is the same
   at both visits and **cancels** in a difference. The noise that matters is **repeatability**. Result: on 303 simulated
   changes of 5-20 points, the old rule detected **0**.
2. **Worst-site switching.** The tooth's reported number is its worse side. If the worse side switches between visits,
   the number jumps without any bone change.
3. **Registration refused one in five re-takes.** A rotation + scale model cannot fit the slight shear of a different
   beam angle, so 20.5 % of realistic re-takes were declared "cannot compare".

## The new method (deployed)

1. **Same-site comparison.** The two-site landmark model measures both sides of every tooth. A tooth's change is
   measured side with side (left with left, right with right); worst-site switching cannot create a change.
2. **Repeatability threshold, calibrated on validation films only.** A side counts as changed when it moved by more
   than a threshold set at the 95th percentile of the largest per-site change on **unchanged** re-take pairs of
   validation films. Teeth whose mirrored readings agree closely at both visits are more repeatable and use a lower
   threshold; this two-band rule was fixed before the test results were looked at. Thresholds: **4.61 points**
   (mirrored-reading disagreement ≤ 3.52 points at both visits) and **6.15 points** otherwise
   (`backend/weights/progression_calibration.json`, signed; without it the app falls back to the old conservative rule).
3. **Registration with an affine fallback.** If rotation + scale fails only because matches disagree, a full affine fit
   is tried. It must pass every other check (inliers, scale, rotation, image correlation, tooth overlap) plus a new
   shear / stretch limit (≤ 1.15).
4. Everything else stays: same film type, a registration that lines up the teeth themselves, ≥ 30 days between
   visits, and only reliable, detectable changes may drive the grade, risk or recall interval.

## How it was tested

There is no public set of follow-up radiographs with known change, so the bench (`research/progression_bench.py`)
builds two kinds of pairs from DenPAR films with specialist bone-level labels, through the app's own code path:

- **No change:** the same film re-taken: rotation ±4°, scale ±7 %, shift, a slight projective tilt (different beam
  angle), exposure / gamma / contrast, sensor noise, blur and JPEG compression.
- **Known change:** the same, after **simulated bone loss** at one site of one tooth. The crest is moved apically by
  5, 10, 15 or 20 % of root length and the bone between the old and the new crest is replaced by soft-tissue density
  in a crater-shaped defect, keeping the film's grain and never painting over a tooth.

Calibration: 80 validation films (354 unchanged teeth). Test: 100 different test films (DenPAR test split, the 2
duplicated films excluded).

## Results (test films)

| | Old rule | **New rule** |
|---|---|---|
| Specificity, unchanged re-takes (no false alarm) | – | **94.9 %** (95 % CI 91.4-97.1), 237 teeth |
| Sensitivity, true change 5 points | 0 % | 12 % (7-22) |
| Sensitivity, 10 points | 0 % | 39 % (28-50) |
| Sensitivity, 15 points | 0 % | 66 % (55-76) |
| Sensitivity, 20 points | 0 % | **84 %** (74-90) |
| Re-takes that register (registration bench, 200 films) | 79.5 % | **99.0 %** (96.4-99.7) |
| Different patients wrongly registered (300 pairs) | 0 | **0** (95 % CI 0-1.3 %) |

Repeatability: the same site measured on an unchanged re-take moves by SD **2.7 points** (95 % of changes within
5.3 points). The old rule assumed a noise level about seven times larger.

Other teeth of films with a simulated defect show 85 % specificity. That is lower because the defect sits in the
interdental bone shared with the neighbouring tooth, so part of those "false alarms" are real changes in the
neighbour.

## What this does and does not show

- **Shown:** the detector is silent on about 95 % of unchanged teeth and catches most large changes (84 % at 20 points
  of root length, roughly 2.5-3 mm on an average root). The new design is far more sensitive than the old one at the
  same false-alarm level.
- **Not reached: 90 % sensitivity.** The landmark model registers only about half of a simulated change (a true
  20-point loss is measured as about 9.6 points on average), so small changes stay below the noise. This may be partly
  the simulation (a painted defect is not real disease) and partly the model.
- **Not shown: clinical accuracy.** Simulated lesions on re-taken films are a technical (bench) validation, as used in
  subtraction-radiography research. Real progression has other appearances (vertical defects, remodelled crest,
  changed angulation of the patient's own teeth).

**In the thesis:** "On a bench of simulated re-takes and simulated bone loss, the paired same-site detector kept a 95 %
specificity and detected 84 % of 20-point changes (66 % at 15, 39 % at 10). Clinical validation on real follow-up
radiographs is required." Do not write "90 % accurate progression detection".

## What would close the gap

1. **Real follow-up pairs** (the same patient, months or years apart), ideally 50+ pairs with a specialist's judgement
   of change. Then: `python scripts/evaluate_registration.py --pairs pairs.csv` (registration) and the bench's summary
   on those pairs. Sources: a partner clinic (de-identified, ethics approval) or PhysioNet's multimodal dental dataset
   (data-use agreement).
2. **A more sensitive landmark model:** the v3 models (larger, higher resolution, ensemble) on corrected labels
   (`notebooks/train_landmarks_v3_colab.ipynb`), then re-run the bench. Any gain in how fully the model follows
   a crest shift raises sensitivity directly.
3. **Patient-level progression:** AAP/EFP grading needs evidence of progression in the patient, not in one tooth.
   Combining several teeth lowers noise, but it needs real pairs to validate.

## Re-run

From `backend/` (CPU: about 1.5 h with two processes; resumable):

```bash
python -m research.progression_bench run --split val --films 80 --nochange 2 --out ../docs/evidence/predictions/progression_val.csv
python -m research.progression_bench run --split test --films 100 --nochange 1 --out ../docs/evidence/predictions/progression_test.csv
python -m research.progression_bench summary --val ../docs/evidence/predictions/progression_val.csv --test ../docs/evidence/predictions/progression_test.csv --out ../docs/evidence/progression_bench.json --write-calibration
python -m research.registration_bench --films 200 --negatives 300 --out ../docs/evidence/registration_bench.json
```
