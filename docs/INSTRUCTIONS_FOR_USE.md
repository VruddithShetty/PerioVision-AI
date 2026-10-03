# PerioVision AI: Instructions for Use

Read this before using PerioVision AI with patients. Numbers quoted here come from `docs/MODEL_CARD.md` and `docs/VERIFICATION_REPORT.md` (measured 2026-10-02); the live values are always on the **Model trust** page.

## 1. Intended use
PerioVision AI supports qualified dental professionals who are reviewing **dental radiographs**. For each tooth it can locate, it suggests radiographic bone loss, a periodontitis stage and grade (2017 AAP/EFP classification), the change since an earlier radiograph, and a relative risk score.

**It is decision support, not a diagnosis.** Every result must be reviewed by a dentist, who makes and owns every clinical decision. Do not use it without clinician oversight, as the only basis for treatment, or for anything other than periodontal bone-level assessment.

**Status:** not cleared or approved by any medical-device regulator.

## 2. Users
Dentists (review and sign-off), dental technicians (upload), auditors (security and audit review) and administrators (accounts). In live mode, dentists and administrators must set up multi-factor authentication before they can use the system.

## 3. Supported images

| Image | Support |
|---|---|
| **Periapical radiographs** | Validated. Bone-loss error averages 7.4 percentage points (median 5.0); the stage matches the specialist label for 73 % of teeth. |
| Panoramic radiographs | Teeth are detected and numbered (FDI). **No per-tooth bone-loss numbers** (not accurate enough on panoramic films). Instead a **whole-film estimate** for the patient: generalised bone loss suggested yes / no for each jaw (test AUC 0.85 / 0.87) and the worst tooth's bone loss with a 90 % range (average error 11 points, stage agreement 69 %; it underestimates very severe cases). Take periapical films of the teeth you want measured. |
| Bitewings, CBCT, intra-oral photos, other X-rays | Not supported. Images with no detectable teeth are rejected. |
| File types | PNG, JPEG or DICOM (.dcm), up to 16 MB. Identifying DICOM tags and image metadata are removed on upload. |
| Quality | Images that are too small, blurred or flat are rejected. Borderline images are flagged for review. |

## 4. Reading the results
- **Bone loss %:** the crest's position between the CEJ and the root apex, as a percentage of root length. It is shown in mm only when the image carries DICOM pixel spacing.
- **Interval and stage set:** the true value lies inside the shown interval for about 90 % of teeth (measured 92.2 % on held-out data). The interval is on average ±19 points: narrower (about ±14) where the model reads the tooth consistently, and wider (±40 or more) where its normal and mirrored readings disagree. If more than one stage fits inside it, the stage cannot be decided from the image and the case goes to review. That is the usual outcome, by design.
- **"Not measured":** the landmark model could not place the CEJ, crest and apex on that tooth. No number is shown. **Assess the tooth clinically.**
- **Progression:** shown as a real change only when both radiographs are the same type, register to each other, and the change is larger than both readings' intervals combined (typically 30–40 points). Otherwise it reads "no change beyond measurement error" or "unreliable comparison". Small real changes over one or two years are usually **not** detectable from radiographs with this accuracy, so rely on clinical charting for them.
- **Grade:** taken from measured progression when available, otherwise from bone loss ÷ age, raised by smoking or HbA1c as in the 2017 classification.
- **Clinical risk profile:** the share of US adults with the same age, sex, smoking and diabetes / HbA1c profile who have moderate or severe periodontitis. It comes from a model trained on the CDC's NHANES survey and validated on a later survey cycle (AUC 0.65: a moderate risk indicator, not a diagnosis). It ignores the radiograph and does not predict progression. It is not shown when age, sex or smoking information is missing.
- **Grad-CAM heatmap and "attention outside periodontal area":** show where the model looked. Attention outside the bone-level band sends the case to review.

## 5. Mandatory review
A case cannot become a signed report until a dentist approves, corrects or rejects it whenever any of these apply:

- more than one possible stage
- uncalibrated uncertainty
- borderline image quality or an unusual image
- attention outside the periodontal area
- unmeasured teeth
- landmarks used on an unvalidated image type
- low detection confidence
- demo mode

A dentist's corrections are printed in the signed report next to the model's values.

## 6. Warnings
- Radiographic bone loss is a proxy for clinical attachment loss. Always confirm with probing; the perio chart shows where the two disagree.
- Stage IV needs the clinician-entered number of teeth lost to periodontitis.
- The models were trained on small public datasets (DENTEX, DenPAR) with an unknown demographic mix. Performance on other populations, sensors or exposure settings is unknown.
- **Demo mode** ("Demo mode — synthetic data, not clinical" banner) uses an in-memory database and synthetic patients. Never use it for real patients.

## 7. Security responsibilities of the clinic
- Run the production configuration (`docs/DEPLOYMENT.md`) behind an HTTPS reverse proxy, with MongoDB authentication and fresh keys.
- Keep the private signing key and `.env.production` off shared drives. Rotate keys as described in `docs/KEY_ROTATION.md`.
- An auditor should run **Security center → Verify chain** regularly. Investigate any `MODEL_LOAD_REFUSED`, `HONEYPOT_TRIGGERED` or tamper alert.

## 8. Checking the system yourself
From `backend/`:

```bash
python -m pytest -q
```
```bash
python -m pytest tests_live -q
```

To re-measure accuracy on any labelled split:

```bash
python scripts/evaluate_landmarks.py --images <images> --labels <labels> --out <file>
```
