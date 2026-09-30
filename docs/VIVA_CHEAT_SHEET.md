# Viva cheat sheet: PerioVision AI

## The project in one breath

PerioVision is a secure, explainable decision-support system that measures periodontal bone loss on dental X-rays tooth by tooth, tracks it across visits, says honestly how sure it is, sends anything uncertain to a dentist, and protects every piece of data with encryption, signatures, strict access control and a tamper-evident audit trail.

## Each module in plain language

| Module | What it does, simply |
|---|---|
| Upload guard | Checks that a file really is an image (not a renamed virus), not too big, strips hidden patient data, and stores it encrypted under a random name. |
| Quality gate | Rejects or warns about blurry, flat or tiny X-rays before any AI runs. |
| CLAHE | Boosts local contrast so bone edges are easier to see. |
| Tooth detector (YOLOv8) | Draws a box around each tooth and names it with its FDI number (11–48). |
| Landmarks | Finds three points per tooth: the enamel-root junction (CEJ), the top of the bone (crest) and the root tip (apex). |
| Bone loss & staging | Bone loss % = how far the crest has dropped below the CEJ, as a share of root length. That gives Stage I–IV; the rate of change and risk factors give Grade A–C. |
| Grad-CAM | A heatmap of where the model "looked". If it looked away from the gum-bone area, the case is flagged. |
| Conformal prediction | Turns a single number into an honest range (e.g. 18–30 %) that contains the truth about 90 % of the time on held-out data. If the range spans two stages, a dentist must decide. |
| Review router | Collects every reason for doubt (uncertain stage, poor image, odd image, attention off-target, guessed landmarks, demo mode) and blocks reports until a dentist signs off. |
| Progression | Matches the same tooth across visits and computes how fast bone is being lost per year, but refuses to trust comparisons when the X-rays can't be lined up. |
| Risk fusion | Combines age, smoking, diabetes/HbA1c and image findings into low/moderate/high with plain-language reasons. Honestly labelled as a rule-assisted demo. |
| AES-256-GCM | Encrypts names, contacts, X-rays and reports. GCM also detects any tampering. A fresh random nonce every time. Keys can be rotated. |
| RSA-PSS signatures | Model files and reports are digitally signed. A changed model refuses to load; a changed report fails verification. |
| bcrypt + JWT + MFA | Passwords are slow-hashed; logins give a 15-minute token tied to your device; authenticator-app codes as a second factor. |
| RBAC + Zero Trust | Four roles with a permission table; every single request re-checks token, session, device, account and permission. Anything not explicitly allowed is denied. |
| Audit chain + Merkle | Every action is logged; each entry contains the hash of the previous one, and periodic Merkle roots are anchored outside the database. Any edit is detected and located. |
| Security Lab | Runs seven real attacks on throwaway copies and shows each one being blocked. |
| Chairside tools | Perio chart with probing-vs-X-ray concordance, EFP care plan, patient explainer, recall board. |

## Likely examiner questions

**Why AES-GCM and not AES-CBC?** GCM is authenticated: it detects tampering, while CBC doesn't unless you add a MAC. Our old code also derived IVs deterministically; now every message gets a fresh random 96-bit nonce, which the tests check.

**What stops someone swapping the AI model?** The registry hashes each weight file and checks an RSA-PSS signature over the manifest before loading. The Security Lab flips one bit and shows the refusal.

**How do you know the audit log wasn't edited?** Each entry's hash covers the previous entry's hash, so changing one breaks every later link, and verification names the first bad entry. If someone rebuilds the whole chain, the Merkle roots anchored outside the database (with an HMAC key the database doesn't have) no longer match.

**What is Zero Trust here?** No request is trusted because of where it comes from. Every call re-verifies the token, the server-side session, the device fingerprint, the account state and the role permission, and routes without an explicit rule are denied.

**How accurate is the model?** The tooth detector (YOLO11m, trained on the public DENTEX panoramic dataset on a free Colab GPU) scores **94 % precision, 94.5 % recall and 95.8 % mAP@0.5** on 63 held-out test X-rays it never saw during training. About 95 % of teeth are found with the correct FDI number. We do *not* quote a number for landmarks or bone-loss %, because we have no clinician-annotated keypoint test set, and inventing one would be dishonest. Those teeth go to a dentist instead.

**Why is mAP@0.5:0.95 only 56 %?** It demands very tight boxes (up to 95 % overlap). Tooth edges are fuzzy on X-rays, so 50-60 % is typical; mAP@0.5 (95.8 %) is the usual headline figure for detection.

**How did you avoid cheating on the test set?** The split is made once with a fixed seed and saved. The test images are never used for training or for picking the best epoch, and near-duplicates of test images are removed from the extra training data.

**What is conformal prediction, in one line?** Use a held-out set to learn how wrong the model usually is, then widen each prediction by that amount so the true value falls inside the range at the chosen rate (e.g. 90 %).

**Why is the case marked "uncalibrated"?** Our pose labels were generated geometrically, not drawn per tooth, so they can't calibrate honestly. Until real labels exist, every case goes to review. This is safe by design.

**What does Grad-CAM prove?** Not correctness, only where the model focused. We use it as a sanity check: attention outside the periodontal band pushes the case to review.

**How is patient privacy protected in logs?** Logs never contain names; patients appear as HMAC pseudonyms (P-…), IPs as salted hashes. Auditors can read logs but cannot open patient records.

**Is it HIPAA compliant?** It is aligned with HIPAA Security Rule safeguards (access control, audit, integrity, authentication, transmission security), not certified.

**What happens if a token is stolen?** It expires in 15 minutes, only works from the same device fingerprint, and reusing an old refresh token revokes the whole session.

**Why a honeypot?** Decoy patient records that no real clinician owns. Anyone who opens one is probably probing IDs; the account is locked for an hour and an alert is logged.

**Why is the risk model rule-based?** There is no outcome dataset, so training would mean fitting noise. A transparent logistic score with literature-based directions is honest and explainable; the UI and reports say so.

## Numbers worth remembering

- 4 roles, ~20 permissions, 50 API operations, all documented at `/api/docs`.
- 74 automated backend tests; the frontend type-checks, lints and builds cleanly.
- 7 of 7 Security Lab attacks blocked.
- Tooth detector on held-out test X-rays: 94.1 % precision, 94.5 % recall, 95.8 % mAP@0.5, tooth-level F1 94.8 %.
- Adversarial screen: 0 false alarms on 30 real radiographs; catches ±8 grey-level perturbation.
